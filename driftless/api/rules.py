"""The invariants a write must satisfy before it reaches the database.

These are the rules a CHECK constraint cannot express, because each one needs a
query: that a task's estimate unit matches its project's delivery mode, that a
baseline line points at a task inside the same project, that moving a portfolio
does not strand children in another business. The database enforces shape;
this module enforces relationships across rows.

Each rule raises ``HTTPException`` and returns ``None`` — never a bool — so a
caller cannot accidentally ignore a falsy result and write anyway. They come in
two arities, matching the two moments a write can be refused: ``(db, payload)``
before a create, and ``(db, row, data)`` before a patch, where ``data`` is the
patch as submitted rather than the merged result. A rule that must see the
merged state says so by reading both.

Registration lives in ``driftless.api.app``, which names these as the ``Check``
callables it hangs off each route; the ones with no caller there are helpers the
other rules share.
"""

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import fetch
from driftless.models import (
    BacklogItem,
    Baseline,
    BaselineLine,
    Deliverable,
    Department,
    DepartmentService,
    OPPORTUNITY_STRATEGIES,
    OperatingControl,
    Portfolio,
    Program,
    Project,
    QualityMetric,
    Requirement,
    ResourceBreakdown,
    Risk,
    ScorecardContribution,
    ScorecardSource,
    Sprint,
    Stakeholder,
    StrategicObjective,
    THREAT_STRATEGIES,
    Task,
    Workstream,
)
from driftless.services.schedule_writes import refuse_dependency_cycle

Check = Callable[[Session, Any, dict[str, Any]], None]  # a rule run over a pending patch
CreateCheck = Callable[[Session, Any], None]  # a rule run over a create payload
DeleteCheck = Callable[[Session, Any], None]  # a rule run over a row about to be deleted

_UNIT_FOR_MODE = {"agile": "points", "predictive": "hours"}  # hybrid takes either


def require_matching_unit(db: Session, workstream_id: int, estimate_unit: str) -> None:
    """Reject a unit the project's mode does not use — a rule spanning two rows."""
    project = fetch(db, Workstream, workstream_id).project
    required = _UNIT_FOR_MODE.get(project.delivery_mode)
    if required is not None and estimate_unit != required:
        raise HTTPException(
            422,
            f"a {project.delivery_mode} project estimates in {required}, not {estimate_unit}",
        )


def metric_source_is_registered(db: Session, payload: Any) -> None:
    """A connector key must be an active source owned by the objective's business."""
    if payload.source_type != "registered_connector":
        return
    objective = fetch(db, StrategicObjective, payload.objective_id)
    source = db.scalar(
        select(ScorecardSource).where(
            ScorecardSource.business_id == objective.business_id,
            ScorecardSource.key == payload.source_key,
        )
    )
    if source is None:
        raise HTTPException(
            404, f"Scorecard source {payload.source_key!r} not found for objective business"
        )
    if source.status != "active":
        raise HTTPException(409, f"Scorecard source {payload.source_key!r} is retired")


def contribution_stays_in_business(db: Session, payload: Any) -> None:
    project = fetch(db, Project, payload.project_id)
    objective = fetch(db, StrategicObjective, payload.objective_id)
    if project.portfolio.business_id != objective.business_id:
        raise HTTPException(
            409,
            f"Project {project.id} and StrategicObjective {objective.id} belong to different businesses",
        )


def contribution_patch_stays_in_business(
    db: Session, row: ScorecardContribution, data: dict[str, Any]
) -> None:
    project = fetch(db, Project, data.get("project_id", row.project_id))
    objective = fetch(db, StrategicObjective, data.get("objective_id", row.objective_id))
    if project.portfolio.business_id != objective.business_id:
        raise HTTPException(
            409,
            f"Project {project.id} and StrategicObjective {objective.id} belong to different businesses",
        )


def _task_unit_still_matches(db: Session, row: Task, data: dict[str, Any]) -> None:
    """The same rule, applied to the task as the patch will leave it — not as it is."""
    require_matching_unit(
        db,
        data.get("workstream_id", row.workstream_id),
        data.get("estimate_unit", row.estimate_unit),
    )


