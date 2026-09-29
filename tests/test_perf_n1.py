"""Statement-count guard against the dashboard N+1 cascades.

``gather.portfolio_nodes`` (GET /) and ``assess.top_threats`` (GET /threats)
walk the Portfolio -> Project -> Baseline -> Line -> Task hierarchy plus each
project's milestones. With the model relationships left at the default
``lazy="select"`` every project, baseline, line, task and milestone was a
separate round trip, so the statement count scaled with projects x tasks.
``feed.attention_feed`` had the same shape one layer up: its per-project
completeness/wizard walk queried the sign-off ledger and every tracked
resolver fresh for each project, so the home dashboard (which renders the
feed twice, plus ``business_process_cells`` and the portfolio hierarchy)
scaled with projects x catalog processes too.

The defect is the STATEMENT COUNT, not the SQLite wall-time: in-process SQLite
hides a per-statement cost that a networked Postgres would not. These ceilings
sit just above the eager-loaded (``selectinload``) expectation and well below
the pre-fix count, so the pre-fix code fails them and the eager-loaded code
passes. A determinism check rides along: the eager path must return byte-equal
trees/threats to the lazy path.

One guard here counts ROWS instead. Once every read is batched, a statement count
stops being able to see how much of the store a call actually reads — the scoped
project-hub board and the whole-store one differ by 281 rows and by MINUS four
statements — so the scoping is pinned on the axis that still separates them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import cli, models as m
from driftless.api.app import app as _app  # noqa: F401  (see import-order note below)
from driftless.api.app import get_session
from driftless.assess import engine as assess
from driftless.assess import adapters, feed
from driftless.assess.evaluators import resource
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import catalog, rollup
from driftless.pmbok import state as st
from driftless.report import gather
from driftless.report.documents import process_map, scope_baseline
from driftless.web import create_router, views
from driftless.web.process_map import create_process_map_router
from driftless.web.project_hub import create_project_hub_router
from driftless.web.wizard_pages import create_wizard_router

# ``driftless.api.app`` and the web route modules import each other (the app
# mounts their routers; they use the app's ``fetch``/``insert``
# helpers). Importing ``app`` first lets that cycle resolve the way every other
# web test already relies on; importing one of them directly first would hit a
# partially-initialized module.

AS_OF = date(2026, 6, 30)
JAN = date(2026, 1, 1)

# A store large enough for an N+1 to dominate but small enough to stay fast.
N_PORTF = 2
N_PROJ = 6
TASKS_PER = 4
RISKS_PER = 2
MILES_PER = 2
N_PEOPLE = 4  # cycled across each project's tasks -- see the Resource N+1 note below

# Ceilings the lazy code blows past and the eager code clears (measured on this
# seed: portfolio_nodes 114 -> 75, top_threats 133 -> 101; batching the last
# per-project evaluator reads took those to 21 and 16). The hierarchy walk is
# now constant in the store size; what remains scales only with the per-project
# evaluator queries, not with tasks-per-project. A regression back to lazy
# loading re-adds one query per baseline line and trips these.
#
# HEADROOM, everywhere below: ONE or TWO statements over the measured count, and
# never "one per project the call walks" — read as a flat N_PROJ that margin is
# exactly the price of the cheapest defect these guards name, so a relapse
# costing one statement per project lands ON the ``<=`` boundary and passes.
# Where a mutation has PRICED the regression the ceiling sits below that price,
# +1 rather than +2 if that is what it takes (``MAX_THREAT_CARDS_SCOPED_STMTS``,
# whose defect costs two). A ceiling several statements clear of what the code
# costs cannot fail, and a test that cannot fail is decoration.
#
# Every ceiling is DERIVED from its ``MEASURED`` entry rather than written as a
# literal, and every entry is re-measured by the test that uses it (see
# ``assert_recorded``): baselines kept drifting upward while recorded only in a
# comment, one onto its own ceiling exactly, so the next honest read would have
# failed as a mystery breach. Downward drift is caught the same way — the report
# path's two counts fell nine and nineteen on this master, and said so.
MEASURED: dict[str, int] = {
    # The seven bumped below all run the risk evaluator, which now reads
    # RiskResponse (risk-response planning) as well as Risk: +1 for a store-wide
    # walk, where ``adapters.prefetched`` batches the extra read across every
    # project in the scope; the three that also run ``live_threats`` twice
    # OUTSIDE that scope for a week-over-week delta (threat_cards_scoped,
    # project_hub_page) or read it inside AND out (threat_cards) pay more —
    # each unscoped evaluate() call re-reads Risk and RiskResponse fresh.
    #
    # Same shape again for TaskDependency: schedule.evaluate() now reads it
    # too, batched inside ``adapters.prefetched`` -- +1 (or +2, unscoped x2).
    "portfolio_nodes": 26,
    "top_threats": 21,
    # The seven bumped again here all walk every resolver for completeness/state,
    # which now also reads the scope records: ``requirements_documentation``
    # checks filed ``Requirement`` rows before falling back to prose,
    # ``requirements_traceability_matrix``/``work_breakdown_structure`` read
    # ``Requirement``/``Deliverable``, and ``verified_deliverables``/
    # ``accepted_deliverables`` join through ``AcceptanceRecord`` — each a new
    # batched read inside ``adapters.prefetched``, not a per-project one.
    #
    # The same six bumped again here, +5 apiece: the resolver walk now also reads
    # the resource records. ``resource_management_plan``/``team_charter``/
    # ``team_performance_assessments`` check filed ``ResourceType``/
    # ``ResponsibilityAssignment``/``TeamAssessment`` rows before falling back to
    # prose, and ``resource_breakdown_structure``/``physical_resource_assignments``
    # are new resolvers reading ``ResourceBreakdown`` and a joined
    # ``Acquisition``/``ResourceType`` query — five new batched reads inside
    # ``adapters.prefetched``, not a per-project one. ``home_render`` pays it three
    # times over (the feed renders twice plus its own ``business_process_cells``
    # call), so its own bump is +15.
    #
    # Every store-wide walk moved +1 once more when ``lessons_learned_register``
    # started resolving off ``LessonLearned`` (a batched query of its own rather
    # than sharing ``NarrativeArtifact``'s); ``project_hub_page`` +4 and
    # ``home_render`` +3 because the hub's flow tile (``pmbok.flow_facts``) and
    # the risk-reserve line (``pmbok.risk_facts``) each read one batched row set
    # more. Honest batched reads inside ``adapters.prefetched``, never per-project.
    # Every store-wide walk moved +1 once more: ``project_calendars`` now resolves
    # off ``ProjectCalendar``, and ``schedule_data``/the network-diagram resolver
    # read the ``TaskDependency`` join through one honest batched query each (both
    # go through ``mapping._grouped``, not a per-project one). ``home_render`` pays
    # it three times over (the feed renders twice plus its own
    # ``business_process_cells`` call), so its own bump is +3.
    "business_process_cells": 27,
    "threat_cards": 60,
    "threat_cards_scoped": 66,
    "attention_feed": 49,
    "home_render": 166,
    "process_map_page": 27,
    "project_hub_page": 110,
    "wizard_page": 3,
    "resource_evaluator": 19,
    "process_map_document": 27,
    "scope_baseline_document": 7,
    "wizard_status_cli": 27,
}


def assert_recorded(baselines: dict[str, int], name: str, stmts: int) -> None:
    """Fail when a live count drifts from the recorded baseline its ceiling is
    derived from, naming BOTH numbers — so an honest extra read is reported the
    moment it lands, instead of eating the margin until some later change trips
    the ceiling and reads as that change's fault. Shared with the other two perf
    modules: one drift guard, not three that can drift apart."""
    assert stmts == baselines[name], (
        f"{name} measures {stmts} statements, recorded {baselines[name]}: the baseline "
        f"drifted. Find the read that moved; if it is honest, record {stmts} and "
        "re-derive the ceiling from it (measured + 1, or 2)."
    )


MAX_PORTFOLIO_NODES_STMTS = MEASURED["portfolio_nodes"] + 2
MAX_TOP_THREATS_STMTS = MEASURED["top_threats"] + 2

# ``rollup.business_process_cells`` used to run ``latest_sign_off`` plus one
# resolver SELECT per tracked output for every (project, process) pair —
# ~77 statements PER PROJECT on this seed (460+ for six projects). Batched it
# pays a fixed query set (projects + the sign-off ledger + one query per
# tracked model), so this ceiling is flat in the project count — the same
# derivation the route-level ceiling over the rendered /process-map carries for
# the same measured count.
MAX_BUSINESS_MAP_STMTS = MEASURED["business_process_cells"] + 2

# ``views.threat_cards`` ran its OWN ``select(Project)`` with no eager options
# before calling ``assess.assess_project`` per project — bypassing the same
# ``adapters.eager_project()`` load ``top_threats`` uses for the same walk, so
# the statement count scaled with tasks-per-project again (measured on this
# seed: 305 unfixed -> 273 fixed; unfixed grows further with more baseline
# lines per project, fixed does not). 273 already includes two extra full
# ``top_threats``-shaped passes (current + prior week) plus a from-scratch
# ``assess_project`` pass for actions/names — an accepted, non-N+1 cost the
# eager load does not remove — so this ceiling sits well below the unfixed
# 305 without chasing that fixed cost down to ``top_threats``'s own 101.
# The fixture's people roster (see ``N_PEOPLE``) adds a fixed amount on top:
# three assess_project-shaped passes x six projects, each project's Resource
# evaluator paying one batched ``Person`` select (measured: 345 when it still
# ran ``session.get`` per assignee -> 291 once ``evaluate`` batches into one
# ``IN`` query per project — the same one-query-per-project shape as
# ``portfolio_nodes``/``top_threats`` above, which absorb the same +1 per
# project inside their existing margin without moving). Batching the last
# per-project reads across the whole store then took that 291 to 47: all three
# assess-shaped passes now pay one fixed query set between them, so a
# regression that restores ANY per-project read is a handful of statements, not
# a rounding error. Same measured count, same derivation, as the route-level
# /threats ceiling this path feeds. Mutation-checked and re-priced on this
# master: deleting the eager options from that query takes this path 54 -> 66,
# so it fails on the regression it names, with ten statements to spare.
MAX_THREAT_CARDS_STMTS = MEASURED["threat_cards"] + 2

# The project hub used to call ``threat_cards`` for the WHOLE store and filter to
# one project client-side — a single hub page paying whole-store cost. Scoped via
# ``project_id=``, only that project's assessment runs. Two axes guard that, and
# neither sees what the other does.
#
# ROWS are what the scoping buys, not statements. Once the whole-store path
# batched every read (the 291 -> 47 above), ITS statement count went flat in the
# project count too — measured 54 at 1, 2, 6, 12 and 24 projects — and BELOW the
# scoped call's 58, so no statement ceiling can catch a relapse to
# whole-store-then-filter: the number would go DOWN. What still separates them is
# how much of the store lands in the session. Measured on this seed, the scoped
# call loads 47 ORM rows at every one of those project counts (slope 0); the same
# call unscoped and filtered afterwards loads 31 -> 652 across that range, ~27 per
# extra project. So the flatness claim is pinned in rows, where removing the
# scoping fails it.
MAX_SCOPED_ROWS_PER_OTHER_PROJECT = 0
FEW_PROJECTS, MANY_PROJECTS = 2, 12

# The statement ceiling the row slope cannot replace: a slope of zero says the hub
# reads only its own project, not that reading it stays batched. A lazy load per
# baseline line inside that one project's walk (the 305 -> 273 defect above, one
# project's share of it) adds statements while loading the same rows, so this
# catches what the slope cannot — the two are complementary, not redundant.
#
# It was 55 and it did NOT catch it. Both halves of that claim are now measured
# rather than argued, by deleting ``.options(*adapters.eager_project())`` from
# ``views.threat_cards``'s query — precisely "the baseline hierarchy loading
# lazily again" — and re-running this file:
#
#   whole-store ``threat_cards``   54 -> 66  vs 56  fails, correctly
#   scoped ``threat_cards``        58 -> 60  vs 59  fails, correctly
#   scoped rows-per-other-project   0 ->  0  vs  0  passes: same rows, lazily
#
# So the slope half holds (it cannot see this defect at all; its own defect,
# whole-store-then-filter, moves it 0 -> 27 rows per project, also measured) —
# but the ceiling half was decoration at 55, and re-priced every round since.
# The defect costs TWO statements here, not the ~12 it costs whole-store, because
# the lazy loads fire once per instance per session and this walk covers one
# project. So this ceiling CANNOT take the +2 its siblings do: +2 over the
# measured 58 is 60, exactly the regression's price, and ``<=`` passes it. +1 fails.
MAX_THREAT_CARDS_SCOPED_STMTS = MEASURED["threat_cards_scoped"] + 1

# ``feed.attention_feed``'s per-project completeness/wizard walk had the same
# shape ``business_process_cells`` used to: ~92 statements PER PROJECT on this
# seed (595 total for six projects), because it called ``state.completeness``
# and ``wizard.next_step`` outside any prefetch. Wrapped in ``state.prefetched``
# it pays the same fixed query set, measured 117 on this seed and 31 once the
# remaining per-project reads batched too. The home dashboard renders the feed
# twice (current + week-ago trend) plus ``business_process_cells`` plus the
# portfolio hierarchy, so its own ceiling is wider but still flat — measured
# 1300 -> 344 -> 114 on this seed and re-measured every round since. That count
# is the SAME one the route-level baseline records over a 5-portfolio store at
# ten times the rows per project — the flatness claim stated as a number.
MAX_ATTENTION_FEED_STMTS = MEASURED["attention_feed"] + 2
MAX_HOME_RENDER_STMTS = MEASURED["home_render"] + 2

# The three per-project pages had the same shape one level down: each called
# ``state.project_process_states`` (or ``wizard.next_step``, which walks the
# same per-process ground) more than once per render, outside any
# ``state.prefetched`` scope, so every call re-ran the sign-off ledger query
# plus one resolver SELECT per tracked output for all 49 catalog processes.
# Measured on this seed: process-map (project_process_states once, then
# _process_grid and area_completeness each recomputing it, plus
# state.completeness's own walk) 317 statements -> 14 fixed; the hub
# (area_completeness + state.completeness, two walks, plus its own scoped
# threat cards/EVM/RAID/milestones cost that this fix does not touch) 218 ->
# 74 fixed; the wizard page's next_step is early-exit bounded so it was
# already small (14 unwrapped, under even the fixed ceiling) but still
# unwrapped — wrapped now for the same reason, and 3 since. All three share
# one prefetch scope per request and pay a fixed query set instead. These sat
# at 60/100/25 while measuring 14/74/3: a ceiling four times what the code
# costs cannot fail, so the wizard's could no longer even catch its own
# pre-fix 14. Re-derived to measured + the headroom above.
MAX_PROCESS_MAP_STMTS = MEASURED["process_map_page"] + 2
# The hub's "74" was stale by five: master already measured 79 when this constant
# was last read, and nothing caught the drift because 79 still cleared 82. Two
# honest reads then landed together — this branch's store-wide capacity read (+3,
# which a ONE-project page must pay, because a person's total load cannot be
# answered from one project's rows) and the dated-progress ChangeLog replay (+1)
# — for 83, one over. Each passed alone; only the pair failed, which is what a
# combined gate is for. Re-derived at measured + the one statement a
# single-project call gets, and the measurement is recorded so the NEXT drift is
# visible instead of silently eating the margin.
#
# That raise was justified by arithmetic — "still nowhere near 218". The guard's
# ability to FAIL is now measured, the way its siblings above are. Deleting the
# ``with state.prefetched(db, [project])`` scope from ``project_hub`` — exactly
# the "re-walking outside the prefetch cache" this names, and the shape the 218
# above was measured on — takes this route 87 -> 477, re-priced on this master.
# So the defect costs 390 statements today against the 144 it cost at 218 -> 74,
# and this ceiling catches it with 389 to spare: a guard, not decoration. It keeps
# the +1 its siblings' +2 replaces — a ONE-project page's defects are priced per
# project walked too, and it walks one.
#
# One mutation does NOT reproduce it, and cost one re-derivation pass before it
# was recognised: passing an empty ``[]`` instead of ``[project]`` measures 82,
# BELOW the healthy 83, because an empty scope makes every resolver read zero
# rows rather than forcing the re-walk. It does not slow the page down, it
# zeroes its answers (this project's completeness 0.35 -> 0.0) — and nothing in
# the suite fails on that, which is a gap on the correctness axis, not this
# one's. Re-check this ceiling by DELETING the scope, never by emptying it — done
# again for the task register's read: clean 87 recorded below, scope deleted 477.
# Master's literal 87 had reached its own ceiling exactly — the drift this catches.
MAX_PROJECT_HUB_STMTS = MEASURED["project_hub_page"] + 1
MAX_WIZARD_STMTS = MEASURED["wizard_page"] + 2

# ``resource.evaluate`` ran ``session.get(Person, ...)`` per distinct assignee,
# and the weak identity map evicts a ``Person`` the moment nothing outside the
# loop holds a reference — so a store-wide walk that calls ``evaluate`` once
# per project paid one SELECT per (project, assignee) pair, not per person.
# Measured on this seed (six projects, four assignees each, plus the
# project-listing select the test itself runs): 31 unfixed (1 + 6 x (1 task
# select + 4 person gets)) -> 13 fixed (1 + 6 x (1 task select + 1 batched
# person select)). Flat regardless of how many distinct people the store has.
# Unlike the flat ceilings above this one is per project BY DESIGN. It was 2 per
# project (18 against a measured 13) until capacity became store-wide: the
# evaluator now also reads ``person_task_loads`` for its assignees, because a
# capacity that belongs to the PERSON cannot be answered from one project's
# rows. That read is batched into the same prefetch scope, so a store-wide walk
# pays it ONCE (top_threats 16 -> 18, portfolio_nodes 21 -> 23, both inside their
# existing margins); this test drives ``evaluate`` project by project with no
# scope open, which is the shape that pays it per project — 3 by design, 19
# measured. Re-derived at measured + 2, still far under the 37 the per-assignee
# ``session.get`` regression now costs on this seed.
MAX_RESOURCE_EVALUATOR_STMTS = MEASURED["resource_evaluator"] + 2

# The report-document surface had NO statement ceiling before this fix — it sat
# one layer below the web pages above, unguarded. ``process_map.render`` called
# ``state.project_process_states`` (via ``_process_rows``) AND ``state.completeness``
# (its own independent walk) outside any ``state.prefetched`` scope, so it paid the
# sign-off-ledger-plus-one-resolver-per-tracked-output cost for all 49 catalog
# processes TWICE. ``scope_baseline.render`` built ``original``/``current`` via two
# ``_baseline_view`` calls, each lazily loading ``line.task`` per line — the session's
# weak identity map evicts the previous call's ``BaselineLine`` rows the moment
# ``_baseline_view`` returns (nothing outside it holds a reference), so the second
# call re-queries every task rather than reusing the first call's load. The wizard
# CLI's ``status`` handler had the identical unwrapped process_process_states shape
# as ``process_map`` one layer further down. Measured on this seed (TASKS_PER=4):
# process_map.render 158 -> 14; scope_baseline.render 12 -> 7 (flat in task count
# once eager-loaded); wizard status CLI 80 -> 14. The first and third sat at 40
# and 35 against a measured 14 — nearly three times the cost, so a regression had
# to double before either noticed; re-derived to measured + the headroom above,
# well below the 158, 12 and 80 they exist to catch.
MAX_PROCESS_MAP_DOCUMENT_STMTS = MEASURED["process_map_document"] + 2
MAX_SCOPE_BASELINE_DOCUMENT_STMTS = MEASURED["scope_baseline_document"] + 2
MAX_WIZARD_STATUS_CLI_STMTS = MEASURED["wizard_status_cli"] + 2


def _populate_n1_store(db: Session, projects: int = N_PROJ) -> None:
    """The N+1 store body ``seeded`` and ``home_client`` both start from.

    ``projects`` varies the project-count axis and nothing else — every project
    carries the same rows either way, and the first one by name is identical in
    every store — so the gap between two counts is the cost of a project.

    Tasks are assigned to a small, department-linked people roster (cycled
    round-robin) so every project has assignees: the Resource evaluator only
    walks its per-assignee ``ratios`` when a project has any, and an
    unassigned fixture left that walk — and the N+1 it used to hide, one
    ``session.get(Person, ...)`` per (project, assignee) once the weak
    identity map evicts between projects — untested.
    """
    biz = m.Business(name="BRC")
    dept = m.Department(name="Delivery", business=biz)
    people = [m.Person(name=f"Person {p:02d}", department=dept) for p in range(N_PEOPLE)]
    db.add_all(people)
    portfolios = [m.Portfolio(name=f"Portfolio {p:02d}", business=biz) for p in range(N_PORTF)]
    db.add_all(portfolios)
    for j in range(projects):
        pf = portfolios[j % N_PORTF]
        proj = m.Project(name=f"Project {j:03d}", portfolio=pf, delivery_mode="predictive")
        ws = m.Workstream(name=f"WS{j}", project=proj)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        for t in range(TASKS_PER):
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
                    planned_cost=1000.0,
                )
            )
        for _ in range(3):
            db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=300.0))
        for r in range(RISKS_PER):
            db.add(
                m.Risk(
                    project=proj,
                    description=f"risk {j}.{r}",
                    probability=0.5,
                    impact=30000.0,
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
    db.commit()


def _in_memory_store(projects: int = N_PROJ) -> tuple[Engine, sessionmaker[Session]]:
    """The N+1 store, ``projects`` deep, on its own in-memory engine."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate_n1_store(db, projects)
    return engine, factory


