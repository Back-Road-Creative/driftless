"""The project hub's completeness must be the ENGINE's answer, not a number the
page can quietly zero.

The hub computes its figures inside a ``state.prefetched`` scope. That scope is a
cache, and its whole promise is that it answers identically to an uncached walk.
Narrowing it to the wrong project set — ``state.prefetched(db, [])`` — is not a
slowdown: ``mapping.rows_for`` then hands EVERY resolver an empty row list, so overall
completeness and all ten area rings drop to 0% while the page still returns 200 with
every ring in place. The whole suite passed with that mutation applied; only the
per-request query guard moved, and it moved DOWN (an empty parent set skips
``selectinload``), so the regression read as an improvement.

So the guard is an equality, not a threshold or a smoke test: what the page prints
must equal what ``state.completeness`` and ``views.area_completeness`` answer for the
same store and as-of, walked OUTSIDE any prefetch scope. That is the invariant the
scope actually promises, asserted where it can be broken. Both tests first assert the
seed is non-degenerate — part-done overall, and areas that disagree with each other —
so an all-zero page can never satisfy the equality. Nothing here is hardcoded, so the
seed can grow without the expected percentages needing an edit.

File-based SQLite so every connection sees the seeded rows, as in the sibling hub test.
"""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
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
from driftless.pmbok import state
from driftless.web.views import area_completeness, pct

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
URL = f"/projects/1/hub?as_of={AS_OF.isoformat()}"

#: One rendered ring: ``<span class="hub-area">Risk 67%</span>`` — area, then label.
_RING = re.compile(r'<span class="hub-area">([A-Za-z ]+) (\S+)</span>')


def _seed(session: Session) -> None:
    """Enough artifacts across enough knowledge areas that completeness lands
    strictly between none and all, and the areas disagree with one another."""
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    project = Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    session.add(
        BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=1000.0,
            planned_start=JAN,
            planned_finish=AS_OF,
        )
    )
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.flush()  # the project takes id 1
    session.add(Risk(project_id=1, description="r", probability=0.5, impact=30000.0))
    session.add(Issue(project_id=1, description="down", raised_on=JAN))
    session.add(ChangeRequest(project_id=1, description="add", raised_on=JAN))
    session.add(Milestone(project_id=1, name="Alpha gate", target_date=date(2026, 2, 15)))
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
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def _engine_figures(db: Session) -> tuple[float | None, dict[str, float | None]]:
    """What the engines answer for the seeded store — walked outside ANY prefetch scope,
    so a scope that hid the rows from the page cannot also hide them from the reference."""
    project = db.get(Project, 1)
    assert project is not None
    return (
        state.completeness(project, db, AS_OF),
        area_completeness(state.project_process_states(project, db, AS_OF)),
    )


def _rendered_rings(body: str) -> dict[str, str]:
    """The rings read back off the page as ``{area key: percent label}``."""
    return {area.lower().replace(" ", "_"): label for area, label in _RING.findall(body)}


def test_the_hub_prints_the_engines_own_completeness(client: TestClient, db: Session) -> None:
    overall, _ = _engine_figures(db)
    assert overall is not None and 0.0 < overall < 1.0, (
        "the seed must leave real work part-done — otherwise a page showing 0% would pass"
    )
    assert f'id="hub-completeness">{pct(overall)}<' in client.get(URL).text


def test_every_area_ring_carries_the_engines_own_figure(client: TestClient, db: Session) -> None:
    _, rings = _engine_figures(db)
    assert len({frac for frac in rings.values() if frac}) > 1, (
        "the seed must make the areas disagree — otherwise one flat figure would pass"
    )
    assert _rendered_rings(client.get(URL).text) == {
        area: pct(frac) for area, frac in rings.items()
    }