def _task_stays_in_its_project(db: Session, row: Task, data: dict[str, Any]) -> None:
    """A task is refiled between its own project's workstreams, never across projects.

    Within one project the move changes nothing any rollup reads, and it is the
    only correction a misfiled task has once its baseline is approved — the plan
    freeze refuses the line delete, and the delete guard refuses the task. A
    target workstream in another project is refused outright: it would carry the
    task's estimates and baseline lines out of one project's numbers into
    another's, the same hole the line-side rule closes from the other end.
    """
    workstream_id = data.get("workstream_id", row.workstream_id)
    if workstream_id == row.workstream_id:
        return
    home = row.workstream.project_id
    target = fetch(db, Workstream, workstream_id).project_id
    if target != home:
        raise HTTPException(
            409,
            f"Workstream {workstream_id} belongs to project {target}, not project {home}; "
            f"a task moves only between its own project's workstreams",
        )


def task_patch_stays_valid(db: Session, row: Task, data: dict[str, Any]) -> None:
    """Every cross-row task rule, applied to the task as the patch will leave it."""
    _task_stays_in_its_project(db, row, data)
    _task_unit_still_matches(db, row, data)


def _refuse_stranded_units(db: Session, mode: str, owned: ColumnElement[bool]) -> None:
    """Refuse a move that would leave ``owned`` tasks estimating in a unit ``mode`` never uses.

    A flip that landed would write-lock every mismatched task: the row itself
    violates ``_task_unit_still_matches``, so each later task PATCH answers 422
    until the flip is reverted. Refusing here keeps that state unconstructable.
    """
    required = _UNIT_FOR_MODE.get(mode)
    if required is None:  # hybrid takes either unit
        return
    stranded = db.scalars(
        select(Task.id).where(owned, Task.estimate_unit != required).order_by(Task.id)
    ).all()
    if stranded:
        ids = ", ".join(str(task_id) for task_id in stranded)
        raise HTTPException(
            409,
            f"a {mode} project estimates in {required}; "
            f"{len(stranded)} task(s) ({ids}) would not — move or re-unit them first",
        )


def _project_mode_still_fits_tasks(db: Session, row: Project, data: dict[str, Any]) -> None:
    """The unit rule from the project side: no mode flip over mismatched tasks."""
    mode = data.get("delivery_mode", row.delivery_mode)
    if mode != row.delivery_mode:
        under = select(Workstream.id).where(Workstream.project_id == row.id)
        _refuse_stranded_units(db, mode, Task.workstream_id.in_(under))


def project_still_consistent(db: Session, row: Project, data: dict[str, Any]) -> None:
    """Every cross-row project rule, applied to the row as the patch will leave it."""
    _project_program_still_home(db, row, data)
    _project_stays_in_its_business(db, row, data)
    require_department_in_business(
        db,
        data.get("portfolio_id", row.portfolio_id),
        data.get("responsible_department_id", row.responsible_department_id),
    )
    _project_mode_still_fits_tasks(db, row, data)


