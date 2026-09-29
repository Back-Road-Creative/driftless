"""The project schedule drawn as bars anyone can read: ``/projects/{id}/gantt``.

driftless held the data — planned windows, percent complete, milestone dates — and drew no
timeline, the one view every competitor shows. These pin the page: a bar per baselined task
sized from its window with progress legible in no colour, a milestone at its target date on
the same scale, byte-identical regeneration for a pinned as-of ("today" is that as-of, never
a wall clock), the shared empty state where there is no approved baseline to draw, and a
statement count flat in the task count — all read off the markup the real app returns.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from test_perf_n1 import count_route

JAN, AS_OF, MAR = date(2026, 1, 1), date(2026, 2, 15), date(2026, 3, 31)
DESIGN, BUILD = (JAN, date(2026, 1, 31)), (date(2026, 2, 1), MAR)
PAGE, DRAFT_PAGE = [f"/projects/{n}/gantt?as_of={AS_OF.isoformat()}" for n in (1, 2)]
# Measured 6, and identical with ten more tasks in the same baseline: the project, its
# lines (newest version picked by scalar subquery, not a second query), those lines'
# tasks batched into the same round trip, the milestones, every dependency edge (names
# joined in, one statement, never one per edge) and the project's own calendar. Two of
# headroom — a ceiling several times the cost cannot fail — and a lazy load per line or
# per edge trips the equality first.
MAX_GANTT_STMTS = 8
_TAG = re.compile(r"<(rect|polygon|line)\b([^>]*?)/?>")
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')
_ROW = re.compile(r"<tr><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>")


def _baselined(db: Session, windows: list[tuple[str, tuple[date, date], int]]) -> None:
    """Tasks on project 1's approved baseline — the seed's write, and the cost test's."""
    stream, baseline = db.get(m.Workstream, 1), db.get(m.Baseline, 1)
    for name, (start, finish), percent in windows:
        task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=percent)
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
        line.planned_start, line.planned_finish = start, finish
        db.add(line)
    db.commit()


def _seed(db: Session) -> None:
    """Project 1: two windowed tasks on an approved baseline, two milestones (one on the
    as-of itself). Project 2: a DRAFT baseline only — the nothing-to-draw case."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    draft = m.Project(name="Unbaselined", portfolio=portfolio, delivery_mode="predictive")
    db.add(m.Workstream(name="Post", project=project))
    db.add(m.Baseline(project=project, version=1, status="approved"))
    db.add(m.Baseline(project=draft, version=1, status="draft"))
    for name, target in (("Alpha gate", AS_OF), ("Launch", MAR)):
        db.add(m.Milestone(project=project, name=name, target_date=target))
    db.commit()  # GMS is added first, so it is project 1 and Unbaselined is project 2
    _baselined(db, [("Design", DESIGN, 40), ("Build", BUILD, 0)])


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:  # a file: TestClient serves on another thread
    engine = new_engine(f"sqlite:///{tmp_path / 'gantt.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """https: an http jar drops the Secure CSRF cookie, which then remints per render."""
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as browser:
        yield browser
    real_app.dependency_overrides.clear()


def _shapes(body: str, tag: str) -> list[dict[str, str]]:
    """Every ``<tag …>`` as an attribute map — attribute ORDER is no contract of ours."""
    return [dict(_ATTR.findall(attrs)) for found, attrs in _TAG.findall(body) if found == tag]


def test_a_bar_per_task_sized_by_window_and_filled_by_progress(client: TestClient) -> None:
    """Position and width are the window; progress is fill LENGTH plus a printed percent."""
    body = client.get(PAGE).text
    rects = _shapes(body, "rect")
    planned = {r["data-task"]: r for r in rects if r["data-bar"] == "planned"}
    done = {r["data-task"]: r for r in rects if r["data-bar"] == "progress"}
    assert sorted(planned) == ["Build", "Design"], "want one bar per baselined task"
    assert float(planned["Design"]["x"]) < float(planned["Build"]["x"]), "later window, righter"
    short, long = float(planned["Design"]["width"]), float(planned["Build"]["width"])
    expected = (BUILD[1] - BUILD[0]).days / (DESIGN[1] - DESIGN[0]).days
    assert long / short == pytest.approx(expected, rel=0.05), "width is not the planned window"
    assert float(done["Design"]["width"]) == pytest.approx(short * 0.4, rel=0.02)
    assert float(done["Build"]["width"]) == 0.0, "an unstarted task draws no progress fill"
    assert ">40%<" in body and ">0%<" in body, "the percentage is never printed as text"


def test_the_as_of_dates_the_page_and_places_every_milestone(client: TestClient) -> None:
    """One property: the page is a pure function of the as-of. Each mark is pinned against
    the page's OWN scale — "Alpha gate" targets the as-of, so it lands on the as-of rule —
    and no wall clock feeds any of it, so only another as-of moves a byte."""
    body = client.get(PAGE).text
    marks = {p["data-milestone"]: p for p in _shapes(body, "polygon")}
    rules = [ln for ln in _shapes(body, "line") if ln.get("data-today")]
    assert len(rules) == 1 and rules[0]["data-today"] == AS_OF.isoformat()
    assert sorted(marks) == ["Alpha gate", "Launch"] and "Launch" in body  # named as text too
    assert float(marks["Alpha gate"]["points"].split(",")[0]) == float(rules[0]["x1"])
    assert float(marks["Launch"]["points"].split(",")[0]) > float(rules[0]["x1"])
    assert client.get(PAGE).text == body, "a pinned as-of did not regenerate byte-identically"
    later = client.get(f"/projects/1/gantt?as_of={MAR.isoformat()}").text
    assert later != body and f'data-today="{MAR.isoformat()}"' in later


def test_the_schedule_as_text_rows_are_the_drawn_bars_and_marks(client: TestClient) -> None:
    """The text twin was rendered but never read: no assert tied its rows to
    ``view.bars`` and ``view.marks``, so a table looping the wrong collection —
    or printing every window as the same dates — stayed green. Row for row, in
    the view's own order: bars by planned start, then milestones by target."""
    assert _ROW.findall(client.get(PAGE).text) == [
        ("Design", str(DESIGN[0]), str(DESIGN[1]), "40% complete"),
        ("Build", str(BUILD[0]), str(BUILD[1]), "0% complete"),
        ("Alpha gate (milestone)", "—", str(AS_OF), "Pending"),
        ("Launch (milestone)", "—", str(MAR), "Pending"),
    ], "the schedule-as-text table does not repeat the drawn schedule"


