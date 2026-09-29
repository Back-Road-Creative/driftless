"""Agile evidence, read as PMP-style control coverage — derived, never copied.

``driftless/pmbok/mapping.py`` resolves each artifact kind to the predictive-shaped
rows a project keeps (a `Baseline`, a `Milestone`, a `NarrativeArtifact` body). A
Scrum or Kanban project's evidence for the SAME control question lives somewhere
else — `driftless/models/agile.py`'s roles, backlog items, releases,
definition-of-done items and impediments, plus the review/retrospective fields
`Sprint` (`driftless/models/delivery.py`) carries for the same reason (see that
module's docstring). ``EQUIVALENCES`` names, for each artifact kind agile evidence
can stand in for, WHERE that evidence lives and the plain-English rule that reads
it — never a second copy of a native row, never a second state rule: `mapping.resolve`
is the one caller, consulting this module only when its own resolver finds nothing
(see that function's docstring for the fallback order).

Every resolver here has exactly the shape `mapping.Resolver` already has —
`(project, session, as_of) -> ArtifactStatus` — and reads through
`mapping.rows_for`, the same batched, `prefetched`-aware read every native resolver
uses, so an agile project's page pays for one query per model here exactly as a
predictive project's does. Nothing in this module calls `session.add`,
`session.flush` or `session.merge` — it only ever reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import (
    BacklogItem,
    DefinitionOfDoneItem,
    DepartmentService,
    Impediment,
    Improvement,
    Incident,
    OperatingControl,
    Project,
    ProjectRole,
    RecurringWork,
    Release,
    ServiceLevel,
    Sprint,
    WorkRequest,
)
from driftless.pmbok.mapping import (
    STATUS_CADENCE_DAYS,
    ArtifactStatus,
    Resolver,
    any_rows_for,
    rows_for,
)

#: Backlog-item statuses that mean the item has been pulled into delivery, not
#: merely proposed — the agile reading of "committed to the plan".
_COMMITTED_STATUSES = ("ready", "in_progress", "done")

#: models/agile.py's five, plus Sprint (models/delivery.py) — every table an
#: agile team's evidence for one of the kinds above could live in.
#: :func:`has_evidence` is the one batched existence check against this list.
_EVIDENCE_MODELS = (BacklogItem, Sprint, Release, DefinitionOfDoneItem, Impediment, ProjectRole)

#: Every models/operations.py table an operations-cadence project's evidence
#: for one of the kinds below could live in — the department-scoped counterpart
#: of ``_EVIDENCE_MODELS``. Department-scoped rows carry no ``project_id`` of
#: their own, so this reads through ``Project.responsible_department_id``
#: rather than ``mapping.any_rows_for``, which is keyed on that column.
_OPERATIONS_EVIDENCE_MODELS = (
    DepartmentService,
    WorkRequest,
    RecurringWork,
    ServiceLevel,
    OperatingControl,
    Incident,
)


def has_evidence(project: Project, session: Session) -> bool:
    """Whether ``project`` carries ANY row this module could read.

    ``mapping.resolve`` checks this before ever calling :func:`resolve`, so a
    predictive project — and an agile one that has recorded nothing yet — never
    pays for a fallback read it cannot use. ``Project.delivery_mode`` is already
    the row in memory: a plain ``predictive`` project answers False with no query
    at all. An ``operations`` project reads its department's own operations
    tables (:func:`_operations_has_evidence`) — it carries none of
    ``_EVIDENCE_MODELS``' rows, an agile project carries none of
    ``models/operations.py``'s, so the two reads never overlap. Anything else
    (agile, hybrid) runs ONE batched existence check (``mapping.any_rows_for``)
    across ``_EVIDENCE_MODELS``, cached per ``prefetched`` scope the same way
    every resolver's own read is — never one query per model per project.
    """
    if project.delivery_mode == "predictive":
        return False
    if project.delivery_mode == "operations":
        return _operations_has_evidence(project, session)
    return any_rows_for(session, _EVIDENCE_MODELS, project.id)


def _operations_has_evidence(project: Project, session: Session) -> bool:
    """Whether the department ``project`` is scoped to (if any) carries any row
    across ``_OPERATIONS_EVIDENCE_MODELS`` — a plain existence check per table
    rather than ``mapping.any_rows_for``'s batch, since these tables key on
    ``department_id``, not the ``project_id`` that helper's scope is built on.
    A project with no responsible department has nothing to read.
    """
    department_id = project.responsible_department_id
    if department_id is None:
        return False
    for model in _OPERATIONS_EVIDENCE_MODELS:
        hit = session.execute(
            select(model.id).where(model.department_id == department_id).limit(1)
        ).first()
        if hit is not None:
            return True
    return False


@dataclass(frozen=True)
class Equivalence:
    """One PMBOK artifact kind, resolved from agile evidence instead of a
    predictive-shaped row.

    ``native_source`` names where the evidence lives in plain words (a model, a
    field); ``rule_in_plain_words`` states the reading rule. Both render verbatim
    on the process page and (a follow-up — see `docs/architecture.md`) the
    artifact page, as "Counted from: <native_source> — <rule_in_plain_words>", so
    the equivalence a reader sees is this dataclass's own text, never restated.
    """

    native_source: str
    rule_in_plain_words: str
    resolver: Resolver


def _requirements_documentation(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    items = rows_for(session, BacklogItem, project.id)
    described = [item for item in items if item.description.strip()]
    present = bool(described)
    healthy = present and len(described) == len(items)
    detail = f"{len(described)} of {len(items)} backlog item(s) with a written description"
    return ArtifactStatus("requirements_documentation", present, healthy, detail)


def _project_schedule(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    releases = rows_for(session, Release, project.id)
    dated = [r for r in releases if r.target_date is not None]
    present = bool(dated)
    detail = f"{len(dated)} of {len(releases)} release(s) with a target date"
    return ArtifactStatus("project_schedule", present, present, detail)


def _scope_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    committed = [
        i for i in rows_for(session, BacklogItem, project.id) if i.status in _COMMITTED_STATUSES
    ]
    done_items = rows_for(session, DefinitionOfDoneItem, project.id)
    present = bool(committed) and bool(done_items)
    detail = (
        f"{len(committed)} committed backlog item(s), {len(done_items)} definition-of-done item(s)"
    )
    return ArtifactStatus("scope_baseline", present, present, detail)


def _issue_log(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    impediments = [i for i in rows_for(session, Impediment, project.id) if i.raised_on <= as_of]
    present = bool(impediments)
    unresolved = sum(1 for i in impediments if i.status in ("open", "in_progress"))
    detail = f"{len(impediments)} impediment(s)"
    return ArtifactStatus("issue_log", present, present and unresolved == 0, detail)


def _lessons_learned_register(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    sprints = rows_for(session, Sprint, project.id)
    reflected = [
        s
        for s in sprints
        if s.retrospective_held_on is not None
        and s.retrospective_held_on <= as_of
        and (s.retrospective_notes or "").strip()
    ]
    present = bool(reflected)
    detail = f"{len(reflected)} sprint(s) with retrospective evidence"
    return ArtifactStatus("lessons_learned_register", present, present, detail)


def _resource_management_plan(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    roles = rows_for(session, ProjectRole, project.id)
    present = bool(roles)
    detail = f"{len(roles)} project role(s) assigned"
    return ArtifactStatus("resource_management_plan", present, present, detail)


def _work_performance_reports(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    sprints = rows_for(session, Sprint, project.id)
    reviewed = [
        s
        for s in sprints
        if s.review_held_on is not None
        and s.review_held_on <= as_of
        and (s.review_notes or "").strip()
    ]
    if not reviewed:
        return ArtifactStatus("work_performance_reports", False, False, "no sprint review evidence")
    latest = max(s.review_held_on for s in reviewed if s.review_held_on is not None)
    fresh = (as_of - latest) <= timedelta(days=STATUS_CADENCE_DAYS)
    detail = f"latest sprint review {latest.isoformat()}" + ("" if fresh else " (stale)")
    return ArtifactStatus("work_performance_reports", True, fresh, detail)


class _DepartmentScoped(Protocol):
    """A mapped row a department-side resolver reads: one integer pk, owned by
    one department — the counterpart of ``mapping._ProjectScoped``."""

    id: Any
    department_id: Any


_D = TypeVar("_D", bound=_DepartmentScoped)


def _department_operations_rows(project: Project, session: Session, model: type[_D]) -> list[_D]:
    """One department-scoped table's rows for the department ``project`` is
    scoped to — plain, not batched, since these keys never appear in the
    project-scoped ``prefetched`` cache :func:`rows_for` reads."""
    department_id = project.responsible_department_id
    if department_id is None:
        return []
    return list(session.scalars(select(model).where(model.department_id == department_id)))


def _work_performance_information(
    project: Project, session: Session, as_of: date
) -> ArtifactStatus:
    """The plan-and-actuals question, read off whichever evidence a project's
    ``delivery_mode`` actually keeps: an agile team's sprints under way, or an
    operations-cadence project's service levels and the incidents raised
    against them.
    """
    kind = "work_performance_information"
    if project.delivery_mode == "operations":
        levels = _department_operations_rows(project, session, ServiceLevel)
        incidents = [
            i
            for i in _department_operations_rows(project, session, Incident)
            if i.raised_on <= as_of
        ]
        if not levels or not incidents:
            return ArtifactStatus(kind, False, False, "no service level or incident evidence")
        latest = max(i.raised_on for i in incidents)
        fresh = (as_of - latest) <= timedelta(days=STATUS_CADENCE_DAYS)
        detail = f"{len(levels)} service level(s), latest incident {latest.isoformat()}" + (
            "" if fresh else " (stale)"
        )
        return ArtifactStatus(kind, True, fresh, detail)
    sprints = [s for s in rows_for(session, Sprint, project.id) if s.start_date <= as_of]
    if not sprints:
        return ArtifactStatus(kind, False, False, "no sprint under way")
    latest_sprint = max(sprints, key=lambda s: s.start_date)
    reference = latest_sprint.review_held_on or latest_sprint.end_date
    fresh = (as_of - reference) <= timedelta(days=STATUS_CADENCE_DAYS)
    detail = f"{len(sprints)} sprint(s) under way, latest {latest_sprint.name}" + (
        "" if fresh else " (stale)"
    )
    return ArtifactStatus(kind, True, fresh, detail)


def _schedule_baseline(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """The team's own current commitment, standing in for a fixed baseline: an
    agile team's committed sprint window, or an operations-cadence project's
    own recurring-work cadence.
    """
    kind = "schedule_baseline"
    if project.delivery_mode == "operations":
        cadence = _department_operations_rows(project, session, RecurringWork)
        present = bool(cadence)
        healthy = present and all(r.next_due_on is not None for r in cadence)
        return ArtifactStatus(kind, present, healthy, f"{len(cadence)} recurring work item(s)")
    sprints = [s for s in rows_for(session, Sprint, project.id) if s.start_date <= as_of]
    present = bool(sprints)
    healthy = present and all(s.committed_points > 0 for s in sprints)
    return ArtifactStatus(kind, present, healthy, f"{len(sprints)} sprint(s) committed")


def _accepted_deliverables(project: Project, session: Session, as_of: date) -> ArtifactStatus:
    """Validate Scope's own output, read off whichever acceptance a project's
    ``delivery_mode`` actually records: an agile team accepts an increment at
    the sprint review, so a reviewed sprint that completed points IS accepted
    work; an operations-cadence project accepts finished work against the
    department's own service levels (``tailoring``'s own operations reading for
    5.5 says as much), so a service level on record is the acceptance criterion
    in force. Never a shadow ``AcceptanceRecord`` — that row stays the predictive
    ledger ``mapping._accepted_deliverables`` reads first.
    """
    kind = "accepted_deliverables"
    if project.delivery_mode == "operations":
        levels = _department_operations_rows(project, session, ServiceLevel)
        if not levels:
            return ArtifactStatus(kind, False, False, "no service level to accept work against")
        return ArtifactStatus(kind, True, True, f"{len(levels)} service level(s) accept work")
    accepted = [
        s
        for s in rows_for(session, Sprint, project.id)
        if s.review_held_on is not None and s.review_held_on <= as_of and s.completed_points > 0
    ]
    if not accepted:
        return ArtifactStatus(kind, False, False, "no reviewed sprint with completed points")
    latest = max(s.review_held_on for s in accepted if s.review_held_on is not None)
    return ArtifactStatus(
        kind, True, True, f"increment accepted at the {latest.isoformat()} review"
    )


#: Every artifact kind agile evidence can stand in for, and where that evidence lives.
#: Each key is an `ARTIFACT_KINDS` member (`tests/test_pmbok_crosswalk.py` pins it).
EQUIVALENCES: dict[str, Equivalence] = {
    "requirements_documentation": Equivalence(
        "backlog items (driftless/models/agile.py:BacklogItem)",
        "a backlog item's description IS its requirement statement; present once "
        "any item has one, healthy once every item does",
        _requirements_documentation,
    ),
    "project_schedule": Equivalence(
        "releases (driftless/models/agile.py:Release)",
        "a release with a target date is the agile reading of a project schedule "
        "when there is no sprint or milestone to read one from",
        _project_schedule,
    ),
    "scope_baseline": Equivalence(
        "committed backlog items and definition-of-done items (models/agile.py)",
        "a committed backlog (status ready/in_progress/done) plus a written "
        "definition of done is what an agile team baselines scope against",
        _scope_baseline,
    ),
    "issue_log": Equivalence(
        "impediments (driftless/models/agile.py:Impediment)",
        "an impediment IS an issue raised against the team's progress; healthy "
        "once none are open or in progress",
        _issue_log,
    ),
    "lessons_learned_register": Equivalence(
        "sprint retrospective evidence (driftless/models/delivery.py:Sprint)",
        "a sprint closed with retrospective notes is a lesson captured, the way a "
        "predictive project files one as prose",
        _lessons_learned_register,
    ),
    "resource_management_plan": Equivalence(
        "project roles (driftless/models/agile.py:ProjectRole)",
        "naming who holds each agile role (product owner, Scrum Master, developer, "
        "stakeholder proxy) is how an agile team plans its resources, in place of "
        "the stored prose plan a predictive project writes",
        _resource_management_plan,
    ),
    "work_performance_reports": Equivalence(
        "sprint review evidence (driftless/models/delivery.py:Sprint)",
        "a sprint closed with review notes is the periodic report the sprint's own "
        "cadence produces, fresh while the latest is inside the reporting window",
        _work_performance_reports,
    ),
    "work_performance_information": Equivalence(
        "sprints under way (driftless/models/delivery.py:Sprint) for an agile project, "
        "or service levels and incidents (driftless/models/operations.py) for an "
        "operations-cadence one",
        "a sprint under way is the work performance data an agile team reads instead of "
        "a baseline-and-actuals pair; an operations-cadence project reads the same "
        "question off its service levels and the incidents raised against them",
        _work_performance_information,
    ),
    "schedule_baseline": Equivalence(
        "the current sprint's committed window (driftless/models/delivery.py:Sprint) for "
        "an agile project, or the department's own recurring work "
        "(driftless/models/operations.py:RecurringWork) for an operations-cadence one",
        "an agile team's schedule is the sprint it has committed to, not a fixed "
        "baseline; an operations-cadence project's schedule is the cadence the "
        "department already runs",
        _schedule_baseline,
    ),
    "accepted_deliverables": Equivalence(
        "reviewed sprints with completed points (driftless/models/delivery.py:Sprint) for an "
        "agile project, or the department's service levels "
        "(driftless/models/operations.py:ServiceLevel) for an operations-cadence one",
        "an agile team accepts an increment at the sprint review, so a reviewed sprint that "
        "completed points is accepted work; an operations-cadence project accepts finished "
        "work against the department's own service levels",
        _accepted_deliverables,
    ),
}

#: Every `models/agile.py` model an `EQUIVALENCES` resolver reads at least one row
#: of. `tests/test_pmbok_crosswalk.py` pins this set-equal against that module's own
#: mapped classes, together with `NO_EQUIVALENCE` for any that is not — empty today,
#: since every agile model is named by an equivalence above.
NAMED_MODELS: frozenset[type] = frozenset(
    {BacklogItem, Release, DefinitionOfDoneItem, Impediment, ProjectRole}
)
NO_EQUIVALENCE: dict[type, str] = {}

#: Every `models/operations.py` model an `EQUIVALENCES` resolver reads at least one
#: row of, on the operations branch. `tests/test_pmbok_mode_aware_state.py` pins this
#: set-equal against that module's own mapped classes, together with
#: `OPERATIONS_NO_EQUIVALENCE` for any that is not — the same partition
#: `NAMED_MODELS`/`NO_EQUIVALENCE` draws for `models/agile.py`.
OPERATIONS_NAMED_MODELS: frozenset[type] = frozenset({ServiceLevel, Incident, RecurringWork})
OPERATIONS_NO_EQUIVALENCE: dict[type, str] = {
    DepartmentService: "a service description names capability, not evidence a control ran",
    WorkRequest: (
        "demand volume is not itself evidence a control produced its output — "
        "read service_level/incident"
    ),
    OperatingControl: (
        "the control's existence is not evidence it ran — read incident, what it "
        "prevents or catches"
    ),
    Improvement: "a proposed change is not evidence of an existing control's output",
}


def resolve(kind: str, project: Project, session: Session, as_of: date) -> ArtifactStatus | None:
    """This module's own answer for ``kind``, or ``None`` if no equivalence is
    defined for it. ``mapping.resolve`` is the one caller. A single resolver
    answers for both branches — its own body reads ``project.delivery_mode``
    to pick agile or operations evidence — so this stays one seam, never a
    second dispatch table."""
    equivalence = EQUIVALENCES.get(kind)
    if equivalence is None:
        return None
    return equivalence.resolver(project, session, as_of)
