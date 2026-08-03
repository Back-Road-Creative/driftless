"""The release-gate performance floor at commercial volume: a page's statement
count must NOT scale with how much data the store holds.

The floor is a STATEMENT COUNT, not a wall-clock budget. A "<500ms server-side"
assertion measures the machine (a CI box, or a dev box running a dozen agents in
parallel), not the code: it goes red on a busy laptop and green on a fast one
with the same defect present, which makes it a flaky late gate on a machine
property. ``test_perf_n1`` already argues this — "the defect is the STATEMENT
COUNT, not the SQLite wall-time" — and the argument holds harder here: in-process
SQLite hides the per-statement round trip a networked Postgres charges, so the
one number that predicts production latency is how many statements the page
issues. This module asserts that number is invariant in the row count, which is
what "no N+1" actually names, and is deterministic on any machine.

Two stores, rendered through the real routes:

* SMALL — 5 portfolios, 6 projects, 30 tasks, 6 risks.
* COMMERCIAL — the SAME topology with ``VOLUME`` x the rows per project: 300
  tasks, 300 baseline lines, 60 risks. Past the plan's ≥5 portfolios / ≥200
  tasks / ≥50 risks bar (pinned by ``test_commercial_fixture_meets_the_volume_floor``).

Only the ROW COUNT differs. The topology (portfolios, projects, milestones,
status snapshots) and the aggregate signals every evaluator reads are held equal
by construction — each project's planned cost is split across however many tasks
it has and its risk exposure across however many risks, and both task counts are
multiples of the 5-step ``percent_complete`` cycle — so the two stores produce
the SAME assessments, the same threats and the same rendered figures. That makes
the expected difference exactly zero: the constant in "within a small constant"
is 0. Any statement the commercial store issues and the small one does not is a
per-row query, i.e. the N+1 this gate exists to catch.

What each page measures (identical at both volumes) is recorded in ``MEASURED``
below, and every ceiling is derived from it — so the ceilings sit just above what
the code costs and an across-the-board regression that scales both stores equally
still fails. The recorded numbers are re-measured on every run rather than
believed, because two of the three had drifted upward in comment form unnoticed.

PROJECT count is the second axis, asserted separately because it is a different
property: row invariance says "no cascade per row", the project slope says "one
more project costs zero statements". ``/`` used to pay ~47 per
extra project — a 50-project store rendering it in ~2,300 round trips to a
networked Postgres — because every evaluator read its rows one project at a
time. Batched (``assess.adapters.prefetched``) that is 0.0, on both pages.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as _app  # noqa: F401  (import order: see test_perf_n1)
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.web import create_router, pages
from driftless.web.business_map import create_business_map_router
from test_perf_n1 import AS_OF, JAN, assert_recorded, count_route

N_PORTF, N_PROJ, MILES_PER, N_PEOPLE = 5, 6, 3, 4
SMALL_TASKS_PER, SMALL_RISKS_PER = 5, 1
VOLUME = 10  # commercial = VOLUME x the rows per project, same topology
PROJECT_PLANNED_COST, PROJECT_RISK_EXPOSURE = 10_000.0, 30_000.0

# Absolute ceilings at commercial volume, each DERIVED from a recorded
# measurement that ``test_statement_count_does_not_scale_with_data_volume``
# re-measures through ``assert_recorded``. A number recorded only in a comment
# drifts unnoticed until it reaches the ceiling and the next honest read fails as
# a mystery; keyed by path (minus any query string) so the parametrised test looks
# its own baseline up rather than a fourth column. Each is flat in the project
# count, and priced: deleting ``threat_cards``'s eager options costs /threats 112.
MEASURED = {"/": 130, "/process-map": 17, "/threats": 54}

# Headroom is TWO statements, never "one per project": at N_PROJ = 6 that margin
# is the price of the very defect these guard, so a one-statement-per-project
# relapse would land on the boundary and pass. See ``test_perf_n1``'s headroom
# note, which these mirror.
MAX_HOME_STMTS = MEASURED["/"] + 2
MAX_BUSINESS_MAP_STMTS = MEASURED["/process-map"] + 2
MAX_THREATS_STMTS = MEASURED["/threats"] + 2

# The project-count axis: the same per-project shape at FEW and MANY projects,
# so the gap over the extra projects IS the marginal cost of one project, and
# counts far apart let that term dominate the fixed per-request query set (the
# quotient reads the slope, not the intercept). Both pages are FLAT in the
# project count -- measured 0.0 per extra project on each -- and the guard
# demands exactly that: statement counts are integers, so the slope is an exact
# rational with no wobble to tolerate, and any nonzero value IS a per-project
# read. A ceiling of 1 waved through the exact N+1 this file exists to catch
# (dropping ``selectinload(Project.milestones)`` puts ``/`` at slope 1.0).
FEW_PROJECTS, MANY_PROJECTS = 5, 20
SLOPE_PAGES = ("/", "/threats")

# The business map is requested with ``?process=`` so the page carries a roster
# of REAL project names: without it the grid is pure frozen-catalog text and an
# empty store would render a byte-similar page, so a content marker could not
# tell a populated render from an empty-state one. Risk Responses is assessable
# and never waived here, so every seeded project is listed.
LISTED_PROCESS = "11.2"
BUSINESS_MAP_PATH = f"/process-map?process={LISTED_PROCESS}"

# (path, ceiling, a marker only the seeded data can put on the page)
PAGES = (
    ("/", MAX_HOME_STMTS, "Project 000"),
    (BUSINESS_MAP_PATH, MAX_BUSINESS_MAP_STMTS, "Project 0"),
    ("/threats", MAX_THREATS_STMTS, "Project 0"),
)


def _populate(db: Session, tasks: int, risks: int, projects: int = N_PROJ) -> None:
    """One store shape at ``tasks``/``risks`` rows per project, ``projects`` deep.

    ``planned_cost`` and ``impact`` divide a per-project TOTAL by the row count,
    so scaling the rows leaves BAC, EV, CPI/SPI and risk exposure identical and
    the two volumes assess the same — the counts below then differ only by
    whatever queries the row count itself drives. ``projects`` varies the OTHER
    axis, leaving that shape alone, so the gap between two counts is the cost of
    a project."""
    biz = m.Business(name="BRC")
    dept = m.Department(name="Delivery", business=biz)
    people = [m.Person(name=f"Person {p:02d}", department=dept) for p in range(N_PEOPLE)]
    db.add_all(people)
    pfs = [m.Portfolio(name=f"Portfolio {p:02d}", business=biz) for p in range(N_PORTF)]
    db.add_all(pfs)
    for j in range(projects):
        pf = pfs[j % N_PORTF]
        proj = m.Project(name=f"Project {j:03d}", portfolio=pf, delivery_mode="predictive")
        ws = m.Workstream(name=f"WS{j}", project=proj)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        for t in range(tasks):
            task = m.Task(
                name=f"T{j}.{t}",
                workstream=ws,
                estimate_unit="hours",
                percent_complete=(t * 20) % 100,
                assignee=people[t % N_PEOPLE],
            )
            db.add(
                m.BaselineLine(
                    baseline=baseline,
                    task=task,
                    planned_start=JAN,
                    planned_finish=AS_OF,
                    planned_cost=PROJECT_PLANNED_COST / tasks,
                )
            )
        for _ in range(3):
            db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=1500.0))
        for r in range(risks):
            db.add(
                m.Risk(
                    project=proj,
                    description=f"risk {j}.{r}",
                    probability=0.5,
                    impact=PROJECT_RISK_EXPOSURE / risks,
                    status="open",
                )
            )
        for ms in range(MILES_PER):
            db.add(
                m.Milestone(
                    project=proj,
                    name=f"M{j}.{ms}",
                    target_date=AS_OF,
                    status="at_risk" if ms == 0 else "pending",
                )
            )
        db.add(m.StatusSnapshot(project=proj, taken_on=AS_OF if j % 2 else JAN))
    db.commit()


def _serve(
    path: Path, tasks: int, risks: int, projects: int = N_PROJ
) -> Iterator[tuple[Engine, TestClient]]:
    """The seeded store behind the real ``/``, ``/process-map`` and ``/threats``
    routes on a throwaway SQLite *file* (an in-memory URL would hand a
    per-request connection its own empty database), mirroring ``home_client``."""
    engine = new_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate(db, tasks, risks, projects)
    with factory() as db:
        app = FastAPI()
        app.include_router(create_router(AS_OF))
        app.include_router(create_business_map_router(AS_OF))
        app.include_router(pages.create_pages_router(AS_OF))
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app) as client:
            yield engine, client


@pytest.fixture
def small(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    yield from _serve(tmp_path / "small.db", SMALL_TASKS_PER, SMALL_RISKS_PER)


@pytest.fixture
def commercial(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    yield from _serve(
        tmp_path / "commercial.db", SMALL_TASKS_PER * VOLUME, SMALL_RISKS_PER * VOLUME
    )


@pytest.fixture
def few_projects(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    yield from _serve(tmp_path / "few.db", SMALL_TASKS_PER, SMALL_RISKS_PER, FEW_PROJECTS)


@pytest.fixture
def many_projects(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    yield from _serve(tmp_path / "many.db", SMALL_TASKS_PER, SMALL_RISKS_PER, MANY_PROJECTS)


@pytest.mark.parametrize("path", SLOPE_PAGES)
def test_cost_per_extra_project_is_zero(
    few_projects: tuple[Engine, TestClient],
    many_projects: tuple[Engine, TestClient],
    path: str,
) -> None:
    """An assessment page's cost per extra project is exactly zero statements —
    the axis a growing business actually grows. Every read the walk makes is
    batched across the whole project list, so a project's marginal cost is zero,
    not the ~47 / ~18 charged before — and not the 1 a ceiling would forgive."""
    lean, lean_status = count_route(*few_projects, path)
    heavy, heavy_status = count_route(*many_projects, path)
    assert (lean_status, heavy_status) == (200, 200)
    slope = (heavy - lean) / (MANY_PROJECTS - FEW_PROJECTS)
    assert slope == 0, (
        f"{path} ran {lean} statements over {FEW_PROJECTS} projects and {heavy} over "
        f"{MANY_PROJECTS}: {slope:.1f} per extra project (must be exactly 0) — some "
        "read the assessment walk makes is firing once per project instead of once "
        "across all of them"
    )


@pytest.mark.parametrize(("path", "ceiling"), [(p, c) for p, c, _ in PAGES])
def test_statement_count_does_not_scale_with_data_volume(
    small: tuple[Engine, TestClient],
    commercial: tuple[Engine, TestClient],
    path: str,
    ceiling: int,
) -> None:
    """The N+1 proof: VOLUME x the rows, the same number of statements."""
    lean, lean_status = count_route(*small, path)
    heavy, heavy_status = count_route(*commercial, path)
    assert (lean_status, heavy_status) == (200, 200)
    assert heavy == lean, (
        f"{path} ran {lean} statements over {SMALL_TASKS_PER * N_PROJ} tasks and {heavy} over "
        f"{SMALL_TASKS_PER * VOLUME * N_PROJ}: the extra {heavy - lean} scale with the row "
        "count, so some relationship is loading lazily per row (fix: selectinload it)"
    )
    assert heavy <= ceiling, (
        f"{path} ran {heavy} statements at commercial volume (ceiling {ceiling}): both volumes "
        "regressed together, so the per-request query set itself grew"
    )
    assert_recorded(MEASURED, path.split("?")[0], heavy)


def test_every_recorded_baseline_belongs_to_a_page_under_test() -> None:
    """The drift guard above only covers the paths ``PAGES`` drives, so a
    baseline recorded for anything else would never be re-measured."""
    assert set(MEASURED) == {path.split("?")[0] for path, _, _ in PAGES}


@pytest.mark.parametrize(("path", "marker"), [(p, mk) for p, _, mk in PAGES])
def test_pages_render_seeded_content_at_commercial_volume(
    commercial: tuple[Engine, TestClient], path: str, marker: str
) -> None:
    """200 is not enough: an empty-state render is cheap and would sail through
    the ceilings above, so each page must show data that only the seed can put
    there."""
    _, client = commercial
    response = client.get(path)
    assert response.status_code == 200
    assert marker in response.text, f"{path} rendered without seeded content"


def test_commercial_fixture_meets_the_volume_floor(
    commercial: tuple[Engine, TestClient],
) -> None:
    """The gate is only worth its name if the store is genuinely commercial —
    pin the plan's bar so a future trim of the fixture fails here, loudly,
    instead of quietly turning the ceilings above into a small-store test."""
    engine, _ = commercial
    with Session(engine) as db:
        counts = {
            model.__name__: db.scalar(select(func.count()).select_from(model))
            for model in (m.Portfolio, m.Task, m.Risk)
        }
    assert counts == {"Portfolio": N_PORTF, "Task": 300, "Risk": 60}
    assert counts["Portfolio"] >= 5  # the plan's commercial bar, per row kind
    assert counts["Task"] >= 200
    assert counts["Risk"] >= 50
