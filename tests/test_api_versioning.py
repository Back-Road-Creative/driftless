"""``/api/v1`` is the canonical resource path; the bare path is a kept-alive alias.

Every route was registered bare, which left no way to change a response shape without
breaking whatever already read it. These pin the three things that make introducing a
version safe: the versioned path works, the bare path still works, and the credential
gate's open set did not move.

That last one is the reason this file exists. ``is_open_path`` matches ``/health``
EXACTLY, so ``/health/ready`` stays gated -- and an ``/api/v1/health`` alias would not
match it and would land behind the gate. Bare ``/health`` would go on answering, so a
suite that only exercised it would stay green while a probe on the versioned path
started failing.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.api.openapi import page_route_paths
from driftless.api.secure import is_open_path
from driftless.api.versioning import API_PREFIX
from driftless.db import Base, new_engine, new_session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as bound:
        yield bound
    app.dependency_overrides.clear()


def _api_paths() -> set[str]:
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def test_the_same_resource_answers_under_both_paths(client: TestClient) -> None:
    """One endpoint function, two addresses -- so the two cannot drift apart."""
    created = client.post(f"{API_PREFIX}/businesses", json={"name": "Back Road Creative"})
    assert created.status_code == 201, created.text

    versioned = client.get(f"{API_PREFIX}/businesses")
    bare = client.get("/businesses")

    assert versioned.status_code == bare.status_code == 200
    assert versioned.json() == bare.json(), "a row written under one path is visible from both"


def test_the_bare_path_still_answers_but_is_no_longer_advertised() -> None:
    """Existing clients keep working; generated ones are written against the version.
    Listing both would document two names for one endpoint and leave the reader to guess
    which is going to outlive the other."""
    advertised = {r.path for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema}

    assert "/projects" in _api_paths(), "the bare path must still be served"
    assert "/projects" not in advertised
    assert f"{API_PREFIX}/projects" in advertised


def test_versioning_did_not_widen_the_credential_gates_open_set() -> None:
    """The security assertion. ``/health`` is the one open API route, before and after;
    nothing under the prefix is open, because nothing under the prefix exists for the
    paths ``is_open_path`` accepts."""
    open_now = sorted(path for path in _api_paths() if is_open_path(path))

    assert open_now == ["/health"]
    assert not [p for p in _api_paths() if p.startswith(API_PREFIX) and is_open_path(p)]


def test_health_is_not_versioned_at_all(client: TestClient) -> None:
    """Not an oversight -- the alternative was teaching ``is_open_path`` about prefixes,
    which widens a security control to serve a routing change. Operating the service is
    not a resource contract, so a version buys nothing here."""
    assert f"{API_PREFIX}/health" not in _api_paths()
    assert client.get(f"{API_PREFIX}/health").status_code == 404
    assert client.get("/health").status_code == 200, "the real probe is untouched"


def test_no_html_page_got_a_versioned_twin() -> None:
    """Pages are excluded by route CLASS, reusing the schema filter's own rule rather
    than a second one here -- a page router mounted later needs no edit, and two rules
    that could disagree about what an HTML route is would be worse than one."""
    pages = page_route_paths(app)

    assert pages, "no page routes found -- the exclusion would be vacuously true"
    assert not [
        path for path in _api_paths() if path.startswith(f"{API_PREFIX}/") and path in pages
    ]


def test_every_resource_route_got_a_twin_and_infrastructure_did_not() -> None:
    """Derived, not enumerated: a resource added later is versioned with no edit."""
    paths = _api_paths()
    versioned = {p[len(API_PREFIX) :] for p in paths if p.startswith(API_PREFIX)}
    pages = page_route_paths(app)
    resources = {
        p
        for p in paths
        if not p.startswith((API_PREFIX, "/health", "/metrics", "/docs", "/redoc", "/static"))
        and p not in pages
    }

    assert resources <= versioned, f"unversioned resource routes: {sorted(resources - versioned)}"
    assert not versioned & {"/health", "/health/ready", "/metrics"}
