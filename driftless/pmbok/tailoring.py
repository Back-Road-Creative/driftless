"""Hybrid tailoring: which controls run on a predictive baseline, an adaptive
commitment, or an operations cadence, and why.

A project does not pick one delivery style for every control — a hybrid project
can hold its cost plan to a fixed baseline while letting scope and schedule move
with a sprint cadence. This module names that choice explicitly, per Monitoring &
Controlling process, for each of the delivery modes ``Project.delivery_mode``
actually offers (``driftless.models.hierarchy.DELIVERY_MODES``): predictive,
agile, hybrid, operations. ``ControlMode.OPERATIONS_CADENCE`` is the reading a
project takes on when its own ``delivery_mode`` is ``"operations"`` — a project a
department runs as standing service work, read against that department's own
service levels and incidents (``driftless.models.operations``) rather than a
project baseline or a sprint commitment. There is deliberately no separate
``Department.delivery_mode``: the selector is the project's own field, the same
one every other mode reads.

Two Monitoring & Controlling processes never move: 4.5 (Monitor and Control
Project Work) and 4.6 (Perform Integrated Change Control) are the one change and
approval boundary in every profile — the ``ChangeRequest`` → ``Baseline`` chain
(``driftless.models.records.ChangeRequest``, ``driftless.models.delivery.Baseline``)
is how a plan changes regardless of how the day-to-day work is tailored.
``driftless.web.change_boundary`` is the one place that link is rendered.

Totality is a property, not a hand check: ``tests/test_pmbok_tailoring.py`` walks
every profile against ``catalog.by_group(ProcessGroup.MONITORING)`` and fails if a
control is missing, duplicated, or maps to a process the catalog does not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from driftless.models.hierarchy import DELIVERY_MODES
from driftless.pmbok import catalog
from driftless.pmbok.model import ProcessGroup


class ControlMode(str, Enum):
    """How a control's completeness is read: against a fixed plan, a team's own
    current commitment, or a department's standing service cadence."""

    PREDICTIVE_BASELINE = "predictive_baseline"
    ADAPTIVE_COMMITMENT = "adaptive_commitment"
    OPERATIONS_CADENCE = "operations_cadence"


#: Plain words for each mode, shared by every page that prints one.
MODE_WORDS = {
    ControlMode.PREDICTIVE_BASELINE: "predictive baseline",
    ControlMode.ADAPTIVE_COMMITMENT: "adaptive commitment",
    ControlMode.OPERATIONS_CADENCE: "operations cadence",
}


@dataclass(frozen=True)
class ControlTailoring:
    """One Monitoring & Controlling process's mode and plain-language reason, for
    one delivery profile."""

    process_id: str
    mode: ControlMode
    reason: str


@dataclass(frozen=True)
class TailoringProfile:
    """One delivery mode's full set of control tailorings — every Monitoring &
    Controlling process in the catalog, exactly once."""

    key: str
    display_name: str
    plain_summary: str
    controls: tuple[ControlTailoring, ...]

    def for_process(self, process_id: str) -> ControlTailoring | None:
        """This profile's tailoring for ``process_id``, or ``None`` if it names one
        the catalog does not track as Monitoring & Controlling."""
        for control in self.controls:
            if control.process_id == process_id:
                return control
        return None


# One (predictive reason, adaptive reason) pair per Monitoring & Controlling
# process, keyed by its PMBOK clause id. 4.5 and 4.6 are never read from this
# table — they are always PREDICTIVE_BASELINE, the fixed change boundary — but a
# pair is still named for them so every profile builder pulls from one table.
_REASONS: dict[str, tuple[str, str]] = {
    "4.5": (
        "Overall project performance is compared against the approved baseline "
        "no matter how the day-to-day work is tailored.",
        "Overall project performance is compared against the approved baseline "
        "no matter how the day-to-day work is tailored.",
    ),
    "4.6": (
        "Every plan change goes through one request-and-approval chain, so there "
        "is only ever one way to change the plan.",
        "Every plan change goes through one request-and-approval chain, so there "
        "is only ever one way to change the plan.",
    ),
    "5.5": (
        "Finished work is accepted against the scope baseline the project approved.",
        "Finished work is accepted at the team's own review of what it just built.",
    ),
    "5.6": (
        "Scope changes are measured as variance from the approved scope baseline.",
        "Scope changes are absorbed by re-ordering the backlog rather than "
        "reopening an approved document.",
    ),
    "6.6": (
        "Progress is measured as variance from the approved schedule baseline.",
        "Progress is measured against the team's own commitment for its current cycle.",
    ),
    "7.4": (
        "Spend is tracked against the approved cost baseline, however the work "
        "that earns it gets done.",
        "Spend is tracked against the approved cost baseline, however the work "
        "that earns it gets done.",
    ),
    "8.3": (
        "Quality is checked against the standard set out in the quality baseline.",
        "Quality is checked against the team's own definition of done, each cycle.",
    ),
    "9.6": (
        "Resource use is tracked against the plan the project approved.",
        "Resource use is tracked against the plan the project approved.",
    ),
    "10.3": (
        "Communications are checked against the plan the project approved.",
        "Communications are checked against the team's own review of what actually landed.",
    ),
    "11.7": (
        "Risks are reviewed against the response plan the project approved.",
        "Risks are reviewed at the team's own regular review, as they come up.",
    ),
    "12.3": (
        "Procurement performance is measured against the agreement the project approved.",
        "Procurement performance is measured against the agreement the project approved.",
    ),
    "13.4": (
        "Stakeholder engagement is checked against the plan the project approved.",
        "Stakeholder engagement is checked at the team's own regular review of feedback.",
    ),
}

