"""The project hub: ``/projects/{id}/hub`` — every EVM slot agreeing with the
canonical adapter, this project's threats/RAID/milestones ONLY (the second
seeded project carries its own rows, so a dropped ``project_id ==`` clause
fails loudly), links to the three deep pages. File-based SQLite so every
connection sees the seeded rows."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess import adapters
from driftless.assess.evaluators import schedule
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    ChangeRequest,
    CostEntry,
    Issue,
    Milestone,
    Portfolio,
    Project,
    Risk,
    Task,
    Workstream,
)

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _overspender(session: Session, name: str, portfolio: Portfolio) -> None:
    """One overspending project (raising its own cost threat), flushed to get its id."""
    project = Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.flush()


def _seed(session: Session) -> None:
    """Two overspending projects, plus RAID rows and milestones on BOTH —
    threat scoping and open-vs-closed counts have real work to prove, and every
    scoped read fails loudly if a ``project_id ==`` clause is dropped, because
    the second project's rows would bleed into the first's page."""
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    for name in ("GMS", "Other"):  # GMS flushes to id 1 before Other is added
        _overspender(session, name, portfolio)
    for st, p, i in (("open", 0.5, 30000.0), ("mitigating", 0.4, 20000.0), ("closed", 0.2, 1e3)):
        session.add(Risk(project_id=1, description="r", probability=p, impact=i, status=st))
    session.add(Issue(project_id=1, description="down", raised_on=JAN))
    session.add(Issue(project_id=1, description="done", raised_on=JAN, status="resolved"))
    session.add(ChangeRequest(project_id=1, description="add", raised_on=JAN))
    session.add(ChangeRequest(project_id=1, description="no", raised_on=JAN, status="rejected"))
    session.add(
        Milestone(
            project_id=1,
            name="Alpha gate",
            target_date=date(2026, 2, 15),
            baseline_date=date(2026, 1, 15),
        )
    )
    session.add(Milestone(project_id=1, name="Launch", target_date=date(2026, 6, 30)))
    # Project 2's own open RAID rows and slipped milestone: cross-bleed tripwires
    # for every count and list project 1's hub renders.
    session.add(Risk(project_id=2, description="r2", probability=0.5, impact=30000.0))
    session.add(Issue(project_id=2, description="other down", raised_on=JAN))
    session.add(ChangeRequest(project_id=2, description="other add", raised_on=JAN))
    session.add(
        Milestone(
            project_id=2,
            name="Other gate",
            target_date=date(2026, 2, 20),
            baseline_date=date(2026, 1, 20),
        )
    )
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_hub_renders_every_evm_slot_agreeing_with_the_canonical_adapter(
    client: TestClient, db: Session
) -> None:
    body = client.get(f"/projects/1/hub{Q}").text
    assert "GMS" in body
    project = db.get(Project, 1)
    assert project is not None
    snap = adapters.snapshot_from(project, adapters.project_costs(db, project), AS_OF)
    assert snap.cpi is not None and snap.spi is not None and snap.eac is not None
    # Each slot pinned to ITS OWN computed value — and the five figures required
    # pairwise distinct (seed: EV 200.0, CPI 0.25, SPI 0.2, EAC 4000.0,
    # BAC 1000.0), so CPI printed into the SPI slot cannot pass.
    figures = {
        "ev": round(snap.ev, 2),
        "cpi": round(snap.cpi, 3),
        "spi": round(snap.spi, 3),
        "eac": round(snap.eac, 2),
        "bac": round(snap.bac, 2),
    }
    assert len(set(figures.values())) == 5, f"seed drift, slots no longer pinned: {figures}"
    for slot, value in figures.items():
        assert f'id="evm-{slot}">{value}<' in body, f"evm-{slot} does not render {value}"


def test_the_hub_shows_only_this_projects_threats(client: TestClient) -> None:
    body = client.get(f"/projects/1/hub{Q}").text
    assert 'data-threat="cost:project:1"' in body
    assert "cost:project:2" not in body, "another project's threat must not leak in"


def test_the_hub_raid_counts_match_the_seeded_rows(client: TestClient) -> None:
    # Project 2 carries one open row of each kind, so an unscoped count reads 3/2/2.
    body = client.get(f"/projects/1/hub{Q}").text
    assert 'id="raid-risks">2<' in body  # open + mitigating; closed and project 2 excluded
    assert 'id="raid-issues">1<' in body  # open; resolved and project 2 excluded
    assert 'id="raid-changes">1<' in body  # proposed; rejected and project 2 excluded


def test_the_hub_loads_only_this_projects_cost_rows(client: TestClient, db: Session) -> None:
    """The hub is a ONE-project page: its cost read must be scoped to the project,
    never a store-wide ``select(CostEntry)`` grouped after the fact — at portfolio
    size that hands every project's spend to a page that renders one. The shared-
    session override makes the leak observable: any CostEntry the request pulled
    is sitting in this session's identity map afterwards."""
    client.get(f"/projects/1/hub{Q}")
    bled = {row.project_id for row in db.identity_map.values() if isinstance(row, CostEntry)}
    assert bled <= {1}, f"hub for project 1 fetched cost rows of projects {sorted(bled - {1})}"


