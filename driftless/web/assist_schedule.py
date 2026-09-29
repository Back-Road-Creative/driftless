"""The schedule-network calculator: ``GET /projects/{project_id}/assist/schedule``.

Routes six of the seven Develop-Schedule/Control-Schedule techniques
(``assess.model.ASSISTANT_ROUTES``): critical path method, precedence diagramming,
leads and lags, schedule network analysis, resource optimization and schedule
compression all read off the SAME network this page draws — the network read
straight off the newest approved baseline as of the page's as-of
(``pmbok.schedule_facts.schedule_facts``), never a second copy. The seventh,
critical chain method, is the Driftless extension ``tt.EXTENSIONS`` already marks
it as: no PMBOK process names it, and its buffer figures are labelled as an
extension on the page, not attributed to the Guide.

``?crash=<task_id>:<days>`` and ``?fast_track=<predecessor_id>:<successor_id>`` each
preview ONE scenario — never both at once — over the SAME network, through
``services.schedule_scenarios``: crashing shortens one activity's duration,
fast-tracking turns one finish-to-start pair into a start-to-start overlap. Neither
touches the stored plan; both are a GET.

The one write this page offers is a POST that proposes the ACTIVE preview as a
baseline change: it creates a draft ``Baseline`` (with lines carrying the
scenario's dates) and a ``ChangeRequest`` describing it, through
``services.schedule_scenarios.propose_baseline_change`` — and stops there.
Approving the change and promoting the draft to the live plan is the existing
human step (``PATCH /baselines/{id}``, then ``PATCH /change-requests/{id}``),
never automated by this page. No plan is ever silently edited: a preview is
always labelled as one, and the write always lands as a proposal, never a
replacement.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess.adapters import project_snapshot
from driftless.calc import evm
from driftless.calc.network import (
    EarlyDates,
    LateDates,
    NetworkDiagram,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
    free_float,
    network_diagram,
    resource_levelling_preview,
    schedule_compression_preview,
    total_float,
)
from driftless.models import Project
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.schedule_facts import ScheduleFacts, schedule_facts
from driftless.services.schedule_scenarios import (
    CrashInput,
    FastTrackInput,
    ScenarioInput,
    UnknownActivityError,
    UnknownProcessError,
    propose_baseline_change,
    scenario_dates,
    scenario_project_summary,
)
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: Develop Schedule names every technique this page routes except the change
#: proposal itself, which is a Control Schedule action — the same "monitor and
#: control changes to the schedule baseline" process a re-baseline already is.
PROCESS_ID = "6.5"
CHANGE_PROCESS_ID = "6.6"

#: Diagram geometry, the same 320-wide user-unit convention gantt.py's SVG uses.
_COL_W, _BOX_W, _BOX_H, _ROW, _TOP = 74.0, 62.0, 16.0, 22.0, 12.0


def _provenance(as_of: date) -> dict[str, str]:
    technique = TECHNIQUES["critical_path_method"]
    return {
        "process": PROCESS_ID,
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
    }


def _parse_pair(value: str, name: str) -> tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 2 or not all(parts):
        raise HTTPException(422, f"{name} must be '<a>:<b>'")
    return parts[0], parts[1]


def _crash_input(value: str) -> CrashInput:
    task, days = _parse_pair(value, "crash")
    try:
        return CrashInput(task_id=int(task), days=int(days))
    except ValueError as error:
        raise HTTPException(422, "crash must be '<task_id>:<days>'") from error


def _fast_track_input(value: str) -> FastTrackInput:
    predecessor, successor = _parse_pair(value, "fast_track")
    try:
        return FastTrackInput(
            predecessor_task_id=int(predecessor), successor_task_id=int(successor)
        )
    except ValueError as error:
        raise HTTPException(422, "fast_track must be '<predecessor_id>:<successor_id>'") from error


def _scenario(crash: str | None, fast_track: str | None) -> tuple[ScenarioInput, str]:
    if crash and fast_track:
        raise HTTPException(422, "Preview one scenario at a time: crash or fast_track, not both.")
    if crash:
        return _crash_input(crash), "crash"
    if fast_track:
        return _fast_track_input(fast_track), "fast_track"
    return None, "levelling"


def _activity_rows(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
    floats: Mapping[str, int],
    free: Mapping[str, int],
    task_names: Mapping[str, str],
    starts: Mapping[str, int],
    finishes: Mapping[str, int],
    anchor: date,
) -> list[dict[str, Any]]:
    """One row per activity, in plain words: its float, whether it is critical, its
    predecessor names, and where the previewed scenario would place it — a reader
    gets the same figures the diagram draws, without decoding an SVG."""
    predecessors: dict[str, list[str]] = {a.id: [] for a in network.activities}
    for dep in network.dependencies:
        predecessors[dep.successor].append(task_names.get(dep.predecessor, dep.predecessor))
    rows = []
    for activity in sorted(network.activities, key=lambda a: (early[a.id].early_start, a.id)):
        aid = activity.id
        rows.append(
            {
                "id": aid,
                "name": task_names.get(aid, aid),
                "duration": activity.duration,
                "depends_on": sorted(predecessors[aid]),
                "early_start": early[aid].early_start,
                "early_finish": early[aid].early_finish,
                "late_start": late[aid].late_start,
                "late_finish": late[aid].late_finish,
                "total_float": floats[aid],
                "free_float": free[aid],
                "critical": floats[aid] == 0,
                "proposed_start": anchor + timedelta(days=starts[aid]),
                "proposed_finish": anchor + timedelta(days=finishes[aid]),
            }
        )
    return rows


def _diagram_view(diagram: NetworkDiagram, early: Mapping[str, EarlyDates]) -> dict[str, Any]:
    """Node/edge positions for the inline SVG, the same box-plus-line idiom
    ``gantt.py`` draws bars with: one column per distinct earliest start, activities
    sharing a column stacked in rows."""
    columns = sorted({early[node.id].early_start for node in diagram.nodes}) or [0]
    col_x = {value: index for index, value in enumerate(columns)}
    row_count: dict[int, int] = {}
    positions: dict[str, dict[str, float]] = {}
    for node in sorted(diagram.nodes, key=lambda n: (early[n.id].early_start, n.id)):
        col = col_x[early[node.id].early_start]
        row = row_count.get(col, 0)
        row_count[col] = row + 1
        x = round(4 + col * _COL_W, 1)
        y = round(_TOP + row * _ROW, 1)
        positions[node.id] = {"x": x, "y": y}
    nodes = [
        {
            "id": node.id,
            "label": node.label,
            "critical": node.critical,
            "x": positions[node.id]["x"],
            "y": positions[node.id]["y"],
        }
        for node in diagram.nodes
    ]
    edges = [
        {
            "x1": round(positions[edge.source]["x"] + _BOX_W, 1),
            "y1": round(positions[edge.source]["y"] + _BOX_H / 2, 1),
            "x2": positions[edge.target]["x"],
            "y2": round(positions[edge.target]["y"] + _BOX_H / 2, 1),
            "kind": edge.kind,
            "critical": edge.critical,
        }
        for edge in diagram.edges
    ]
    width = round(4 + len(columns) * _COL_W + _BOX_W + 4, 1)
    height = round(_TOP + max(row_count.values(), default=1) * _ROW + 8, 1)
    return {"nodes": nodes, "edges": edges, "width": width, "height": height}


def _critical_chain_view(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
    safety: Mapping[str, float],
    task_names: Mapping[str, str],
) -> dict[str, Any]:
    """The Driftless extension: a project buffer sized at half the summed safety
    on the critical chain, plus one feeding buffer — half its own safety — per
    non-critical activity that merges directly into it. A task with no recorded
    three-point estimate contributes zero safety, never an invented figure."""
    floats = total_float(early, late)
    critical_ids = {aid for aid, f in floats.items() if f == 0}
    chain_safety = sum(safety.get(aid, 0.0) for aid in critical_ids)
    feeds = [
        {
            "task": task_names.get(dep.predecessor, dep.predecessor),
            "feeds_into": task_names.get(dep.successor, dep.successor),
            "buffer_days": round(safety.get(dep.predecessor, 0.0) / 2, 1),
        }
        for dep in network.dependencies
        if dep.successor in critical_ids and dep.predecessor not in critical_ids
    ]
    return {
        "chain_safety_days": round(chain_safety, 1),
        "project_buffer_days": round(chain_safety / 2, 1),
        "feeding_buffers": sorted(feeds, key=lambda f: (f["feeds_into"], f["task"])),
    }


def _view(facts: ScheduleFacts, scenario: ScenarioInput, scenario_kind: str) -> dict[str, Any]:
    try:
        network, starts, finishes = scenario_dates(facts, scenario)
    except UnknownActivityError as error:
        raise HTTPException(422, str(error)) from error
    early = forward_pass(network)
    late = backward_pass(network, early)
    floats = total_float(early, late)
    free = free_float(network, early, late)
    paths = critical_path(network, early, late)
    diagram = network_diagram(network, early, late)
    compression = schedule_compression_preview(network, early, late, facts.cost_per_day)
    levelling = resource_levelling_preview(network, early, late, facts.demand)
    return {
        "baseline_version": facts.baseline_version,
        "activities": _activity_rows(
            network, early, late, floats, free, facts.task_names, starts, finishes, facts.anchor
        ),
        "critical_paths": [[facts.task_names.get(aid, aid) for aid in path] for path in paths],
        "diagram": _diagram_view(diagram, early),
        "crash_candidates": [
            {
                "task": facts.task_names.get(c.activity_id, c.activity_id),
                "cost_per_day": round(c.cost_per_day, 2),
            }
            for c in compression.crash_candidates
        ],
        "fast_track_candidates": [
            {
                "predecessor_id": c.predecessor,
                "successor_id": c.successor,
                "predecessor": facts.task_names.get(c.predecessor, c.predecessor),
                "successor": facts.task_names.get(c.successor, c.successor),
            }
            for c in compression.fast_track_candidates
        ],
        "peak_demand_before": levelling.peak_demand_before,
        "peak_demand_after": levelling.peak_demand_after,
        "critical_chain": _critical_chain_view(
            network, early, late, facts.three_point_safety, facts.task_names
        ),
        "scenario_kind": scenario_kind,
    }


def _cost_view(
    finish: date,
    critical_paths: tuple[tuple[str, ...], ...],
    total_cost: float,
    task_names: Mapping[str, str],
    cpi: float | None,
) -> dict[str, Any]:
    eac = evm.estimate_at_completion(total_cost, cpi)
    return {
        "finish": finish.isoformat(),
        "critical_paths": [[task_names.get(aid, aid) for aid in path] for path in critical_paths],
        "total_cost": round(total_cost, 2),
        "eac": round(eac, 2) if eac is not None else None,
    }


def _scenario_comparison(
    db: Session, project: Project, at: date, facts: ScheduleFacts, scenario: ScenarioInput
) -> dict[str, Any]:
    """Current plan and previewed scenario, finish/critical-path/EAC side by side —
    the smallest useful extension of :func:`scenario_project_summary`: it already
    computes the scenario's finish, critical path and total cost; this reuses the
    project's own cost-performance index (``assess.adapters.project_snapshot``, the
    same figure the earned-value page shows) so a schedule change's EAC is read
    with TODAY'S cost efficiency, never an invented one. Read-only: nothing here
    is stored, the same rule every other figure on this page follows."""
    cpi = project_snapshot(db, project, at).cpi
    current = scenario_project_summary(facts, None)
    proposed = scenario_project_summary(facts, scenario) if scenario is not None else current
    return {
        "current": _cost_view(
            current.finish, current.critical_paths, current.total_cost, facts.task_names, cpi
        ),
        "scenario": _cost_view(
            proposed.finish, proposed.critical_paths, proposed.total_cost, facts.task_names, cpi
        ),
    }


def create_assist_schedule_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The schedule-network calculator page and its one write, defaulting to
    ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/schedule", response_class=HTMLResponse)
    def assist_schedule(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        crash: str | None = None,
        fast_track: str | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        facts = schedule_facts(db, project, at)
        scenario, scenario_kind = _scenario(crash, fast_track)
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "facts": facts,
            "view": _view(facts, scenario, scenario_kind) if facts else None,
            "comparison": _scenario_comparison(db, project, at, facts, scenario) if facts else None,
            "crash": crash or "",
            "fast_track": fast_track or "",
            "provenance": _provenance(at),
            "change_process_id": CHANGE_PROCESS_ID,
        }
        return TEMPLATES.TemplateResponse(request, "assist_schedule.html", context)

    @router.post("/projects/{project_id}/assist/schedule/propose")
    def assist_schedule_propose(
        request: Request,
        project_id: int,
        db: Db,
        description: Annotated[str, Form()],
        as_of: Annotated[date | None, Form()] = None,
        crash: Annotated[str | None, Form()] = None,
        fast_track: Annotated[str | None, Form()] = None,
        origin_process_id: Annotated[str, Form()] = CHANGE_PROCESS_ID,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        facts = schedule_facts(db, project, at)
        if facts is None:
            raise HTTPException(422, "No approved baseline to propose a schedule change against.")
        scenario, _ = _scenario(crash, fast_track)
        try:
            propose_baseline_change(
                db, project, at, description, origin_process_id, facts, scenario
            )
        except (UnknownActivityError, UnknownProcessError) as error:
            raise HTTPException(422, str(error)) from error
        return RedirectResponse(
            f"/projects/{project_id}/assist/schedule?as_of={at.isoformat()}", status_code=303
        )

    return router
