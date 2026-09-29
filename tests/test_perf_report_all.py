"""Statement-count guards for the ``driftless report all`` render path.

``cli._render_all`` used to run a bare ``select(Project)`` — no
``adapters.eager_project()`` options, unlike every web route over the same walk —
so ``snapshot_from`` lazy-loaded ``line.task`` once per baseline line, and the
document loop ran outside any prefetch scope, so every per-project evaluator and
process-state read paid its own query set per (document, project). One layer
down, ``process_map.render`` opened ``state.prefetched([project])`` INSIDE the
per-project render, re-running the whole sign-off-ledger scan once per project
even when a store-wide caller already held a scope over every project.

The ceilings here sit at measured + one or two statements — the margin
``test_perf_n1`` documents, never "one per project the call walks", which at four
projects is the price of the per-project defect these name — so a relapse to lazy
loading or per-project scoping fails while an honest extra read does not. A
byte-equality guard rides along: the scoped batch render must write exactly the
bytes each document renders on its own, scope-free — the scopes may change how
many statements run, never which bytes land. The ``auto_reload`` pins cover the
same finding's tail: both Jinja environments render packaged templates that
change only with a deploy, so neither may re-stat template files per render.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import models as m
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import state
from driftless.report import cli
from driftless.report import engine as report_engine
from driftless.report import receipt as report_receipt
from driftless.report.documents import process_map
from driftless.web.templating import TEMPLATES
from test_perf_n1 import assert_recorded

AS_OF = date(2026, 6, 30)
JAN = date(2026, 1, 1)
TASKS_PER = 5  # the finding's shape: enough baseline lines for a lazy walk to dominate
FEW_PROJECTS, MANY_PROJECTS = 2, 4

# Measured on this seed AFTER the eager options + one adapters.prefetched /
# state.prefetched pair around the document loop (the pre-fix path measures 174
# at 2 projects and 316 at 4 — one lazy ``line.task`` load per baseline line
# plus a per-project query set per document). Every ceiling is DERIVED from its
# recorded measurement here and re-measured on every run by ``assert_recorded``,
# shared with ``test_perf_n1`` — one drift guard, not three that drift apart —
# so a read that moves is reported rather than eating the margin. Both counts
# just moved DOWN, 107 -> 98 and 151 -> 132, when the sign-off prefetch stopped
# being scoped per project on this path; the guard reported that too.
# Deleting JUST the eager options, keeping both scopes, costs 108 and 156, and
# re-opening the nested scope 116 and 182 — all re-priced here, not restated.
# Both counts moved UP by 2 (98 -> 100, 132 -> 134) when the risk evaluator's
# "no response planned" rule and the risk-register document both started
# reading ``RiskResponse`` (``pmbok.mapping.rows_for``): ONE query for the
# outer ``state.prefetched`` scope the whole loop opens, and a SECOND for
# ``report.gather.business_nodes``'s own nested ``adapters.prefetched`` (which
# nests a fresh ``mapping.prefetched`` of its own around its per-leaf
# ``assess_project`` calls) — flat regardless of project count, never a
# per-project cost, which is what the ceiling above still catches.
# Both counts moved UP by 3 again (100 -> 103, 134 -> 137), and
# ``process_map_under_scope`` by 3 (17 -> 20), when the scope resolvers started
# reading ``Requirement``/``Deliverable``/``RequirementTrace``/``AcceptanceRecord``
# for completeness: each is one honest batched query through
# ``mapping.rows_for``/``mapping._grouped``, flat regardless of project count —
# never a per-project cost, which is what every ceiling here still catches.
# All three moved UP by 1 again (108 -> 109, 142 -> 143, 25 -> 26) when
# ``lessons_learned_register`` started resolving off ``LessonLearned`` — one
# batched query of its own per whole-store walk, flat regardless of project count.
# Both render_all counts moved UP by 2 again (109 -> 111, 143 -> 145): schedule.evaluate()
# now reads TaskDependency too, batched via adapters.project_grouped, paid once by the
# outer state.prefetched loop and once more by business_nodes's own nested
# adapters.prefetched -- flat regardless of project count, same shape as the
# RiskResponse bump above.
# All three moved UP by 1 again (111 -> 112, 145 -> 146, 26 -> 27) when
# ``project_calendars`` gained a resolver: one honest ``mapping.rows_for`` query
# over ``ProjectCalendar``, batched through the same ``_grouped`` cache every
# other resolver here already rides, flat regardless of project count.
# ``schedule_data`` and ``project_schedule_network_diagram`` gained resolvers
# too, but both read off ``_dependency_edges``, the same batched TaskDependency
# read the schedule.evaluate() bump above already paid for — no further cost.
MEASURED = {"render_all_few": 112, "render_all_many": 146, "process_map_under_scope": 27}
MAX_RENDER_ALL_FEW_STMTS = MEASURED["render_all_few"] + 2
MAX_RENDER_ALL_MANY_STMTS = MEASURED["render_all_many"] + 2

# ``process_map.render`` for every project inside ONE open ``state.prefetched``
# scope: the ledger scan and the per-model resolver reads run once for the
# store, not once per project. Recorded below for 4 projects once the render
# rides the open scope; re-opening the nested per-project scope costs 66.
MAX_PROCESS_MAP_UNDER_SCOPE_STMTS = MEASURED["process_map_under_scope"] + 2


def _populate(db: Session, projects: int) -> None:
    """A predictive store whose every project exercises each document: an approved
    baseline of ``TASKS_PER`` lines (the EVM walk), a milestone with a baseline
    date (charter/schedule/forecast), a cost entry, a risk, and one department
    with a person (the business-scoped department roll-up)."""
    business = m.Business(name="BRC")
    dept = m.Department(name="Delivery", business=business)
    dept.people.append(m.Person(name="Sam", role="editor", cost_rate=90.0))
    portfolio = m.Portfolio(name="Content Brands", business=business)
    for j in range(projects):
        proj = m.Project(
            name=f"Project {j:03d}",
            portfolio=portfolio,
            delivery_mode="predictive",
            responsible_department=dept,
        )
        ws = m.Workstream(name=f"WS{j}", project=proj)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        for t in range(TASKS_PER):
            task = m.Task(
                name=f"T{j}.{t}",
                workstream=ws,
                estimate_unit="hours",
                percent_complete=(t * 20) % 100,
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
        db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=300.0))
        db.add(
            m.Risk(
                project=proj,
                description=f"risk {j}",
                probability=0.5,
                impact=30000.0,
                status="open",
            )
        )
        db.add(
            m.Milestone(
                project=proj,
                name=f"M{j}",
                target_date=AS_OF,
                baseline_date=JAN,
                status="at_risk",
            )
        )
    db.commit()


def _store(projects: int) -> tuple[Engine, sessionmaker[Session]]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate(db, projects)
    return engine, factory


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


def _render_all_statements(projects: int, out: Path) -> int:
    engine, factory = _store(projects)
    return _count(engine, factory, lambda db: cli._render_all(db, out, AS_OF))


def test_render_all_stays_under_the_statement_ceiling(tmp_path: Path) -> None:
    stmts = _render_all_statements(MANY_PROJECTS, tmp_path)
    assert stmts <= MAX_RENDER_ALL_MANY_STMTS, (
        f"_render_all ran {stmts} statements over {MANY_PROJECTS} projects "
        f"(ceiling {MAX_RENDER_ALL_MANY_STMTS}): the project query lost its eager "
        "options or the document loop is running outside the prefetch scopes again"
    )
    assert_recorded(MEASURED, "render_all_many", stmts)


def test_render_all_stays_under_the_statement_ceiling_on_a_small_store(tmp_path: Path) -> None:
    """The second size pins the growth: with the walk batched, two more projects
    cost the documents' own per-project reads, not a per-baseline-line cascade."""
    stmts = _render_all_statements(FEW_PROJECTS, tmp_path)
    assert stmts <= MAX_RENDER_ALL_FEW_STMTS, (
        f"_render_all ran {stmts} statements over {FEW_PROJECTS} projects "
        f"(ceiling {MAX_RENDER_ALL_FEW_STMTS}): the project query lost its eager "
        "options or the document loop is running outside the prefetch scopes again"
    )
    assert_recorded(MEASURED, "render_all_few", stmts)