@pytest.fixture
def seeded() -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    yield _in_memory_store()


@pytest.fixture
def home_client(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    """The identical N+1 store as ``seeded``, on a throwaway SQLite *file* — an
    in-memory URL would give the home route's per-request connection its own
    empty database — served through the real ``/`` route, so the ceiling below
    exercises the exact code path a browser hits."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate_n1_store(db)
    with factory() as db:
        app = FastAPI()
        app.include_router(create_router(AS_OF))
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app) as client:
            yield engine, client


@pytest.fixture
def project_pages_client(tmp_path: Path) -> Iterator[tuple[Engine, TestClient, int]]:
    """The identical N+1 store as ``seeded``, on a throwaway SQLite *file*, served
    through the real per-project pages (process map, hub, wizard) — the routes a
    browser hits, not the bare engine functions. Mirrors ``home_client``."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless_pages.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate_n1_store(db)
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()
    with factory() as db:
        app = FastAPI()
        # One include per router serving a counted route. `pages.py` is being carved
        # into per-controller modules, so a route this fixture counts leaves its module
        # with no signal here but a 404, which reads as a render failure, not a missing
        # mount.
        app.include_router(create_process_map_router(AS_OF))
        app.include_router(create_project_hub_router(AS_OF))
        app.include_router(create_wizard_router(AS_OF))
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app) as client:
            yield engine, client, project_id