def test_no_approved_baseline_says_so_instead_of_an_empty_grid(client: TestClient) -> None:
    body = client.get(DRAFT_PAGE).text
    assert "<svg" not in body and "<table" not in body, "an empty chart or grid skeleton shipped"
    section = re.search(r'<section class="empty-state".*?</section>', body, re.S)
    assert section, "no approved baseline renders no designed empty state"
    assert "<code" in section.group(0) or "<a " in section.group(0), "it names no next step"


def test_a_baseline_approved_after_the_as_of_does_not_repaint_it(
    client: TestClient, db: Session
) -> None:
    """#184 closed this for EVM by gating ``plan_baseline`` on ``approved_at <= as_of``;
    the Gantt page picked its baseline in SQL and never inherited the gate. A v2 approved
    in March must not become the plan a render at February's as-of draws."""
    project = db.get(m.Project, 1)
    task = m.Task(name="Rushed", workstream=db.get(m.Workstream, 1), estimate_unit="hours")
    line = m.BaselineLine(
        baseline=m.Baseline(
            project=project,
            version=2,
            status="approved",
            approved_at=datetime.combine(MAR, time(9)),
        ),
        task=task,
        planned_cost=500.0,
    )
    line.planned_start, line.planned_finish = MAR, MAR
    db.add(line)
    db.commit()
    body = client.get(PAGE).text  # PAGE renders as_of=AS_OF, before v2's own approval
    names = {r["data-task"] for r in _shapes(body, "rect") if r["data-bar"] == "planned"}
    assert names == {"Design", "Build"}, "v2, approved after the as-of, repainted the page early"


@pytest.mark.parametrize(
    ("approved", "drawn"),
    [
        (datetime.combine(AS_OF, time(23, 59, 59)), True),
        (datetime.combine(AS_OF + timedelta(days=1), time()), False),
    ],
)
def test_the_gate_falls_between_the_as_of_and_the_day_after(
    client: TestClient, db: Session, approved: datetime, drawn: bool
) -> None:
    """The boundary the rule turns on, which the March case above is too far away to pin.
    ``adapters.plan_baseline`` compares ``approved_at.date() <= as_of``, so an approval at
    any hour of the as-of's OWN day counts and midnight starting the next day does not.
    ``approved_as_of`` states that as a half-open instant compare rather than a
    day-truncating SQL function -- portable across the SQLite the suite runs on and the
    Postgres a deployment runs, which no CI job exercises with an application query. Off
    by a day in either direction, one of these two cases fails."""
    project = db.get(m.Project, 1)
    task = m.Task(name="Rushed", workstream=db.get(m.Workstream, 1), estimate_unit="hours")
    line = m.BaselineLine(
        baseline=m.Baseline(project=project, version=2, status="approved", approved_at=approved),
        task=task,
        planned_cost=500.0,
    )
    line.planned_start, line.planned_finish = MAR, MAR
    db.add(line)
    db.commit()
    body = client.get(PAGE).text
    names = {r["data-task"] for r in _shapes(body, "rect") if r["data-bar"] == "planned"}
    assert names == ({"Rushed"} if drawn else {"Design", "Build"})


def test_dependencies_and_a_calendar_note_appear_beside_the_bars(
    client: TestClient, db: Session
) -> None:
    """The dependency table names the waiting task, what it waits on, and the typed
    lag/lead; the calendar note names the project's own working pattern."""
    design_task = db.scalar(select(m.Task).where(m.Task.name == "Design"))
    build_task = db.scalar(select(m.Task).where(m.Task.name == "Build"))
    assert design_task is not None and build_task is not None
    db.add(m.TaskDependency(predecessor=design_task, successor=build_task, kind="FS", lag_days=2))
    db.add(m.ProjectCalendar(project=db.get(m.Project, 1), name="Standard", working_days=31))
    db.commit()

    body = client.get(PAGE).text
    assert "Design (FS +2d)" in body, "the dependency table does not name predecessor and lag"
    assert "Calendar: Standard (Mon, Tue, Wed, Thu, Fri)" in body


def test_the_page_does_not_query_per_task(client: TestClient, db: Session) -> None:
    """One query for the lines with their tasks batched in, never one per row: so twelve
    tasks cost exactly what two cost."""
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    few, status = count_route(engine, client, PAGE)
    assert status == 200, status
    _baselined(db, [(f"Extra {n}", BUILD, 50) for n in range(10)])
    many, status = count_route(engine, client, PAGE)
    assert (status, many) == (200, few) and many <= MAX_GANTT_STMTS, (few, many)