#: Process ids that are always the change boundary, in every profile, regardless
#: of how the rest of the project's controls are tailored.
_ALWAYS_PREDICTIVE = ("4.5", "4.6")

#: Per delivery mode, the Monitoring & Controlling processes tailored to
#: ``ADAPTIVE_COMMITMENT`` — everything else in that profile is
#: ``PREDICTIVE_BASELINE``. Chosen so every profile is a genuine, distinct
#: reading of the same 12 processes, not a relabeled copy of another profile.
#: ``"operations"`` builds its own profile below (every control an operations
#: project runs reads on ``OPERATIONS_CADENCE``, not a mix), so it names no
#: entry here.
_ADAPTIVE_BY_MODE: dict[str, tuple[str, ...]] = {
    "predictive": (),
    "agile": ("5.5", "5.6", "6.6", "7.4", "8.3", "10.3", "11.7", "13.4"),
    "hybrid": ("5.5", "5.6", "6.6", "8.3", "11.7", "13.4"),
}

#: Plain-language reasons for the ``"operations"`` profile — one per
#: Monitoring & Controlling process the catalog tracks (4.5/4.6 never read
#: this table; the change boundary is fixed).
_OPERATIONS_REASONS: dict[str, str] = {
    "5.5": "Finished work is accepted against the department's own service levels for it.",
    "5.6": "Scope changes are absorbed by the department's standing service catalogue.",
    "6.6": "Progress is measured against the department's own recurring-work cadence.",
    "7.4": "Spend is tracked against the department's own service delivery, not a project baseline.",
    "8.3": "Quality is checked against the incidents raised on the department's operating controls.",
    "9.6": "Resource use is tracked against the department's own service catalogue and workload.",
    "10.3": "Communications are checked against the department's own service-level reporting.",
    "11.7": "Risks are reviewed as the incidents raised against the department's operating controls.",
    "12.3": "Procurement performance is measured against the agreement the project approved.",
    "13.4": "Stakeholder engagement is checked at the department's own regular service review.",
}

_PROFILE_TEXT: dict[str, tuple[str, str]] = {
    "predictive": (
        "Predictive",
        "Every control compares live work back to the one approved baseline.",
    ),
    "agile": (
        "Agile",
        "Most controls compare live work to the team's current commitment, not a "
        "fixed baseline; the plan itself still only changes through one approval chain.",
    ),
    "hybrid": (
        "Hybrid",
        "Scope, schedule, quality, risk and stakeholder controls follow the team's "
        "current commitment; cost, resourcing, communications and procurement stay on "
        "the approved baseline; the plan itself still only changes through one approval chain.",
    ),
    "operations": (
        "Operations",
        "Every control reads against the department's own standing service cadence — "
        "its service levels, incidents and recurring work — instead of a project baseline "
        "or a sprint commitment; the plan itself still only changes through one approval chain.",
    ),
}


def _build_profile(key: str) -> TailoringProfile:
    display_name, summary = _PROFILE_TEXT[key]
    adaptive = set(_ADAPTIVE_BY_MODE.get(key, ()))
    controls = []
    for process in catalog.by_group(ProcessGroup.MONITORING):
        predictive_reason, adaptive_reason = _REASONS[process.id]
        if process.id in _ALWAYS_PREDICTIVE:
            mode = ControlMode.PREDICTIVE_BASELINE
            reason = predictive_reason
        elif key == "operations":
            mode = ControlMode.OPERATIONS_CADENCE
            reason = _OPERATIONS_REASONS[process.id]
        elif process.id in adaptive:
            mode = ControlMode.ADAPTIVE_COMMITMENT
            reason = adaptive_reason
        else:
            mode = ControlMode.PREDICTIVE_BASELINE
            reason = predictive_reason
        controls.append(ControlTailoring(process.id, mode, reason))
    return TailoringProfile(key, display_name, summary, tuple(controls))


#: One profile per ``driftless.models.hierarchy.DELIVERY_MODES`` value, built once
#: at import time from the frozen catalog — pure data, no I/O, no wall clock.
PROFILES: dict[str, TailoringProfile] = {key: _build_profile(key) for key in DELIVERY_MODES}


def profile_for(delivery_mode: str) -> TailoringProfile:
    """The tailoring profile for a project's ``delivery_mode``, or ``KeyError``."""
    return PROFILES[delivery_mode]


def control_tailoring(process_id: str, delivery_mode: str) -> ControlTailoring | None:
    """This delivery mode's tailoring for ``process_id``, or ``None`` if the
    process is not one the catalog tracks as Monitoring & Controlling."""
    return profile_for(delivery_mode).for_process(process_id)


def mode_word(mode: ControlMode) -> str:
    """The plain words a page prints for a mode."""
    return MODE_WORDS[mode]