def count_route(engine: Engine, client: TestClient, path: str) -> tuple[int, int]:
    """(statement count, HTTP status) for one GET through a live TestClient.

    Public because ``test_perf_commercial_volume`` counts the same way over the
    same engine-level listener — one counting helper, not two that could drift."""
    counter = {"n": 0}

    def _bump(*_: Any) -> None:
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _bump)
    try:
        response = client.get(path)
    finally:
        event.remove(engine, "before_cursor_execute", _bump)
    return counter["n"], response.status_code


def _count(engine: Engine, factory: sessionmaker[Session], call: Callable[[Session], Any]) -> int:
    """Statements executed while ``call`` runs on a cold (post-commit) session."""
    counter = {"n": 0}

    def _bump(*_: Any) -> None:
        counter["n"] += 1

    with factory() as db:
        event.listen(engine, "before_cursor_execute", _bump)
        try:
            call(db)
        finally:
            event.remove(engine, "before_cursor_execute", _bump)
    return counter["n"]


def _count_rows_loaded(factory: sessionmaker[Session], call: Callable[[Session], Any]) -> int:
    """ORM rows ``call`` pulls into a cold (post-commit) session.

    ``loaded_as_persistent`` fires once per instance a query materialises, so this
    counts how much of the store a call reads — the axis a statement count stops
    seeing once every read is batched into a fixed query set."""
    counter = {"n": 0}

    def _bump(*_: Any) -> None:
        counter["n"] += 1

    with factory() as db:
        event.listen(db, "loaded_as_persistent", _bump)
        try:
            call(db)
        finally:
            event.remove(db, "loaded_as_persistent", _bump)
    return counter["n"]


