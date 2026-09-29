"""``refuse_dependency_cycle``: the one write-boundary check a ``TaskDependency``
CHECK constraint cannot express.

A CHECK sees one row; whether a new edge closes a loop needs a walk across
every edge already stored, so it is enforced here instead, ahead of the
create/patch write itself (``driftless.api.rules.dependency_lands_valid``).
This is the small, self-contained graph walk the plan called for; once
``driftless.calc.network``'s own cycle detection lands (#330, a sibling
branch), this function's body is the one place that later import replaces.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.models import EstimateScenario, Project, Task
from driftless.models.schedule import TaskDependency


def _adjacency(db: Session, *, exclude_id: int | None = None) -> dict[int, list[int]]:
    """Every stored edge, predecessor -> its successors, in one query.

    ``exclude_id`` drops one dependency's own current edge from the walk —
    what a patch that leaves its predecessor/successor untouched needs, so
    checking a row against itself never reads as a cycle.
    """
    adjacency: dict[int, list[int]] = {}
    rows = db.execute(
        select(
            TaskDependency.id, TaskDependency.predecessor_task_id, TaskDependency.successor_task_id
        )
    )
    for dependency_id, predecessor_id, successor_id in rows:
        if dependency_id == exclude_id:
            continue
        adjacency.setdefault(predecessor_id, []).append(successor_id)
    return adjacency


def _reaches(adjacency: dict[int, list[int]], start: int, target: int) -> bool:
    """Whether ``target`` is reachable from ``start`` by following stored edges."""
    seen, stack = {start}, [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        for next_node in adjacency.get(node, ()):
            if next_node not in seen:
                seen.add(next_node)
                stack.append(next_node)
    return False


def refuse_dependency_cycle(
    db: Session, predecessor_task_id: int, successor_task_id: int, *, exclude_id: int | None = None
) -> None:
    """Refuse an edge that would close a loop through the edges already stored.

    Adding ``predecessor -> successor`` closes a cycle exactly when
    ``successor`` can already reach ``predecessor`` through some chain of
    existing edges: the new edge would complete the loop back to where it
    started.
    """
    if _reaches(_adjacency(db, exclude_id=exclude_id), successor_task_id, predecessor_task_id):
        raise HTTPException(
            409,
            f"Task {successor_task_id} already reaches task {predecessor_task_id} through "
            "existing dependencies; this edge would close a cycle",
        )


def file_estimate_scenario(db: Session, payload: s.EstimateScenarioIn) -> EstimateScenario:
    """Validate and file one stored estimate — the cost workbench's one write — through
    the same schema and cross-row rule (``estimate_scenario_lands_valid``) the JSON
    route runs, so the two write paths are one. ``api.rules`` imports this module for
    ``refuse_dependency_cycle``, so its rule is imported here at call time, not load
    time — both modules are fully loaded by the time a form posts."""
    from driftless.api.rules import estimate_scenario_lands_valid

    estimate_scenario_lands_valid(db, payload)
    return insert(db, EstimateScenario, payload, project_id=Project, subject_task_id=Task)
