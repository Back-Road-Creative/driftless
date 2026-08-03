"""The assembled ITTO catalog and its queries.

Concatenates the ten per-area ``PROCESSES`` tuples into one immutable catalog and
offers the handful of lookups the CLI, the process-state engine and the wizard
need. Pure data and pure functions — no I/O, no wall clock — so a query answers
identically run to run.
"""

from __future__ import annotations

from driftless.pmbok.areas import (
    communications,
    cost,
    integration,
    procurement,
    quality,
    resource,
    risk,
    schedule,
    scope,
    stakeholder,
)
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

# Area order is the PMBOK knowledge-area order; within an area the module's own
# order (process-number order) is preserved.
_AREA_MODULES = (
    integration,
    scope,
    schedule,
    cost,
    quality,
    resource,
    communications,
    risk,
    procurement,
    stakeholder,
)

#: Every process in the catalog, area order then process order.
PROCESSES: tuple[Process, ...] = tuple(p for module in _AREA_MODULES for p in module.PROCESSES)


def by_area(area: KnowledgeArea) -> tuple[Process, ...]:
    """Every process in ``area``, in catalog order."""
    return tuple(p for p in PROCESSES if p.area is area)


def by_group(group: ProcessGroup) -> tuple[Process, ...]:
    """Every process in ``group``, in catalog order."""
    return tuple(p for p in PROCESSES if p.group is group)


def get(process_id: str) -> Process:
    """The process with ``process_id`` (its PMBOK clause number), or ``KeyError``."""
    for process in PROCESSES:
        if process.id == process_id:
            return process
    raise KeyError(f"no process with id {process_id!r}")
