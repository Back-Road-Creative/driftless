"""Producing one wizard output, for whichever surface asked -- the CLI or the browser.

Lived in :mod:`driftless.wizard.cli` until the CLI was the only surface writing
through a raw session: every producer here writes through
``driftless.api.records.insert`` (or :func:`_stage`, the same schema-validated
shape for the two multi-row producers), audited on the ChangeLog exactly as an
HTTP write is, and now credited to an actor exactly as an HTTP write is too.

:func:`produce` is the one entry point: it requires ``actor`` and stamps the
session with it (:func:`driftless.db.changelog.set_actor`) before any row is
written, so the CLI -- which never sat behind a request's ``get_session`` -- no
longer leaves a ChangeLog row that blames nobody.

Every producer here writes a brand-new row, never an existing one, so there is no
stale-write race for a caller-stated revision to guard against: ``row_revision``
starts every row at 1. :func:`~driftless.services.concurrency.check_revision`
belongs to :mod:`driftless.api.crud`'s PATCH/DELETE, not to this module's inserts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import fetch, insert
from driftless.db import Base
from driftless.db.changelog import ACTOR_KEY, set_actor
from driftless.models import (
    COST_CATEGORIES,
    LESSON_CATEGORIES,
    RAG_STATUSES,
    RESOURCE_KINDS,
    Acquisition,
    Baseline,
    BaselineLine,
    BudgetLine,
    ChangeRequest,
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
    Risk,
    Stakeholder,
    Task,
    TaskDependency,
    Workstream,
)
from driftless.services.status_snapshots import create_status_snapshot

Fields = dict[str, Any]
M = TypeVar("M", bound=Base)


def _next_baseline_version(session: Session, project: Project) -> int:
    versions = session.scalars(
        select(Baseline.version).where(Baseline.project_id == project.id)
    ).all()
    return (max(versions) + 1) if versions else 1


class MissingField(ValueError):
    """A producible kind was asked for without a value only its caller can know.

    Producers refuse instead of substituting one: the presence checks are content-blind
    ``bool(rows)``, so a substituted value marks that output produced for good and nothing
    asks for the real one again. The placeholders live in :func:`seed_fields` now."""


class MissingBody(MissingField):
    """A narrative kind was asked for with no prose. Refused, not filed."""


def _need(fields: Fields, name: str) -> str:
    """``fields[name]``, or a refusal — the one way a producer reads a required value.
    Blank is the same nothing as absent (a form posts ``""`` for an untouched input),
    and the kind is named by :func:`produce`, since two kinds share a producer."""
    if not (value := str(fields.get(name) or "").strip()):
        raise MissingField(f"needs {name}, and the wizard invents none")
    return value


class AlreadyBaselined(ValueError):
    """The project already has an approved baseline — the plan of record. Refused.

    ``adapters.plan_baseline`` is max(version) over approved rows, so a seeded
    approved vN+1 would silently become the plan every EVM figure reads — and an
    approved row can be neither deleted nor patched back to draft (both 409).
    Re-baselining is change control's job, not the onboarding wizard's.
    """


def _narrative(kind: str, stored: str) -> Callable[[Session, Project, Fields, date], int]:
    def make(session: Session, project: Project, fields: Fields, as_of: date) -> int:
        # A narrative artifact IS its prose, so there is no default to fall back on:
        # substituting one files words nobody wrote as the project's own record. The
        # request schema will not catch it either — ``body`` defaults to `""` there —
        # and the row that lands reads *absent* to ``pmbok.mapping``, so the wizard
        # would report an output every completeness figure still counts missing,
        # behind a unique (project, kind) that makes the honest retry a duplicate key.
        if not (typed := str(fields.get("body") or "").strip()):
            raise MissingBody("is a record of prose and needs a body")
        payload = s.NarrativeArtifactIn(
            project_id=project.id,
            kind=stored,  # type: ignore[arg-type]
            body=typed,
            # Threaded, never a clock: without it ``pmbok.mapping``'s narrative
            # resolver (which only filters a *set* ``updated_on``) reads this row as
            # having always existed, present at every as-of including before the
            # wizard wrote it — the one gap that made a narrative-kind process the
            # only one on the process map immune to its own as-of.
            updated_on=as_of,
        )
        return insert(session, NarrativeArtifact, payload, project_id=Project).id

    return make


def _make_risk(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.RiskIn(
        project_id=project.id,
        description=_need(fields, "description"),
        probability=float(_need(fields, "probability")),
        impact=float(_need(fields, "impact")),
    )
    return insert(session, Risk, payload, project_id=Project).id


def _make_stakeholder(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.StakeholderIn(project_id=project.id, name=_need(fields, "name"))
    return insert(session, Stakeholder, payload, project_id=Project).id


def _make_budget_line(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.BudgetLineIn(
        project_id=project.id,
        category=_need(fields, "category"),  # type: ignore[arg-type]
        planned_amount=float(_need(fields, "planned_amount")),
    )
    return insert(session, BudgetLine, payload, project_id=Project).id


def _make_milestone(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.MilestoneIn(
        project_id=project.id,
        name=_need(fields, "name"),
        target_date=date.fromisoformat(_need(fields, "target_date")),
    )
    return insert(session, Milestone, payload, project_id=Project).id


def _make_issue(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.IssueIn(
        project_id=project.id,
        description=_need(fields, "description"),
        raised_on=as_of,
    )
    return insert(session, Issue, payload, project_id=Project).id


def _make_change_request(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.ChangeRequestIn(
        project_id=project.id,
        description=_need(fields, "description"),
        raised_on=as_of,
        origin_process_id=fields.get("origin_process_id"),
    )
    return insert(session, ChangeRequest, payload, project_id=Project).id


def _make_agreement(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.ProcurementAgreementIn(
        project_id=project.id,
        vendor=_need(fields, "vendor"),
        start_date=as_of,
    )
    return insert(session, ProcurementAgreement, payload, project_id=Project).id


def _make_quality(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.QualityMeasurementIn(
        project_id=project.id,
        metric=_need(fields, "metric"),
        target_value=float(_need(fields, "target_value")),
        actual_value=float(_need(fields, "actual_value")),
        measured_on=as_of,
    )
    return insert(session, QualityMeasurement, payload, project_id=Project).id


def _make_lesson_learned(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """A dated, categorised row — the register's own shape, never the retired
    single-body ``lessons_learned`` narrative kind."""
    payload = s.LessonLearnedIn(
        project_id=project.id,
        raised_on=as_of,
        category=_need(fields, "category"),  # type: ignore[arg-type]
        what_happened=_need(fields, "what_happened"),
        what_to_do_next_time=_need(fields, "what_to_do_next_time"),
        actor=_need(fields, "actor"),
    )
    return insert(session, LessonLearned, payload, project_id=Project).id


def _stage(session: Session, model: type[M], payload: BaseModel, **parents: type[Base]) -> M:
    """``api.records.insert`` minus the per-row commit: same schema dump, same parent
    checks, flushed so the row carries its id — committed only by the caller.

    The flush is what keeps the ChangeLog honest here: its listeners fire per
    flush, inside the open transaction, so a rolled-back write rolls its audit
    rows back with it — the log never claims an insert the store does not hold.
    """
    data = payload.model_dump()
    for name, parent in parents.items():
        if data[name] is not None:
            fetch(session, parent, data[name])
    row = model(**data)
    session.add(row)
    session.flush()
    return row


def _make_deliverable(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    payload = s.DeliverableIn(
        project_id=project.id, name=_need(fields, "name"), wbs_code=_need(fields, "wbs_code")
    )
    return insert(session, Deliverable, payload, project_id=Project, parent_id=Deliverable).id


def _make_requirement_trace(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """A requirement, a WBS node and the trace between them — the wizard's own
    self-contained trio, the same "stage every row through its schema, one
    commit" shape :func:`_make_baseline` already uses below: a trace needs a
    target to point at, and the wizard invents no existing row to reuse rather
    than guess which one the caller meant."""
    try:
        requirement = _stage(
            session,
            Requirement,
            s.RequirementIn(
                project_id=project.id,
                code=_need(fields, "code"),
                statement=_need(fields, "statement"),
                actor=fields.get("actor") or "wizard",
            ),
            project_id=Project,
        )
        deliverable = _stage(
            session,
            Deliverable,
            s.DeliverableIn(
                project_id=project.id,
                name=_need(fields, "name"),
                wbs_code=_need(fields, "wbs_code"),
            ),
            project_id=Project,
        )
        trace = _stage(
            session,
            RequirementTrace,
            s.RequirementTraceIn(requirement_id=requirement.id, deliverable_id=deliverable.id),
            requirement_id=Requirement,
            deliverable_id=Deliverable,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return trace.id


def _make_resource_breakdown(
    session: Session, project: Project, fields: Fields, as_of: date
) -> int:
    """A resource type and an RBS node over it — the wizard's own self-contained
    pair, the same shape :func:`_make_requirement_trace` uses: a node needs a
    resource type to point at, and the wizard invents no existing row to reuse."""
    try:
        resource_type = _stage(
            session,
            ResourceType,
            s.ResourceTypeIn(
                project_id=project.id,
                name=_need(fields, "name"),
                kind=_need(fields, "kind"),  # type: ignore[arg-type]
            ),
            project_id=Project,
        )
        node = _stage(
            session,
            ResourceBreakdown,
            s.ResourceBreakdownIn(project_id=project.id, resource_type_id=resource_type.id),
            project_id=Project,
            resource_type_id=ResourceType,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return node.id


def _make_acquisition(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """A resource type and an acquisition against it — the same self-contained
    pair :func:`_make_resource_breakdown` uses."""
    try:
        resource_type = _stage(
            session,
            ResourceType,
            s.ResourceTypeIn(
                project_id=project.id,
                name=_need(fields, "name"),
                kind=_need(fields, "kind"),  # type: ignore[arg-type]
            ),
            project_id=Project,
        )
        acquisition = _stage(
            session,
            Acquisition,
            s.AcquisitionIn(
                project_id=project.id, resource_type_id=resource_type.id, requested_on=as_of
            ),
            project_id=Project,
            resource_type_id=ResourceType,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return acquisition.id


def _make_dependency_edge(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """Two tasks and the precedence edge between them — the wizard's own
    self-contained pair, the same shape :func:`_make_resource_breakdown` uses:
    an edge needs two endpoints to point between, and the wizard invents no
    existing task to reuse rather than guess which pair the caller meant. The
    same cross-row rule the API route runs (``driftless.api.rules.dependency_lands_valid``)
    runs here too, ahead of the write, even though a freshly staged pair can
    never fail it — one validated path, not a second one this producer trusts
    itself to have gotten right."""
    from driftless.api.rules import dependency_lands_valid

    try:
        workstream = _stage(
            session,
            Workstream,
            s.WorkstreamIn(name="Sequencing", project_id=project.id),
            project_id=Project,
        )
        predecessor = _stage(
            session,
            Task,
            s.TaskIn(name=_need(fields, "predecessor_name"), workstream_id=workstream.id),
        )
        successor = _stage(
            session,
            Task,
            s.TaskIn(name=_need(fields, "successor_name"), workstream_id=workstream.id),
        )
        payload = s.TaskDependencyIn(
            predecessor_task_id=predecessor.id, successor_task_id=successor.id
        )
        dependency_lands_valid(session, payload)
        dependency = _stage(
            session,
            TaskDependency,
            payload,
            predecessor_task_id=Task,
            successor_task_id=Task,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dependency.id


def _make_calendar(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """A project's working-day pattern: the row itself IS the calendar, so this
    is the plainest producer here — one schema-validated insert, no pair to
    stage."""
    payload = s.ProjectCalendarIn(project_id=project.id, name=_need(fields, "name"))
    return insert(session, ProjectCalendar, payload, project_id=Project).id


def _make_baseline(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """An approved baseline with one workstream, task and line — so both the scope
    and schedule baselines resolve present. Every row goes through a request schema.

    Refuses while an approved baseline exists (:class:`AlreadyBaselined`): the
    wizard stands the first plan up, never replaces the plan of record; a draft
    does not refuse. The four rows land on ONE commit — per-row commits meant a
    failure on the fourth left a committed ``(vN, 'approved', 0 lines)`` baseline
    plus an orphan workstream and task, unrepairable through the API.
    """
    if approved := [b.version for b in project.baselines if b.status == "approved"]:
        raise AlreadyBaselined(
            f"project {project.name!r} already has an approved baseline "
            f"(v{max(approved)}) — the plan of record. Re-baselining goes through "
            "change control on the API, not the onboarding wizard."
        )
    # Read before anything is staged: planned cost IS BAC, the figure every EVM number on
    # every report is measured against, so substituting one is the costliest invention here.
    cost = float(_need(fields, "planned_cost"))
    unit = "points" if project.delivery_mode == "agile" else "hours"
    try:
        workstream = _stage(
            session,
            Workstream,
            s.WorkstreamIn(name="Delivery", project_id=project.id),
            project_id=Project,
        )
        task = _stage(
            session,
            Task,
            s.TaskIn(name="Baseline task", workstream_id=workstream.id, estimate_unit=unit),  # type: ignore[arg-type]
        )
        baseline = _stage(
            session,
            Baseline,
            s.BaselineIn(
                project_id=project.id,
                version=_next_baseline_version(session, project),
                status="approved",
                # Approval is one fact in two columns, so the stamp is not optional.
                # It comes from the threaded ``as_of``, never the wall clock, so a
                # seeded store is byte-identical for a pinned date.
                approved_at=datetime.combine(as_of, time.min),
            ),
            project_id=Project,
        )
        _stage(
            session,
            BaselineLine,
            s.BaselineLineIn(
                baseline_id=baseline.id,
                task_id=task.id,
                planned_start=as_of,
                planned_finish=as_of,
                planned_cost=cost,
            ),
            baseline_id=Baseline,
            task_id=Task,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return baseline.id


def _make_status_report(session: Session, project: Project, fields: Fields, as_of: date) -> int:
    """The one producer that reaches a sibling service, rather than writing its own row.

    A status report IS a :class:`~driftless.models.StatusSnapshot`, so it is filed
    through :func:`~driftless.services.status_snapshots.create_status_snapshot` — the
    same function the JSON route and the status page call — rather than a second
    copy of "stamp percent from calc." The actor credited is the one :func:`produce`
    already stamped the session with; ``create_status_snapshot`` re-stamps the same
    value, which is idempotent.
    """
    # Checked here rather than left to the table's CHECK: a reading the API would refuse
    # comes back as a refusal a caller can read, not a 500.
    if (rag := _need(fields, "rag_status")) not in RAG_STATUSES:
        raise MissingField(f"rag_status must be one of {', '.join(RAG_STATUSES)}")
    actor = session.info.get(ACTOR_KEY) or "wizard"
    payload = s.StatusSnapshotIn(
        project_id=project.id,
        taken_on=as_of,
        rag_status=rag,  # type: ignore[arg-type]
        note=fields.get("note"),
    )
    return create_status_snapshot(session, payload, actor).id


#: Producible kind -> the ``NarrativeArtifact.kind`` its prose is stored as. These are
#: the only producible kinds whose output IS a body of text, so this is the one place
#: that answers "does this kind need prose typed into it?": ``_PRODUCERS`` is built from
#: it and :func:`body_kinds` reads it, which is what lets the wizard's form ask for a
#: body without a second hand-written kind list to fall out of step with this one.
#: The three legacy kinds keep their short stored names; every prose kind after them is
#: stored under the catalog kind exactly, mirroring ``pmbok.mapping``'s resolvers — so
#: every prose kind the store resolves is one this wizard can put a body into.
#: ``lessons_learned_register`` is no longer here: it produces a :class:`LessonLearned`
#: row now, never prose (see :func:`_make_lesson_learned`), so the retired
#: ``lessons_learned`` narrative kind stays in ``NARRATIVE_KINDS`` unproduced rather
#: than resolved through.
_NARRATIVE = {
    "assumption_log": "assumption_log",
    "enterprise_environmental_factors": "eef",
    "organizational_process_assets": "opa",
    **{
        kind: kind
        for kind in (
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
            "project_scope_statement",
            "requirements_documentation",
            "team_charter",
            "basis_of_estimates",
            "team_performance_assessments",
        )
    },
}

#: The tracked artifact kinds the wizard can produce, each through the boundary.
_PRODUCERS: dict[str, Callable[[Session, Project, Fields, date], int]] = {
    **{kind: _narrative(kind, stored) for kind, stored in _NARRATIVE.items()},
    "risk_register": _make_risk,
    "stakeholder_register": _make_stakeholder,
    "cost_baseline": _make_budget_line,
    "milestone_list": _make_milestone,
    "project_schedule": _make_milestone,
    "issue_log": _make_issue,
    "change_log": _make_change_request,
    "agreements": _make_agreement,
    "quality_report": _make_quality,
    "scope_baseline": _make_baseline,
    "schedule_baseline": _make_baseline,
    "status_report": _make_status_report,
    "work_breakdown_structure": _make_deliverable,
    "requirements_traceability_matrix": _make_requirement_trace,
    "resource_breakdown_structure": _make_resource_breakdown,
    "physical_resource_assignments": _make_acquisition,
    "lessons_learned_register": _make_lesson_learned,
    "project_schedule_network_diagram": _make_dependency_edge,
    "project_calendars": _make_calendar,
}


def producible_kinds() -> tuple[str, ...]:
    """The artifact kinds ``produce`` can create, sorted."""
    return tuple(sorted(_PRODUCERS))


def body_kinds() -> frozenset[str]:
    """The producible kinds whose output is prose — the ones a form must collect a body for.

    Derived from ``_NARRATIVE`` rather than listed again, so a fifth narrative kind
    given a producer is asked for by every form on the same commit.
    """
    return frozenset(_NARRATIVE)


#: What a *seeded* narrative row says. It is honest wherever it lands, because the only
#: thing that puts it there is :func:`seed_fields` — a caller that asked to be seeded.
#: Nothing reads it back: ``pmbok.mapping`` only asks whether a body is non-blank, and
#: no report, page or export treats this string as anything but the prose it stands in for.
SEED_BODY = "(seeded by the onboarding wizard)"

#: What each non-prose kind needs from its caller, mapped to what an unattended driver
#: seeds it with — ONE table behind two answers: :func:`required_fields` tells a form which
#: inputs to render and :func:`seed_fields` answers them for a no-human run. Vocabulary
#: values come from the ORM tuples, and ``{as_of}`` from the threaded date, never a clock.
_ASKS: dict[str, dict[str, str]] = {
    "risk_register": {"description": SEED_BODY, "probability": "0.2", "impact": "1000"},
    "stakeholder_register": {"name": SEED_BODY},
    "cost_baseline": {"category": COST_CATEGORIES[0], "planned_amount": "1000"},
    "milestone_list": {"name": SEED_BODY, "target_date": "{as_of}"},
    "project_schedule": {"name": SEED_BODY, "target_date": "{as_of}"},
    "issue_log": {"description": SEED_BODY},
    "change_log": {"description": SEED_BODY},
    "agreements": {"vendor": SEED_BODY},
    "quality_report": {"metric": SEED_BODY, "target_value": "1", "actual_value": "0.5"},
    "scope_baseline": {"planned_cost": "1000"},
    "schedule_baseline": {"planned_cost": "1000"},
    "status_report": {"rag_status": RAG_STATUSES[0]},
    "work_breakdown_structure": {"name": SEED_BODY, "wbs_code": "1"},
    "requirements_traceability_matrix": {
        "code": "REQ-WIZ",
        "statement": SEED_BODY,
        "name": SEED_BODY,
        "wbs_code": "T1",
    },
    "resource_breakdown_structure": {"name": SEED_BODY, "kind": RESOURCE_KINDS[0]},
    "physical_resource_assignments": {"name": SEED_BODY, "kind": "equipment"},
    "lessons_learned_register": {
        "category": LESSON_CATEGORIES[0],
        "what_happened": SEED_BODY,
        "what_to_do_next_time": SEED_BODY,
        "actor": SEED_BODY,
    },
    "project_calendars": {"name": SEED_BODY},
    "project_schedule_network_diagram": {
        "predecessor_name": SEED_BODY,
        "successor_name": SEED_BODY,
    },
}


def required_fields(kind: str) -> tuple[str, ...]:
    """The field names ``kind`` refuses without — what a form has to collect, read off the
    table the producers refuse against so the two cannot disagree. Prose is not in here: a
    body is asked for through :func:`body_kinds`."""
    return tuple(_ASKS.get(kind, ()))


def seed_fields(kind: str, as_of: date) -> Fields:
    """The fields an *unattended* driver supplies for ``kind`` — seeding and demos.

    No producer invents a value now, so this is the seam that keeps a no-human run
    converging: the placeholders live here, on the seeding side that knows it is seeding,
    not inside the producers where they reached real operators too. ``as_of`` is threaded,
    never a clock, so a seeded store is byte-identical for a pinned date.
    """
    asked = _ASKS.get(kind, {}).items()
    seeded = {name: value.format(as_of=as_of.isoformat()) for name, value in asked}
    return {"body": SEED_BODY, **seeded} if kind in _NARRATIVE else seeded


def produce(
    session: Session, project: Project, kind: str, fields: Fields, as_of: date, actor: str
) -> int:
    """Produce one output ``kind`` through the validated write path; return its row id.

    ``actor`` is required and stamped on the session (:func:`driftless.db.changelog.set_actor`)
    before the producer runs, so the ChangeLog row every write here leaves credits
    who asked for it — the CLI and the browser form both resolve one and hand it in,
    exactly as ``driftless.api.deps.get_session`` already does for every other API
    and web write.

    Raises ``KeyError`` for a kind the wizard cannot produce, ``MissingField`` (its
    ``MissingBody`` case for prose) for one handed less than :func:`required_fields`
    asks for — this path invents none — and ``AlreadyBaselined``
    for a baseline kind on a project whose plan of record is already approved. A driver
    that wants a store stood up with nothing typed passes :func:`seed_fields` and owns
    that choice.
    """
    set_actor(session, actor)
    producer = _PRODUCERS.get(kind)
    if producer is None:
        raise KeyError(f"the wizard cannot produce {kind!r}")
    try:
        return producer(session, project, fields, as_of)
    except MissingField as gap:
        # Named here, once: two kinds share a producer, and "risk_register needs impact"
        # is the whole message a browser 422 and a CLI stderr line have to work from.
        raise type(gap)(f"{kind} {gap}") from None


__all__ = [
    "AlreadyBaselined",
    "Fields",
    "MissingBody",
    "MissingField",
    "SEED_BODY",
    "body_kinds",
    "produce",
    "producible_kinds",
    "required_fields",
    "seed_fields",
]