def test_portfolio_nodes_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    stmts = _count(engine, factory, lambda db: gather.portfolio_nodes(db, AS_OF))
    assert stmts <= MAX_PORTFOLIO_NODES_STMTS, (
        f"portfolio_nodes ran {stmts} statements (ceiling {MAX_PORTFOLIO_NODES_STMTS}): "
        "the hierarchy is loading lazily again"
    )
    assert_recorded(MEASURED, "portfolio_nodes", stmts)


def test_top_threats_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    stmts = _count(engine, factory, lambda db: assess.top_threats(db, AS_OF))
    assert stmts <= MAX_TOP_THREATS_STMTS, (
        f"top_threats ran {stmts} statements (ceiling {MAX_TOP_THREATS_STMTS}): "
        "the hierarchy is loading lazily again"
    )
    assert_recorded(MEASURED, "top_threats", stmts)


def test_resource_evaluator_batches_its_assignees(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    """``resource.evaluate`` itself, driven directly across every project in one
    session: one task select plus one batched ``Person`` select per project,
    not one ``Person`` select per distinct assignee. The store-wide callers
    above (``portfolio_nodes``, ``top_threats``) exercise the same code
    through their own walks; this pins the evaluator's own cost so a
    regression back to per-assignee ``session.get`` fails here directly,
    independent of whatever else those walks do."""
    engine, factory = seeded

    def call(db: Session) -> None:
        for project in db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)):
            resource.evaluate(db, project, AS_OF)

    stmts = _count(engine, factory, call)
    assert stmts <= MAX_RESOURCE_EVALUATOR_STMTS, (
        f"resource.evaluate ran {stmts} statements across {N_PROJ} projects "
        f"(ceiling {MAX_RESOURCE_EVALUATOR_STMTS}): the per-assignee Person "
        "lookup is querying one at a time again"
    )
    assert_recorded(MEASURED, "resource_evaluator", stmts)


