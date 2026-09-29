"""Integration: the demo seed, walked through the real validated API and
rendered on the real dashboard -- charts get shape, and the no-data project
keeps its unknown RAG rather than a false green/amber/red verdict.

The realism pins live here too: every page renders with something on it, and every
closed vocabulary a viewer meets has a row behind it. Both are derived -- the page
list from the seeded ids, the vocabularies from the model's own tuples -- so a new
page or a grown vocabulary fails here rather than going unrepresented."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.pmbok import flow_facts

Q = f"?as_of={ANCHOR.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """A throwaway SQLite *file*: an in-memory URL gives each connection its own
    empty database, which the real app's per-request sessions would each see
    as blank."""
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


def _hollow() -> str:
    """The project the payload deliberately leaves without data, by name."""
    folios = [pf for b in demo_payload(ANCHOR)["businesses"] for pf in b["portfolios"]]
    projects = [p for pf in folios for p in pf["projects"]]
    return str(next(p["name"] for p in projects if p["no_data"]))


def _pages(client: TestClient) -> list[tuple[str, str]]:
    """Every rendered surface with real seeded ids, tagged with the project it belongs
    to (``""`` store-wide) -- built from the store, so a page for a row the seeder
    stops creating stops being walked."""

    def ids(resource: str) -> list[int]:
        return [int(row["id"]) for row in client.get(resource).json()]

    wide = (
        f"/{Q}",
        f"/scorecard{Q}",
        "/org/configuration",
        f"/threats{Q}",
        f"/process-map{Q}",
        "/org/departments",
        "/pmbok",
    )
    paths = [(path, "") for path in wide]
    paths += [(f"/org/departments/{i}", "") for i in ids("/departments")]
    for kind in ("portfolio", "program"):
        paths += [(f"/{kind}s/{i}/rollup{Q}", "") for i in ids(f"/{kind}s")]
    for row in client.get("/projects").json():
        leaves = (f"hub{Q}", f"process-map{Q}", f"wizard{Q}", f"status{Q}", "board", f"gantt{Q}")
        paths += [(f"/projects/{row['id']}/{leaf}", str(row["name"])) for leaf in leaves]
    return paths


def test_every_page_of_the_seeded_store_renders_something_real(client: TestClient) -> None:
    """Open every surface and find content on it. Only the project the payload marks
    ``no_data`` may fall back to a designed empty state -- and it must, or the contrast
    it exists to draw is gone."""
    _seed(client)
    hollow, hollow_was_empty = _hollow(), False
    for path, project in _pages(client):
        page = client.get(path)
        assert page.status_code == 200, f"{path}: {page.text[:200]}"
        empty = re.findall(r'<section class="empty-state"[^>]*id="([^"]*)"', page.text)
        if project == hollow:
            hollow_was_empty = hollow_was_empty or bool(empty)
        else:
            assert not empty, f"{path} has nothing on it: {empty}"
    assert hollow_was_empty, f"{hollow} lost the empty states its no-data story is made of"


def test_every_closed_vocabulary_a_viewer_meets_has_a_row_behind_it(client: TestClient) -> None:
    """Read off the model's own tuples, never a list written here: grow a vocabulary and
    this fails rather than the new value never reaching a board column or a RAID row."""
    _seed(client)
    for resource, field, vocabulary in (
        ("/tasks", "status", m.TASK_STATUSES),
        ("/risks", "status", m.RISK_STATUSES),
        ("/risks", "response", m.RISK_RESPONSES),
        ("/milestones", "status", m.MILESTONE_STATUSES),
        ("/status-snapshots", "rag_status", m.RAG_STATUSES),
    ):
        shown = {row[field] for row in client.get(resource).json()}
        missing = sorted(set(vocabulary) - shown)
        assert not missing, f"nothing in the demo shows {resource} {field} {missing}"


def test_the_dashboard_rag_column_is_not_one_colour(client: TestClient) -> None:
    """A rollup where every verdict is the same colour reads as a broken import,
    not a portfolio. Every stored RAG value plus the derived ``unknown`` shows."""
    _seed(client)
    rendered = set(re.findall(r'data-rag="(\w+)"', client.get(f"/{Q}").text))
    missing = sorted((set(m.RAG_STATUSES) | {"unknown"}) - rendered)
    assert not missing, f"the dashboard only ever reads {sorted(rendered)}, never {missing}"


def test_the_demo_scorecard_shows_all_perspectives_and_real_evidence(client: TestClient) -> None:
    _seed(client)
    page = client.get(f"/scorecard{Q}")

    assert page.status_code == 200
    for label in (
        "Financial",
        "Customer &amp; Stakeholder",
        "Internal Operations",
        "People &amp; Capability",
    ):
        assert label in page.text
    assert "Protect delivery margin" in page.text
    assert "Escaped defects" in page.text
    assert "unknown" in page.text


def test_the_demo_shows_someone_over_capacity(client: TestClient) -> None:
    """A seed where everybody fits inside their own capacity demonstrates nothing
    about capacity, and the RAG guard above can be satisfied by exactly that --
    give everyone room and the colours come back for the wrong reason. Read off a
    rendered page, so it fails when the product stops SAYING it, not merely when
    the hours move."""
    _seed(client)
    ids = [int(row["id"]) for row in client.get("/projects").json()]
    hubs = [client.get(f"/projects/{i}/hub{Q}").text for i in ids]
    assert any("over-allocated" in page for page in hubs), (
        "no project in the demo reports anyone over capacity: the Resource area is "
        "the one thing this seed cannot show by accident"
    )


def test_the_hub_shows_value_actually_earned(client: TestClient) -> None:
    """Every task sat at 0% complete, so EV, CPI and SPI read 0.00 and EAC "no data
    yet" on every project -- money spent, nothing earned. Task progress is what
    makes the hub's figures, the S-curve and the schedule's fill lengths mean
    anything."""
    _seed(client)
    hollow = _hollow()
    for path, project in _pages(client):
        if project in ("", hollow) or not path.endswith(f"hub{Q}"):
            continue
        figures = dict(re.findall(r'id="evm-(\w+)">([\d,.]+|no data yet)<', client.get(path).text))
        ev = float(figures["ev"].replace(",", ""))
        spi = float(figures["spi"].replace(",", ""))
        assert ev > 0 and spi > 0, f"{project} earned nothing"
        assert figures["eac"] != "no data yet", f"{project} forecasts nothing"


def test_seeded_store_charts_render_and_the_no_data_project_stays_unknown(
    client: TestClient,
) -> None:
    _seed(client)
    page = client.get("/", params={"as_of": ANCHOR.isoformat()})
    assert page.status_code == 200, page.text
    html = page.text

    assert html.count("<svg") >= 3, "S-curve, treemap and at least one burn sparkline render"

    widths = [float(w) for w in re.findall(r'<rect class="tm \w+"[^>]*width="([\d.]+)"', html)]
    assert len(widths) == 2 and all(w > 0 for w in widths), "both portfolio rects have area"

    assert re.search(
        r'<tr class="project" data-rag="unknown">\s*<td[^>]*><a[^>]*>Route Optimization Pilot</a>',
        html,
    ), "the no-data project still renders unknown, never a computed verdict"


def test_the_adaptive_project_lights_every_flow_surface(client: TestClient, db: Session) -> None:
    """The demo ran predictive end to end, so every flow surface demonstrated its EMPTY
    state. These assert the figures, not their presence, so a seed that stops producing
    them fails here rather than quietly regressing to it."""
    _seed(client)
    project = db.query(m.Project).filter(m.Project.name == "Fleet Modernization").one()
    assert project.delivery_mode == "hybrid"

    sprints = sorted(project.sprints, key=lambda s: s.start_date)
    assert [s.completed_points for s in sprints] == [18, 21, 19, 8]
    closed = [s for s in sprints if s.review_held_on is not None]
    assert len(closed) >= 2 and all(s.goal for s in sprints)
    assert all(s.review_notes and s.retrospective_notes for s in closed)
    assert {s.release.name for s in sprints if s.release} == {"Driver App 2.0"}

    items = db.query(m.BacklogItem).filter(m.BacklogItem.project_id == project.id).all()
    assert {i.status for i in items} == set(m.BACKLOG_ITEM_STATUSES)
    impediments = db.query(m.Impediment).filter(m.Impediment.project_id == project.id).all()
    assert [i.status for i in impediments].count("open") == 1
    assert any(i.resolved_on is not None for i in impediments)
    assert db.query(m.DefinitionOfDoneItem).count() >= 2
    assert {r.role for r in db.query(m.ProjectRole).all()} == {"product_owner", "scrum_master"}

    snap = flow_facts.flow_snapshot(db, project, ANCHOR)
    assert snap.wip == 2, "two cards are genuinely in progress"
    assert snap.cycle_time.count == 3 and snap.lead_time.count == 3
    # The seed dates every card in effective time, so the durations are the seeded
    # story rather than an artefact of when the rows were written: a card finished
    # inside the trailing week keeps throughput off zero, and three genuinely
    # different started-to-done spans keep the medians off zero at a FIXED anchor in
    # the past -- which is what the ``date.min`` fallback used to make impossible.
    assert snap.throughput == 1, "the carried-over fuel log landed inside the week"
    assert snap.cycle_time.median == 7.0 and snap.cycle_time.p85 == 22.0
    assert snap.lead_time.median == 14.0 and snap.lead_time.p85 == 36.0
    assert snap.active_sprint is not None
    assert snap.active_sprint.start_date <= ANCHOR <= snap.active_sprint.end_date
    assert snap.burndown[-1].remaining_points == 34.0
    assert (snap.burnup[-1].scope_points, snap.burnup[-1].completed_points) == (50.0, 16.0)
    assert (snap.cumulative_flow[-1].done, snap.cumulative_flow[-1].in_progress) == (3, 2)

    band = snap.forecast
    assert band is not None and band.sprints_used == 3
    assert band.remaining_points == 21.0 and band.likely is not None and band.likely > ANCHOR
    page = client.get(f"/projects/{project.id}/flow{Q}").text
    assert "No completed sprint yet" not in page and "the likely completion date is" in page
