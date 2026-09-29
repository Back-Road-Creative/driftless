"""Probability x impact scoring: ``GET /projects/{project_id}/assist/risk-pi``.

Routes ``risk_probability_and_impact_assessment`` (11.3, Perform Qualitative Risk
Analysis): every open risk on the 5x5 P x I matrix from ``driftless.calc.risk`` —
never recomputed here. Read-only, and ``Risk`` carries no date column, so this page
reads no dated row and no as-of can leak through it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.risk import (
    DEFAULT_MATRIX,
    DEFAULT_PROBABILITY_SCALE,
    Level,
    RiskScale,
    score,
)
from driftless.models import Project, Risk
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: Perform Qualitative Risk Analysis — the technique this page routes is one of its tools.
PROCESS_ID = "11.3"

#: The risk-management plan is free text with no structured threshold field.
DEFAULT_THRESHOLD_NOTE = "Default bands: 1-4 is low, 5-12 is moderate, 13-25 is high."


def _provenance() -> dict[str, str]:
    """A record of where this page's figures come from — technique and process, shown
    on the page rather than only known to the code. No as-of: ``Risk`` carries no date
    column, so ``at`` filters nothing here (``_rows`` is not passed it) and an as-of
    line would show the reader a date that changes nothing."""
    return {
        "technique": TECHNIQUES["risk_probability_and_impact_assessment"].display_name,
        "process": PROCESS_ID,
    }


def _impact_scale(impacts: Sequence[float]) -> RiskScale:
    """A project-scoped impact scale over the open register's own range."""
    names = [level.name for level in DEFAULT_PROBABILITY_SCALE.levels]
    lo, hi = min(impacts), max(impacts)
    if lo == hi:
        hi = lo + 1.0  # a single-value register still needs non-zero-width bands
    bounds = [lo + (hi - lo) * i / len(names) for i in range(len(names) + 1)]
    bounds[-1] = hi  # exact, so the highest impact always falls in the top band
    return RiskScale(tuple(Level(name, bounds[i], bounds[i + 1]) for i, name in enumerate(names)))


def _rows(session: Session, project: Project) -> list[dict[str, Any]]:
    """Every open risk, its P x I score and band, ranked worst-scoring first."""
    risks = session.scalars(
        select(Risk)
        .where(Risk.project_id == project.id, Risk.status.in_(OPEN_RISK_STATUSES))
        .order_by(Risk.exposure.desc(), Risk.id)
    ).all()
    if not risks:
        return []
    impact_scale = _impact_scale([r.impact for r in risks])

    def _row(risk: Risk) -> dict[str, Any]:
        p = DEFAULT_PROBABILITY_SCALE.level_for(risk.probability).name
        i = impact_scale.level_for(risk.impact).name
        value, band = score(p, i, DEFAULT_MATRIX)
        return {
            "risk": risk,
            "probability_level": p,
            "impact_level": i,
            "score": value,
            "band": band,
        }

    rows = [_row(risk) for risk in risks]
    rows.sort(key=lambda r: (-int(r["score"]), r["risk"].id))
    return rows


def _matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 5x5 grid: probability rows (highest first) x impact columns."""
    names = [level.name for level in DEFAULT_PROBABILITY_SCALE.levels]

    def _cell(p: str, i: str) -> dict[str, Any]:
        value, band = score(p, i, DEFAULT_MATRIX)
        hits = [r["risk"] for r in rows if r["probability_level"] == p and r["impact_level"] == i]
        return {"impact_level": i, "value": value, "band": band, "risks": hits}

    return [
        {"probability_level": p_name, "cells": [_cell(p_name, i_name) for i_name in names]}
        for p_name in reversed(names)
    ]


def create_assist_risk_pi_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The P x I scoring page."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/risk-pi", response_class=HTMLResponse)
    def assist_risk_pi(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        rows = _rows(db, project)
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "rows": rows,
            "matrix": _matrix(rows),
            "threshold_note": DEFAULT_THRESHOLD_NOTE,
            "provenance": _provenance(),
        }
        return TEMPLATES.TemplateResponse(request, "assist_risk_pi.html", context)

    return router