def test_render_all_writes_the_same_bytes_as_unscoped_single_renders(tmp_path: Path) -> None:
    """The scopes are a cost cut, not a rewrite: every file the batched loop wrote
    is byte-identical to the same document rendered alone on a fresh, scope-free
    session — the path the web's ``render_document`` callers and every per-document
    test still run."""
    _, factory = _store(MANY_PROJECTS)
    with factory() as db:
        written = cli._render_all(db, tmp_path, AS_OF)
    assert written  # something rendered on this seed

    root = tmp_path / AS_OF.isoformat()
    with factory() as db:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        for module in report_engine.iter_documents():
            slug = module.SLUG
            if getattr(module, "SCOPE", "project") == "business":
                path = root / f"{slug}.md"
                expected = report_receipt.attach_markdown_receipt(module.render(db, AS_OF), AS_OF)
                assert path.read_text(encoding="utf-8") == expected, slug
            else:
                for project in projects:
                    path = root / cli._slugify(project.name) / f"{slug}.md"
                    single = module.render(db, project, AS_OF)
                    expected = report_receipt.attach_markdown_receipt(single, AS_OF)
                    assert path.read_text(encoding="utf-8") == expected, (slug, project.name)


def test_process_map_render_rides_an_open_prefetch_scope() -> None:
    """Inside one store-wide ``state.prefetched`` scope, rendering the map for
    every project must not re-open the nested per-project scope — that re-runs
    the whole sign-off-ledger scan and the per-model resolver reads once per
    project, which is exactly the cost the outer scope exists to remove."""
    engine, factory = _store(MANY_PROJECTS)

    def call(db: Session) -> None:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        with state.prefetched(db, projects):
            for project in projects:
                process_map.render(db, project, AS_OF)

    stmts = _count(engine, factory, call)
    assert stmts <= MAX_PROCESS_MAP_UNDER_SCOPE_STMTS, (
        f"process_map.render ran {stmts} statements over {MANY_PROJECTS} projects inside "
        f"one open scope (ceiling {MAX_PROCESS_MAP_UNDER_SCOPE_STMTS}): the render is "
        "re-scanning the ledger once per project again"
    )
    assert_recorded(MEASURED, "process_map_under_scope", stmts)


def test_every_recorded_baseline_is_re_measured() -> None:
    """A recorded number nothing re-measures goes stale in silence — the drift
    ``test_perf_n1`` was carrying in six of its own before this guard existed."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert not [k for k in MEASURED if f'assert_recorded(MEASURED, "{k}",' not in source]


def test_the_report_environment_does_not_reload_templates() -> None:
    """Packaged templates change only with a deploy: a warm render must not pay
    an ``os.stat`` per template checking for edits that cannot happen."""
    assert report_engine._ENV.auto_reload is False


def test_the_web_environment_does_not_reload_templates() -> None:
    assert TEMPLATES.env.auto_reload is False
