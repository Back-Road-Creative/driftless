"""Artifact ↔ live-store mapping: which PMBOK outputs actually exist for a project.

The catalog (``driftless.pmbok.catalog``) says what a process *should* produce, in the
closed ``ARTIFACT_KINDS`` vocabulary. This module answers, for a real project and an
explicit as-of date, whether each kind actually exists in the store and how healthy it
is — the input the process-state engine and the wizard both read. Only the kinds the
store can answer for have a resolver — most reading rows somebody wrote, some derived
on read from the inputs those rows already carry; the rest answer ``present=False,
detail="not tracked"`` rather than pretending to know. No resolver reads a wall clock,
and each honours as-of wherever its rows store a date (``approved_at``, ``raised_on``,
``updated_on``): a row dated after as-of does not exist yet, and an undated row (a
wizard-filed narrative, a budget line) still counts — reproducible, never the future.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, TypeVar, cast

from sqlalchemy import ScalarResult, select, union_all
from sqlalchemy.orm import Session, selectinload

from driftless.models import (
    AcceptanceRecord,
    Acquisition,
    Baseline,
    BudgetLine,
    ChangeRequest,
    CostEntry,
    Deliverable,
    Issue,
    LessonLearned,
    Milestone,
    NarrativeArtifact,
    ProcurementAgreement,
    Project,
    ProjectCalendar,
    QualityMeasurement,
    Requirement,
    RequirementTrace,
    ResourceBreakdown,
    ResourceType,
    ResponsibilityAssignment,
    Risk,
    Sprint,
    Stakeholder,
    StatusSnapshot,
    Task,
    TaskDependency,
    TeamAssessment,
    Workstream,
)

#: A status report older than this many days (relative to as-of) is stale.
STATUS_CADENCE_DAYS = 14
#: A quality measurement older than this is treated as stale evidence.
QUALITY_RECENCY_DAYS = 30


@dataclass(frozen=True)
class ArtifactStatus:
    """Whether a PMBOK artifact kind exists for a project, and how healthy it is.

    ``present`` — the artifact has been produced at all. ``healthy`` — it is
    present *and* in good standing (fresh, approved, in tolerance). ``detail`` is
    a short human-readable reason, byte-stable for a given store and as-of.
    """

    kind: str
    present: bool
    healthy: bool
    detail: str


Resolver = Callable[[Project, Session, date], ArtifactStatus]


class _ProjectScoped(Protocol):
    """A mapped row a resolver reads: one integer pk, owned by one project."""

    id: Any
    project_id: Any


_M = TypeVar("_M", bound=_ProjectScoped)

_PREFETCH_KEY = "driftless.pmbok.mapping.prefetch"
#: The open scope: covered project ids, plus per-read row groups :func:`_grouped` fills lazily.
_PrefetchScope = tuple[list[int], dict[Any, dict[int, list[Any]]]]
_Load = Callable[[Sequence[int]], Iterable[tuple[int, Any]]]  # scope ids -> (project_id, row)


@contextmanager
def prefetched(session: Session, projects: Sequence[Project]) -> Iterator[None]:
    """Batch every resolver's per-project read across ``projects`` while active.

    Inside this scope :func:`_grouped` loads a read's rows for EVERY project in one
    IN-query (id order, the same order the per-project SELECTs return) the first
    time any project asks, and serves the rest from memory — lazily, so there is
    no registry of reads to keep in step and a scope opened for one cheap read
    pays for that read alone. Per-project semantics are identical; a project the
    scope was NOT opened for raises, since ``[]`` would read "nothing to assess"
    and grade it green. The previous scope is saved and restored, so nesting
    (``state``, ``assess.adapters``) narrows the cache for the inner block only.
    """
    outer: _PrefetchScope | None = session.info.get(_PREFETCH_KEY)
    session.info[_PREFETCH_KEY] = ([project.id for project in projects], {})
    try:
        yield
    finally:
        if outer is None:
            session.info.pop(_PREFETCH_KEY, None)
        else:
            session.info[_PREFETCH_KEY] = outer


def _grouped(session: Session, key: Any, load: _Load, project_id: int) -> list[Any]:
    """One project's rows from ``load`` — batched across the whole ``prefetched`` scope
    when one is open, else run for this project alone.

    ``key`` names the read in the scope's cache, and rows group by the ``project_id``
    ``load`` yields beside each one — so a read whose rows carry no ``project_id``
    column of their own (:func:`_tasks` hangs off ``Workstream``) batches through this
    same cache rather than a second one that could drift from it.
    """
    scope: _PrefetchScope | None = session.info.get(_PREFETCH_KEY)
    if scope is None:
        return [row for _, row in load([project_id])]
    ids, cache = scope
    if key not in cache:
        grouped: dict[int, list[Any]] = {pid: [] for pid in ids}
        for pid, row in load(ids):
            grouped[pid].append(row)
        cache[key] = grouped
    if project_id not in cache[key]:  # fail closed — out of scope is a bug, not "no rows"
        raise LookupError(f"project {project_id} is outside the open prefetched scope")
    return list(cache[key][project_id])


def rows_for(session: Session, model: type[_M], project_id: int) -> list[_M]:
    """``model``'s rows for one project — batched across the whole ``prefetched``
    scope when one is open, else the single per-project SELECT, id order.

    Public: this is the one batched, ``prefetched``-aware read every resolver in
    this module uses, and ``driftless.pmbok.crosswalk``'s agile-evidence resolvers
    read through it too, so an agile project's page pays for one query per model
    exactly as a predictive project's does. A leading underscore would mark it
    "mine, do not import" — the opposite of what a second module reading through
    it needs (``tests/test_package.py``'s no-private-cross-import rule). A caller
    outside this module (e.g. ``RiskResponse``'s readers) also wants THIS scope
    rather than ``assess.adapters``'s: :func:`prefetched` saves and restores the
    outer scope across nesting, so a read batched through here survives a NESTED
    ``assess.adapters.prefetched``, whose context manager pops its whole scope
    unconditionally on exit.
    """
    table: Any = model

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = select(table).where(table.project_id.in_(ids)).order_by(table.id)
        if model is Baseline:
            stmt = stmt.options(selectinload(Baseline.lines))  # judged via ``.lines``
        rows: ScalarResult[Any] = session.scalars(stmt)
        return ((row.project_id, row) for row in rows)

    rows: list[_M] = _grouped(session, model, load, project_id)
    return rows


_ANY_ROWS_KEY = "driftless.pmbok.mapping.any_rows_for"


def any_rows_for(session: Session, models: Sequence[type[_ProjectScoped]], project_id: int) -> bool:
    """Whether ANY of ``models`` has a row for ``project_id`` — ONE ``UNION ALL``
    statement, batched across the whole open ``prefetched`` scope and cached
    exactly like :func:`rows_for`, so "does this project have any evidence across
    a family of tables" (``driftless.pmbok.crosswalk``'s agile-evidence gate)
    costs one query total across a whole store walk, never one query per model
    per project — and nothing at all for a project a caller has already ruled
    out some cheaper way (``crosswalk.has_evidence`` checks ``delivery_mode``
    first, in memory, before ever calling this). Public for the same reason
    :func:`rows_for` is: a second module reads through it.
    """
    key = (_ANY_ROWS_KEY, tuple(models))

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        selects = [
            select(cast(Any, model).project_id).where(cast(Any, model).project_id.in_(ids))
            for model in models
        ]
        stmt = union_all(*selects) if len(selects) > 1 else selects[0]
        hits = {row[0] for row in session.execute(stmt)}
        return ((pid, pid) for pid in hits)

    return bool(_grouped(session, key, load, project_id))


def _tasks(session: Session, project_id: int) -> list[Task]:
    """One project's tasks — the activity register the two derived kinds below read.

    ``Task`` carries ``workstream_id``, not ``project_id``, so it cannot go through
    :func:`rows_for`: the batch joins ``Workstream`` and groups on ITS ``project_id``.
    Neither table stores a date, so there is no as-of filter to apply here and none
    missing — a task is an undated row and counts at every as-of, the rule the module
    docstring states for a wizard-filed narrative or a budget line.
    """

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = (
            select(Workstream.project_id, Task)
            .join(Task, Task.workstream_id == Workstream.id)
            .where(Workstream.project_id.in_(ids))
            .order_by(Task.id)
        )
        return ((pid, task) for pid, task in session.execute(stmt))

    tasks: list[Task] = _grouped(session, _tasks, load, project_id)
    return tasks


def _requirement_traces(session: Session, project_id: int) -> list[RequirementTrace]:
    """One project's traceability lines — the same "join, then group on the
    OTHER side's project_id" shape :func:`_tasks` already uses, since
    ``RequirementTrace`` carries no ``project_id`` column of its own."""

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = (
            select(Requirement.project_id, RequirementTrace)
            .join(RequirementTrace, RequirementTrace.requirement_id == Requirement.id)
            .where(Requirement.project_id.in_(ids))
            .order_by(RequirementTrace.id)
        )
        return ((pid, trace) for pid, trace in session.execute(stmt))

    traces: list[RequirementTrace] = _grouped(session, _requirement_traces, load, project_id)
    return traces


def _acceptance_records(session: Session, project_id: int) -> list[AcceptanceRecord]:
    """One project's acceptance ledger entries — joined through ``Deliverable``,
    the same shape :func:`_requirement_traces` uses through ``Requirement``."""

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = (
            select(Deliverable.project_id, AcceptanceRecord)
            .join(AcceptanceRecord, AcceptanceRecord.deliverable_id == Deliverable.id)
            .where(Deliverable.project_id.in_(ids))
            .order_by(AcceptanceRecord.id)
        )
        return ((pid, record) for pid, record in session.execute(stmt))

    records: list[AcceptanceRecord] = _grouped(session, _acceptance_records, load, project_id)
    return records


def _approved_baseline(project: Project, session: Session, as_of: date) -> Baseline | None:
    """``adapters.plan_baseline``'s rule, over ``rows_for``'s batch read, not ``project.baselines``."""
    rows = [b for b in rows_for(session, Baseline, project.id) if b.status == "approved"]
    rows = [b for b in rows if b.approved_at is None or b.approved_at.date() <= as_of]
    return max(rows, key=lambda baseline: baseline.version) if rows else None


def _scope_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """An approved baseline AND a WBS — the scope baseline is the plan's cost/schedule
    figures AND the decomposition that produced them, never one alone."""
    baseline = _approved_baseline(project, session, as_of)
    if baseline is None:
        return ArtifactStatus("scope_baseline", False, False, "no approved baseline")
    nodes = rows_for(session, Deliverable, project.id)
    healthy = bool(baseline.lines) and bool(nodes)
    detail = f"approved baseline v{baseline.version}, {len(nodes)} WBS node(s)"
    if not healthy:
        detail += " (no lines)" if not baseline.lines else " (no WBS)"
    return ArtifactStatus("scope_baseline", True, healthy, detail)


def _work_breakdown_structure(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    kind = "work_breakdown_structure"
    nodes = rows_for(session, Deliverable, project.id)
    present = bool(nodes)
    return ArtifactStatus(kind, present, present, f"{len(nodes)} WBS node(s)")


def _requirements_traceability_matrix(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    kind = "requirements_traceability_matrix"
    requirements = rows_for(session, Requirement, project.id)
    if not requirements:
        return ArtifactStatus(kind, False, False, "no requirements filed")
    traces = _requirement_traces(session, project.id)
    traced_ids = {trace.requirement_id for trace in traces}
    untraced = [r for r in requirements if r.id not in traced_ids]
    healthy = not untraced
    detail = f"{len(traces)} trace(s) over {len(requirements)} requirement(s)"
    if untraced:
        detail += f" ({len(untraced)} untraced)"
    return ArtifactStatus(kind, True, healthy, detail)


def _verified_deliverables(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    kind = "verified_deliverables"
    records = [
        r
        for r in _acceptance_records(session, project.id)
        if r.verified_on is not None and r.verified_on <= as_of
    ]
    verified_ids = {r.deliverable_id for r in records}
    present = bool(verified_ids)
    return ArtifactStatus(kind, present, present, f"{len(verified_ids)} deliverable(s) verified")


def _accepted_deliverables(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    kind = "accepted_deliverables"
    records = [
        r
        for r in _acceptance_records(session, project.id)
        if r.accepted_on is not None and r.accepted_on <= as_of
    ]
    accepted_ids = {r.deliverable_id for r in records}
    present = bool(accepted_ids)
    return ArtifactStatus(kind, present, present, f"{len(accepted_ids)} deliverable(s) accepted")


def _requirements_documentation(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Native rows first — filed ``Requirement``s ARE the documentation; a project
    with none falls back to the stored prose kind (``_narrative``'s crosswalk),
    since a PM may have written the document before any row was ever filed."""
    kind = "requirements_documentation"
    requirements = rows_for(session, Requirement, project.id)
    if requirements:
        return ArtifactStatus(kind, True, True, f"{len(requirements)} requirement(s) filed")
    return _narrative(kind, kind)(project, session, as_of)


def _resource_management_plan(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Native rows first — filed ``ResourceType`` catalog entries ARE the plan's own
    input; a project with none falls back to the stored prose kind (``_narrative``'s
    crosswalk), the same "rows, else prose" order :func:`_requirements_documentation`
    already uses."""
    kind = "resource_management_plan"
    types = rows_for(session, ResourceType, project.id)
    if types:
        return ArtifactStatus(kind, True, True, f"{len(types)} resource type(s) catalogued")
    return _narrative(kind, kind)(project, session, as_of)


def _resource_breakdown_structure(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    kind = "resource_breakdown_structure"
    nodes = rows_for(session, ResourceBreakdown, project.id)
    present = bool(nodes)
    return ArtifactStatus(kind, present, present, f"{len(nodes)} RBS node(s)")


def _team_charter(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Native rows first — filed ``ResponsibilityAssignment`` rows (the RACI) are
    ground rules the team has actually agreed to; a project with none falls back to
    the stored prose kind, the same order :func:`_requirements_documentation` uses.
    Healthy once at least one row names an accountable owner — a charter with
    nobody accountable is not one."""
    kind = "team_charter"
    assignments = rows_for(session, ResponsibilityAssignment, project.id)
    if assignments:
        healthy = any(a.role == "accountable" for a in assignments)
        detail = f"{len(assignments)} RACI assignment(s)"
        return ArtifactStatus(kind, True, healthy, detail)
    return _narrative(kind, kind)(project, session, as_of)


def _team_performance_assessments(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    """Native rows first — filed, dated ``TeamAssessment`` readings; a project with
    none falls back to the stored prose kind. Healthy while the latest dimension
    scored is at or above a passing mark, the same fresh/pass shape
    :func:`_quality_report` reads off its own latest row."""
    kind = "team_performance_assessments"
    assessments = [
        a for a in rows_for(session, TeamAssessment, project.id) if a.assessed_on <= as_of
    ]
    if assessments:
        latest = max(assessments, key=lambda a: (a.assessed_on, a.id))
        healthy = latest.score >= 70
        detail = f"latest {latest.assessed_on.isoformat()}: {latest.dimension} {latest.score:g}"
        return ArtifactStatus(kind, True, healthy, detail)
    return _narrative(kind, kind)(project, session, as_of)


def _physical_acquisitions(session: Session, project_id: int) -> list[Acquisition]:
    """One project's acquisitions of a non-``people`` resource type — joined
    through ``ResourceType``, the same shape :func:`_acceptance_records` joins
    through ``Deliverable``, since ``Acquisition`` carries no resource KIND of
    its own to filter on."""

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = (
            select(Acquisition.project_id, Acquisition)
            .join(ResourceType, Acquisition.resource_type_id == ResourceType.id)
            .where(Acquisition.project_id.in_(ids), ResourceType.kind != "people")
            .order_by(Acquisition.id)
        )
        return ((pid, acquisition) for pid, acquisition in session.execute(stmt))

    rows: list[Acquisition] = _grouped(session, _physical_acquisitions, load, project_id)
    return rows


def _physical_resource_assignments(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    """Equipment and material acquisitions, not people — the resource kind the
    project team assignments resolver never sees, since ``Task.assignee_id`` is
    a person only."""
    kind = "physical_resource_assignments"
    acquisitions = [
        a for a in _physical_acquisitions(session, project.id) if a.requested_on <= as_of
    ]
    if not acquisitions:
        return ArtifactStatus(kind, False, False, "no physical resource acquired")
    fulfilled = sum(1 for a in acquisitions if a.status == "fulfilled")
    detail = f"{fulfilled} of {len(acquisitions)} physical resource(s) fulfilled"
    return ArtifactStatus(kind, True, fulfilled == len(acquisitions), detail)


def _schedule_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    baseline = _approved_baseline(project, session, as_of)
    if baseline is None or not baseline.lines:
        return ArtifactStatus("schedule_baseline", False, False, "no baselined schedule")
    windowed = all(line.planned_start <= line.planned_finish for line in baseline.lines)
    return ArtifactStatus("schedule_baseline", True, windowed, f"v{baseline.version}")


def _cost_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    lines = rows_for(session, BudgetLine, project.id)
    if not lines:
        return ArtifactStatus("cost_baseline", False, False, "no budget lines")
    total = sum(line.planned_amount for line in lines)
    healthy = total > 0
    return ArtifactStatus("cost_baseline", True, healthy, f"{len(lines)} budget line(s)")


def _project_schedule(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    milestones = rows_for(session, Milestone, project.id)
    sprints = rows_for(session, Sprint, project.id)
    present = bool(milestones or sprints)
    detail = f"{len(milestones)} milestone(s), {len(sprints)} sprint(s)"
    return ArtifactStatus("project_schedule", present, present, detail)


def _activity_attributes(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The scheduled activities and the attributes that make them schedulable.

    A task IS the activity — name, status, estimate and unit, actual effort, percent
    complete and assignee are exactly PMBOK's activity attributes — so presence is
    "this project has tasks at all". Health is the estimate, not a tick: an activity
    nobody has sized cannot be sequenced, weighed against capacity or measured against
    a plan, so it is a name rather than an activity, and a half-sized register reads
    present-and-unhealthy with the shortfall counted in the detail.
    """
    tasks = _tasks(session, project.id)
    if not tasks:
        return ArtifactStatus("activity_attributes", False, False, "no activities")
    unsized = sum(1 for task in tasks if task.estimate is None)
    detail = f"{len(tasks)} activity(ies)" + (f" ({unsized} unestimated)" if unsized else "")
    return ArtifactStatus("activity_attributes", True, not unsized, detail)


def _dependency_edges(session: Session, project_id: int) -> list[TaskDependency]:
    """One project's ``TaskDependency`` rows — the project-scoped, batched read
    :func:`_project_schedule_network_diagram` and :func:`_schedule_data` both
    need, shared so the join stays written once.

    Grouped, like :func:`_tasks`, on the OTHER side's ``project_id``: a
    dependency carries neither a ``project_id`` column of its own nor even a
    direct FK to ``Workstream``, so this joins through the predecessor task's
    workstream. The successor is never checked separately — a cross-project
    edge is refused at the write boundary
    (``driftless.services.schedule_writes``), so any edge landing here via its
    predecessor's project is, by construction, wholly that project's own.
    """

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = (
            select(Workstream.project_id, TaskDependency)
            .select_from(TaskDependency)
            .join(Task, Task.id == TaskDependency.predecessor_task_id)
            .join(Workstream, Workstream.id == Task.workstream_id)
            .where(Workstream.project_id.in_(ids))
            .order_by(TaskDependency.id)
        )
        return ((pid, dep) for pid, dep in session.execute(stmt))

    deps: list[TaskDependency] = _grouped(session, _dependency_edges, load, project_id)
    return deps


def _project_schedule_network_diagram(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    """The typed precedence edges between this project's own tasks: PMBOK's activity
    network. Present once one ``TaskDependency`` links two tasks under this project's
    own workstreams — the edge IS the network entry; a register of unlinked activities
    is a list, not yet a diagram. Healthy is the same as present: a self-loop is a
    CHECK constraint no row can carry, and a cross-project edge or a cycle is refused
    at the write boundary (``driftless.services.schedule_writes``), so any edge that
    made it into the store is already a valid one.
    """
    tasks = _tasks(session, project.id)
    if not tasks:
        return ArtifactStatus("project_schedule_network_diagram", False, False, "no activities")
    deps = _dependency_edges(session, project.id)
    present = bool(deps)
    detail = f"{len(deps)} dependency edge(s)" if present else "no dependency edges"
    return ArtifactStatus("project_schedule_network_diagram", present, present, detail)


def _schedule_data(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The activity list's dates and the edges between them, read together: PMBOK's
    own definition of the working schedule file, not the baseline that freezes it.

    Present only once BOTH halves exist — an approved baseline giving at least one
    task a dated window (the same ``BaselineLine`` rows :func:`_schedule_baseline`
    reads) AND at least one ``TaskDependency`` linking two of this project's own
    tasks (the same edges :func:`_project_schedule_network_diagram` reads). Dates
    with no edges are a date list; edges with no dates are a diagram nobody has
    timed — neither alone is schedule data, and this is the smallest honest
    reading that needs both without asking for a third row of its own.
    """
    kind = "schedule_data"
    baseline = _approved_baseline(project, session, as_of)
    lines = baseline.lines if baseline else []
    deps = _dependency_edges(session, project.id)
    present = bool(lines) and bool(deps)
    detail = f"{len(lines)} dated line(s), {len(deps)} dependency edge(s)"
    return ArtifactStatus(kind, present, present, detail)


def _project_calendars(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """A project's working-day pattern: present once one ``ProjectCalendar`` row
    (``driftless/models/schedule.py``) exists for the project — the row itself IS
    the calendar, so presence is exactly having filed one. Undated, like a task:
    counts at every as-of."""
    kind = "project_calendars"
    calendars = rows_for(session, ProjectCalendar, project.id)
    present = bool(calendars)
    return ArtifactStatus(kind, present, present, f"{len(calendars)} calendar(s)")


def _project_team_assignments(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Who is doing the work: ``Task.assignee_id`` IS the assignment record.

    Present once one task names somebody — that is the first assignment made, and the
    store keeps no separate roster to wait for. Healthy only when nobody is unowned:
    an unassigned task is work no person has accepted, which is the gap Acquire
    Resources exists to close, so the detail names the shortfall rather than a tick.
    """
    tasks = _tasks(session, project.id)
    owned = sum(1 for task in tasks if task.assignee_id is not None)
    if not owned:
        return ArtifactStatus("project_team_assignments", False, False, "nobody assigned")
    detail = f"{owned} of {len(tasks)} task(s) assigned"
    return ArtifactStatus("project_team_assignments", True, owned == len(tasks), detail)


def _milestone_list(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    milestones = rows_for(session, Milestone, project.id)
    present = bool(milestones)
    slipped = any(m.status == "missed" for m in milestones)
    return ArtifactStatus(
        "milestone_list", present, present and not slipped, f"{len(milestones)} milestone(s)"
    )


def _risk_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    risks = rows_for(session, Risk, project.id)
    present = bool(risks)
    open_realised = any(r.status == "realised" for r in risks)
    return ArtifactStatus(
        "risk_register", present, present and not open_realised, f"{len(risks)} risk(s)"
    )


def _issue_log(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    issues = [i for i in rows_for(session, Issue, project.id) if i.raised_on <= as_of]
    present = bool(issues)
    unresolved = sum(1 for i in issues if i.status in ("open", "in_progress"))
    return ArtifactStatus(
        "issue_log", present, present and unresolved == 0, f"{len(issues)} issue(s)"
    )


def _change_log(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    changes = [c for c in rows_for(session, ChangeRequest, project.id) if c.raised_on <= as_of]
    present = bool(changes)
    return ArtifactStatus("change_log", present, present, f"{len(changes)} change request(s)")


def _change_requests(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The raw request list: the same dated ``ChangeRequest`` rows :func:`_change_log`
    already reads, under the catalog's own kind name for the list itself."""
    changes = [c for c in rows_for(session, ChangeRequest, project.id) if c.raised_on <= as_of]
    present = bool(changes)
    return ArtifactStatus("change_requests", present, present, f"{len(changes)} change request(s)")


def _risk_report(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The register plus derived exposure: the same ``Risk`` rows :func:`_risk_register`
    already reads, with a probability-weighted exposure total computed on read — never
    stored. Not the Monte Carlo simulation (``driftless.calc.risk.simulate_exposure``),
    which nothing in the risk area wires up; this is the plain sum every ``Risk`` row
    already carries the inputs for."""
    risks = rows_for(session, Risk, project.id)
    present = bool(risks)
    open_realised = any(r.status == "realised" for r in risks)
    exposure = sum(r.probability * r.impact for r in risks)
    detail = f"{len(risks)} risk(s), exposure {exposure:.2f}"
    return ArtifactStatus("risk_report", present, present and not open_realised, detail)


def _stakeholder_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    holders = rows_for(session, Stakeholder, project.id)
    present = bool(holders)
    return ArtifactStatus(
        "stakeholder_register", present, present, f"{len(holders)} stakeholder(s)"
    )


def _reported_status(kind: str) -> Resolver:
    """Presence and freshness of the status-snapshot series, answered under ``kind``.

    Two keys share this one behaviour, so the names cannot drift apart: ``status_report``,
    the record the Communications evaluator and the wizard reach directly, and
    ``work_performance_reports``, the catalog's own name for that periodic report.
    """

    def resolve(project: Project, session: Session, as_of: date) -> ArtifactStatus:
        # Two snapshots may now share a date (the correction path — see
        # docs/temporal-model.md), so ``max()`` on ``taken_on`` alone no longer picks a
        # single row. What this reads off ``latest`` is its DATE, which every same-date
        # candidate agrees on, so the answer is unaffected either way — but the tiebreak is
        # spelled out rather than left to whichever row ``max`` happened to see first,
        # because a later reader adding a field here would otherwise inherit a silent
        # arbitrary choice.
        snaps = [s for s in rows_for(session, StatusSnapshot, project.id) if s.taken_on <= as_of]
        if not snaps:
            return ArtifactStatus(kind, False, False, "no status snapshot")
        latest = max(snaps, key=lambda snap: (snap.taken_on, snap.id))
        fresh = (as_of - latest.taken_on) <= timedelta(days=STATUS_CADENCE_DAYS)
        detail = f"latest {latest.taken_on.isoformat()}" + ("" if fresh else " (stale)")
        return ArtifactStatus(kind, True, fresh, detail)

    return resolve


def _project_communications(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Communications actually made — the NOTE a status snapshot carries, not the number.

    Reads :func:`_reported_status`'s table and judges the column it ignores: ``note`` is
    nullable, so a snapshot without one is a figure filed and nobody was told anything. Present
    once a note exists at or before as-of; healthy only while the newest NOTED snapshot is inside
    ``STATUS_CADENCE_DAYS`` — communicating once then going quiet is not managing communications.
    """
    kind = "project_communications"
    snaps = [s for s in rows_for(session, StatusSnapshot, project.id) if s.taken_on <= as_of]
    noted = [s for s in snaps if (s.note or "").strip()]
    if not noted:
        return ArtifactStatus(kind, False, False, "no noted status snapshot")
    latest = max(noted, key=lambda snap: snap.taken_on)
    fresh = (as_of - latest.taken_on) <= timedelta(days=STATUS_CADENCE_DAYS)
    detail = f"{len(noted)} of {len(snaps)} snapshot(s) noted" + ("" if fresh else " (stale)")
    return ArtifactStatus(kind, True, fresh, detail)


def _project_management_plan(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The plan-of-plans: a roll-up over the ten subsidiary plans, never a stored body.

    Storing one would restate the plans it binds — the duplication the design forbids — so it is
    derived *through* :func:`resolve`, not by re-reading the narrative rows: one definition of a
    subsidiary plan's presence and health, inherited here. Present is ALL ten, never any: 4.2
    names this its one required output, so "any" reads PRODUCED off one written plan.
    """
    plans = [resolve(name, project, session, as_of) for name in SUBSIDIARY_PLANS]
    stored = [plan for plan in plans if plan.present]
    present = len(stored) == len(plans)
    healthy = present and all(plan.healthy for plan in plans)
    detail = f"{len(stored)} of {len(plans)} subsidiary plans"
    return ArtifactStatus("project_management_plan", present, healthy, detail)


def _work_performance_information(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    """Work performance data read in the context of the plan — PMBOK's own definition.

    Both halves are required, because neither alone is information: an approved
    baseline with lines to measure against, and dated actuals at or before ``as_of``
    to measure — the cost entries and status snapshots the store already keeps. Health
    is currency, not a checkbox: information nothing has refreshed inside
    ``STATUS_CADENCE_DAYS`` is present and stale, the rule :func:`_reported_status` and
    :func:`_quality_report` carry. Storing it would be the duplication forbidden here.
    """
    kind = "work_performance_information"
    baseline = _approved_baseline(project, session, as_of)
    if baseline is None or not baseline.lines:
        return ArtifactStatus(kind, False, False, "no plan to measure against")
    dated = [entry.incurred_on for entry in rows_for(session, CostEntry, project.id)]
    dated += [snap.taken_on for snap in rows_for(session, StatusSnapshot, project.id)]
    actuals = [when for when in dated if when <= as_of]
    if not actuals:
        return ArtifactStatus(kind, False, False, "plan but no actuals")
    latest = max(actuals)
    fresh = (as_of - latest) <= timedelta(days=STATUS_CADENCE_DAYS)
    detail = f"plan + actuals to {latest.isoformat()}" + ("" if fresh else " (stale)")
    return ArtifactStatus(kind, True, fresh, detail)


def _narrative(kind: str, narrative_kind: str) -> Resolver:
    def resolve(project: Project, session: Session, as_of: date) -> ArtifactStatus:
        # (project_id, kind) is unique, so "the first match" is "the row".
        prose = rows_for(session, NarrativeArtifact, project.id)
        rows = [n for n in prose if n.kind == narrative_kind]
        rows = [n for n in rows if n.updated_on is None or n.updated_on <= as_of]
        present = bool(rows) and bool(rows[0].body.strip())
        return ArtifactStatus(kind, present, present, "present" if present else "absent")

    return resolve


def _agreements(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    agreements = rows_for(session, ProcurementAgreement, project.id)
    present = bool(agreements)
    disputed = any(a.status == "disputed" for a in agreements)
    return ArtifactStatus(
        "agreements", present, present and not disputed, f"{len(agreements)} agreement(s)"
    )


def _lessons_learned_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Rows, not prose: a project has a lessons learned register once any lesson is
    raised at or before ``as_of`` — one row per lesson, replacing the retired
    single-body ``lessons_learned`` narrative kind."""
    lessons = [
        row for row in rows_for(session, LessonLearned, project.id) if row.raised_on <= as_of
    ]
    present = bool(lessons)
    return ArtifactStatus("lessons_learned_register", present, present, f"{len(lessons)} lesson(s)")


def _quality_report(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    rows = [q for q in rows_for(session, QualityMeasurement, project.id) if q.measured_on <= as_of]
    if not rows:
        return ArtifactStatus("quality_report", False, False, "no measurements")
    latest = max(rows, key=lambda q: (q.measured_on, q.id))  # the old (date, id) DESC first()
    fresh = (as_of - latest.measured_on) <= timedelta(days=QUALITY_RECENCY_DAYS)
    in_tolerance = latest.actual_value <= latest.target_value
    return ArtifactStatus(
        "quality_report", True, fresh and in_tolerance, f"latest {latest.measured_on.isoformat()}"
    )


#: The ten subsidiary management plans the project management plan binds together: stored prose
#: each, and all :func:`_project_management_plan` rolls up, so the two cannot name different tens.
SUBSIDIARY_PLANS = (
    "scope_management_plan",
    "requirements_management_plan",
    "schedule_management_plan",
    "cost_management_plan",
    "quality_management_plan",
    "resource_management_plan",
    "communications_management_plan",
    "risk_management_plan",
    "procurement_management_plan",
    "stakeholder_engagement_plan",
)

#: The kinds the store can answer for: rows somebody wrote, or a figure derived from
#: them — a derived kind has no producer, having nothing of its own to write.
RESOLVERS: dict[str, Resolver] = {
    "scope_baseline": _scope_baseline,
    "schedule_baseline": _schedule_baseline,
    "cost_baseline": _cost_baseline,
    "project_schedule": _project_schedule,
    "activity_attributes": _activity_attributes,
    "project_schedule_network_diagram": _project_schedule_network_diagram,
    "schedule_data": _schedule_data,
    "project_calendars": _project_calendars,
    "milestone_list": _milestone_list,
    "risk_register": _risk_register,
    "risk_report": _risk_report,
    "issue_log": _issue_log,
    "change_log": _change_log,
    "change_requests": _change_requests,
    "stakeholder_register": _stakeholder_register,
    "project_team_assignments": _project_team_assignments,
    "status_report": _reported_status("status_report"),
    "work_performance_reports": _reported_status("work_performance_reports"),
    "work_performance_information": _work_performance_information,
    "project_communications": _project_communications,
    "project_management_plan": _project_management_plan,
    "agreements": _agreements,
    "quality_report": _quality_report,
    "assumption_log": _narrative("assumption_log", "assumption_log"),
    "lessons_learned_register": _lessons_learned_register,
    "enterprise_environmental_factors": _narrative("enterprise_environmental_factors", "eef"),
    "organizational_process_assets": _narrative("organizational_process_assets", "opa"),
    # Scope: requirements, their traces, the WBS/deliverable tree, and its
    # acceptance ledger — rows now, not derived-from-elsewhere or narrative alone.
    "requirements_documentation": _requirements_documentation,
    "requirements_traceability_matrix": _requirements_traceability_matrix,
    "work_breakdown_structure": _work_breakdown_structure,
    "verified_deliverables": _verified_deliverables,
    "accepted_deliverables": _accepted_deliverables,
    # Every prose kind the store accepts a body for: the ten subsidiary management
    # plans, then the four definition-and-team documents. All are stored under the
    # catalog kind exactly (the convention every narrative kind after the legacy four
    # follows), so each resolver is one entry and a written body is what "present" means.
    **{
        kind: _narrative(kind, kind)
        for kind in (
            *SUBSIDIARY_PLANS,
            "project_scope_statement",
            "team_charter",
            "basis_of_estimates",
            "team_performance_assessments",
        )
    },
    # Resource: the resource catalog, its RBS tree, the stored RACI (team_charter),
    # team-assessment readings and physical (non-people) acquisitions — rows now,
    # narrative-first crosswalk still the fallback for the three that used to be
    # narrative-only (module docstring's "native, then narrative" order).
    "resource_management_plan": _resource_management_plan,
    "resource_breakdown_structure": _resource_breakdown_structure,
    "team_charter": _team_charter,
    "team_performance_assessments": _team_performance_assessments,
    "physical_resource_assignments": _physical_resource_assignments,
}


def resolve(
    kind: str, project: Project, session: Session, as_of: date, *, allow_crosswalk: bool = True
) -> ArtifactStatus:
    """Resolve one artifact kind against the store, as of ``as_of``.

    A native resolver runs first when one exists. When it (or the absence of
    one) reads ``present=False``, ``driftless.pmbok.crosswalk`` gets a turn:
    a Scrum or Kanban project's evidence for the same control often lives in
    ``models/agile.py`` rather than the predictive-shaped rows this module
    reads, and an operations-cadence project's lives in ``models/operations.py``
    — the crosswalk answers for the kinds it names an equivalence for, reading
    whichever of those a project's own ``delivery_mode`` names. The crosswalk
    NEVER overrides a native present answer — it only fills a gap — and its
    detail is marked so a reader can tell which read answered.

    ``allow_crosswalk=False`` is the one seam a caller reaches for when a
    kind must be read on a fixed baseline regardless of ``delivery_mode`` —
    ``driftless.pmbok.state`` sets it per Monitoring & Controlling control,
    off that control's own ``tailoring.ControlMode`` (not off the project's
    ``delivery_mode`` alone): a hybrid project keeps its cost control on
    ``PREDICTIVE_BASELINE`` even though the SAME project's scope control reads
    ``ADAPTIVE_COMMITMENT``, so the gate has to be per control, not per project.
    Every other caller leaves it at the default, unchanged from before this
    parameter existed.

    Two more things gate the crosswalk before it ever runs a resolver, so a
    predictive-only project's page pays nothing for a fallback it can never use:
    ``kind`` must be one it names an equivalence for at all, and
    ``crosswalk.has_evidence`` must answer True — ``Project.delivery_mode``
    already in memory for a plain ``predictive`` project, one batched existence
    check (``any_rows_for``) for an agile/hybrid one, and a department-scoped
    read off ``Project.responsible_department_id`` for an operations one.
    Imported here rather than at module level: the crosswalk itself reads this
    module's ``ArtifactStatus``/``Resolver``/``rows_for``/``any_rows_for``, so
    importing it at load time would be a cycle; both modules are fully loaded by
    the time any resolver actually runs. A kind neither side can answer for
    reads ``present=False, detail="not tracked"``.
    """
    resolver = RESOLVERS.get(kind)
    native = resolver(project, session, as_of) if resolver is not None else None
    if native is not None and native.present:
        return native
    from driftless.pmbok import crosswalk

    equivalent = None
    if (
        allow_crosswalk
        and kind in crosswalk.EQUIVALENCES
        and crosswalk.has_evidence(project, session)
    ):
        equivalent = crosswalk.resolve(kind, project, session, as_of)
    if equivalent is not None and equivalent.present:
        source = (
            "operations crosswalk" if project.delivery_mode == "operations" else "agile crosswalk"
        )
        return ArtifactStatus(kind, True, equivalent.healthy, f"{equivalent.detail} ({source})")
    if native is not None:
        return native
    return ArtifactStatus(kind, False, False, "not tracked")


def is_tracked(kind: str) -> bool:
    """Whether the store can resolve ``kind`` at all (has a resolver)."""
    return kind in RESOLVERS


#: Why each untracked vocabulary kind stays untracked — one reader-actionable line per
#: kind, naming what the store consults instead. ``RESOLVERS`` and this dict partition
#: ``ARTIFACT_KINDS`` exactly (pinned by tests/test_pmbok_catalog.py), so a new kind
#: cannot land silently undispositioned: it either gains a resolver or records, here,
#: why it never will. Prose counterpart: docs/pmbok-mapping.md, "Not implemented".
UNTRACKED_DISPOSITIONS: dict[str, str] = {
    # Charters and plans — every plan resolves now; what stays is generated or structural.
    "project_charter": (
        "generated on read by the report engine (driftless/report/documents/charter.py); "
        "a stored copy is the duplication the design forbids — read the Charter document"
    ),
    "change_management_plan": "change control is structural: approval freezes a baseline",
    "configuration_management_plan": "enforced structurally — read the baseline versions",
    "development_approach": "carried as Project.delivery_mode — read the project row",
    # Activities and the schedule network — the attributes resolve off the task rows
    # now; what stays out is the enumeration and the edges between activities.
    "activity_list": "the enumeration is activity_attributes' own count — read that",
    "schedule_forecasts": "computed on read from sprint velocity — read the completion forecast",
    # Resource planning — capacity is shown, never levelled.
    "resource_calendars": (
        "one project calendar exists (ProjectCalendar); per-person calendars do not — "
        "capacity is weekly hours, read the heatmap"
    ),
    "resource_requirements": "implicit in assignment versus capacity — read the heatmap",
    # Estimating — one figure per task or line, no range; the basis is stored prose.
    "duration_estimates": "a task carries exactly one estimate — read the task rows",
    "cost_estimates": "one planned cost per baseline line — read cost_baseline",
    "independent_cost_estimates": "procurement enters at signature; pre-award work is elsewhere",
    # EVM stops at the snapshot; funding is arithmetic over stored lines.
    "performance_measurement_baseline": "the three approved baselines are the PMB — read those",
    "cost_forecasts": "EAC/ETC/VAC are computed on read — read the earned-value snapshot",
    "project_funding_requirements": "arithmetic over budget lines — read cost_baseline",
    # Quality — a dated measurement against a target is the whole record.
    "quality_metrics": "targets live on each dated measurement row — read quality_report",
    "quality_control_measurements": "the dated measurement rows themselves — read quality_report",
    "test_and_evaluation_documents": "no test record; measurements are the evidence",
    # Procurement before signature happens outside the store.
    "procurement_statement_of_work": "pre-signature work happens elsewhere — read agreements",
    "procurement_documentation": "the store starts at signature — read agreements",
    "procurement_strategy": "pre-signature work happens elsewhere — read agreements",
    "source_selection_criteria": "selection precedes the store — read agreements",
    "bid_documents": "solicitation happens outside the store — read agreements",
    "seller_proposals": "solicitation happens outside the store — read agreements",
    "selected_sellers": "selection precedes signature — read agreements for the outcome",
    "closed_procurements": "closure is an agreement status, not a document — read agreements",
    # Deliverables and closeout — the list itself has no dedicated artifact reading;
    # verified_deliverables and accepted_deliverables (below RESOLVERS) now read the
    # Deliverable/AcceptanceRecord rows directly.
    "deliverables": "the Deliverable rows themselves — read work_breakdown_structure",
    "final_product_service_result": "no closeout artifact — read the sign-off ledger",
    "final_report": "no closeout document — read the sign-off ledger for done-ness",
    # Pre-authorisation — the store begins at the project.
    "business_case": "the store begins at the project; earlier analysis is elsewhere",
    "benefits_management_plan": "pre-authorisation value analysis is somebody else's tool",
    "agreements_initial": "pre-project agreements live elsewhere — signed ones are agreements",
    # Work performance flow — computed on read, never stored copies.
    "work_performance_data": "computed on read; storing it is the duplication the design forbids",
    # Change control — a new baseline version is what approval produces, so only that
    # half still has no resolver of its own; change_requests resolves above.
    "approved_change_requests": "approval causes a new baseline version — read change_log",
}
