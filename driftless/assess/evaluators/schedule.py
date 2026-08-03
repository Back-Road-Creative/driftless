"""Schedule knowledge-area evaluator: schedule performance and milestone slip.

Signal: SPI from the earned-value snapshot, and whether any milestone has
slipped — either marked ``missed`` outright, or still open but its current
target has moved past what was baselined. Red when any milestone has slipped
or SPI has fallen below 0.9; amber when SPI has slipped below 1.0 but not yet
past the red line; green otherwise, and when there is nothing to assess. The
recommended actions are the PMBOK schedule tools & techniques. Pure and
as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Milestone, Project
from driftless.pmbok.state import threat_subject_ref

KIND = "schedule"

_AMBER_SPI = 1.0
_RED_SPI = 0.9


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
    if snap.bac == 0 and not milestones:
        return Assessment(KIND, as_of, 0.0, "green")

    spi = snap.spi
    slipped_names = sorted(m.name for m in milestones if milestone_slipped(m, as_of))
    slipped_count = len(slipped_names)
    # One unit for the whole score: fractions of schedule lost. ``1 - SPI`` is
    # the share of planned progress not earned; the slip term is the slipped
    # SHARE of the milestone list, never the raw count — adding a count to a
    # fraction let one slipped milestone (1.0) outrank near-total schedule
    # collapse (SPI 0.10 -> 0.9) on the ranked board (same unit-bug class the
    # risk evaluator's module docstring documents).
    spi_gap = max(0.0, 1.0 - spi) if spi is not None else 0.0
    slip_share = slipped_count / len(milestones) if milestones else 0.0
    score = round(spi_gap + slip_share, 4)

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    red = slipped_count > 0 or (spi is not None and spi < _RED_SPI)
    amber = not red and spi is not None and spi < _AMBER_SPI
    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    severity: RagStatus = "red" if red else "amber"
    spi_text = f"{spi:.2f}" if spi is not None else "n/a"
    slip_text = f"{slipped_count} milestone(s) slipped"
    if slipped_names:
        slip_text += ": " + ", ".join(slipped_names)
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"Schedule slipping (SPI {spi_text}, {slip_text}).",
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