def test_attention_feed_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    stmts = _count(engine, factory, lambda db: feed.attention_feed(db, AS_OF))
    assert stmts <= MAX_ATTENTION_FEED_STMTS, (
        f"attention_feed ran {stmts} statements (ceiling {MAX_ATTENTION_FEED_STMTS}): "
        "the per-project completeness/wizard walk is querying lazily again"
    )
    assert_recorded(MEASURED, "attention_feed", stmts)


def test_home_render_stays_under_the_statement_ceiling(
    home_client: tuple[Engine, TestClient],
) -> None:
    engine, client = home_client
    counter = {"n": 0}

    def _bump(*_: Any) -> None:
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _bump)
    try:
        response = client.get("/")
    finally:
        event.remove(engine, "before_cursor_execute", _bump)
    assert response.status_code == 200
    assert counter["n"] <= MAX_HOME_RENDER_STMTS, (
        f"home render ran {counter['n']} statements (ceiling {MAX_HOME_RENDER_STMTS}): "
        "attention_feed's per-project walk is querying lazily again"
    )
    assert_recorded(MEASURED, "home_render", counter["n"])


def test_process_map_stays_under_the_statement_ceiling(
    project_pages_client: tuple[Engine, TestClient, int],
) -> None:
    engine, client, project_id = project_pages_client
    stmts, status = count_route(engine, client, f"/projects/{project_id}/process-map")
    assert status == 200
    assert stmts <= MAX_PROCESS_MAP_STMTS, (
        f"process_map ran {stmts} statements (ceiling {MAX_PROCESS_MAP_STMTS}): "
        "project_process_states is being re-walked outside the prefetch cache again"
    )
    assert_recorded(MEASURED, "process_map_page", stmts)


