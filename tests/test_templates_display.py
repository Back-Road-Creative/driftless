"""Money and status-badge formatting is ONE idiom across every rendered page, not
one derivation per template. Money: ``"{:,.0f}"`` via the ``money`` filter
(``driftless.web.templating``), never a bare ``round(x, 2)`` float. Severity/RAG
badges: a ``sev-{status}`` ancestor carrying a ``badge sev-badge`` child, the
idiom the live-threats card already used, so a fill actually shows rather than
a card-stripe rule doing double duty as a "badge"."""

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

# A raw money float sitting right after one of these labels -- the exact bug: a
# page-local ``round(x, 2)`` rendered instead of the ``money`` filter.
_RAW_MONEY = re.compile(r"(Budget|EV|EAC|Impact|Exposure)\D{0,40}?\b\d+\.\d+\b")
_COMMA_MONEY = re.compile(r"\b\d{1,3},\d{3}\b")


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


def _seed(client: TestClient) -> None:
    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)


def _funded_project_id(client: TestClient) -> int:
    """A project the demo actually costed and put risks against -- never the
    ``no_data`` project, which has nothing on it to assert money formatting on."""
    for row in client.get("/projects").json():
        risks = client.get(f"/risks?project_id={row['id']}").json()
        if risks:
            return int(row["id"])
    raise AssertionError("no seeded project carries a risk to assert money formatting on")


def test_hub_status_and_raid_print_no_raw_money_floats(client: TestClient) -> None:
    _seed(client)
    project_id = _funded_project_id(client)
    for path in (
        f"/projects/{project_id}/hub{Q}",
        f"/projects/{project_id}/status{Q}",
        f"/projects/{project_id}/raid{Q}",
    ):
        page = client.get(path)
        assert page.status_code == 200, page.text[:200]
        bad = _RAW_MONEY.findall(page.text)
        assert not bad, f"{path} still prints a raw money float: {bad}"


def test_hub_budget_reads_comma_grouped(client: TestClient) -> None:
    _seed(client)
    project_id = _funded_project_id(client)
    page = client.get(f"/projects/{project_id}/hub{Q}")
    assert _COMMA_MONEY.search(page.text), "hub budget is not comma-grouped like the rollup"


def test_scorecard_has_no_bare_status_span(client: TestClient) -> None:
    """Every RAG status word on the scorecard is a filled badge now, never a bare
    ``<span class="amber">amber</span>`` with no ``badge`` class at all."""
    _seed(client)
    page = client.get(f"/scorecard{Q}")
    assert page.status_code == 200
    for status in ("red", "amber", "green", "unknown"):
        assert f'<span class="{status}">' not in page.text, status


def test_raid_status_badges_use_the_hub_idiom(client: TestClient) -> None:
    """RAID's status pill carries the same ``badge sev-badge`` fill the hub's live
    threats already use, not the bare ``badge sev-red`` that only ever drew the
    card-stripe rule."""
    _seed(client)
    project_id = _funded_project_id(client)
    page = client.get(f"/projects/{project_id}/raid{Q}")
    assert page.status_code == 200
    assert '<span class="badge sev-badge">' in page.text
    assert re.search(r'class="badge sev-(red|amber|green)"', page.text) is None


def test_threat_score_matches_two_decimals_on_hub_and_board(client: TestClient) -> None:
    _seed(client)
    project_id = _funded_project_id(client)
    hub = client.get(f"/projects/{project_id}/hub{Q}")
    board = client.get(f"/threats{Q}")
    assert hub.status_code == 200
    assert board.status_code == 200
    assert re.search(r"score \d+\.\d{4,}", hub.text) is None
    assert re.search(r"score \d+\.\d{4,}", board.text) is None


def test_hub_render_is_byte_identical_for_a_pinned_as_of(client: TestClient) -> None:
    _seed(client)
    project_id = _funded_project_id(client)
    path = f"/projects/{project_id}/hub{Q}"
    first = client.get(path).content
    second = client.get(path).content
    assert first == second
