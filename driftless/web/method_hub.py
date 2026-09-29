"""The Method section's landing page: ``GET /method`` — the front door the cluster's
seven nav destinations lacked, and what the breadcrumb's "Method" crumb now points at.
One card per section: what it is for, and its own size measured off the frozen
registry that decides it, never typed here. No as-of, no store.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from driftless.pmbok import catalog
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.methods import METHODS
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


@dataclass(frozen=True)
class Section:
    """One card. ``count`` is a phrase, not a number: a figure never says what it counted."""

    title: str
    href: str
    what: str
    count: str


def _sections() -> tuple[Section, ...]:
    nodes, ties = GRAPH.size()
    return (
        Section(
            "PMBOK",
            "/pmbok",
            "Every step the method names, as a grid — open one for what it needs and produces.",
            f"{len(catalog.PROCESSES)} processes",
        ),
        Section(
            "Techniques",
            "/techniques",
            "Every way of working, one at a time: when to use it, when not to, and the steps.",
            f"{len(TECHNIQUES)} techniques",
        ),
        Section(
            "Methods",
            "/methods",
            "How Scrum and Kanban work, and which standard step each practice most resembles.",
            f"{len(METHODS)} method profiles",
        ),
        Section(
            "Artifacts",
            "/artifacts",
            "Every document a step reads or produces, and whether this product can track it.",
            f"{len(ARTIFACTS)} artifact kinds",
        ),
        Section(
            "Glossary",
            "/glossary",
            "Every term of art these pages use — open it when a word does unexpected work.",
            f"{len(GLOSSARY)} terms",
        ),
        Section(
            "Process status",
            "/process-map",
            "The same grid, washed by what your projects have done — follow a cell for them.",
            f"{len(catalog.PROCESSES)} processes, rolled up across every project",
        ),
        Section(
            "Method map",
            "/map",
            "Every step, technique and artifact as one picture, joined wherever one feeds another.",
            f"{nodes} nodes and {ties:,} ties",
        ),
    )


SECTIONS: tuple[Section, ...] = _sections()


def create_method_hub_router() -> APIRouter:
    """The one Method landing page. No as-of: every registry it counts is frozen."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/method", response_class=HTMLResponse)
    def method_hub(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "method_hub.html", {"sections": SECTIONS})

    return router