def test_project_hub_stays_under_the_statement_ceiling(
    project_pages_client: tuple[Engine, TestClient, int],
) -> None:
    engine, client, project_id = project_pages_client
    stmts, status = count_route(engine, client, f"/projects/{project_id}/hub")
    assert status == 200
    assert stmts <= MAX_PROJECT_HUB_STMTS, (
        f"project_hub ran {stmts} statements (ceiling {MAX_PROJECT_HUB_STMTS}): "
        "area_completeness/state.completeness are re-walking outside the prefetch cache again"
    )
    assert_recorded(MEASURED, "project_hub_page", stmts)


def test_wizard_page_stays_under_the_statement_ceiling(
    project_pages_client: tuple[Engine, TestClient, int],
) -> None:
    engine, client, project_id = project_pages_client
    stmts, status = count_route(engine, client, f"/projects/{project_id}/wizard")
    assert status == 200
    assert stmts <= MAX_WIZARD_STMTS, (
        f"wizard_page ran {stmts} statements (ceiling {MAX_WIZARD_STMTS}): "
        "next_step's per-process scan is querying lazily again"
    )
    assert_recorded(MEASURED, "wizard_page", stmts)


def test_process_map_document_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    with factory() as db:
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()

    def call(db: Session) -> None:
        project = db.get(m.Project, project_id)
        assert project is not None
        process_map.render(db, project, AS_OF)

    stmts = _count(engine, factory, call)
    assert stmts <= MAX_PROCESS_MAP_DOCUMENT_STMTS, (
        f"process_map.render ran {stmts} statements (ceiling {MAX_PROCESS_MAP_DOCUMENT_STMTS}): "
        "project_process_states/completeness are walking outside a prefetch cache again"
    )
    assert_recorded(MEASURED, "process_map_document", stmts)


