"""Business-wide process map: ``catalog.PROCESSES`` rolled up across every
project into the same knowledge-area x process-group grid the per-project map
uses, reusing its ``.st-*`` wash vocabulary. Figures come from
``driftless.pmbok.rollup``; this module buckets a cell's SHARE onto a wash.

Two completions this page adds on top of the grid: a per-knowledge-area
completion ring row (the SAME ring markup ``process_map.html`` draws per
project, pooled store-wide via ``rollup.business_area_shares``) and a
``?process={id}`` listing of one process's applicable projects, reached by
clicking a cell — reusing ``pages.STATE_RANK``/``pct`` so the state word and
its wash can never drift from the ones the per-project map already renders."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from driftless.api.app import get_session
from driftless.pmbok import catalog, state
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.rollup import (
    CellAgg,
    ProjectCell,
    business_area_shares,
    business_process_cells,
)
from driftless.web.pages import STATE_RANK, pct
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]


def _bucket(share: float | None) -> str:
    """No "bad"/red — not-started reads neutral. None/0.0 -> muted; (0,.5) ->
    warn; [.5,1.0) -> ok; 1.0 -> signed."""
    if share is None or share == 0.0:
        return "muted"
    if share < 0.5:
        return "warn"
    if share < 1.0:
        return "ok"
    return "signed"


# The GRID's legend, and only the grid's: it buckets a share onto a wash. The listing
# below paints a project's own process STATE onto the same four washes, so one page-wide
# legend taught ``st-ok`` as "half+" over badges that print "Produced". Each vocabulary
# is legended beside the badges it explains; this one says so in its own intro line.
_LEGEND = [("none", "muted"), ("under half", "warn"), ("half+", "ok"), ("all done", "signed")]


def _business_grid(cells: tuple[CellAgg, ...]) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Same area x group shape as ``pages._process_grid``."""
    grid: dict[str, dict[str, list[dict[str, str]]]] = {
        area.value: {group.value: [] for group in ProcessGroup} for area in KnowledgeArea
    }
    for cell in cells:
        row = {"id": cell.process_id, "name": cell.process_name, "share": pct(cell.share)}
        row["rank"] = _bucket(cell.share)
        grid[cell.area.value][cell.group.value].append(row)
    return grid


@dataclass(frozen=True)
class _ListingRow:
    """One applicable project's own state for the listed process."""

    project_id: int
    project_name: str
    state: str
    rank: str


def _row(cell: ProjectCell) -> _ListingRow:
    return _ListingRow(
        cell.project_id, cell.project_name, cell.state.value, STATE_RANK[cell.state.value]
    )


@dataclass(frozen=True)
class _ProcessListing:
    """The ``?process={id}`` section: one process, its applicable projects.

    ``legend`` names the state vocabulary a row here can carry, read off the SAME
    predicate that filters ``rows`` — so it can neither omit a state a row shows
    nor name one no row can reach, and a sixth process state would appear in both
    at once or in neither.

    An empty ``rows`` is a product state with exactly three causes, and they are
    exhaustive: an assessable process and a project that is neither waived nor
    excluded IS a row. So no rows means not ``assessable`` (the store tracks none
    of the process's outputs), or every project sits in ``waived``, or there are
    no projects at all — and the template names whichever one holds instead of
    saying "No applicable projects." to all three."""

    process_id: str
    process_name: str
    rows: tuple[_ListingRow, ...]
    legend: tuple[tuple[str, str], ...]
    assessable: bool
    waived: tuple[_ListingRow, ...]


def _process_listing(cells: tuple[CellAgg, ...], process_id: str | None) -> _ProcessListing | None:
    """``None`` for an absent or unknown id — no listing renders. Otherwise the
    cell's roster filtered to the SAME applicable pairs the grid's own ``share``
    pools: ``state.excluded_from_completeness`` is the single rule for that
    (waived and not-assessable excluded), matching ``cell.applicable`` exactly
    (a not-assessable process excludes every project, not just the waived ones,
    since none of them count no matter their raw state)."""
    if process_id is None:
        return None
    cell = next((c for c in cells if c.process_id == process_id), None)
    if cell is None:
        return None
    process = catalog.get(cell.process_id)
    return _ProcessListing(
        cell.process_id,
        cell.process_name,
        tuple(
            _row(pc)
            for pc in cell.projects
            if not state.excluded_from_completeness(process, pc.state)
        ),
        tuple(
            (s.value, STATE_RANK[s.value])
            for s in state.ProcessState
            if not state.excluded_from_completeness(process, s)
        ),
        state.is_assessable(process),
        tuple(_row(pc) for pc in cell.projects if pc.state is state.ProcessState.WAIVED),
    )


def create_business_map_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """``GET /process-map``, the business-wide rollup grid."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/process-map", response_class=HTMLResponse)
    def business_map(
        request: Request, db: Db, as_of: date | None = None, process: str | None = None
    ) -> HTMLResponse:
        at = as_of or resolve()
        cells = business_process_cells(db, at)
        shares = business_area_shares(cells)
        context = {
            "as_of": at.isoformat(),
            "groups": [g.value for g in ProcessGroup],
            "areas": [a.value for a in KnowledgeArea],
            "grid": _business_grid(cells),
            "legend": _LEGEND,
            "rings": {s.area.value: s.share for s in shares},
            "ring_labels": {s.area.value: pct(s.share) for s in shares},
            "listing": _process_listing(cells, process),
        }
        return TEMPLATES.TemplateResponse(request, "business_map.html", context)

    return router
