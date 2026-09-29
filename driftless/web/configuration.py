"""The organization setup surface: ``GET /org/configuration``.

The delivery dashboard deliberately answers execution questions.  This small,
read-only companion answers the setup question instead: what operating
structure is present, and which validated resource creates each missing layer.
It does not offer a second write path; the API remains the one authority for
validation and persistence.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.api.deps import get_session
from driftless.models import (
    Business,
    Department,
    Person,
    Portfolio,
    Program,
    Project,
    QualityMetric,
    ScorecardContribution,
    ScorecardMetricDefinition,
    ScorecardMetricObservation,
    ScorecardSource,
    StrategicObjective,
)
from driftless.pmbok import tailoring
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]


def _configuration_counts(db: Session) -> tuple[tuple[str, int], ...]:
    """Return each setup layer's durable count without loading its rows."""
    return (
        ("business", db.scalar(select(func.count(Business.id))) or 0),
        ("portfolio", db.scalar(select(func.count(Portfolio.id))) or 0),
        ("program", db.scalar(select(func.count(Program.id))) or 0),
        ("project", db.scalar(select(func.count(Project.id))) or 0),
        ("department", db.scalar(select(func.count(Department.id))) or 0),
        ("person", db.scalar(select(func.count(Person.id))) or 0),
        ("quality metric", db.scalar(select(func.count(QualityMetric.id))) or 0),
        ("strategic objective", db.scalar(select(func.count(StrategicObjective.id))) or 0),
        ("metric definition", db.scalar(select(func.count(ScorecardMetricDefinition.id))) or 0),
        ("metric observation", db.scalar(select(func.count(ScorecardMetricObservation.id))) or 0),
        ("scorecard contribution", db.scalar(select(func.count(ScorecardContribution.id))) or 0),
        ("scorecard source", db.scalar(select(func.count(ScorecardSource.id))) or 0),
    )


def _configuration_readiness(
    db: Session, counts: tuple[tuple[str, int], ...]
) -> tuple[dict[str, object], ...]:
    """Turn the durable inventory into actionable setup checks."""
    total = dict(counts)
    owned_projects = (
        db.scalar(
            select(func.count(Project.id)).where(Project.responsible_department_id.is_not(None))
        )
        or 0
    )
    checks = (
        ("Business root", total["business"], "POST /businesses", None),
        ("Delivery hierarchy", total["project"], "POST /projects", "/"),
        (
            "Ownership and capacity",
            min(total["department"], owned_projects),
            "POST /departments and assign projects",
            "/org/departments",
        ),
        (
            "Strategy objectives",
            total["strategic objective"],
            "POST /strategic-objectives",
            "/scorecard",
        ),
        (
            "Metric definitions",
            total["metric definition"],
            "POST /metric-definitions",
            "/scorecard",
        ),
        ("Metric evidence", total["metric observation"], "POST /metric-observations", "/scorecard"),
        (
            "Project strategy links",
            total["scorecard contribution"],
            "POST /scorecard-contributions",
            "/scorecard",
        ),
    )
    return tuple(
        {
            "label": label,
            "count": count,
            "state": "Ready" if count else "Needs setup",
            "ready": bool(count),
            "action": action,
            "href": href,
        }
        for label, count, action, href in checks
    )


def _tailoring_rows() -> tuple[dict[str, object], ...]:
    """Each delivery-mode profile in plain words: how many controls it reads on a
    fixed baseline, the team's own current commitment, or a department's standing
    service cadence. Pure code, no store read — the profiles are
    ``driftless.pmbok.tailoring.PROFILES``, built once from the frozen catalog, so
    this can never drift from the process map's own reading.

    Walked over every ``ControlMode`` member rather than one counted field and the
    rest folded into "everything else": a fourth mode would otherwise land silently
    in whichever bucket happened to be the leftover, the way ``OPERATIONS_CADENCE``
    controls used to count as ``predictive_count`` before this counted them by their
    own mode. ``tests/test_web_configuration.py`` pins that the three counts sum to
    every profile's own control count, so a mode this loop does not know about
    fails loudly rather than vanishing from the total.
    """
    rows = []
    for profile in tailoring.PROFILES.values():
        counts = {mode: 0 for mode in tailoring.ControlMode}
        for control in profile.controls:
            counts[control.mode] += 1
        rows.append(
            {
                "key": profile.key,
                "display_name": profile.display_name,
                "plain_summary": profile.plain_summary,
                "predictive_count": counts[tailoring.ControlMode.PREDICTIVE_BASELINE],
                "adaptive_count": counts[tailoring.ControlMode.ADAPTIVE_COMMITMENT],
                "operations_count": counts[tailoring.ControlMode.OPERATIONS_CADENCE],
            }
        )
    return tuple(rows)


def create_configuration_router() -> APIRouter:
    """Expose the organization configuration inventory and setup order."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/org/configuration", response_class=HTMLResponse)
    def configuration(request: Request, db: Db) -> HTMLResponse:
        counts = _configuration_counts(db)
        return TEMPLATES.TemplateResponse(
            request,
            "configuration.html",
            {
                "counts": counts,
                "readiness": _configuration_readiness(db, counts),
                "tailoring": _tailoring_rows(),
            },
        )

    return router
