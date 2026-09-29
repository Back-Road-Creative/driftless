"""Who is over capacity, and in which week: ``/org/heatmap`` (rationale in the module and the
README). Pinned: the verdict in words with every colour stripped out, no-capacity apart from
no-load, columns off the as-of not a clock, byte-identical refetch, the nav link, a row total
that IS the Resource evaluator's own remaining hours, a horizon that is bounded, refuses
rather than clamps and still defaults to six, and a flat statement count."""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app, get_session
from driftless.assess.evaluators.resource import person_task_loads
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.heatmap import (
    HORIZON_CHOICES,
    HORIZON_WEEKS,
    _WASHES,
    allocation,
    capacity_cell,
    legend,
    weeks_from,
)
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
    assert cells[("Bo", week)] == ("under", "20 50%")
    assert cells[("Cass", week)] == ("under", "0 0%") and cells[("Cass", "capacity")][1] == "40"
    grey = _cells(re.sub(r'\sclass="[^"]*"', "", client.get(PAGE).text))
    assert grey[("Ada", week)][1] == "60 150% over", grey[("Ada", week)]
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
        [("under", "20 50%")] * 4 + [("under", "0 0%")] * 2
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
    booked = [cells[("Fay", week.isoformat())][1].split()[0] for week in weeks_from(AS_OF)]
    assert booked == ["0", "0", "20", "0", "0", "0"], (
        "the hours must sit in the NEWEST approved window alone — not the superseded "
        f"week-one plan and not the draft week-five one: {booked}"
    )
    assert cells[("Fay", "total")][1] == "20", "a re-baselined task books once, not per version"


def test_a_baseline_approved_after_the_as_of_books_no_hours(
    client: TestClient, db: Session
) -> None:
    """#184 closed this for EVM by gating ``plan_baseline`` on ``approved_at <= as_of``;
    the heatmap picked its window in SQL and never inherited the gate. A v5 approved in
    April must not consume capacity for a render at February's as-of."""
    task = m.Task(name="Gwen10", workstream=db.get(m.Workstream, 1))
    task.estimate, task.estimate_unit, task.assignee = 10.0, "hours", m.Person(name="Gwen")
    db.add(task)
    project = db.get(m.Project, 1)
    line = m.BaselineLine(
        baseline=m.Baseline(
            project=project, version=5, status="approved", approved_at=datetime(2026, 4, 1, 9)
        ),
        task=task,
        planned_cost=0.0,
    )
    line.planned_start, line.planned_finish = MONDAY, MONDAY + timedelta(6)
    db.add(line)
    db.commit()
    cells = _cells(client.get(PAGE).text)
    assert cells[("Gwen", MONDAY.isoformat())] == ("under", "0 0%"), (
        "future-approved v5 booked hours early"
    )
    # The estimate is real regardless of approval date, so it still counts toward the
    # person's total -- exactly like a task with no baseline line at all -- but with no
    # visible approved window as of the render, it goes unplaced rather than into a week.
    assert cells[("Gwen", "total")][1] == "10"
    assert cells[("Gwen", "unplaced")][1] == "10", (
        "v5's window is invisible, so its hours go unplaced"
    )


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


_CSS = Path(__file__).resolve().parents[1] / "driftless/web/static/driftless.css"


def test_the_heatmap_legend_chips_are_styled_by_the_stylesheet_the_page_links(
    client: TestClient,
) -> None:
    """heatmap.html extends base.html, which links driftless.css — NOT home.html's own
    page-local <style> block. Its legend renders empty ``<span class="chip ...">``
    swatches as the colour key; if ``.chip`` is declared only in home.html's block, this
    page never sees it and the swatches render at zero size — bare text labels with no
    key. Assert reachability from THIS page: it links driftless.css, its markup uses
    .chip, and driftless.css is what actually gives that class a box."""
    page = client.get(PAGE).text
    assert '<link rel="stylesheet" href="/static/driftless.css">' in page, (
        "the page must link the shared stylesheet"
    )
    assert re.search(r'<span class="chip[^"]*"></span>', page), "the legend renders .chip swatches"

    css = _CSS.read_text()
    match = re.search(r"(?:^|[,}\s])\.chip\s*\{([^}]*)\}", css, re.M)
    assert match is not None, ".chip is not declared in driftless.css, the sheet this page links"
    body = match.group(1)
    assert re.search(r"\bwidth\s*:", body) and re.search(r"\bheight\s*:", body), (
        "driftless.css's .chip declares no box size — the swatch would render at zero size"
    )


_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULES = re.compile(r"([^{}@]+)\{([^{}]*)\}")


def _declarations(selector: str) -> str:
    """Every declaration driftless.css writes for a rule naming ``selector``.

    Joined rather than picked: the frozen columns share one rule for what they have in
    common and take a second each for their own offset, and a test that read only the
    first would pass on a stylesheet that had dropped the second."""
    css = _COMMENT.sub("", _CSS.read_text())
    return " ".join(body for sel, body in _RULES.findall(css) if selector in sel)


def _bars(body: str) -> dict[tuple[str, str], str]:
    """``(person, week) -> the cell's style attribute``, for the grid cells only."""
    read = (dict(_ATTR.findall(attrs)) for attrs, _ in _TD.findall(body))
    return {
        (a["data-person"], a["data-field"]): a.get("style", "") for a in read if "data-state" in a
    }


