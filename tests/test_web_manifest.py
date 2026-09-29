"""The web app manifest (gap G16): an installable-PWA manifest, served with
``application/manifest+json``, linked from every page's ``<head>`` next to the
print stylesheet. No service worker, no offline write — a second write path
stays out of scope."""

from __future__ import annotations

import json
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
    engine = new_engine(f"sqlite:///{tmp_path / 'manifest.db'}")
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


def test_every_page_links_the_manifest(client: TestClient) -> None:
    page = client.get("/").text
    assert '<link rel="manifest" href="/static/manifest.webmanifest">' in page


def test_manifest_is_served_with_the_right_content_type(db: Session) -> None:
    """Matches ``test_print_css_is_served``: the real, fully-assembled app
    mounts ``/static`` — the local ``client`` fixture's bare router does not."""
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        response = test_client.get("/static/manifest.webmanifest")
    real_app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/manifest+json"
    body = json.loads(response.text)
    assert body["name"]
    assert body["short_name"]
    assert body["start_url"] == "/"
    assert body["display"] == "standalone"
    assert body["theme_color"]
    assert body["background_color"]
    assert len(body["icons"]) >= 1
    icon = body["icons"][0]
    assert icon["src"]
    assert icon["type"]
    assert icon["sizes"]
