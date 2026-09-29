"""An ``OperatingControl``'s RAG state, computed from its linked incidents — never
stored, the same philosophy ``assess.scorecard.evaluate_metric`` applies to a
scorecard metric and ``calc.evidence_age`` applies to a project's own figures.

Pure over :class:`IncidentEvidence`, a plain value object: callers adapt a stored
``Incident`` row (``driftless/models/operations.py``) into one rather than handing
the ORM row in, the same convention ``calc.risk`` and ``calc.evm`` already use.

An open high/critical incident makes a control ``red`` outright — no amount of
fresh evidence offsets an active high-severity event. An open lower-severity
incident, or evidence older than ``STALE_AFTER_DAYS``, makes it ``amber``. With
no open incident and evidence at or under the threshold, it is ``green``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from driftless.calc.evidence_age import EvidenceAge, evidence_age
from driftless.calc.rollup import RagStatus

#: A control with no evidence dated within this many days of ``as_of`` cannot be
#: read as ``green`` even with no open incident — matches
#: ``assess.scorecard``'s per-metric ``cadence_days`` idiom, but a control has no
#: cadence of its own to read, so one shared constant does for every control.
STALE_AFTER_DAYS = 90

#: Severities that make an open incident outrank staleness and force ``red``.
HIGH_SEVERITIES = ("high", "critical")

#: Incident statuses counted as still open against the control they name.
OPEN_STATUSES = ("open", "investigating")


@dataclass(frozen=True)
class IncidentEvidence:
    """The fields of one ``Incident`` row a control's state is judged from."""

    status: str
    severity: str
    raised_on: date
    resolved_on: date | None = None


@dataclass(frozen=True)
class ControlState:
    """One control's as-of RAG state: why, and how old the evidence behind it is."""

    status: RagStatus
    reasons: tuple[str, ...]
    evidence: EvidenceAge | None


def control_state(
    incidents: Sequence[IncidentEvidence],
    as_of: date,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> ControlState:
    """Classify a control from the incidents already linked to it.

    ``incidents`` is scoped to ONE control by the caller — this function never
    filters by a control id, so it never disagrees with how the caller counted
    "linked". Incidents raised after ``as_of`` are excluded from both the
    open-incident check and the evidence sweep, the same "no evidence from the
    future" rule :func:`evidence_age` holds.
    """
    eligible = [row for row in incidents if row.raised_on <= as_of]
    open_incidents = [row for row in eligible if row.status in OPEN_STATUSES]
    high_severity = [row for row in open_incidents if row.severity in HIGH_SEVERITIES]
    evidence = evidence_age(
        as_of, [row.raised_on for row in eligible] + [row.resolved_on for row in eligible]
    )
    stale = evidence is None or evidence.age_days > stale_after_days

    reasons: list[str] = []
    if high_severity:
        status: RagStatus = "red"
        reasons.append(f"{len(high_severity)} open high/critical incident(s)")
    elif open_incidents:
        status = "amber"
        reasons.append(f"{len(open_incidents)} open incident(s)")
    elif stale:
        status = "amber"
        reasons.append(
            "no evidence yet"
            if evidence is None
            else f"evidence is {evidence.age_days} days old (over {stale_after_days})"
        )
    else:
        status = "green"
        reasons.append(f"evidence is {evidence.age_days} days old" if evidence else "no incidents")

    return ControlState(status=status, reasons=tuple(reasons), evidence=evidence)
