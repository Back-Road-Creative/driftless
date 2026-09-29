"""Cost knowledge-area evaluator: earned-value efficiency and the variance at completion.

Signal: CPI from the earned-value snapshot sets the RAG band — red when CPI < 0.9
(earning far less than spent), amber when 0.9 <= CPI < 1.0 (efficiency slipped but
not yet past the red line), green when CPI >= 1.0 and when there is no baseline to
measure against. The band turns on CPI alone: VAC is negative for every CPI < 1.0,
so it carries no severity signal the CPI thresholds don't already give — it stays
in the threat text and the score, not the classification. The recommended actions
are the PMBOK cost tools & techniques. Pure and as-of-parameterised — reads no
wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Project
from driftless.pmbok.state import threat_subject_ref

KIND = "cost"

_AMBER_CPI = 1.0
_RED_CPI = 0.9


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's cost health as of ``as_of``."""
    snap = adapters.project_snapshot(session, project, as_of)
    if snap.bac == 0:
        return Assessment(KIND, as_of, 0.0, "green", coverage="missing")

    cpi, vac = snap.cpi, snap.vac
    overrun = max(0.0, -vac) / snap.bac if vac is not None else 0.0
    inefficiency = max(0.0, _AMBER_CPI - cpi) if cpi is not None else 0.0
    score = round(inefficiency + overrun, 4)

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    red = cpi is not None and cpi < _RED_CPI
    amber = not red and cpi is not None and cpi < _AMBER_CPI
    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    severity: RagStatus = "red" if red else "amber"
    cpi_text = f"{cpi:.2f}" if cpi is not None else "n/a"
    vac_text = f"{vac:,.0f}" if vac is not None else "n/a"
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"Cost efficiency slipping (CPI {cpi_text}, VAC {vac_text}).",
        ref,
    )
    actions = (
        Action(
            f"cost:eac:{project.id}",
            "Re-estimate at completion",
            "earned_value_analysis",
            "Recompute EAC from current CPI so the forecast reflects performance to date.",
            ref,
        ),
        Action(
            f"cost:reserve:{project.id}",
            "Run a cost-control reserve analysis",
            "reserve_analysis",
            "Weigh remaining contingency against the emerging overrun.",
            ref,
        ),
        Action(
            f"cost:funding:{project.id}",
            "Reconcile the funding limit",
            "funding_limit_reconciliation",
            "Re-phase spend against the approved funding limits.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
