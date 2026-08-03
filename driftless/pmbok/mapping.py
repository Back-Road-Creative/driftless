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
from typing import Any, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.models import (
    Baseline,
    BudgetLine,
    ChangeRequest,
    CostEntry,
    Issue,
    Milestone,
    NarrativeArtifact,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    Risk,
    Sprint,
    Stakeholder,
    StatusSnapshot,
    Task,
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


def _rows(session: Session, model: type[_M], project_id: int) -> list[_M]:
    """``model``'s rows for one project — batched across the whole ``prefetched``
    scope when one is open, else the single per-project SELECT, id order."""
    table: Any = model

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        stmt = select(table).where(table.project_id.in_(ids)).order_by(table.id)
        if model is Baseline:
            stmt = stmt.options(selectinload(Baseline.lines))  # judged via ``.lines``
        return ((row.project_id, row) for row in session.scalars(stmt))

    rows: list[_M] = _grouped(session, model, load, project_id)
    return rows


def _tasks(session: Session, project_id: int) -> list[Task]:
    """One project's tasks — the activity register the two derived kinds below read.

    ``Task`` carries ``workstream_id``, not ``project_id``, so it cannot go through
    :func:`_rows`: the batch joins ``Workstream`` and groups on ITS ``project_id``.
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


def _approved_baseline(project: Project, session: Session, as_of: date) -> Baseline | None:
    rows = [b for b in _rows(session, Baseline, project.id) if b.status == "approved"]
    rows = [b for b in rows if b.approved_at is None or b.approved_at.date() <= as_of]
    rows.sort(key=lambda baseline: baseline.version, reverse=True)
    return rows[0] if rows else None


def _scope_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    baseline = _approved_baseline(project, session, as_of)
    if baseline is None:
        return ArtifactStatus("scope_baseline", False, False, "no approved baseline")
    healthy = bool(baseline.lines)
    detail = f"approved baseline v{baseline.version}" + ("" if healthy else " (no lines)")
    return ArtifactStatus("scope_baseline", True, healthy, detail)


def _schedule_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    baseline = _approved_baseline(project, session, as_of)
    if baseline is None or not baseline.lines:
        return ArtifactStatus("schedule_baseline", False, False, "no baselined schedule")
    windowed = all(line.planned_start <= line.planned_finish for line in baseline.lines)
    return ArtifactStatus("schedule_baseline", True, windowed, f"v{baseline.version}")


def _cost_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    lines = _rows(session, BudgetLine, project.id)
    if not lines:
        return ArtifactStatus("cost_baseline", False, False, "no budget lines")
    total = sum(line.planned_amount for line in lines)
    healthy = total > 0
    return ArtifactStatus("cost_baseline", True, healthy, f"{len(lines)} budget line(s)")


def _project_schedule(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    milestones = _rows(session, Milestone, project.id)
    sprints = _rows(session, Sprint, project.id)
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
    milestones = _rows(session, Milestone, project.id)
    present = bool(milestones)
    slipped = any(m.status == "missed" for m in milestones)
    return ArtifactStatus(
        "milestone_list", present, present and not slipped, f"{len(milestones)} milestone(s)"
    )


def _risk_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    risks = _rows(session, Risk, project.id)
    present = bool(risks)
    open_realised = any(r.status == "realised" for r in risks)
    return ArtifactStatus(
        "risk_register", present, present and not open_realised, f"{len(risks)} risk(s)"
    )


def _issue_log(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    issues = [i for i in _rows(session, Issue, project.id) if i.raised_on <= as_of]
    present = bool(issues)
    unresolved = sum(1 for i in issues if i.status in ("open", "in_progress"))
    return ArtifactStatus(
        "issue_log", present, present and unresolved == 0, f"{len(issues)} issue(s)"
    )


def _change_log(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    changes = [c for c in _rows(session, ChangeRequest, project.id) if c.raised_on <= as_of]
    present = bool(changes)
    return ArtifactStatus("change_log", present, present, f"{len(changes)} change request(s)")


def _stakeholder_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    holders = _rows(session, Stakeholder, project.id)
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
        # (project_id, taken_on) is unique, so max() IS the old ORDER BY DESC first().
        snaps = [s for s in _rows(session, StatusSnapshot, project.id) if s.taken_on <= as_of]
        if not snaps:
            return ArtifactStatus(kind, False, False, "no status snapshot")
        latest = max(snaps, key=lambda snap: snap.taken_on)
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
    snaps = [s for s in _rows(session, StatusSnapshot, project.id) if s.taken_on <= as_of]
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
    dated = [entry.incurred_on for entry in _rows(session, CostEntry, project.id)]
    dated += [snap.taken_on for snap in _rows(session, StatusSnapshot, project.id)]
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
        prose = _rows(session, NarrativeArtifact, project.id)
        rows = [n for n in prose if n.kind == narrative_kind]
        rows = [n for n in rows if n.updated_on is None or n.updated_on <= as_of]
        present = bool(rows) and bool(rows[0].body.strip())
        return ArtifactStatus(kind, present, present, "present" if present else "absent")

    return resolve


def _agreements(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    agreements = _rows(session, ProcurementAgreement, project.id)
    present = bool(agreements)
    disputed = any(a.status == "disputed" for a in agreements)
    return ArtifactStatus(
        "agreements", present, present and not disputed, f"{len(agreements)} agreement(s)"
    )


def _quality_report(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    rows = [q for q in _rows(session, QualityMeasurement, project.id) if q.measured_on <= as_of]
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
    "milestone_list": _milestone_list,
    "risk_register": _risk_register,
    "issue_log": _issue_log,
    "change_log": _change_log,
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
    "lessons_learned_register": _narrative("lessons_learned_register", "lessons_learned"),
    "enterprise_environmental_factors": _narrative("enterprise_environmental_factors", "eef"),
    "organizational_process_assets": _narrative("organizational_process_assets", "opa"),
    # Every prose kind the store accepts a body for: the ten subsidiary management
    # plans, then the five definition-and-team documents. All are stored under the
    # catalog kind exactly (the convention every narrative kind after the legacy four
    # follows), so each resolver is one entry and a written body is what "present" means.
    **{
        kind: _narrative(kind, kind)
        for kind in (
            *SUBSIDIARY_PLANS,
            "project_scope_statement",
            "requirements_documentation",
            "team_charter",
            "basis_of_estimates",
            "team_performance_assessments",
        )
    },
}


def resolve(kind: str, project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Resolve one artifact kind against the store, as of ``as_of``.

    A kind with no resolver answers ``present=False, detail="not tracked"`` —
    the system does not store it, so it reports that rather than guessing.
    """
    resolver = RESOLVERS.get(kind)
    if resolver is None:
        return ArtifactStatus(kind, False, False, "not tracked")
    return resolver(project, session, as_of)


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
    # Requirements and decomposition — the statement and the documentation are stored
    # prose now; what stays out has no record behind it to trace or decompose.
    "requirements_traceability_matrix": "no requirement rows to trace — read scope_baseline",
    "work_breakdown_structure": "no WBS node type — read the project/workstream/task hierarchy",
    # Activities and the schedule network — the attributes resolve off the task rows
    # now; what stays out is the enumeration and the edges between activities.
    "activity_list": "the enumeration is activity_attributes' own count — read that",
    "project_schedule_network_diagram": "tasks carry no predecessor edges, so no network",
    "schedule_data": "the Gantt draws baseline windows, never computes — read schedule_baseline",
    "schedule_forecasts": "computed on read from sprint velocity — read the completion forecast",
    # Resource planning — capacity is shown, never levelled.
    "resource_calendars": "no calendar record; capacity is weekly hours — read the heatmap",
    "project_calendars": "no calendar record — read baseline windows for the plan dates",
    "resource_requirements": "implicit in assignment versus capacity — read the heatmap",
    "resource_breakdown_structure": "no RBS node type; people sit under departments — read those",
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
    # Team development — the charter, the appraisal and the people assignments are all
    # answered now; what stays out is the resource that is not a person.
    "physical_resource_assignments": "people are the only tracked resource — read the heatmap",
    # Deliverables and closeout — done-ness is status plus the sign-off ledger.
    "deliverables": "done-ness is task status and percent complete — read the task rows",
    "verified_deliverables": "verification is not stored — read task status and percent",
    "accepted_deliverables": "acceptance is 'accepted' in the sign-off ledger — read the ledger",
    "final_product_service_result": "no closeout artifact — read the sign-off ledger",
    "final_report": "no closeout document — read the sign-off ledger for done-ness",
    # Pre-authorisation — the store begins at the project.
    "business_case": "the store begins at the project; earlier analysis is elsewhere",
    "benefits_management_plan": "pre-authorisation value analysis is somebody else's tool",
    "agreements_initial": "pre-project agreements live elsewhere — signed ones are agreements",
    # Work performance flow — computed on read, never stored copies.
    "work_performance_data": "computed on read; storing it is the duplication the design forbids",
    # Risk reporting — the register plus a seeded Monte Carlo, on read.
    "risk_report": "the register plus the seeded Monte Carlo, on read — read risk_register",
    # Change control — enforced by baseline versioning, surfaced as change_log.
    "change_requests": "stored as ChangeRequest rows surfaced as change_log — read change_log",
    "approved_change_requests": "approval causes a new baseline version — read change_log",
}
