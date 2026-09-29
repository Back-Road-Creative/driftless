"""The print stylesheet (gap G9): every page links ``/static/print.css`` under
``media="print"``, the file itself is served, and a page carrying an ``as_of``
shows a Print link whose href carries that same as-of — so the printed page is
the one the viewer saw, never whatever the wall clock resolves to on refetch."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.web import create_router

AS_OF = date(2026, 3, 31)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'print.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_router(AS_OF))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def test_every_page_links_print_css_under_media_print(client: TestClient) -> None:
    page = client.get("/").text
    assert '<link rel="stylesheet" href="/static/print.css" media="print">' in page


def test_print_css_is_served(db: Session) -> None:
    """The real, fully-assembled app mounts ``/static`` — the local ``client`` fixture's
    bare router does not, matching ``test_the_static_asset_is_served`` in
    tests/test_web_pages.py for ``driftless.js``."""
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        response = test_client.get("/static/print.css")
    real_app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "@media print" in response.text


def test_print_link_carries_the_pages_as_of(client: TestClient) -> None:
    page = client.get(f"/?as_of={AS_OF.isoformat()}").text
    assert f'id="print-link" href="/?as_of={AS_OF.isoformat()}"' in page


def test_the_same_as_of_renders_byte_identically_twice(client: TestClient) -> None:
    query = f"/?as_of={AS_OF.isoformat()}"
    assert client.get(query).text == client.get(query).text
