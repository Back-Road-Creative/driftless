"""Who is over capacity, and in which week: ``/org/heatmap`` (rationale in the module and the
README). Pinned: the verdict in words with every colour stripped out, no-capacity apart from
no-load, columns off the as-of not a clock, byte-identical refetch, the nav link, a row total
that IS the Resource evaluator's own remaining hours, a horizon that is bounded, refuses
rather than clamps and still defaults to six, and a flat statement count."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app, get_session
from driftless.assess.evaluators.resource import person_task_loads
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.heatmap import allocation, weeks_from
from test_perf_n1 import count_route

AS_OF, MONDAY = date(2026, 2, 18), date(2026, 2, 16)  # a Wednesday, and its own week's Monday
WEEK1, LATER = (MONDAY, MONDAY + timedelta(6)), (MONDAY + timedelta(56), MONDAY + timedelta(62))
PAGE, APRIL = f"/org/heatmap?as_of={AS_OF.isoformat()}", "/org/heatmap?as_of=2026-04-15"
# Ada 60 h this week (over 40) + 10 h in week nine, past the horizon; Dee 36 h (tight, 0.9);
# Bo 20 h (under) + 5 h on a task with no baseline line at all; Cass nothing assigned.
LOAD = (("Ada", 60.0, WEEK1), ("Ada", 10.0, LATER), ("Bo", 20.0, WEEK1), ("Bo", 5.0, None))
LOAD += (("Dee", 36.0, WEEK1),)
# Measured 2 (assignments, people); a lazy load per person or week trips the equality first.
MAX_HEATMAP_STMTS = 5
# The page's own ceiling, written out here rather than imported: the number is a decision,
# and a test that asks the module what its limit is cannot notice the limit moving.
MAX_WEEKS = 26

_TD = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.S)
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


def _cells(body: str) -> dict[tuple[str, str], tuple[str, str]]:
    """``(person, field) -> (state, visible text)``; ORDER of attributes is no contract."""
    read = ((dict(_ATTR.findall(a)), re.sub(r"<[^>]+>", " ", i)) for a, i in _TD.findall(body))
    return {
        (attr["data-person"], attr["data-field"]): (attr.get("data-state", ""), " ".join(t.split()))
        for attr, t in read
        if "data-field" in attr
    }


def _assign(db: Session, person: m.Person, hours: float, window: tuple[date, date] | None) -> None:
    """One open, hour-estimated task for ``person``, on baseline 1 only when given a window."""
    task = m.Task(name=f"{person.name}{hours:g}", workstream=db.get(m.Workstream, 1))
    task.estimate, task.estimate_unit, task.assignee = hours, "hours", person
    db.add(task)
    if window is not None:
        line = m.BaselineLine(baseline=db.get(m.Baseline, 1), task=task, planned_cost=0.0)
        line.planned_start, line.planned_finish = window
        db.add(line)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:  # a file: TestClient serves on another thread
    """One project, four people at the default 40 h/week, and ``LOAD``'s assignments."""
    engine = new_engine(f"sqlite:///{tmp_path / 'heatmap.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
        project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
        session.add(m.Workstream(name="Post", project=project))
        session.add(m.Baseline(project=project, version=1, status="approved"))
        session.add_all(m.Person(name=name) for name in ("Ada", "Bo", "Cass", "Dee"))
        session.commit()
        people = {person.name: person for person in session.scalars(select(m.Person))}
        for who, hours, window in LOAD:
            _assign(session, people[who], hours, window)
        session.commit()
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """https: an http jar drops the Secure CSRF cookie, which then remints per render."""
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as browser:
        yield browser
    real_app.dependency_overrides.clear()


def test_each_cell_states_its_load_in_words_and_survives_greyscale(client: TestClient) -> None:
    """Deleting every ``class`` takes every wash with it, and the page still says which week
    Ada is over in. The last block is the other reading no shade carries: no capacity RECORDED
    is not zero load — and the CHECK forbids that row, so only the pure grid can build it."""
    week = MONDAY.isoformat()
    cells = _cells(client.get(PAGE).text)
    assert cells[("Ada", week)][0] == "over"
    assert cells[("Dee", week)][0] == "tight", "0.9 of capacity is the evaluator's amber"
    assert cells[("Bo", week)] == ("under", "20")
    assert cells[("Cass", week)] == ("under", "0") and cells[("Cass", "capacity")][1] == "40"
    grey = _cells(re.sub(r'\sclass="[^"]*"', "", client.get(PAGE).text))
    assert grey[("Ada", week)][1] == "60 over", grey[("Ada", week)]
    assert "over" not in grey[("Bo", week)][1] and "over" not in grey[("Cass", week)][1]
    ghost, idle = m.Person(id=1, capacity_hours=0.0), m.Person(id=2, capacity_hours=40.0)
    unrated, rated = allocation([ghost, idle], [], weeks_from(AS_OF, 2))
    assert (unrated["capacity"], rated["capacity"]) == ("not recorded", "40")
    assert [c["state"] for c in unrated["cells"]] == ["unknown"] * 2, "0% would read as fine"
    assert [(c["state"], c["hours"]) for c in rated["cells"]] == [("under", "0")] * 2


def test_the_as_of_and_the_evaluator_decide_everything(client: TestClient, db: Session) -> None:
    """Columns come from the as-of and the fixed horizon, not a wall clock, so a pinned as-of
    refetches byte-identically; every row total is ``person_task_loads``'s own, weeks plus
    unplaced accounting for each hour. The nav link rides along: unlinked is half shipped."""
    assert weeks_from(AS_OF, 3) == [MONDAY + timedelta(days=7 * n) for n in range(3)]
    body = client.get(PAGE).text
    assert re.findall(r'data-week="([^"]+)"', body) == [d.isoformat() for d in weeks_from(AS_OF)]
    assert client.get(PAGE).text == body, "a pinned as-of did not regenerate byte-identically"
    assert 'data-week="2026-04-13"' in client.get(APRIL).text, "another as-of moves the grid"
    assert '<a href="/org/heatmap" aria-current="page">' in body, "the nav does not link it"
    cells, people = _cells(body), db.scalars(select(m.Person).order_by(m.Person.id)).all()
    loads = person_task_loads(db, [person.id for person in people])
    for person in people:
        total = float(cells[(person.name, "total")][1])
        assert total == loads[person.id][1], f"{person.name}'s total drifts from the evaluator"
        weeks = (week.isoformat() for week in weeks_from(AS_OF))
        placed = sum(float(cells[(person.name, w)][1].split()[0]) for w in weeks)
        assert placed + float(cells[(person.name, "unplaced")][1]) == pytest.approx(total)
    assert max(hours for _, hours in loads.values()) == 70.0, "the fixture loads nobody"


def test_a_multi_week_task_books_its_hours_week_by_week_across_its_window(
    client: TestClient, db: Session
) -> None:
    """Every window above is exactly one Monday-aligned week, so a spread that
    dumped a task's whole estimate into its first week — 80/0/0/0 for this task
    where the real code books 20/20/20/20 — was invisible: a red over-capacity
    cell against an evenly loaded month. Four weeks, 80 hours: 20 a week."""
    _assign(db, m.Person(name="Eve"), 80.0, (MONDAY, MONDAY + timedelta(days=27)))
    db.commit()
    cells = _cells(client.get(PAGE).text)
    weeks = [week.isoformat() for week in weeks_from(AS_OF)]
    assert [cells[("Eve", week)] for week in weeks] == (
        [("under", "20")] * 4 + [("under", "0")] * 2
    ), "an 80 h task windowed over four weeks must book 20 in each, not 80 up front"
    assert cells[("Eve", "total")][1] == "80" and cells[("Eve", "unplaced")][1] == "0"


def test_only_the_newest_approved_baseline_windows_a_tasks_hours(
    client: TestClient, db: Session
) -> None:
    """The fixture holds a single approved version, so a query reading EVERY
    approved line — booking a re-baselined task under its superseded window too,
    or twice — was invisible. One task, three plans: superseded approved v2 in
    week one, newest approved v3 in week three, a draft v4 in week five. Only
    the newest APPROVED window may place the hours, and only once."""
    task = m.Task(name="Fay20", workstream=db.get(m.Workstream, 1))
    task.estimate, task.estimate_unit, task.assignee = 20.0, "hours", m.Person(name="Fay")
    db.add(task)
    project = db.get(m.Project, 1)
    for version, status, offset in ((2, "approved", 0), (3, "approved", 14), (4, "draft", 28)):
        line = m.BaselineLine(
            baseline=m.Baseline(project=project, version=version, status=status),
            task=task,
            planned_cost=0.0,
        )
        line.planned_start = MONDAY + timedelta(days=offset)
        line.planned_finish = MONDAY + timedelta(days=offset + 6)
        db.add(line)
    db.commit()
    cells = _cells(client.get(PAGE).text)
    booked = [cells[("Fay", week.isoformat())][1] for week in weeks_from(AS_OF)]
    assert booked == ["0", "0", "20", "0", "0", "0"], (
        "the hours must sit in the NEWEST approved window alone — not the superseded "
        f"week-one plan and not the draft week-five one: {booked}"
    )
    assert cells[("Fay", "total")][1] == "20", "a re-baselined task books once, not per version"


def test_the_horizon_is_bounded_and_refuses_rather_than_clamping(client: TestClient) -> None:
    """``?weeks=N`` moves the far edge and nothing else. Six with no parameter, so every
    address that predates the parameter renders what it always did; the far column is still
    the as-of's arithmetic, so the widest grid refetches byte-identically too, and it stays
    inside the shared scroll wrapper where twenty-six columns cannot clip the page.

    Out of range REFUSES. A caller asking for 5,000 columns asked for a page this one cannot
    be, and quietly handing back six is how a wrong number gets believed — so the answer is
    the refusal page, holding no grid at all."""
    default = re.findall(r'data-week="([^"]+)"', client.get(PAGE).text)
    assert default == [week.isoformat() for week in weeks_from(AS_OF)] and len(default) == 6
    wide = client.get(f"{PAGE}&weeks={MAX_WEEKS}").text
    columns = re.findall(r'data-week="([^"]+)"', wide)
    assert len(columns) == MAX_WEEKS, f"asked for {MAX_WEEKS} columns, drew {len(columns)}"
    assert columns[-1] == (MONDAY + timedelta(7 * (MAX_WEEKS - 1))).isoformat()
    assert client.get(f"{PAGE}&weeks={MAX_WEEKS}").text == wide, "the wide grid regenerated"
    assert re.search(r'class="scroll-x"[^>]*>\s*<table', wide), "the widest grid can clip"
    assert f"weeks={MAX_WEEKS}" in client.get(PAGE).text, "no reader can reach the parameter"
    for asked in (0, -1, MAX_WEEKS + 1, 5000):
        refused = client.get(f"{PAGE}&weeks={asked}")
        assert refused.status_code == 404, f"weeks={asked} was served, not refused"
        assert "data-week=" not in refused.text, f"weeks={asked} was clamped into a grid"
    for asked in (0, MAX_WEEKS + 1):
        with pytest.raises(ValueError):  # no second, quietly-clamping way in
            weeks_from(AS_OF, asked)


def test_the_count_is_flat_in_people_and_tasks_and_an_unassigned_store_says_so(
    client: TestClient, db: Session
) -> None:
    """Two queries whatever the store size OR the horizon — equality both ways, since a
    ceiling alone would pass a page that had quietly started querying per week; then, with
    nobody assigned, the shared empty state."""
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    few, status = count_route(engine, client, PAGE)
    assert status == 200, status
    for n in range(20):
        _assign(db, m.Person(name=f"Extra {n:02d}"), 8.0, WEEK1)
    db.commit()
    many, status = count_route(engine, client, PAGE)
    assert (status, many) == (200, few) and many <= MAX_HEATMAP_STMTS, (few, many)
    near, close = count_route(engine, client, f"{PAGE}&weeks=1")
    far, distant = count_route(engine, client, f"{PAGE}&weeks={MAX_WEEKS}")
    assert (close, distant, near) == (200, 200, far), (near, far, close, distant)
    assert far == many, f"the horizon changed the query count: {many} -> {far}"
    for task in db.scalars(select(m.Task)):
        task.assignee = None
    db.commit()
    bare = client.get(PAGE).text
    assert "<table" not in bare, "an empty grid skeleton shipped"
    assert re.search(r'<section class="empty-state".*?<code', bare, re.S), "no next step named"
