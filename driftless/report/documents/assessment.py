"""The Assessment Report: every knowledge area's reading for one project, with its
threats and recommended PMBOK actions, plus the ranked live-threat feed. Project-
scoped. All computed by ``driftless.assess`` from the store and the as-of date, so the
document regenerates byte-identically; the template only formats. (Report imports
assess — the allowed direction: assess sits below report.) ``assess_project`` runs
ONCE per render: rows and threat feed are both derived from its assessments."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from driftless.assess import engine as assess
from driftless.assess.model import Assessment, Threat
from driftless.models import Project
from driftless.report import engine

SLUG = "assessment"
TITLE = "Assessment Report"


def _assessment_rows(assessments: tuple[Assessment, ...]) -> list[dict[str, Any]]:
    return [
        {
            "kind": a.kind,
            "status": a.status,
            "score": f"{a.risk_score:.4f}",
            "threats": [t.description for t in a.threats],
            "actions": [
                {
                    "label": ac.label,
                    "technique": ac.technique.display_name,
                    "launch_href": ac.launch_href,
                    "reference_href": ac.reference_href,
                }
                for ac in a.actions
            ],
        }
        for a in assessments
    ]


def _live_threats(
    session: Session, assessments: tuple[Assessment, ...], as_of: date
) -> list[Threat]:
    """The unsuppressed threats of ``assessments``, most severe first — the same
    filter (``assess.is_suppressed``) and ranking (``assess._rank_key``, the one
    definition the engine's own feeds sort by) applied to assessments this render
    already computed; pinned equal to ``assess.live_threats``'s answer in
    ``tests/test_report_documents_batching.py``, suppression included."""
    live = [
        threat
        for a in assessments
        for threat in a.threats
        if not assess.is_suppressed(session, threat, as_of)
    ]
    return sorted(live, key=assess._rank_key, reverse=True)


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Assessment Report for ``project`` as of ``as_of``."""
    assessments = assess.assess_project(session, project, as_of)
    threats = [
        {"severity": t.severity, "kind": t.kind, "description": t.description}
        for t in _live_threats(session, assessments, as_of)
    ]
    return engine.render(
        "assessment.md",
        {
            "title": TITLE,
            "project": project,
            "as_of": as_of,
            "assessments": _assessment_rows(assessments),
            "threats": threats,
        },
    )
