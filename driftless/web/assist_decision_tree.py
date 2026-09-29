"""Decision-tree / EMV calculator: ``GET /projects/{project_id}/assist/decision-tree``.

Routes ``decision_tree_analysis`` (``assess.model.ASSISTANT_ROUTES``), Perform
Quantitative Risk Analysis (11.4). A stateless what-if, the same "type it, see it,
nothing saved" contract ``assist_decisions``'s boxes use: every figure comes from
``driftless.calc.risk.decision_tree``/``DecisionBranch.emv``, never a second EMV
formula here. A branch whose outcomes fail to build reports its own error text
rather than losing the page. It reads no dated row but the project itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.risk import DecisionBranch, Outcome, decision_tree
from driftless.models import Project
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

PROCESS_ID = "11.4"  # Perform Quantitative Risk Analysis and Modeling Techniques


def _parse_branches(value: str | None) -> tuple[tuple[DecisionBranch | None, str], ...]:
    """Parse ``"name:p=v,p=v;name:p=v"`` into one ``(branch, error)`` pair per block.
    A block that does not build keeps ``branch`` ``None`` and carries its own
    message, so one bad option never hides the others."""
    results: list[tuple[DecisionBranch | None, str]] = []
    for block in (part.strip() for part in (value or "").split(";")):
        if not block:
            continue
        name, sep, raw = block.partition(":")
        name = name.strip()
        if not sep or not name:
            continue
        try:
            outcomes = []
            for pair in raw.split(","):
                prob_str, psep, value_str = pair.partition("=")
                if not psep:
                    raise ValueError(f"outcome {pair!r} is not probability=value")
                outcomes.append(Outcome(float(prob_str), float(value_str)))
            branch = DecisionBranch(name, tuple(outcomes))
            _ = branch.emv  # forces the probabilities-sum-to-1 check now, not at render
            results.append((branch, ""))
        except ValueError as error:
            results.append((None, f"{name}: {error}"))
    return tuple(results)


def _arithmetic(branch: DecisionBranch) -> str:
    """The EMV sum written out: ``"0.4 x 700000.0 + 0.6 x -100000.0 = 220000.0"``."""
    terms = " + ".join(f"{o.probability} x {o.value}" for o in branch.outcomes)
    return f"{terms} = {branch.emv}"


def create_assist_decision_tree_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The decision-tree/EMV calculator page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/decision-tree", response_class=HTMLResponse)
    def assist_decision_tree(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        options: str | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        parsed = _parse_branches(options)
        errors = [message for branch, message in parsed if branch is None]
        branches = tuple(branch for branch, _ in parsed if branch is not None)
        best = decision_tree(branches).best if branches else None
        branch_views = [
            {
                "name": branch.name,
                "outcomes": [
                    {"probability": o.probability, "value": o.value} for o in branch.outcomes
                ],
                "emv": branch.emv,
                "arithmetic": _arithmetic(branch),
                "is_best": branch is best,
            }
            for branch in branches
        ]
        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "options": options or "",
            "errors": errors,
            "branches": branch_views,
            "best_name": best.name if best is not None else "none yet",
            "best_emv": best.emv if best is not None else "none yet",
            "provenance": {
                "technique": TECHNIQUES["decision_tree_analysis"].display_name,
                "process": PROCESS_ID,
                "as_of": at.isoformat(),
            },
        }
        return TEMPLATES.TemplateResponse(request, "assist_decision_tree.html", context)

    return router