def test_the_hub_lists_milestones_and_marks_the_slipped_one(client: TestClient) -> None:
    body = client.get(f"/projects/1/hub{Q}").text
    alpha, launch = body.index('ms-name">Alpha gate'), body.index('ms-name">Launch')
    assert alpha < launch, "milestones are ordered by target_date"
    # Project 2's "Other gate" is ALSO slipped, so an unscoped milestone read
    # would both leak the name and mark a second slip.
    assert "Other gate" not in body, "another project's milestone must not leak in"
    # Alpha gate's target moved past its baseline (schedule.milestone_slipped's canon);
    # Launch is un-baselined and unmoved, so it never counts as a slip.
    assert body.count("ms-slipped") == 1, (
        "only the milestone whose target outran its baseline is marked"
    )
    assert alpha < body.index("ms-slipped") < launch


def test_the_hub_badge_agrees_with_the_schedule_evaluators_slip_predicate(
    tmp_path: Path,
) -> None:
    """The hub badge and the schedule evaluator's threat must share one predicate.

    Proven on the two milestones that used to diverge under the hub's old ad hoc
    check (``target_date < as_of and status == "pending"``): a missed milestone
    (the evaluator counts it a slip; the old badge check did not, since status
    isn't "pending") and a baseline-less pending milestone past its target (the
    old badge check marked it; the evaluator does not, absent a baseline to have
    slipped past).
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'agreement.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        project = Project(
            name="Agreement",
            portfolio=Portfolio(name="Content", business=Business(name="BRC")),
            delivery_mode="predictive",
        )
        session.add(project)
        session.flush()
        missed = Milestone(
            project_id=project.id,
            name="Missed gate",
            target_date=date(2026, 1, 10),
            baseline_date=date(2026, 1, 1),
            status="missed",
        )
        overdue_pending = Milestone(
            project_id=project.id,
            name="Overdue pending",
            target_date=date(2026, 1, 5),
            status="pending",
        )
        session.add_all([missed, overdue_pending])
        session.commit()
        project_id = project.id
        assert schedule.milestone_slipped(missed, AS_OF) is True
        assert schedule.milestone_slipped(overdue_pending, AS_OF) is False

    with factory() as session:
        real_app.dependency_overrides[get_session] = lambda: session
        with TestClient(real_app) as test_client:
            body = test_client.get(f"/projects/{project_id}/hub{Q}").text
        real_app.dependency_overrides.clear()

    # Split on the milestone-table rows specifically — "Missed gate" also appears in the
    # threats panel's slip description, above the table, and would otherwise match first.
    rows = body.split("<tr>")
    missed_row = next(r for r in rows if 'ms-name">Missed gate' in r)
    pending_row = next(r for r in rows if 'ms-name">Overdue pending' in r)
    assert "ms-slipped" in missed_row, "missed w/ baseline: predicate True, badge must show"
    assert "ms-slipped" not in pending_row, "baseline-less pending: predicate False, no badge"


def test_the_hub_links_the_three_deep_pages(client: TestClient) -> None:
    body = client.get(f"/projects/1/hub{Q}").text
    for page in ("process-map", "wizard", "status"):
        assert f'href="/projects/1/{page}' in body


def test_home_project_rows_point_at_the_hub(client: TestClient) -> None:
    body = client.get(f"/{Q}").text
    assert '<a href="/projects/1/hub">' in body
    assert "/projects/1/process-map" not in body


def test_an_unknown_project_is_404(client: TestClient) -> None:
    assert client.get(f"/projects/999/hub{Q}").status_code == 404


def test_a_pinned_as_of_regenerates_byte_identically(client: TestClient) -> None:
    url = f"/projects/1/hub{Q}"
    assert client.get(url).content == client.get(url).content
