"""The format-neutral shape both importers parse into, and the one write path
that lands it: ``write_imported_schedule`` goes through ``api.schemas`` and
``api.records.insert`` — the same validated boundary the HTTP API writes
through — so an imported task or dependency is audited on the ChangeLog
exactly like a browser or API write, never a second write path.

``duration_days`` is the parsed format's own duration, converted to whole
days by the caller (``msproject``/``xer``) before it reaches here — this
module does no unit conversion of its own, only the write.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.api.rules import dependency_lands_valid
from driftless.calc.network import DependencyKind
from driftless.models import Project, Task, Workstream
from driftless.models.schedule import TaskDependency


@dataclass(frozen=True)
class ImportedTask:
    """One activity from the source file: its own id there, its name, and its
    duration in whole days."""

    external_id: str
    name: str
    duration_days: int


@dataclass(frozen=True)
class ImportedDependency:
    """One precedence edge, named by the two tasks' ``external_id``s."""

    predecessor: str
    successor: str
    kind: DependencyKind = "FS"
    lag_days: int = 0


@dataclass(frozen=True)
class ImportedSchedule:
    """Everything one source file described: its tasks and their edges."""

    tasks: tuple[ImportedTask, ...]
    dependencies: tuple[ImportedDependency, ...] = ()


def write_imported_schedule(
    db: Session, project: Project, schedule: ImportedSchedule, *, workstream_name: str
) -> dict[str, Task]:
    """Write ``schedule`` into one new workstream under ``project``, through the
    validated write path both the API and the wizard CLI already use.

    Returns the source file's ``external_id`` mapped to the ``Task`` row it
    became, so a caller can drive ``calc.network`` against the imported data
    without a second query.
    """
    workstream = insert(db, Workstream, s.WorkstreamIn(name=workstream_name, project_id=project.id))
    tasks: dict[str, Task] = {}
    for imported in schedule.tasks:
        task = insert(
            db,
            Task,
            s.TaskIn(
                name=imported.name,
                workstream_id=workstream.id,
                estimate=float(imported.duration_days),
                estimate_unit="hours",
            ),
        )
        tasks[imported.external_id] = task
    for dep in schedule.dependencies:
        payload = s.TaskDependencyIn(
            predecessor_task_id=tasks[dep.predecessor].id,
            successor_task_id=tasks[dep.successor].id,
            kind=dep.kind,
            lag_days=dep.lag_days,
        )
        dependency_lands_valid(db, payload)
        insert(
            db,
            TaskDependency,
            payload,
            predecessor_task_id=Task,
            successor_task_id=Task,
        )
    return tasks