def test_every_cell_prints_its_share_of_capacity_and_draws_it_at_that_length(
    client: TestClient,
) -> None:
    """The complaint the grid drew as a table: every cell under 80% painted IDENTICALLY —
    5% of capacity and 78% of it were the same blank box — so the heat was in the numbers
    and nowhere else. Each cell now carries the ratio twice: as a percentage in its own
    text, and as a bar whose LENGTH is that percentage, clamped at the full width so an
    over-capacity cell cannot draw past its own box. Length is not colour, and the
    percentage is not either, so neither greyscale nor forced-colours takes the reading
    away."""
    week = MONDAY.isoformat()
    cells, bars = _cells(client.get(PAGE).text), _bars(client.get(PAGE).text)
    assert cells[("Bo", week)] == ("under", "20 50%"), "20 of 40 hours is half a person's week"
    assert cells[("Dee", week)] == ("tight", "36 90% tight")
    assert cells[("Ada", week)] == ("over", "60 150% over")
    assert cells[("Cass", week)] == ("under", "0 0%")
    assert bars[("Bo", week)] == "--load: 50%" and bars[("Cass", week)] == "--load: 0%"
    assert bars[("Ada", week)] == "--load: 100%", "a 150% bar must clamp, not run past its box"
    stripped = re.sub(r'\s(?:class|style)="[^"]*"', "", client.get(PAGE).text)
    assert _cells(stripped)[("Ada", week)][1] == "60 150% over", "the wash was the only carrier"
    assert _cells(stripped)[("Bo", week)][1] == "20 50%"
    blind = capacity_cell(5.0, 0.0)
    assert (blind["percent"], blind["fill"], blind["mark"]) == ("", "0%", "unknown"), blind
    grid = _declarations(".heatmap-grid td.hm-cell")
    assert "linear-gradient" in grid and "var(--load" in grid, grid


def test_the_person_and_capacity_columns_stay_put_while_the_weeks_scroll(
    client: TestClient,
) -> None:
    """Twenty-six columns scroll sideways inside ``.scroll-x``; before this the two that say
    WHICH row you are reading scrolled away with them, so half way across the grid a figure
    belonged to nobody. Both are pinned to the left edge of the scroll box — the capacity
    column at exactly the person column's own width, or the two would overlap — and the pair
    is narrow enough to leave scrollable grid on a 390px phone (24.375rem inside no gutter at
    all), so freezing them cannot be what pushes the page sideways."""
    page = client.get(PAGE).text
    assert '<table class="heatmap-grid"' in page, "the grid does not claim its own rule"
    assert page.count('"hm-who"') == 5 and page.count('"hm-cap"') == 5, "header plus four people"
    shared = _declarations(".hm-who")
    assert "position: sticky" in shared and "box-sizing: border-box" in shared, shared
    assert "position: sticky" in _declarations(".hm-cap")
    assert re.search(r"left:\s*0\b", shared), "the person column is not pinned to the edge"
    width = re.search(r"(?<!max-)(?<!min-)width:\s*([\d.]+)rem", shared)
    offset = re.search(r"left:\s*([\d.]+)rem", _declarations(".hm-cap"))
    assert width is not None and offset is not None, (shared, _declarations(".hm-cap"))
    assert width.group(1) == offset.group(1), "the capacity column is not flush with the person"
    capacity = re.search(r"(?<!max-)(?<!min-)width:\s*([\d.]+)rem", _declarations(".hm-cap"))
    assert capacity is not None
    assert float(offset.group(1)) + float(capacity.group(1)) < 20.0, "no grid left on a phone"


def test_the_legend_is_built_from_the_thresholds_the_cells_are_judged_by(
    client: TestClient,
) -> None:
    """A legend is a second copy of the rule, and this one had drifted: it printed 100-120%
    as "near cap" and over 120% as "overloaded" while ``capacity_cell`` had been calling
    anything over 100% over since the day it was written. So it is no longer written — it is
    BUILT from ``_WASHES`` and the evaluator's own ratios, and every state a cell can take
    has a row, or the two cannot disagree again."""
    key = legend()
    assert [band["state"] for band in key] == ["under", "tight", "over", "unknown"]
    assert {band["wash"] for band in key} == set(_WASHES.values())
    page = client.get(PAGE).text
    assert '<dl class="legend hm-legend">' in page
    for band in key:
        assert band["reach"] in page, f"{band['state']} is missing from the rendered legend"
    assert "80%" in page and "100%" in page, "the legend does not name the evaluator's ratios"
    assert "120%" not in page, "the legend still claims a threshold the code does not use"


def test_the_showcase_takes_the_six_week_default_and_the_long_horizon_stays_a_link(
    client: TestClient,
) -> None:
    """The static showcase exports the heatmap at its default horizon — it walks the
    app's route templates and appends only ``?as_of=``, never ``?weeks=`` — and swaps
    the picker for a note, so the bundle never links a horizon it does not carry. Live,
    every longer horizon stays one link away in the page's own selector."""
    spec = importlib.util.spec_from_file_location(
        "driftless_showcase_heatmap",
        Path(__file__).resolve().parents[1] / "bin/driftless-showcase.py",
    )
    assert spec is not None and spec.loader is not None
    showcase = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(showcase)
    assert "/org/heatmap" not in showcase.EXCLUDED_ROUTES
    live = client.get(PAGE).text
    exported = showcase.HEATMAP_HORIZON_PICKER.sub(showcase.HEATMAP_HORIZON_COPY, live, count=1)
    assert "weeks=" in live and "weeks=" not in exported
    assert "default horizon" in exported
    assert HORIZON_WEEKS == 6 and HORIZON_CHOICES[-1] == MAX_WEEKS
    page = client.get(PAGE).text
    assert len(re.findall(r'data-week="', page)) == HORIZON_WEEKS
    for reachable in HORIZON_CHOICES:
        if reachable != HORIZON_WEEKS:  # the one in force prints as a word, not a link
            assert f"weeks={reachable}" in page, f"the {reachable}-week horizon is unreachable"
