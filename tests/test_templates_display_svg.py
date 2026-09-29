"""Template display: the schedule-network, gantt and status-trend/EVM SVGs must
scale to their column rather than render at a fixed 320px box (illegible text at
that box's actual on-page width), and no template may reference the undefined
``--page-bg`` token -- ``--background`` is the real one (driftless.css)."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload

Q = f"?as_of={ANCHOR.isoformat()}"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "driftless" / "web" / "templates"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def _seed(client: TestClient) -> int:
    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)
    row = next(row for row in client.get("/projects").json() if row["name"] == "Season 4 Rollout")
    return int(row["id"])


def _assert_svg_scales(html: str) -> None:
    assert not re.search(r'<svg[^>]*\bwidth="320"', html), "chart SVG still fixed at 320px"
    assert 'font-size="7"' not in html, "label font-size still floored at 7px"
    assert "--page-bg" not in html, "rendered HTML still references the undefined token"
    svgs = re.findall(r"<svg\b[^>]*>", html)
    charts = [tag for tag in svgs if "viewBox" in tag]
    assert charts, "expected at least one chart SVG on this page"
    for tag in charts:
        assert 'class="scurve"' in tag, f"chart SVG missing the scaling class: {tag}"


def test_schedule_network_svg_scales_and_uses_the_real_token(client: TestClient) -> None:
    project_id = _seed(client)
    page = client.get(f"/projects/{project_id}/assist/schedule{Q}")
    assert page.status_code == 200, page.text
    _assert_svg_scales(page.text)


def test_gantt_svg_scales(client: TestClient) -> None:
    project_id = _seed(client)
    page = client.get(f"/projects/{project_id}/gantt{Q}")
    assert page.status_code == 200, page.text
    _assert_svg_scales(page.text)


def test_status_form_svgs_scale(client: TestClient) -> None:
    project_id = _seed(client)
    page = client.get(f"/projects/{project_id}/status{Q}")
    assert page.status_code == 200, page.text
    _assert_svg_scales(page.text)


def test_no_template_references_the_undefined_page_bg_token() -> None:
    offenders = {
        path.name: path.read_text()
        for path in TEMPLATES_DIR.glob("*.html")
        if "--page-bg" in path.read_text()
    }
    assert not offenders, f"templates still reference --page-bg: {sorted(offenders)}"