def test_scope_baseline_document_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    with factory() as db:
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()

    def call(db: Session) -> None:
        project = db.get(m.Project, project_id)
        assert project is not None
        scope_baseline.render(db, project, AS_OF)

    stmts = _count(engine, factory, call)
    assert stmts <= MAX_SCOPE_BASELINE_DOCUMENT_STMTS, (
        f"scope_baseline.render ran {stmts} statements (ceiling {MAX_SCOPE_BASELINE_DOCUMENT_STMTS}): "
        "line.task is loading lazily per baseline line again"
    )
    assert_recorded(MEASURED, "scope_baseline_document", stmts)


@pytest.fixture
def wizard_cli_store(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """The identical N+1 store as ``seeded``, on a throwaway SQLite *file* — the
    wizard CLI opens its own engine per invocation (``wizard.cli._open``), so an
    in-memory URL would hand it an empty database. Mirrors ``home_client``."""
    url = f"sqlite:///{tmp_path / 'driftless_wizard.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate_n1_store(db)
        project_name = db.scalars(select(m.Project.name).order_by(m.Project.name).limit(1)).one()
    yield url, project_name


def test_wizard_status_cli_stays_under_the_statement_ceiling(
    wizard_cli_store: tuple[str, str],
) -> None:
    url, project_name = wizard_cli_store
    counter = {"n": 0}

    def _bump(*_: Any) -> None:
        counter["n"] += 1

    event.listen(Engine, "before_cursor_execute", _bump)
    try:
        rc = cli.main(
            [
                "wizard",
                "status",
                "--project",
                project_name,
                "--as-of",
                AS_OF.isoformat(),
                "--db-url",
                url,
            ]
        )
    finally:
        event.remove(Engine, "before_cursor_execute", _bump)
    assert rc == 0
    assert counter["n"] <= MAX_WIZARD_STATUS_CLI_STMTS, (
        f"wizard status ran {counter['n']} statements (ceiling {MAX_WIZARD_STATUS_CLI_STMTS}): "
        "project_process_states is walking outside a prefetch cache again"
    )
    assert_recorded(MEASURED, "wizard_status_cli", counter["n"])


@pytest.fixture
def pmbok_seeded(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> tuple[Engine, sessionmaker[Session]]:
    """The N+1 store plus process sign-offs (waived / superseded-then-accepted)
    and per-kind artifacts, so the rollup crosses the sign-off ledger and
    several resolver kinds — narrative blank/present, status fresh/stale."""
    _, factory = seeded
    with factory() as db:
        alpha, beta = db.scalars(select(m.Project).order_by(m.Project.name).limit(2)).all()
        risks, comms = catalog.get("11.2"), catalog.get("10.1")
        for project, process, decision in (
            (beta, risks, "waived"),
            (alpha, comms, "rejected"),
            (alpha, comms, "accepted"),  # supersedes the rejection: latest wins
        ):
            db.add(
                m.SignOff(
                    project=project,
                    subject_kind="process",
                    subject_ref=st.process_subject_ref(process, project),
                    decision=decision,
                )
            )
        db.add(m.NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
        db.add(m.NarrativeArtifact(project=beta, kind="assumption_log", body="   "))  # blank
        db.add(m.StatusSnapshot(project=alpha, taken_on=AS_OF))
        db.add(m.StatusSnapshot(project=beta, taken_on=JAN))  # stale by the cadence
        db.add(m.BudgetLine(project=alpha, category="labour", planned_amount=500.0))
        db.commit()
    return seeded


def test_business_process_cells_stays_under_the_statement_ceiling(
    pmbok_seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = pmbok_seeded
    stmts = _count(engine, factory, lambda db: rollup.business_process_cells(db, AS_OF))
    assert stmts <= MAX_BUSINESS_MAP_STMTS, (
        f"business_process_cells ran {stmts} statements (ceiling {MAX_BUSINESS_MAP_STMTS}): "
        "the process map is querying per (project, process) again"
    )
    assert_recorded(MEASURED, "business_process_cells", stmts)


def test_business_process_cells_agree_with_the_per_project_engine(
    pmbok_seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    """The batched rollup must be indistinguishable from driving
    ``state.project_process_states`` project by project — the pre-batch path,
    still what the single-project pages run — so the /process-map render, a
    pure function of these cells, is byte-identical. Roster order and
    repeat-call determinism ride along."""
    _, factory = pmbok_seeded
    with factory() as db:
        by_id = {c.process_id: c for c in rollup.business_process_cells(db, AS_OF)}
        projects = db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)).all()
        for cell in by_id.values():
            assert [pc.project_id for pc in cell.projects] == [p.id for p in projects]
        for project in projects:
            for process, expected in st.project_process_states(project, db, AS_OF):
                states = {pc.project_id: pc.state for pc in by_id[process.id].projects}
                assert states[project.id] is expected, f"{process.id} drifts on {project.name}"
        assert rollup.business_process_cells(db, AS_OF) == tuple(
            by_id[p.id] for p in catalog.PROCESSES
        )


def test_threat_cards_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, factory = seeded
    stmts = _count(engine, factory, lambda db: views.threat_cards(db, AS_OF))
    assert stmts <= MAX_THREAT_CARDS_STMTS, (
        f"threat_cards ran {stmts} statements (ceiling {MAX_THREAT_CARDS_STMTS}): "
        "its own project query is loading the baseline hierarchy lazily again"
    )
    assert_recorded(MEASURED, "threat_cards", stmts)


def _scoped_rows_loaded(projects: int) -> int:
    """ORM rows the hub's scoped ``threat_cards`` reads out of a ``projects``-deep
    store — scoped to the first project by name, which is the same project in
    every such store."""
    _, factory = _in_memory_store(projects)
    with factory() as db:
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()
    return _count_rows_loaded(
        factory, lambda db: views.threat_cards(db, AS_OF, project_id=project_id)
    )


def test_threat_cards_scoped_reads_nothing_for_the_other_projects() -> None:
    """The hub's scoped call costs the same whether the store holds
    ``FEW_PROJECTS`` or ``MANY_PROJECTS``: the projects it is not about cost it
    nothing at all. Measured in ROWS, because statements cannot say this — the
    whole-store path batches, so it is flat on that axis too and now measures
    BELOW the scoped call (see the constants above); a relapse to
    whole-store-then-filter shows up here as ~27 rows per extra project and
    nowhere else."""
    lean = _scoped_rows_loaded(FEW_PROJECTS)
    heavy = _scoped_rows_loaded(MANY_PROJECTS)
    slope = (heavy - lean) / (MANY_PROJECTS - FEW_PROJECTS)
    assert slope <= MAX_SCOPED_ROWS_PER_OTHER_PROJECT, (
        f"threat_cards(project_id=...) loaded {lean} rows over {FEW_PROJECTS} projects and "
        f"{heavy} over {MANY_PROJECTS}: {slope:.1f} per project it was not asked about "
        f"(ceiling {MAX_SCOPED_ROWS_PER_OTHER_PROJECT}) — the hub is reading the whole "
        "store and filtering again"
    )


def test_threat_cards_scoped_stays_under_the_statement_ceiling(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    """The scoped call's own reads stay batched. Its sibling above pins WHICH
    project it reads; this pins that reading it does not go lazy per baseline
    line — a regression the row count cannot see, because it loads the same
    rows either way. Priced at two statements for this one-project walk (58 ->
    60 with the eager options deleted), so the ceiling has to sit at measured
    + 1, not the + 2 its siblings take; see the constant."""
    engine, factory = seeded
    with factory() as db:
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()
    stmts = _count(engine, factory, lambda db: views.threat_cards(db, AS_OF, project_id=project_id))
    assert stmts <= MAX_THREAT_CARDS_SCOPED_STMTS, (
        f"threat_cards(project_id=...) ran {stmts} statements "
        f"(ceiling {MAX_THREAT_CARDS_SCOPED_STMTS}): its one project's walk is "
        "loading the baseline hierarchy lazily again"
    )
    assert_recorded(MEASURED, "threat_cards_scoped", stmts)


def test_threat_cards_scoped_matches_the_whole_store_filtered(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    """Scoping to one project is a cost cut, not a rewrite: it must return
    exactly the whole-store cards for that project, in the same order."""
    _, factory = seeded
    with factory() as db:
        project_id = db.scalars(select(m.Project.id).order_by(m.Project.name).limit(1)).one()
        board = views.threat_cards(db, AS_OF)
        scoped = views.threat_cards(db, AS_OF, project_id=project_id)
    assert scoped == [c for c in board if c["project_id"] == project_id]
    assert scoped, "the seed's overspend gives this project at least one live threat"


def test_every_recorded_baseline_is_re_measured() -> None:
    """A recorded number nothing re-measures is exactly the drift this file was
    fixing: it sits in the module looking authoritative while the code moves
    underneath it. Every ``MEASURED`` key must be handed to ``assert_recorded``
    by one of the ceiling tests above, so adding a baseline without a live count
    fails HERE rather than going stale in silence."""
    source = Path(__file__).read_text(encoding="utf-8")
    unchecked = sorted(k for k in MEASURED if f'assert_recorded(MEASURED, "{k}",' not in source)
    assert not unchecked, f"recorded in MEASURED but never re-measured: {unchecked}"


def test_eager_loading_is_byte_identical(
    seeded: tuple[Engine, sessionmaker[Session]],
) -> None:
    """The eager path returns the same tree and the same threats twice over, and
    ``adapters.prefetched`` — which batches what each evaluator reads across
    every project at once — returns the same assessments as reading one project
    at a time. Both change how many queries run, never which rows come back."""
    _, factory = seeded
    with factory() as db:
        tree = gather.portfolio_nodes(db, AS_OF)
        threats = assess.top_threats(db, AS_OF)
    with factory() as db:
        assert gather.portfolio_nodes(db, AS_OF) == tree
        assert assess.top_threats(db, AS_OF) == threats
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        loose = [assess.assess_project(db, p, AS_OF) for p in projects]
        with adapters.prefetched(db, projects):
            assert [assess.assess_project(db, p, AS_OF) for p in projects] == loose
