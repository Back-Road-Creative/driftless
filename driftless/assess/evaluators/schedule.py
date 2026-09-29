"""Schedule knowledge-area evaluator: schedule performance and milestone slip.

Signal: SPI, whether any milestone has slipped — marked ``missed`` outright,
or still open past its baseline — and whether the approved baseline's own
STORED task dates fall outside the window (read-only check) its own
``calc.network`` forward/backward pass allows. Red when any milestone has
slipped, SPI < 0.9, or a stored date disagrees; amber when SPI < 1.0 but not
yet red; green otherwise, and when there is nothing to assess. Pure and
as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.calc.network import (
    Activity,
    Dependency,
    DependencyKind,
    ScheduleNetwork,
    network_disagreements,
)
from driftless.models import Milestone, Project, Task, TaskDependency, Workstream
from driftless.pmbok.state import threat_subject_ref

KIND = "schedule"

_AMBER_SPI = 1.0
_RED_SPI = 0.9


def _stored_network(
    session: Session, project: Project, as_of: date
) -> tuple[ScheduleNetwork, dict[str, int], dict[str, int], dict[str, str]] | None:
    """The approved baseline's own network, each task's stored start/finish
    day-offset from its earliest planned start, and its name — ``None`` when
    there is no approved, lined baseline to build one from."""
    baseline = adapters.plan_baseline(project, as_of)
    if baseline is None or not baseline.lines:
        return None
    lines = sorted(baseline.lines, key=lambda line: line.task_id)
    anchor = min(line.planned_start for line in lines)
    activities = tuple(
        Activity(
            id=str(line.task_id), duration=max((line.planned_finish - line.planned_start).days, 0)
        )
        for line in lines
    )
    stored_start = {str(line.task_id): (line.planned_start - anchor).days for line in lines}
    stored_finish = {str(line.task_id): (line.planned_finish - anchor).days for line in lines}
    task_names = {str(line.task_id): line.task.name for line in lines}
    task_ids = {line.task_id for line in lines}
    dependencies = tuple(
        Dependency(
            predecessor=str(dep.predecessor_task_id),
            successor=str(dep.successor_task_id),
            kind=cast(DependencyKind, dep.kind),
            lag=dep.lag_days,
        )
        for dep in _dependencies(session, project.id)
        if dep.predecessor_task_id in task_ids and dep.successor_task_id in task_ids
    )
    network = ScheduleNetwork(activities=activities, dependencies=dependencies)
    return network, stored_start, stored_finish, task_names


def _dependencies(session: Session, project_id: int) -> list[TaskDependency]:
    """Every ``TaskDependency`` this project's tasks predecess — batched via
    :func:`adapters.project_grouped`, joined through ``Task``/``Workstream``
    since the table carries no ``project_id`` (the resource evaluator's own
    ``Workstream``-scoped read uses the same join)."""

    def load(ids: Sequence[int]) -> Iterable[tuple[int, TaskDependency]]:
        rows = session.execute(
            select(Workstream.project_id, TaskDependency)
            .join(Task, Task.id == TaskDependency.predecessor_task_id)
            .join(Workstream, Workstream.id == Task.workstream_id)
            .where(Workstream.project_id.in_(ids))
            .order_by(TaskDependency.id)
        )
        return ((pid, dep) for pid, dep in rows)

    return adapters.project_grouped(session, TaskDependency, load, project_id)


def milestone_slipped(milestone: Milestone, as_of: date) -> bool:
    """A milestone has slipped if it was missed, or is still open past its baseline.

    An achieved (``met``) milestone never counts as a slip even if it landed later
    than baselined — the delivery happened; only a missed one, or one still
    pending/at-risk whose target has moved past its baseline date, is a live slip.

    Public so ``web.project_hub`` can badge the exact milestones this evaluator
    threats — one predicate, both surfaces (see module docstring). Takes ``as_of``
    for symmetry with the other as-of-parameterised signals in this module; the
    definition itself has no wall-clock component today.
    """
    if milestone.status == "missed":
        return True
    if milestone.status == "met":
        return False
    return milestone.baseline_date is not None and milestone.target_date > milestone.baseline_date


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's schedule health as of ``as_of``."""
    snap = adapters.project_snapshot(session, project, as_of)
    milestones = adapters.project_rows(session, Milestone, project.id)
    stored = _stored_network(session, project, as_of)
    disagreements = network_disagreements(stored[0], stored[1], stored[2]) if stored else ()
    if snap.bac == 0 and not milestones and not disagreements:
        return Assessment(KIND, as_of, 0.0, "green")

    spi = snap.spi
    slipped_names = sorted(m.name for m in milestones if milestone_slipped(m, as_of))
    slipped_count = len(slipped_names)
    task_names = stored[3] if stored else {}
    activity_count = len(stored[0].activities) if stored else 0
    disagreement_count = len(disagreements)
    disagreement_names = sorted(task_names.get(d.activity_id, d.activity_id) for d in disagreements)
    # One unit for the whole score: fractions of schedule lost, never a raw
    # count — a count would let one slip outrank near-total collapse.
    spi_gap = max(0.0, 1.0 - spi) if spi is not None else 0.0
    slip_share = slipped_count / len(milestones) if milestones else 0.0
    disagreement_share = disagreement_count / activity_count if activity_count else 0.0
    score = round(spi_gap + slip_share + disagreement_share, 4)

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    red = slipped_count > 0 or disagreement_count > 0 or (spi is not None and spi < _RED_SPI)
    amber = not red and spi is not None and spi < _AMBER_SPI
    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    severity: RagStatus = "red" if red else "amber"
    spi_text = f"{spi:.2f}" if spi is not None else "no data yet"
    slip_text = f"{slipped_count} milestone{'' if slipped_count == 1 else 's'} slipped"
    if slipped_names:
        slip_text += ": " + ", ".join(slipped_names)
    parts = [f"SPI {spi_text}", slip_text]
    if disagreements:
        plural = "" if disagreement_count == 1 else "s"
        verb = "disagrees" if disagreement_count == 1 else "disagree"
        parts.append(
            f"{disagreement_count} task{plural} {verb} with its own network: "
            + ", ".join(disagreement_names)
        )
    description = f"Schedule slipping ({', '.join(parts)})."
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        description,
        ref,
    )
    actions = (
        Action(
            f"schedule:compress:{project.id}",
            "Compress the schedule",
            "schedule_compression",
            "Crash or fast-track remaining work to recover the lost time.",
            ref,
        ),
        Action(
            f"schedule:rebaseline:{project.id}",
            "Re-baseline the critical path",
            "critical_path_method",
            "Re-run the critical path method against current progress and slipped milestones.",
            ref,
        ),
        Action(
            f"schedule:relevel:{project.id}",
            "Re-level resources",
            "resource_optimization",
            "Re-optimize resource allocation against the recovered schedule.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
