"""The provenance contract every technique-run assistant must return.

``Provenance`` is the shape a calculator hands back after running a technique
for a project: which technique, which process it served, who ran it, as of
what date, and which version of its definition it used.
:func:`driftless.services.technique_runs.record_run` is the only thing that
turns one into a stored row.

``MethodContext`` is the local enum validated against here. The full
predictive/scrum/kanban/department profile vocabulary lives in the method
profile registry, on a sibling change; that crosswalks onto these four values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class MethodContext(str, Enum):
    """The method a technique ran under."""

    PREDICTIVE = "predictive"
    SCRUM = "scrum"
    KANBAN = "kanban"
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Provenance:
    """What ran, for what, by whom, when, and against which definition of it."""

    technique_key: str
    process_id: str
    actor: str
    as_of: date
    source_version: str
