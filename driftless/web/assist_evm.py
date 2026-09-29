"""The earned-value calculator: ``GET /projects/{project_id}/assist/earned-value``.

The first two routed techniques' assistant (``assess.model.ASSISTANT_ROUTES``):
Control Costs' (7.4) ``earned_value_analysis`` and ``to_complete_performance_index``
share this one page, since TCPI is computed FROM the same earned-value snapshot the
page already shows rather than standing apart from it. Every figure here is
``adapters.project_snapshot``'s answer, unchanged — the same call the project hub
and the cost evaluator make — so this page can never disagree with either. The
``whatif_remaining_cost`` and ``whatif_cpi`` query parameters each recompute an
ALTERNATE EAC/TCPI reading purely in this response — one from a hypothetical
remaining cost, the other from a hypothetical cost performance index carried
across every remaining dollar (the same assumption ``estimate_at_completion``
already makes of the CURRENT CPI). Nothing is written, and the stored snapshot
is untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.calc import evm
from driftless.models import Project
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.change_boundary import change_boundary
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The PMBOK-6 process this calculator applies: Control Costs, which names both
#: routed techniques. Cited here rather than derived, the same way every technique's
#: ``source_version`` is a literal rather than a lookup nothing else needs.
PROCESS_ID = "7.4"


#: GET ``method`` values, in display order — label + plain "when to use" mirror
#: :class:`evm.EacMethod`'s own docstring, so no two explanations disagree.
_EAC_METHODS: tuple[tuple[str, evm.EacMethod, str, str], ...] = (
    ("cpi", evm.EacMethod.CPI, "Cost-performance-index (BAC ÷ CPI)", "Today's efficiency holds."),
    (
        "remaining_at_plan",
        evm.EacMethod.REMAINING_AT_PLAN,
        "Remaining work at the original plan (AC + (BAC − EV))",
        "Today's variance is a one-off; the rest runs at the planned rate.",
    ),
    (
        "remaining_at_current",
        evm.EacMethod.REMAINING_AT_CURRENT,
        "Remaining work at current efficiency (AC + (BAC − EV) ÷ (CPI × SPI))",
        "Both cost AND schedule performance keep shaping what's left.",
    ),
    (
        "bottom_up",
        evm.EacMethod.BOTTOM_UP,
        "Bottom-up (AC + a re-estimated remaining cost)",
        "The team re-estimated the remaining work directly.",
    ),
)


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _eac_options(
    snap: evm.EarnedValueSnapshot, selected: str, bottom_up_etc: float | None
) -> list[dict[str, Any]]:
    """All four standard EAC readings off the same snapshot, side by side.

    Bottom-up borrows ``whatif_remaining_cost`` (``no data yet`` when unset) since
    there is no stored re-estimate to draw on — never a fabricated number.
    """
    return [
        {
            "id": method_id,
            "label": label,
            "when": when,
            "eac": _round_or_none(
                evm.estimate_at_completion(
                    snap.bac,
                    snap.cpi,
                    method=method,
                    ev=snap.ev,
                    ac=snap.ac,
                    spi=snap.spi,
                    etc=bottom_up_etc,
                ),
                2,
            ),
            "selected": method_id == selected,
        }
        for method_id, method, label, when in _EAC_METHODS
    ]


def _cpi_interpretation(cpi: float | None) -> str:
    """One plain sentence a reader with no PMBOK background can act on."""
    if cpi is None:
        return "Nothing has been spent against the plan yet, so cost efficiency has no meaning."
    if cpi < 1.0:
        return "You have spent more than the work you finished is worth."
    if cpi > 1.0:
        return "The work you finished is worth more than what you have spent."
    return "Spend and the value of finished work are exactly in balance."


def _tcpi_interpretation(tcpi_to_bac: float | None) -> str:
    """One plain sentence about what the REMAINING work must do to land on budget."""
    if tcpi_to_bac is None:
        return "Nothing is left in the budget to measure the remaining work against."
    if tcpi_to_bac > 1.0:
        return (
            "The remaining work must run more efficiently than planned to still finish on budget."
        )
    return "The remaining work can run at or below planned efficiency and still finish on budget."


def _earned_schedule_context(db: Db, project: Project, at: date) -> dict[str, Any]:
    """ES, AT, PD, SPI(t), SV(t) and IEAC(t) for ``project`` as of ``at``.

    Same baseline-selection and progress-replay rules as ``adapters.snapshot_from``
    (``plan_baseline`` resolved at ``at``, dropped entirely before the plan's own
    earliest ``planned_start``) so this can never disagree with the EV figures
    the rest of the page already shows. An unbaselined or not-yet-started project
    passes an empty baseline straight into ``evm.earned_schedule_snapshot``, whose
    every field is already ``None`` for that input — never a fabricated zero.
    """
    baseline = adapters.plan_baseline(project, at)
    lines = baseline.lines if baseline else []
    if lines and at < min(line.planned_start for line in lines):
        lines = []
    ordered = sorted(lines, key=lambda line: line.task_id)
    plan = [
        evm.BaselineTask(str(x.task_id), x.planned_start, x.planned_finish, x.planned_cost)
        for x in ordered
    ]
    progress = adapters.progress_history(db, project, at)
    snap = evm.earned_schedule_snapshot(plan, progress, at)
    return {
        "es": _round_or_none(snap.es, 1),
        "at": snap.at,
        "pd": snap.pd,
        "spi_t": _round_or_none(snap.spi_t, 3),
        "sv_t": _round_or_none(snap.sv_t, 1),
        "ieac_t": _round_or_none(snap.ieac_t, 1),
    }


def _provenance(as_of: date) -> dict[str, str]:
    """A record of where this page's figures come from — technique, process, as-of
    and source edition — shown on the page rather than only known to the code."""
    technique = TECHNIQUES["earned_value_analysis"]
    return {
        "technique": technique.display_name,
        "process": PROCESS_ID,
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
    }


def create_assist_evm_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The earned-value calculator page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/earned-value", response_class=HTMLResponse)
    def assist_earned_value(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        whatif_remaining_cost: float | None = None,
        whatif_cpi: float | None = None,
        method: str = "cpi",
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        snap = adapters.project_snapshot(db, project, at)
        tcpi = evm.to_complete_performance_index(snap.bac, snap.ev, snap.ac, snap.eac)
        selected_method = method if method in {m for m, *_ in _EAC_METHODS} else "cpi"
        eac_options = _eac_options(snap, selected_method, whatif_remaining_cost)
        whatif: dict[str, Any] | None = None
        if whatif_remaining_cost is not None:
            whatif_eac = snap.ac + whatif_remaining_cost
            whatif_tcpi = evm.to_complete_performance_index(snap.bac, snap.ev, snap.ac, whatif_eac)
            whatif = {
                "remaining_cost": round(whatif_remaining_cost, 2),
                "eac": round(whatif_eac, 2),
                "vac": round(snap.bac - whatif_eac, 2),
                "tcpi_to_eac": _round_or_none(whatif_tcpi.to_eac, 3),
            }
        whatif_cpi_result: dict[str, Any] | None = None
        if whatif_cpi is not None:
            cpi_eac = evm.estimate_at_completion(snap.bac, whatif_cpi)
            cpi_tcpi = evm.to_complete_performance_index(snap.bac, snap.ev, snap.ac, cpi_eac)
            whatif_cpi_result = {
                "cpi": round(whatif_cpi, 3),
                "eac": _round_or_none(cpi_eac, 2),
                "vac": _round_or_none(snap.bac - cpi_eac, 2) if cpi_eac is not None else None,
                "tcpi_to_eac": _round_or_none(cpi_tcpi.to_eac, 3),
                "interpretation": _cpi_interpretation(whatif_cpi),
            }
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "snapshot": {
                "bac": round(snap.bac, 2),
                "pv": round(snap.pv, 2),
                "ev": round(snap.ev, 2),
                "ac": round(snap.ac, 2),
                "cpi": _round_or_none(snap.cpi, 3),
                "spi": _round_or_none(snap.spi, 3),
                "eac": _round_or_none(snap.eac, 2),
                "etc": _round_or_none(snap.etc, 2),
                "vac": _round_or_none(snap.vac, 2),
                "cv": round(snap.cv, 2),
                "sv": round(snap.sv, 2),
                "cv_pct": _round_or_none(snap.cv_pct, 3),
                "sv_pct": _round_or_none(snap.sv_pct, 3),
            },
            "earned_schedule": _earned_schedule_context(db, project, at),
            "tcpi": {
                "to_bac": _round_or_none(tcpi.to_bac, 3),
                "to_eac": _round_or_none(tcpi.to_eac, 3),
            },
            "cpi_interpretation": _cpi_interpretation(snap.cpi),
            "tcpi_interpretation": _tcpi_interpretation(tcpi.to_bac),
            "cv_words": "under budget" if snap.cv >= 0 else "over budget",
            "sv_words": "ahead of plan" if snap.sv >= 0 else "behind plan",
            "eac_options": eac_options,
            "selected_method": selected_method,
            "whatif_remaining_cost": whatif_remaining_cost,
            "whatif": whatif,
            "whatif_cpi": whatif_cpi,
            "whatif_cpi_result": whatif_cpi_result,
            "provenance": _provenance(at),
            # A what-if here is only ever hypothetical — nothing is saved. If one of
            # these numbers should become the real plan, this is the one link to the
            # actual change boundary (driftless.web.change_boundary): raising a
            # change request against THIS process, never a second approval path.
            "change_boundary": change_boundary(project_id, PROCESS_ID),
        }
        return TEMPLATES.TemplateResponse(request, "assist_evm.html", context)

    return router
