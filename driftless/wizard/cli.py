"""The ``driftless wizard`` command — the agent-drivable onboarding surface.

Three subcommands: ``next`` prints the next process to work (JSON), ``status``
prints the whole process-state map (JSON), and ``apply`` produces one output.
Producing goes through ``produce`` below, which reuses the API's own validated
write path — the Pydantic request schemas plus ``driftless.api.app.insert`` — so a
wizard write is validated and audited on the ChangeLog exactly as an HTTP write
is. That is why this module (an entry point) may import the API while the wizard
engine stays below it.

So the loop that drives this — human or agent — can stand a project up end to
end without touching the database directly: ``next`` says what to make, ``apply``
makes it through the boundary, ``status`` confirms it landed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.app import fetch, insert, stamped_percent
from driftless.cli_support import resolve_project
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.db.config import database_url
from driftless.models import (
    COST_CATEGORIES,
    RAG_STATUSES,
    Baseline,
    BaselineLine,
    BudgetLine,
    ChangeRequest,
    Issue,
    Milestone,
    NarrativeArtifact,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    Risk,
    Stakeholder,
    StatusSnapshot,
    Task,
    Workstream,
)
from driftless.pmbok import state
from driftless.pmbok.model import ProcessGroup
from driftless.wizard import engine

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


def _stage(session: Session, model: type[M], payload: BaseModel, **parents: type[Base]) -> M:
    """``api.app.insert`` minus the per-row commit: same schema dump, same parent
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
    """The one bespoke write: a status snapshot whose percent is stamped from calc."""
    # Checked here rather than left to the table's CHECK: a reading the API would refuse
    # comes back as a refusal a caller can read, not a 500.
    if (rag := _need(fields, "rag_status")) not in RAG_STATUSES:
        raise MissingField(f"rag_status must be one of {', '.join(RAG_STATUSES)}")
    row = StatusSnapshot(
        project_id=project.id,
        taken_on=as_of,
        rag_status=rag,
        note=fields.get("note"),
        percent_complete=stamped_percent(session, project, as_of),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.id


#: Producible kind -> the ``NarrativeArtifact.kind`` its prose is stored as. These are
#: the only producible kinds whose output IS a body of text, so this is the one place
#: that answers "does this kind need prose typed into it?": ``_PRODUCERS`` is built from
#: it and :func:`body_kinds` reads it, which is what lets the wizard's form ask for a
#: body without a second hand-written kind list to fall out of step with this one.
#: The four legacy kinds keep their short stored names; every prose kind after them is
#: stored under the catalog kind exactly, mirroring ``pmbok.mapping``'s resolvers — so
#: every prose kind the store resolves is one this wizard can put a body into.
_NARRATIVE = {
    "assumption_log": "assumption_log",
    "lessons_learned_register": "lessons_learned",
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


def produce(session: Session, project: Project, kind: str, fields: Fields, as_of: date) -> int:
    """Produce one output ``kind`` through the validated write path; return its row id.

    Raises ``KeyError`` for a kind the wizard cannot produce, ``MissingField`` (its
    ``MissingBody`` case for prose) for one handed less than :func:`required_fields`
    asks for — this path invents none — and ``AlreadyBaselined``
    for a baseline kind on a project whose plan of record is already approved. A driver
    that wants a store stood up with nothing typed passes :func:`seed_fields` and owns
    that choice.
    """
    producer = _PRODUCERS.get(kind)
    if producer is None:
        raise KeyError(f"the wizard cannot produce {kind!r}")
    try:
        return producer(session, project, fields, as_of)
    except MissingField as gap:
        # Named here, once: two kinds share a producer, and "risk_register needs impact"
        # is the whole message a browser 422 and a CLI stderr line have to work from.
        raise type(gap)(f"{kind} {gap}") from None


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit(
            "error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL "
            "(the legacy PMHUB_DATABASE_URL and PMHUB_DB_URL aliases are still honoured)"
        )
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # wizard writes are audited, exactly like the API's
    return factory()


def _parse_fields(pairs: list[str] | None) -> Fields:
    fields: Fields = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        fields[key] = value
    return fields


def _run_next(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        groups = [ProcessGroup(g) for g in args.group] if args.group else None
        # next_step's per-process scan (state.process_state / mapping.resolve)
        # rides the same cache — mirrors the identical wrap on the web wizard
        # page (driftless.web.pages.wizard_page).
        with state.prefetched(session, [project]):
            step = engine.next_step(session, project, as_of, groups)
        print(json.dumps(dataclasses.asdict(step) if step is not None else None, indent=2))
    return 0


def _run_status(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        # status walks every catalog process (project_process_states), the same
        # store-wide shape the process-map document/page bound with this cache.
        with state.prefetched(session, [project]):
            statuses = engine.status(session, project, as_of)
        print(json.dumps(dict(statuses), indent=2))
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        fields = _parse_fields(args.field)
        if args.process is not None:
            fields["origin_process_id"] = args.process
        try:
            row_id = produce(session, project, args.kind, fields, as_of)
        except (KeyError, ValueError) as error:
            # Same refusal the browser form answers 422 with, in the CLI's currency: a
            # message on stderr and rc 2. One surface inventing a value the other refuses
            # is how the placeholders outlived the form fix. ValueError catches them all,
            # pydantic's ValidationError included — a bad --field is not a traceback.
            print(f"error: {error}", file=sys.stderr)
            return 2
        print(f"produced {args.kind} (row {row_id})")
    return 0


def add_wizard_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``wizard`` command onto a parent's subparsers."""
    wizard = commands.add_parser("wizard", help="drive project onboarding")
    sub = wizard.add_subparsers(dest="wizard_command", required=True)

    def _common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--project", required=True, help="project name or id")
        parser.add_argument("--as-of", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD")
        parser.add_argument("--db-url", default=None, metavar="URL")

    nxt = sub.add_parser("next", help="the next process to work, as JSON")
    _common(nxt)
    nxt.add_argument(
        "--group",
        action="append",
        choices=[g.value for g in ProcessGroup],
        help="restrict to these process groups (repeatable)",
    )
    nxt.set_defaults(handler=_run_next)

    stat = sub.add_parser("status", help="the whole process-state map, as JSON")
    _common(stat)
    stat.set_defaults(handler=_run_status)

    apply = sub.add_parser("apply", help="produce one output through the API boundary")
    _common(apply)
    apply.add_argument("--kind", required=True, choices=producible_kinds())
    apply.add_argument(
        "--field",
        action="append",
        metavar="KEY=VALUE",
        help="output field, repeatable; each kind requires the fields it is made of and "
        "the wizard refuses rather than inventing one (prose kinds body=…, risk_register "
        "description=… probability=… impact=…) — see the README for the per-kind list",
    )
    apply.add_argument(
        "--process",
        default=None,
        metavar="ID",
        help="PMBOK clause id of the process raising this output (e.g. 5.6); "
        "validated against the live catalog at the schema boundary",
    )
    apply.set_defaults(handler=_run_apply)
