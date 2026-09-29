"""The quality workbench: ``GET /projects/{project_id}/assist/quality``.

Six tools over ``driftless.calc.quality`` and this project's own rows, nothing
written by any of them:

* **Control charts** — one per ``QualityMetric``/legacy metric name with two or more
  dated readings as of ``at``, drawn as an inline SVG polyline with a text twin table,
  plus the rule-of-seven run signal in words. Fewer than two readings gets a plain
  "not enough readings yet" line rather than a chart that lies about a spread.
* **A Pareto of measurement failures**, one category per metric name, with the
  vital-few cut named.
* **A statistical sampling plan** what-if (``?population=&confidence=&margin=``),
  computed only when all three are given and well-formed — GET, nothing saved.
* **A root-cause worksheet** over one issue (``?issue=<id>``): a fixed Ishikawa
  category shape (no candidate causes are stored, so none are pre-filled) and a
  five-whys chain read from up to five ``why`` query parameters.
* **A cost-of-quality what-if** (``?prevention=&appraisal=&internal_failure=&external_failure=``):
  ``BudgetLine``'s cost-category vocabulary (labour, materials, services, travel,
  contingency) has no member that maps to conformance/non-conformance spend, so
  there is no stored figure to read this from; the reader types the four bands by
  hand and nothing typed is saved.
* **An audit checklist**, one line per sentence of the project's own
  ``quality_management_plan`` narrative — a reading list for the audit, not a
  pass/fail record nothing stores.

Three of the six route a ``TT_CATALOG`` technique (``root_cause_analysis``,
``cost_of_quality``, ``audits`` — see ``assess.model.ASSISTANT_ROUTES``) and carry
that technique's provenance; the other three (control charts, the Pareto split,
statistical sampling) name no ``TT_CATALOG`` member of their own, so they explain
themselves in prose instead of a citation block.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess.adapters import project_rows
from driftless.calc import quality as calc
from driftless.calc.quality import CONFIDENCE_Z
from driftless.models import Issue, NarrativeArtifact, Project
from driftless.naming import technique_slug
from driftless.pmbok import quality_facts
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The PMBOK-6 process each routed technique here belongs to — cited literally,
#: the same way ``assist_evm.PROCESS_ID`` and ``assist_scope._PROCESS_IDS`` are.
_PROCESS_IDS: dict[str, str] = {
    "cost_of_quality": "8.1",
    "audits": "8.2",
    "root_cause_analysis": "8.2",
}

#: The standard Ishikawa (fishbone) category shape — PMBOK-6 names no closed list
#: of its own for it, the same reason ``assist_scope._PROTOTYPE_CHECKLIST`` is a
#: fixed prompt set rather than a derived one. No candidate causes are pre-filled:
#: nothing stores them, so a filled-in cell here would be a fabricated finding.
FISHBONE_CATEGORIES: tuple[str, ...] = (
    "Method",
    "Machine",
    "Material",
    "People",
    "Measurement",
    "Environment",
)

#: How many "why" answers the worksheet accepts — the technique's own name.
FIVE_WHYS_DEPTH = 5

#: Splits a narrative body into one checklist line per sentence: the sentence-ending
#: punctuation plus the whitespace after it. A body with no such punctuation reads as
#: one line, which is still an honest answer for a one-line plan.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _chart_geometry(series: quality_facts.MetricSeries) -> dict[str, Any] | None:
    """Pixel coordinates for one metric's control-chart SVG, or ``None`` when there
    are too few readings to draw one. Mirrors the plain-arithmetic layout
    ``status_form.html``'s trend chart already draws its polyline with — computed
    here, in Python, rather than in the template, the same way
    ``assist_scope._context_diagram`` places its actors."""
    chart = series.chart
    if chart is None:
        return None
    values = [value for _, value in series.readings]
    lower = min(values + [chart.lcl])
    upper = max(values + [chart.ucl])
    span = (upper - lower) or 1.0
    n = len(values)

    def x(i: int) -> float:
        return round(40 + (i / (n - 1)) * 270, 1) if n > 1 else 40.0

    def y(value: float) -> float:
        return round(130 - (value - lower) / span * 118, 1)

    points = [
        {
            "x": x(i),
            "y": y(value),
            "out_of_control": i in chart.out_of_control,
            "out_of_spec": i in chart.out_of_spec,
        }
        for i, value in enumerate(values)
    ]
    return {
        "points": points,
        "mean_y": y(chart.mean),
        "ucl_y": y(chart.ucl),
        "lcl_y": y(chart.lcl),
    }


def _audit_checklist(narrative: list[NarrativeArtifact]) -> list[str]:
    body = next((row.body for row in narrative if row.kind == "quality_management_plan"), "")
    if not body.strip():
        return []
    return [line.strip() for line in _SENTENCE_SPLIT.split(body.strip()) if line.strip()]


def _provenance(as_of: date, key: str) -> dict[str, str]:
    """Where one routed section's figures come from — mirrors
    ``assist_scope._provenance``, once per technique this page routes."""
    technique = TECHNIQUES[key]
    return {
        "technique": technique.display_name,
        "process": _PROCESS_IDS[key],
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
        "reference_href": f"/techniques/{technique_slug(key)}",
    }


def create_assist_quality_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The quality workbench page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/quality", response_class=HTMLResponse)
    def assist_quality(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        population: int | None = None,
        confidence: float | None = None,
        margin: float | None = None,
        issue: int | None = None,
        why: list[str] = Query(default=[]),
        prevention: float | None = None,
        appraisal: float | None = None,
        internal_failure: float | None = None,
        external_failure: float | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)

        series = quality_facts.metric_series(db, project, at)
        charts = [
            {"series": chart_series, "geometry": _chart_geometry(chart_series)}
            for chart_series in series
        ]
        pareto = quality_facts.failure_pareto(db, project, at)

        sampling_result = None
        if (
            population is not None
            and confidence is not None
            and margin is not None
            and population >= 1
            and confidence in CONFIDENCE_Z
            and 0 < margin < 1
        ):
            sampling_result = calc.sampling_plan(population, confidence, margin)

        issues = project_rows(db, Issue, project_id)
        selected_issue = next((row for row in issues if row.id == issue), None)
        fishbone = None
        whys = None
        if selected_issue is not None:
            fishbone = calc.root_cause(
                selected_issue.description, {name: () for name in FISHBONE_CATEGORIES}
            )
            answered = [w for w in why[:FIVE_WHYS_DEPTH] if w.strip()]
            if answered:
                whys = calc.five_whys(answered)

        coq_result = None
        if None not in (prevention, appraisal, internal_failure, external_failure):
            assert prevention is not None and appraisal is not None
            assert internal_failure is not None and external_failure is not None
            coq_result = calc.cost_of_quality(
                prevention, appraisal, internal_failure, external_failure
            )

        narrative = project_rows(db, NarrativeArtifact, project_id)
        checklist = _audit_checklist(narrative)

        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "charts": charts,
            "pareto": pareto,
            "sampling": {
                "population": population,
                "confidence": confidence,
                "margin": margin,
                "confidence_options": sorted(CONFIDENCE_Z),
                "result": sampling_result,
            },
            "issues": issues,
            "selected_issue": selected_issue,
            "fishbone": fishbone,
            "fishbone_categories": FISHBONE_CATEGORIES,
            "why_depth": range(FIVE_WHYS_DEPTH),
            "why_answers": why,
            "whys": whys,
            "cost_of_quality": {
                "prevention": prevention,
                "appraisal": appraisal,
                "internal_failure": internal_failure,
                "external_failure": external_failure,
                "result": coq_result,
            },
            "checklist": checklist,
            "provenance": {key: _provenance(at, key) for key in _PROCESS_IDS},
        }
        return TEMPLATES.TemplateResponse(request, "assist_quality.html", context)

    return router