def _workstream_tasks_still_fit(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """The unit rule from the workstream side: its tasks must fit the target project's mode."""
    project_id = data.get("project_id", row.project_id)
    if project_id != row.project_id:
        project = fetch(db, Project, project_id)
        _refuse_stranded_units(db, project.delivery_mode, Task.workstream_id == row.id)


def _workstream_tasks_stay_home(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """A workstream move is a batched task move — refuse it while tasks would follow.

    A task's home project is derived through its workstream, so this move carried
    every task under it across the boundary ``_task_stays_in_its_project`` refuses
    one task at a time — in a single 200 that never touched a task row, and never
    passed the plan freeze, leaving an approved baseline's line planning work that
    now lives elsewhere. Emptied, the move is legitimate and still goes through.
    """
    if data.get("project_id", row.project_id) == row.project_id:
        return
    carried = db.scalars(select(Task.id).where(Task.workstream_id == row.id)).all()
    if carried:
        ids = ", ".join(str(task_id) for task_id in sorted(carried))
        raise HTTPException(
            409,
            f"Workstream {row.id} still has {len(carried)} task(s) ({ids}); "
            f"a task does not change project by patch — move them first",
        )


def workstream_patch_stays_valid(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """Every workstream patch rule: no task crosses a project, and units still fit."""
    _workstream_tasks_stay_home(db, row, data)
    _workstream_tasks_still_fit(db, row, data)


def _require_baseline_open(db: Session, baseline_id: int) -> None:
    """An approved baseline is the plan of record — writes are refused, not merged.

    ``models.delivery`` holds the approval fact and leaves refusal to this layer
    deliberately. The check reads the row as it stands, so the approval PATCH
    itself — stamping ``approved_at`` onto a draft — is the one write that
    passes, and every write after it answers 409.

    Approval is read from *either* signal. Both write paths now hold the two in
    step (``schemas.approval_is_atomic``), so they cannot disagree; keying on
    either is defence in depth, so a row that somehow carries only one — a legacy
    row, a future path that sets the status alone — is still the plan of record
    and still frozen, rather than silently editable and deletable.
    """
    baseline = fetch(db, Baseline, baseline_id)
    if baseline.status == "approved" or baseline.approved_at is not None:
        raise HTTPException(
            409,
            f"Baseline {baseline_id} is approved (at {baseline.approved_at}); "
            f"a plan change is a new version",
        )


def _baseline_still_open(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    _require_baseline_open(db, row.id)


def _baseline_approval_stays_atomic(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    """``status == "approved"`` and ``approved_at`` move together or not at all.

    The rule itself is ``schemas.approval_is_atomic`` — stated once, so the two
    write paths cannot drift apart. A create settles it in the request type; a
    patch carries only some of the fields, so it is asked here of the row as the
    patch will leave it.
    """
    if not s.approval_is_atomic(
        data.get("status", row.status), data.get("approved_at", row.approved_at)
    ):
        raise HTTPException(
            422, "a baseline's status 'approved' and approved_at must be set together"
        )


def baseline_patch_stays_valid(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    """Every baseline patch rule: an approved plan is frozen, and approval is atomic."""
    _baseline_still_open(db, row, data)
    _baseline_approval_stays_atomic(db, row, data)


def baseline_delete_only_while_open(db: Session, row: Baseline) -> None:
    """Deleting an approved baseline vaporizes the plan of record — refuse it.

    Draining a baseline's lines then deleting it would erase the numbers a report
    was built from with no child left for the generic delete guard to catch. This
    mirrors ``line_leaves_baseline_open`` on the line side.
    """
    _require_baseline_open(db, row.id)


def _require_line_inside_project(db: Session, baseline_id: int, task_id: int) -> None:
    """A line may only plan a task of its baseline's own project — a rule spanning rows.

    Without it one project's EV silently borrows another's task, and both
    projects report numbers built from work only one of them owns.
    """
    baseline = fetch(db, Baseline, baseline_id)
    home = fetch(db, Task, task_id).workstream.project_id
    if home != baseline.project_id:
        raise HTTPException(
            422,
            f"Task {task_id} belongs to project {home}, "
            f"not project {baseline.project_id} that Baseline {baseline_id} plans",
        )


def line_lands_open_and_inside(db: Session, payload: Any) -> None:
    _require_baseline_open(db, payload.baseline_id)
    _require_line_inside_project(db, payload.baseline_id, payload.task_id)


def line_still_open_and_inside(db: Session, row: BaselineLine, data: dict[str, Any]) -> None:
    _require_baseline_open(db, row.baseline_id)
    baseline_id = data.get("baseline_id", row.baseline_id)
    if baseline_id != row.baseline_id:
        _require_baseline_open(db, baseline_id)  # nor may a line slide into an approved plan
    _require_line_inside_project(db, baseline_id, data.get("task_id", row.task_id))


def line_leaves_baseline_open(db: Session, row: BaselineLine) -> None:
    _require_baseline_open(db, row.baseline_id)


def require_program_in_portfolio(db: Session, portfolio_id: int, program_id: int | None) -> None:
    """Reject a program from another portfolio — a rule spanning two rows.

    Without it the row would land but vanish from every rollup surface: the
    grouped walk only yields a portfolio's own programs, so a project filed
    under a foreign program has no bucket to appear in.
    """
    if program_id is None:
        return
    program = fetch(db, Program, program_id)
    if program.portfolio_id != portfolio_id:
        raise HTTPException(
            422,
            f"Program {program_id} lives in portfolio {program.portfolio_id}, "
            f"not portfolio {portfolio_id}",
        )


def _project_program_still_home(db: Session, row: Project, data: dict[str, Any]) -> None:
    """The same rule, applied to the project as the patch will leave it — not as it is."""
    require_program_in_portfolio(
        db,
        data.get("portfolio_id", row.portfolio_id),
        data.get("program_id", row.program_id),
    )


def program_projects_still_home(db: Session, row: Program, data: dict[str, Any]) -> None:
    """Refuse to move a program out from under its projects — a rule spanning rows.

    Changing ``portfolio_id`` while projects reference the program creates
    exactly the stray rows the grouped rollup walk fails loudly on, taking the
    dashboard down with it. Delete refuses to orphan children; so does a move.
    """
    if data.get("portfolio_id", row.portfolio_id) == row.portfolio_id:
        return
    stranded = db.scalars(
        select(Project.id).where(Project.program_id == row.id).order_by(Project.id)
    ).all()
    if stranded:
        ids = ", ".join(str(project_id) for project_id in stranded)
        raise HTTPException(
            409,
            f"Program {row.id} still has {len(stranded)} project(s) ({ids}); move them first",
        )


def _refuse_move_with_children(label: str, row_id: int, held: dict[str, bool]) -> None:
    """Refuse a business move that would drag rows along, naming what holds it.

    Reads like the delete guard on purpose — "still has programs" — because it
    refuses the same loss for the same reason: everything under the row would
    change business in one call, and both businesses' rollups would silently
    restate. Emptied, the move is legitimate and goes through.
    """
    kinds = [kind for kind, present in held.items() if present]
    if kinds:
        raise HTTPException(409, f"{label} {row_id} still has {', '.join(kinds)}; move them first")


def portfolio_children_stay_home(db: Session, row: Portfolio, data: dict[str, Any]) -> None:
    """A portfolio carries every program, project and record under it — no silent move."""
    if data.get("business_id", row.business_id) != row.business_id:
        _refuse_move_with_children(
            "Portfolio", row.id, {"programs": bool(row.programs), "projects": bool(row.projects)}
        )


def department_children_stay_home(db: Session, row: Department, data: dict[str, Any]) -> None:
    """A department's people, the projects it answers for, and every operating
    record it keeps (its own service catalog, work queue, recurring work,
    SLAs, controls, incidents, improvements and budget lines) all belong to
    its business — a business move would silently drag every one of them into
    a business that never owned the work."""
    if data.get("business_id", row.business_id) != row.business_id:
        responsible = db.scalar(
            select(Project.id).where(Project.responsible_department_id == row.id)
        )
        _refuse_move_with_children(
            "Department",
            row.id,
            {
                "people": bool(row.people),
                "responsible projects": responsible is not None,
                "department_services": bool(row.department_services),
                "work_requests": bool(row.work_requests),
                "recurring_work_items": bool(row.recurring_work_items),
                "service_levels": bool(row.service_levels),
                "operating_controls": bool(row.operating_controls),
                "incidents": bool(row.incidents),
                "improvements": bool(row.improvements),
                "budget_lines": bool(row.budget_lines),
            },
        )


def _business_of(db: Session, portfolio_id: int) -> int:
    return fetch(db, Portfolio, portfolio_id).business_id


def _project_stays_in_its_business(db: Session, row: Project, data: dict[str, Any]) -> None:
    """A patch may re-file a project inside its business, never across businesses.

    ``require_program_in_portfolio`` returns early for a programless project and
    ``program_id`` is nullable by design, so that rule alone left the common case
    free to land under any portfolio anywhere — taking its cost entries and every
    record under it out of the business that owns the work.
    """
    portfolio_id = data.get("portfolio_id", row.portfolio_id)
    if portfolio_id == row.portfolio_id:
        return
    home, target = _business_of(db, row.portfolio_id), _business_of(db, portfolio_id)
    if target != home:
        raise HTTPException(
            409,
            f"Portfolio {portfolio_id} is in business {target}, not business {home}; "
            f"Project {row.id} does not change business by patch",
        )


def require_department_in_business(
    db: Session, portfolio_id: int, department_id: int | None
) -> None:
    """Reject a responsible department from another business — a rule spanning rows.

    The Department report rolls a business's projects up by the department
    accountable for each, so a foreign department files a project's numbers
    under a business that does not own the work.
    """
    if department_id is None:
        return
    business_id = _business_of(db, portfolio_id)
    department = fetch(db, Department, department_id)
    if department.business_id != business_id:
        raise HTTPException(
            409,
            f"Department {department_id} is in business {department.business_id}, "
            f"not business {business_id} that this project's portfolio belongs to",
        )


def link_stays_in_project(
    model: type[Risk] | type[Baseline] | type[QualityMetric] | type[Stakeholder], field: str
) -> tuple[CreateCheck, Check]:
    """Build the create *and* patch rules that keep a secondary link inside its project.

    ``Issue.risk_id`` and ``ChangeRequest.resulting_baseline_id`` are links rather
    than parents, so the patch twin keeps them — and neither write path scoped
    them at all. Every reader takes the link as same-project by construction: the
    risk register reads a risk's issues as its own lineage, and the scope report
    reads a change request's baseline as the plan version it produced. Both rules
    come from one call, so a registration cannot wire the create and forget the
    patch.
    """

    def require(db: Session, link_id: int | None, project_id: int) -> None:
        if link_id is None:
            return
        home = fetch(db, model, link_id).project_id
        if home != project_id:
            raise HTTPException(
                409,
                f"{model.__name__} {link_id} belongs to project {home}, not project "
                f"{project_id}; {field} links only inside its own project",
            )

    def on_create(db: Session, payload: Any) -> None:
        require(db, getattr(payload, field), payload.project_id)

    def on_patch(db: Session, row: Any, data: dict[str, Any]) -> None:
        require(db, data.get(field, getattr(row, field)), row.project_id)

    return on_create, on_patch


def link_stays_in_department(
    model: type[DepartmentService] | type[OperatingControl], field: str
) -> tuple[CreateCheck, Check]:
    """The same rule as :func:`link_stays_in_project`, scoped to a department instead.

    ``WorkRequest.service_id``, ``ServiceLevel.service_id`` and
    ``Incident.control_id`` are links, not parents (``models.operations`` module
    docstring) — a request/SLA may name no service, an incident may name no
    control — so the patch twin keeps them and neither write path scoped them
    at all until this closes it.
    """

    def require(db: Session, link_id: int | None, department_id: int) -> None:
        if link_id is None:
            return
        home = fetch(db, model, link_id).department_id
        if home != department_id:
            raise HTTPException(
                409,
                f"{model.__name__} {link_id} belongs to department {home}, not department "
                f"{department_id}; {field} links only inside its own department",
            )

    def on_create(db: Session, payload: Any) -> None:
        require(db, getattr(payload, field), payload.department_id)

    def on_patch(db: Session, row: Any, data: dict[str, Any]) -> None:
        require(db, data.get(field, getattr(row, field)), row.department_id)

    return on_create, on_patch


def sprint_window_still_ordered(db: Session, row: Sprint, data: dict[str, Any]) -> None:
    """The ``SprintIn`` date-order rule, applied to the sprint as the patch will leave it."""
    start = data.get("start_date", row.start_date)
    end = data.get("end_date", row.end_date)
    if end <= start:
        raise HTTPException(422, f"end_date {end} must be strictly after start_date {start}")


def _require_dependency_inside_one_project(
    db: Session, predecessor_task_id: int, successor_task_id: int
) -> None:
    """A dependency's two tasks must share a project — a rule spanning two rows.

    Without it one project's network silently borrows another's task, and the
    gantt page's dependency table would draw an edge that names a task no
    reader of this project's schedule can see.
    """
    predecessor = fetch(db, Task, predecessor_task_id).workstream.project_id
    successor = fetch(db, Task, successor_task_id).workstream.project_id
    if predecessor != successor:
        raise HTTPException(
            422,
            f"Task {predecessor_task_id} belongs to project {predecessor}, "
            f"Task {successor_task_id} to project {successor}; "
            f"a dependency links only tasks of the same project",
        )


def dependency_lands_valid(db: Session, payload: Any) -> None:
    """Every ``TaskDependency`` create rule: same project, and no cycle.

    ``predecessor_task_id``/``successor_task_id`` are frozen on the patch twin
    (``api.schemas._FROZEN_FK``) — a dependency is refiled by delete and
    recreate, never re-pointed — so this is the only write path either rule
    has to guard.
    """
    _require_dependency_inside_one_project(
        db, payload.predecessor_task_id, payload.successor_task_id
    )
    refuse_dependency_cycle(db, payload.predecessor_task_id, payload.successor_task_id)


def _require_estimate_subject_inside_project(
    db: Session, project_id: int, subject_task_id: int | None
) -> None:
    """Reject an estimate scenario's subject task from another project.

    ``EstimateScenario.subject_task_id`` is a link, not a parent (its own
    project comes from ``project_id``), the same shape ``Issue.risk_id``
    already uses — so neither write path scopes it without this rule.
    """
    if subject_task_id is None:
        return
    home = fetch(db, Task, subject_task_id).workstream.project_id
    if home != project_id:
        raise HTTPException(
            409,
            f"Task {subject_task_id} belongs to project {home}, not project "
            f"{project_id}; subject_task_id links only inside its own project",
        )


def estimate_scenario_lands_valid(db: Session, payload: Any) -> None:
    _require_estimate_subject_inside_project(db, payload.project_id, payload.subject_task_id)


def estimate_scenario_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    _require_estimate_subject_inside_project(
        db,
        data.get("project_id", row.project_id),
        data.get("subject_task_id", row.subject_task_id),
    )


def _require_response_inside_project(db: Session, risk_id: int, project_id: int) -> Risk:
    """A response's risk must belong to its own ``project_id`` — the same rule
    ``link_stays_in_project`` gives ``Issue.risk_id``, folded in here because a
    write route accepts only one ``Check`` and this resource needs two rules."""
    risk = fetch(db, Risk, risk_id)
    if risk.project_id != project_id:
        raise HTTPException(
            409,
            f"Risk {risk_id} belongs to project {risk.project_id}, not project "
            f"{project_id}; risk_id links only inside its own project",
        )
    return risk


def _require_strategy_matches_kind(kind: str, strategy: str) -> None:
    """A response's ``strategy`` must belong to its risk's ``kind`` family.

    A column CHECK sees only ``risk_response`` itself, so it can enforce that
    ``strategy`` is ONE OF the eight-value union but not that it is the RIGHT
    half of it for this particular risk — that needs the risk's own ``kind``,
    a different row. ``escalate`` and ``accept`` are common to both families and
    never refused either way.
    """
    allowed = THREAT_STRATEGIES if kind == "threat" else OPPORTUNITY_STRATEGIES
    if strategy not in allowed:
        raise HTTPException(
            422,
            f"strategy {strategy!r} does not apply to a {kind} risk; "
            f"choose one of {sorted(allowed)}",
        )


def risk_response_lands_valid(db: Session, payload: Any) -> None:
    risk = _require_response_inside_project(db, payload.risk_id, payload.project_id)
    _require_strategy_matches_kind(risk.kind, payload.strategy)


def risk_response_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    risk = _require_response_inside_project(
        db, data.get("risk_id", row.risk_id), data.get("project_id", row.project_id)
    )
    _require_strategy_matches_kind(risk.kind, data.get("strategy", row.strategy))


def _target_project(
    db: Session, deliverable_id: int | None, task_id: int | None, backlog_item_id: int | None
) -> int:
    """The project the trace's one named target actually belongs to.

    Exactly one of the three is set — ``RequirementTraceIn``'s own validator refuses
    any other shape before a rule here ever runs — so this reads whichever one it is.
    """
    if deliverable_id is not None:
        return fetch(db, Deliverable, deliverable_id).project_id
    if task_id is not None:
        return fetch(db, Task, task_id).workstream.project_id
    assert backlog_item_id is not None
    return fetch(db, BacklogItem, backlog_item_id).project_id


def _require_trace_inside_project(
    db: Session,
    requirement_id: int,
    deliverable_id: int | None,
    task_id: int | None,
    backlog_item_id: int | None,
) -> None:
    """A trace's requirement and its one target must share a project — the same
    "no borrowing another project's row" rule :func:`_require_dependency_inside_one_project`
    already gives task dependencies."""
    requirement = fetch(db, Requirement, requirement_id)
    target_project = _target_project(db, deliverable_id, task_id, backlog_item_id)
    if requirement.project_id != target_project:
        raise HTTPException(
            422,
            f"Requirement {requirement_id} belongs to project {requirement.project_id}, "
            f"its traced target to project {target_project}; a trace links only "
            f"inside its own project",
        )


def requirement_trace_lands_valid(db: Session, payload: Any) -> None:
    _require_trace_inside_project(
        db,
        payload.requirement_id,
        payload.deliverable_id,
        payload.task_id,
        payload.backlog_item_id,
    )


def requirement_trace_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    _require_trace_inside_project(
        db,
        data.get("requirement_id", row.requirement_id),
        data.get("deliverable_id", row.deliverable_id),
        data.get("task_id", row.task_id),
        data.get("backlog_item_id", row.backlog_item_id),
    )


def _require_parent_inside_project(db: Session, project_id: int, parent_id: int | None) -> None:
    """A deliverable's parent must sit in the same project — the WBS tree never
    borrows a node from another project's decomposition."""
    if parent_id is None:
        return
    home = fetch(db, Deliverable, parent_id).project_id
    if home != project_id:
        raise HTTPException(
            409,
            f"Deliverable {parent_id} belongs to project {home}, not project "
            f"{project_id}; parent_id links only inside its own project",
        )


def deliverable_lands_valid(db: Session, payload: Any) -> None:
    _require_parent_inside_project(db, payload.project_id, payload.parent_id)


def deliverable_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    _require_parent_inside_project(
        db, data.get("project_id", row.project_id), data.get("parent_id", row.parent_id)
    )


def _require_rbs_parent_inside_project(db: Session, project_id: int, parent_id: int | None) -> None:
    """A resource-breakdown node's parent must sit in the same project — the same
    "no borrowing another project's node" rule the WBS tree already gives
    ``Deliverable.parent_id`` (:func:`_require_parent_inside_project`)."""
    if parent_id is None:
        return
    home = fetch(db, ResourceBreakdown, parent_id).project_id
    if home != project_id:
        raise HTTPException(
            409,
            f"ResourceBreakdown {parent_id} belongs to project {home}, not project "
            f"{project_id}; parent_id links only inside its own project",
        )


def resource_breakdown_lands_valid(db: Session, payload: Any) -> None:
    _require_rbs_parent_inside_project(db, payload.project_id, payload.parent_id)


def resource_breakdown_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    _require_rbs_parent_inside_project(
        db, data.get("project_id", row.project_id), data.get("parent_id", row.parent_id)
    )


def _target_project_for_assignment(
    db: Session, deliverable_id: int | None, task_id: int | None
) -> int:
    """The project a responsibility assignment's one named target belongs to.

    Exactly one of the two is set — ``ResponsibilityAssignmentIn``'s own validator
    refuses any other shape before a rule here ever runs — so this reads whichever
    one it is, the same shape :func:`_target_project` reads for a requirement trace.
    """
    if deliverable_id is not None:
        return fetch(db, Deliverable, deliverable_id).project_id
    assert task_id is not None
    return fetch(db, Task, task_id).workstream.project_id


def _require_assignment_inside_project(
    db: Session, project_id: int, deliverable_id: int | None, task_id: int | None
) -> None:
    """A responsibility assignment's target must share its own ``project_id`` — the
    same "no borrowing another project's row" rule a requirement trace already gets."""
    target_project = _target_project_for_assignment(db, deliverable_id, task_id)
    if project_id != target_project:
        raise HTTPException(
            422,
            f"ResponsibilityAssignment's target belongs to project {target_project}, not "
            f"project {project_id}; an assignment links only inside its own project",
        )


def responsibility_assignment_lands_valid(db: Session, payload: Any) -> None:
    _require_assignment_inside_project(
        db, payload.project_id, payload.deliverable_id, payload.task_id
    )


def responsibility_assignment_stays_valid(db: Session, row: Any, data: dict[str, Any]) -> None:
    _require_assignment_inside_project(
        db,
        data.get("project_id", row.project_id),
        data.get("deliverable_id", row.deliverable_id),
        data.get("task_id", row.task_id),
    )
