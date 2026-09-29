"""The PMBOK knowledge map as theory: ``GET /pmbok`` and ``GET /pmbok/{process_id}``.

Carved out of ``web/pages.py``, whose one router factory had accumulated eleven route
definitions. These two came first because they need none of what the rest of that module
is built around — no write helper, no CSRF pair rule, no sign-off redirect table.

The grid is the frozen catalog whatever the store holds — the only rows the index reads
are the projects it offers to see that grid washed with — and the detail page reads one
project when asked to.

The pair is deliberately two reading modes of the same clause. Without ``?project=`` it
is the frozen catalog, reachable as theory rather than only through a project; with one,
it is the REST of a process-map drill — that project's live artifacts, its computed
state, and the knowledge area's assessment — carrying the pinned as-of through the hop.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Project
from driftless.pmbok import catalog, crosswalk, tailoring
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.process_definitions import get as get_process_definition
from driftless.services.technique_runs import runs_for_project
from driftless.pmbok.support import ProcessCoverage, build_coverage, driftless_help
from driftless.web import related
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES
from driftless.web.views import process_in_project, reference_grid


#: Each support word a reference cell can print, paired with what it means for the
#: reader. :func:`support_word` answers OUT of these names and the grid's legend is
#: rendered FROM this pairing, so a word can never reach a cell without the legend
#: below it explaining the same word — the two cannot drift apart.
PRODUCIBLE_WORD = "You can fill this in here"
ASSESSABLE_WORD = "We can judge this step"
READ_ONLY_WORD = "Read-only for now"
SUPPORT_LEGEND: tuple[tuple[str, str], ...] = (
    (PRODUCIBLE_WORD, "the wizard can already write one of this step's outputs for you"),
    (ASSESSABLE_WORD, "nothing to fill in yet, but your records can already be judged against it"),
    (READ_ONLY_WORD, "reference only for now — this product works nothing out for this step"),
)


def support_word(coverage: ProcessCoverage) -> str:
    """One process's reference-grid support word, in a newcomer's own language
    rather than a coverage jargon term: whether the wizard can already fill in one
    of its outputs beats mere assessability, which beats plain read-only reference —
    derived straight from ``ProcessCoverage``, never a rule restated here.
    """
    if coverage.has_producible_output:
        return PRODUCIBLE_WORD
    if coverage.assessable:
        return ASSESSABLE_WORD
    return READ_ONLY_WORD


def create_pmbok_reference_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The two PMBOK reference pages, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/pmbok", response_class=HTMLResponse)
    def pmbok_reference(
        request: Request,
        db: Db,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        """The 49 PMBOK processes as a stateless ITTO reference grid.

        The grid is rendered straight from the frozen ``catalog.PROCESSES`` — no
        project state is washed onto it — so the knowledge map is reachable as theory,
        not only through a project (audit findings #8 / #9). Same area×group shape as
        the per-project map, but every cell links to its process's ITTO detail.

        The one thing the page reads from the store is every project, so a reader who
        wants this grid against real progress is offered that project's own process
        map as a link rather than told to assemble a query string (finding PM07) —
        the same courtesy ``/map`` already extends. The words the page explains
        itself with come from the registries: the cell legend from
        :data:`SUPPORT_LEGEND`, the two grid headings from the glossary.
        """
        context: dict[str, Any] = {
            "as_of": at.isoformat(),
            "projects": list(db.scalars(select(Project).order_by(Project.name, Project.id))),
            "groups": [g.value for g in ProcessGroup],
            "areas": [a.value for a in KnowledgeArea],
            "grid": reference_grid(),
            "support": {row.process_id: support_word(row) for row in build_coverage().processes},
            "support_legend": SUPPORT_LEGEND,
            "related": related.for_theory_index("/pmbok"),
        }
        return TEMPLATES.TemplateResponse(request, "pmbok.html", context)

    @router.get("/pmbok/{process_id}", response_class=HTMLResponse)
    def pmbok_detail(
        request: Request,
        process_id: str,
        db: Db,
        project: int | None = None,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        """One process's ITTO — inputs, tools & techniques, outputs — by clause id.

        The drill target of a project process-map cell (finding #12), and with
        ``?project=`` the REST of that drill rather than its dead end: the cell
        carries the project and the pinned as-of through the hop, so the page adds
        this project's live artifacts, its computed state for the process, and its
        knowledge area's assessment with the threats and actions attached — then
        links back to the map the reader came from instead of to the theory grid.
        Without ``?project=`` it is the stateless reference it has always been, so
        the two reading modes stay distinct. Unknown ids (and unknown projects)
        404 rather than 500 (``catalog.get`` raises ``KeyError``).
        """
        try:
            process = catalog.get(process_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        definition = get_process_definition(process_id)
        # For every input/output this process names that an agile crosswalk equivalence
        # covers (driftless.pmbok.crosswalk.EQUIVALENCES) — static, present whether or
        # not ``?project=`` is on the URL, since the equivalence is a fact about the
        # product, not one project's history. The template renders it as "Counted from:
        # <native_source> — <rule_in_plain_words>" beside that input/output, verbatim,
        # never restated here.
        context: dict[str, Any] = {
            "process": process,
            "definition": definition,
            # Built over the frozen registries alone (no store, no clock), so it is
            # the same block in both reading modes — the shared one every Method
            # page renders, never a second list of links written on the template.
            "related": related.for_process(process_id),
            "help_facts": driftless_help(process),
            "live": None,
            "runs": [],
            "equivalences": {
                kind: equivalence
                for kind in dict.fromkeys((*process.inputs, *process.outputs))
                if (equivalence := crosswalk.EQUIVALENCES.get(kind)) is not None
            },
            "tailoring": None,
        }
        if project is not None:
            project_row = fetch(db, Project, project)
            context["live"] = process_in_project(process, project_row, db, at)
            context["runs"] = [
                r for r in runs_for_project(db, project, at) if r.process_id == process.id
            ]
            # Hybrid tailoring (driftless.pmbok.tailoring) only names Monitoring &
            # Controlling processes — every other process reads None here.
            context["tailoring"] = tailoring.control_tailoring(
                process.id, project_row.delivery_mode
            )
        return TEMPLATES.TemplateResponse(request, "pmbok_detail.html", context)

    return router
