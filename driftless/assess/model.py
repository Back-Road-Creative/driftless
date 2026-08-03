"""The assessment value objects: what an evaluator produces for one knowledge area.

An ``Assessment`` is computed, never stored — a pure function of the store and an
explicit as-of date — so it cannot drift and regenerates byte-identically. A
``Threat`` is a named, rankable problem; an ``Action`` is a recommended next step
drawn from a PMBOK tool or technique (its ``pmbok_tt`` is a ``TT_CATALOG``
member). A threat's ``score`` is its numeric severity, higher being worse: it is
what ranks the feed and what a sign-off is measured against, so suppressing a
threat cannot hide a later regression that pushes the score back up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from driftless.calc.rollup import RAG_SEVERITY
from driftless.calc.rollup import RagStatus as RagStatus  # explicit re-export for the evaluators

#: Numeric weight per RAG severity — used to rank threats across knowledge areas
#: and to fold a leaf's RAG in ``report.gather``. ``unknown`` (nothing to assess)
#: sits below green so it never wins a worst-of fold. Derived from calc's
#: canonical ``RAG_SEVERITY`` ranking so the two layers cannot drift apart.
SEVERITY_WEIGHT: dict[RagStatus, float] = {
    status: float(weight) for status, weight in RAG_SEVERITY.items()
}


@dataclass(frozen=True)
class Threat:
    """A named, rankable problem an evaluator raised.

    ``id`` is severity-independent (``"cost:project:42"``) so the same threat
    keeps its identity as its ``score`` moves; ``source_ref`` points at what it is
    about. ``score`` is the numeric severity a sign-off is compared against.
    """

    id: str
    kind: str
    severity: RagStatus
    score: float
    description: str
    source_ref: str


@dataclass(frozen=True)
class Action:
    """A recommended next step: a PMBOK tool/technique applied to a target."""

    id: str
    label: str
    pmbok_tt: str
    rationale: str
    target_ref: str


@dataclass(frozen=True)
class Assessment:
    """One knowledge area's reading for a project as of a date. Computed, never stored."""

    kind: str
    as_of: date
    risk_score: float
    status: RagStatus
    threats: tuple[Threat, ...] = field(default=())
    actions: tuple[Action, ...] = field(default=())
