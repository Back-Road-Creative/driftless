"""The scope worksheet: ``GET /projects/{project_id}/assist/scope``.

Five Scope-family techniques share this one page because none of them computes
anything — each is a WORKSHEET (``pmbok.definitions.AssistanceMode.WORKSHEET``),
never a CALCULATOR: product analysis (Define Scope, 5.3), context diagram,
prototypes and benchmarking (Collect Requirements, 5.2), and inspection
(Validate Scope, 5.5). Every figure below is read straight off the project's
own rows — the ``project_scope_statement`` and ``requirements_documentation``
narrative prose, its stakeholders, its milestones — the same idiom
``assist_evm``'s calculator uses for computed figures, applied to rows instead
of arithmetic. Nothing here writes: filling in a blank narrative body still
goes through the wizard's one producer (``/projects/{id}/wizard``), never a
second write path.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess.adapters import project_rows
from driftless.models import Milestone, NarrativeArtifact, Project, Stakeholder
from driftless.naming import technique_slug
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: Every technique this page serves, and the PMBOK-6 process that names it —
#: cited literally, the same way ``assist_evm.PROCESS_ID`` is, since this one
#: route answers for more than one process.
_PROCESS_IDS: dict[str, str] = {
    "product_analysis": "5.3",
    "context_diagram": "5.2",
    "prototypes": "5.2",
    "benchmarking": "5.2",
    "inspection": "5.5",
}

#: What product analysis breaks a project's objectives into. PMBOK-6 files the
#: technique under Define Scope (5.3), whose one prose output is
#: ``project_scope_statement`` — so every prompt below is a different lens on
#: that SAME narrative row rather than four rows to keep in step.
_PRODUCT_ANALYSIS_PROMPTS: tuple[tuple[str, str], ...] = (
    ("Product breakdown", "What are the pieces this product is made of?"),
    ("Requirements analysis", "What must each piece do?"),
    ("Systems analysis", "How do the pieces work together as a whole?"),
    ("Value engineering", "Where could the same result cost less or arrive sooner?"),
)

#: What a prototype has to show before it earns the time to build it. PMBOK-6
#: names no closed list of its own, so this is a fixed checklist rather than a
#: derived one; whether it is worth building at all is answered against
#: whether there is anything written down yet to build it AGAINST.
_PROTOTYPE_CHECKLIST: tuple[str, ...] = (
    "Shows the product's key features well enough for a stakeholder to react to",
    "Is disposable — cheap enough to throw away and rebuild",
    "Surfaces requirements a written document alone would not have caught",
    "Can be walked through with a stakeholder in one sitting",
)

#: What the benchmarking table compares this project against, per row. PMBOK-6
#: leaves the comparison points to the reader's judgment (``GUIDE_ONLY_REASONS``
#: still names it a judgment call), so this is a fixed prompt list, not a metric.
_BENCHMARK_ROWS: tuple[str, ...] = ("Cost", "Schedule", "Scope", "Quality")


def _narrative_body(rows: list[NarrativeArtifact], kind: str) -> str:
    """This project's current prose for ``kind``, or "" when nothing is filed yet."""
    return next((row.body for row in rows if row.kind == kind), "")


def _milestones(db: Db, project_id: int, at: date) -> list[Milestone]:
    """This project's milestones due on or before ``at`` — never one filed for
    later than the date being inspected. ``project_rows`` carries no ``at``
    parameter (most of this page's other rows are undated prose or a roster,
    which is why it does not filter), so the one row here that IS dated reads
    it the way ``assist_closeout._milestones`` already does, rather than
    inheriting a helper built for rows that carry no date at all."""
    rows = db.scalars(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .where(Milestone.target_date <= at)
        .order_by(Milestone.id)
    ).all()
    return list(rows)


def _checklist_result(total: int, done: int) -> dict[str, Any]:
    """A tiny pass/fail summary over a count of items.

    Nothing under ``driftless/calc`` names a ``checklist_result`` today, so this
    stays a small local helper rather than an import; a shared quality checklist
    helper, on a sibling change, should absorb this instead of standing beside
    it as a second copy.
    """
    return {
        "total": total,
        "done": done,
        "percent": round((done / total) * 100) if total else None,
    }


def _context_diagram(system_name: str, stakeholders: list[Stakeholder]) -> dict[str, Any]:
    """A boundary-and-interfaces worksheet: the project as the system, its
    stakeholders as actors, each placed evenly around a circle so the small
    inline SVG costs one trig call per actor and no layout engine."""
    cx, cy, r = 150.0, 150.0, 110.0
    n = len(stakeholders)
    actors = []
    for i, person in enumerate(stakeholders):
        angle = (2 * math.pi * i / n) if n else 0.0
        actors.append(
            {
                "name": person.name,
                "interest": person.interest,
                "influence": person.influence,
                "x": round(cx + r * math.cos(angle), 1),
                "y": round(cy + r * math.sin(angle), 1),
            }
        )
    return {"cx": cx, "cy": cy, "system": system_name, "actors": actors}


def _provenance(as_of: date, key: str) -> dict[str, str]:
    """Where this section's figures come from — mirrors ``assist_evm._provenance``,
    once per technique since this one page answers for five of them."""
    technique = TECHNIQUES[key]
    return {
        "technique": technique.display_name,
        "process": _PROCESS_IDS[key],
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
        "reference_href": f"/techniques/{technique_slug(key)}",
    }


def create_assist_scope_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The scope worksheet page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/scope", response_class=HTMLResponse)
    def assist_scope(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        against: list[str] = Query(default=[]),
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        narrative = project_rows(db, NarrativeArtifact, project_id)
        stakeholders = project_rows(db, Stakeholder, project_id)
        milestones = _milestones(db, project_id, at)

        scope_statement = _narrative_body(narrative, "project_scope_statement")
        requirements = _narrative_body(narrative, "requirements_documentation")

        product_analysis = [
            {"label": label, "question": question, "answer": scope_statement}
            for label, question in _PRODUCT_ANALYSIS_PROMPTS
        ]
        prototype_checklist = [
            {"item": item, "ready": bool(requirements)} for item in _PROTOTYPE_CHECKLIST
        ]
        done_milestones = sum(1 for m in milestones if m.status == "met")

        context = {
            "project": project,
            "as_of": at.isoformat(),
            "product_analysis": product_analysis,
            "diagram": _context_diagram(project.name, stakeholders),
            "prototype_checklist": prototype_checklist,
            "requirements_present": bool(requirements),
            "benchmark_rows": _BENCHMARK_ROWS,
            "benchmark_columns": against,
            "milestones": milestones,
            "milestone_result": _checklist_result(len(milestones), done_milestones),
            "provenance": {key: _provenance(at, key) for key in _PROCESS_IDS},
        }
        return TEMPLATES.TemplateResponse(request, "assist_scope.html", context)

    return router
