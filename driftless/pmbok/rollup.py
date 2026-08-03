"""Business-wide process rollup: ``catalog.PROCESSES`` aggregated across every
project. Applicable/share exclude WAIVED and not-assessable pairs exactly like
``state.completeness``, pooled across projects instead of one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.pmbok import catalog, state
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.state import ProcessState


@dataclass(frozen=True)
class ProjectCell:
    """One project's own state for one process."""

    project_id: int
    project_name: str
    state: ProcessState


@dataclass(frozen=True)
class CellAgg:
    """One catalog process aggregated across every project: ``counts`` is the
    full unfiltered tally; ``applicable``/``share`` exclude WAIVED and
    not-assessable pairs like ``state.completeness`` does; ``projects`` is
    every project's own state, unfiltered, (name, id) order."""

    process_id: str
    process_name: str
    area: KnowledgeArea
    group: ProcessGroup
    counts: dict[ProcessState, int]
    applicable: int
    share: float | None
    projects: tuple[ProjectCell, ...]


def business_completeness(cells: tuple[CellAgg, ...]) -> float | None:
    """The store-wide produced-or-better share over every applicable
    (project, process) pair — ``state.completeness``'s rule pooled across cells;
    pure over the aggregates, ``None`` when nothing is applicable. A
    never-assessable cell (applicable 0) contributes nothing even when signed."""
    applicable = sum(cell.applicable for cell in cells)
    done = sum(
        cell.counts[ProcessState.PRODUCED] + cell.counts[ProcessState.SIGNED_OFF]
        for cell in cells
        if cell.applicable
    )
    return done / applicable if applicable else None


@dataclass(frozen=True)
class AreaShare:
    """One knowledge area's produced-or-better share, pooled across its cells."""

    area: KnowledgeArea
    share: float | None


def business_area_shares(cells: tuple[CellAgg, ...]) -> tuple[AreaShare, ...]:
    """Per-knowledge-area produced-or-better share over applicable pairs in that
    area's cells — ``business_completeness``'s pooling rule scoped to one area at
    a time, catalog KA order; ``None`` when the area has nothing applicable (a
    never-assessable area, like one whose every process lacks a tracked output,
    stays ``None`` no matter what the store holds). Pure over the aggregates."""
    applicable = dict.fromkeys(KnowledgeArea, 0)
    done = dict.fromkeys(KnowledgeArea, 0)
    for cell in cells:
        if not cell.applicable:
            continue
        applicable[cell.area] += cell.applicable
        done[cell.area] += cell.counts[ProcessState.PRODUCED] + cell.counts[ProcessState.SIGNED_OFF]
    return tuple(
        AreaShare(area, done[area] / applicable[area] if applicable[area] else None)
        for area in KnowledgeArea
    )


def business_process_cells(session: Session, as_of: date) -> tuple[CellAgg, ...]:
    """Every process, catalog order; projects load in ONE query, (name, id), and
    ``state.prefetched`` bounds the whole map to a fixed query set — statements
    do not scale with the project count (pinned by ``test_perf_n1``)."""
    projects = session.scalars(select(Project).order_by(Project.name, Project.id)).all()
    ids = [p.id for p in catalog.PROCESSES]
    counts = {i: {st: 0 for st in ProcessState} for i in ids}
    roster: dict[str, list[ProjectCell]] = {i: [] for i in ids}
    applicable, done = dict.fromkeys(ids, 0), dict.fromkeys(ids, 0)
    with state.prefetched(session, projects):
        for project in projects:
            for process, proc_state in state.project_process_states(project, session, as_of):
                counts[process.id][proc_state] += 1
                roster[process.id].append(ProjectCell(project.id, project.name, proc_state))
                if state.excluded_from_completeness(process, proc_state):
                    continue
                applicable[process.id] += 1
                if proc_state in (ProcessState.PRODUCED, ProcessState.SIGNED_OFF):
                    done[process.id] += 1
    return tuple(
        CellAgg(
            p.id,
            p.name,
            p.area,
            p.group,
            counts[p.id],
            applicable[p.id],
            done[p.id] / applicable[p.id] if applicable[p.id] else None,
            tuple(roster[p.id]),
        )
        for p in catalog.PROCESSES
    )
