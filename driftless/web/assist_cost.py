"""The cost workbench: ``GET /projects/{project_id}/assist/cost``.

Ten Cost-family (plus one Quality-family) techniques share this one page because
each is a no-write what-if over ``driftless.calc.cost``, ``driftless.calc.estimating``
or ``driftless.calc.quality``, read straight off this project's own ``BudgetLine``
and ``CostEntry`` rows — the same idiom ``assist_evm``'s calculator and
``assist_procurement``'s worksheet already use. Nothing here writes: an approved
change to the budget still goes through the change boundary, never a second write
path.

**Cost aggregation** (7.3) rolls this project's ``BudgetLine`` rows up. The model
carries one planned amount per cost CATEGORY, not per work package or control
account — there is no such column — so each category stands in as its own "work
package", and the whole project is the one "control account" every line rolls into.
That is an honest reading of the schema's actual shape, not a hierarchy the store
does not have.

**Reserve analysis** (7.4) treats every category except ``contingency`` as the
work packages' own cost (the base a contingency reserve sits on top of); a stored
``contingency`` budget line, if any, is shown for reference but the what-if always
recomputes from the query parameters, never from that stored figure.

**Funding limit reconciliation** and the **cash-flow S-curve** (both 7.3/7.4) share
one baseline sweep: the S-curve's own cumulative points, differenced back into
one planned amount per sampled period, are what a funding limit is reconciled
against — the same accrual rule (``calc.evm.planned_value``, via
``calc.cost.cash_flow_s_curve``), read once.

**Run rate** reads ``CostEntry`` bucketed by calendar month.

**Historical information review** (7.3) lists OTHER projects' actual spend as of
the same as-of, so a reader has a real reference figure to type into the analogous
estimator below rather than a placeholder library this store does not keep.

**The four estimating techniques** (7.2) are ``calc.estimating``'s pure functions,
run here for the first time — a bottom-up roll-up's raw dollar components are each
wrapped through ``estimating.parametric(rate=1.0, quantity=value)`` so they type as
an ``EstimateScenario`` the same way any other component would, not a private
shortcut into the dataclass.

**Cost of quality** (8.1) is ``calc.quality.cost_of_quality`` — it sits on this page
rather than a quality page because none exists yet on this branch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess import adapters, exposure
from driftless.calc import cost as calc_cost
from driftless.calc import estimating, evm
from driftless.calc import quality as calc_quality
from driftless.models import ESTIMATE_KINDS, BudgetLine, CostEntry, EstimateScenario, Project
from driftless.naming import technique_slug
from driftless.pmbok.definitions import TECHNIQUES
from driftless.services.schedule_writes import file_estimate_scenario
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.change_boundary import change_boundary
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: Every technique this page serves, and the PMBOK-6 process that names it —
#: cited literally, the same way ``assist_evm.PROCESS_ID`` is, since this one
#: route answers for more than one process. ``pmbok/areas/cost.py`` and
#: ``pmbok/areas/quality.py`` are where each pairing is grounded.
PROCESS_IDS: dict[str, str] = {
    "analogous_estimating": "7.2",
    "parametric_estimating": "7.2",
    "three_point_estimating": "7.2",
    "bottom_up_estimating": "7.2",
    "cost_aggregation": "7.3",
    "historical_information_review": "7.3",
    "funding_limit_reconciliation": "7.3",
    "financing": "7.3",
    "reserve_analysis": "7.4",
    "cost_of_quality": "8.1",
}

_HISTORICAL_LIMIT = 10  # other projects shown for reference — a page, not a dump
#: The process a change to the budget is raised against (Determine Budget): every
#: figure on this page is a what-if, and the one way any of them becomes the plan
#: is the change boundary, never a second approval path of the page's own.
CHANGE_PROCESS_ID = "7.3"
_STORED_LIMIT = 20  # stored estimate scenarios listed, newest first — a page, not a dump


def _stored_estimates(db: Session, project: Project, as_of: date) -> list[EstimateScenario]:
    """Cost estimates filed for this project on or before ``as_of``, newest first."""
    return list(
        db.scalars(
            select(EstimateScenario)
            .where(
                EstimateScenario.project_id == project.id,
                EstimateScenario.target == "cost",
                EstimateScenario.as_of <= as_of,
            )
            .order_by(EstimateScenario.as_of.desc(), EstimateScenario.id.desc())
            .limit(_STORED_LIMIT)
        )
    )


def _estimate_prefill(
    works_base: float, results: list[tuple[str, estimating.EstimateScenario | None]]
) -> dict[str, Any]:
    """What the filing form offers: the last what-if computed on this request (its
    own kind, value, range and basis), else the aggregated budget as a bottom-up
    figure — so nothing already on the page is retyped to store it."""
    for kind, result in results:
        if result is not None:
            return {
                "kind": kind,
                "value": round(result.value, 2),
                "low": round(result.low, 2),
                "high": round(result.high, 2),
                "basis": result.basis,
            }
    return {"kind": "bottom_up", "value": round(works_base, 2), "low": "", "high": "", "basis": ""}


def _provenance(as_of: date, key: str) -> dict[str, str]:
    """Where this section's figures come from — mirrors ``assist_evm._provenance``,
    once per technique since this one page answers for ten of them."""
    technique = TECHNIQUES[key]
    return {
        "technique": technique.display_name,
        "process": PROCESS_IDS[key],
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
        "reference_href": f"/techniques/{technique_slug(key)}",
    }


def _cost_lines(project: Project, budget_lines: list[BudgetLine]) -> list[calc_cost.CostLine]:
    """Each budget category as its own "work package", the whole project as the
    one "control account" every line rolls into — see the module docstring."""
    return [
        calc_cost.CostLine(
            work_package=line.category, control_account=project.name, amount=line.planned_amount
        )
        for line in budget_lines
    ]


def _baseline_tasks(project: Project, as_of: date) -> list[evm.BaselineTask]:
    """This project's approved plan lines as ``calc.evm.BaselineTask`` objects —
    the same adaptation ``adapters.snapshot_from`` makes, needed here again because
    the S-curve wants the tasks themselves, not a computed snapshot."""
    baseline = adapters.plan_baseline(project, as_of)
    lines = baseline.lines if baseline else []
    ordered = sorted(lines, key=lambda line: line.task_id)
    return [
        evm.BaselineTask(str(x.task_id), x.planned_start, x.planned_finish, x.planned_cost)
        for x in ordered
    ]


def _planned_periods(curve: tuple[calc_cost.SCurvePoint, ...]) -> list[calc_cost.PeriodAmount]:
    """The S-curve's cumulative points, differenced into one planned amount per
    sampled period — what a funding limit is reconciled against. Clamped at zero:
    the accrual is non-decreasing, so a negative difference is float noise, not a
    real de-accrual."""
    periods: list[calc_cost.PeriodAmount] = []
    previous = 0.0
    for point in curve:
        periods.append(
            calc_cost.PeriodAmount(
                period=point.as_of.isoformat(),
                amount=max(0.0, round(point.cumulative_planned - previous, 2)),
            )
        )
        previous = point.cumulative_planned
    return periods


def _parse_limits(raw: list[str]) -> dict[str, float]:
    """``"<period>:<amount>"`` query values into a limits map. A token that does
    not parse is skipped rather than 500ing this read-only what-if — the page
    still renders every other section."""
    limits: dict[str, float] = {}
    for token in raw:
        period, _, amount = token.partition(":")
        if not amount:
            continue
        try:
            limits[period] = float(amount)
        except ValueError:
            continue
    return limits


def actual_periods(costs: list[CostEntry], as_of: date) -> list[calc_cost.PeriodAmount]:
    """Actual spend, bucketed by calendar month, oldest first — what ``run_rate``
    reads its trailing window from. Public: the department workspace reads the
    same buckets over a department's accountable projects together."""
    buckets: dict[str, float] = {}
    for entry in costs:
        if entry.incurred_on <= as_of:
            key = entry.incurred_on.strftime("%Y-%m")
            buckets[key] = buckets.get(key, 0.0) + entry.amount
    return [
        calc_cost.PeriodAmount(period=k, amount=round(v, 2)) for k, v in sorted(buckets.items())
    ]


def _historical_reference(db: Db, project: Project, as_of: date) -> list[dict[str, Any]]:
    """Other projects' actual spend as of ``as_of`` — real reference figures for
    the analogous estimator below, bounded rather than a whole-store dump."""
    others = db.scalars(
        select(Project)
        .where(Project.id != project.id)
        .order_by(Project.name)
        .limit(_HISTORICAL_LIMIT)
    ).all()
    if not others:
        return []
    other_ids = [other.id for other in others]
    totals: dict[int, float] = dict(
        db.execute(
            select(CostEntry.project_id, func.sum(CostEntry.amount))
            .where(CostEntry.project_id.in_(other_ids))
            .where(CostEntry.incurred_on <= as_of)
            .group_by(CostEntry.project_id)
        )
        .tuples()
        .all()
    )
    return [
        {"name": other.name, "actual_cost": round(totals.get(other.id, 0.0) or 0.0, 2)}
        for other in others
    ]


def create_assist_cost_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The cost workbench page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/cost", response_class=HTMLResponse)
    def assist_cost(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        contingency_pct: float | None = None,
        risk_exposure: float | None = None,
        management_pct: float | None = None,
        limit: list[str] = Query(default=[]),
        financing_principal: float | None = None,
        financing_rate: float | None = None,
        financing_periods: float | None = None,
        financing_method: str = "simple",
        samples: int = Query(default=12, ge=1),
        window: int = Query(default=3, ge=1),
        prevention: float | None = None,
        appraisal: float | None = None,
        internal_failure: float | None = None,
        external_failure: float | None = None,
        analogous_reference_value: float | None = None,
        analogous_reference_size: float | None = None,
        analogous_target_size: float | None = None,
        analogous_adjustment: float = 1.0,
        parametric_rate: float | None = None,
        parametric_quantity: float | None = None,
        three_point_optimistic: float | None = None,
        three_point_most_likely: float | None = None,
        three_point_pessimistic: float | None = None,
        three_point_method: str = "triangular",
        three_point_sigma: float = 1.0,
        bottom_up_component_1: float | None = None,
        bottom_up_component_2: float | None = None,
        bottom_up_component_3: float | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        budget_lines = adapters.project_rows(db, BudgetLine, project_id)
        costs = adapters.project_costs(db, project)

        cost_lines = _cost_lines(project, budget_lines)
        aggregation = calc_cost.cost_aggregation(cost_lines) if cost_lines else None

        works_base = sum(
            line.planned_amount for line in budget_lines if line.category != "contingency"
        )
        stored_contingency = exposure.stored_contingency_line(db, project)
        reserve_result = None
        if management_pct is not None and (contingency_pct is None) != (risk_exposure is None):
            reserve_result = calc_cost.reserve_analysis(
                works_base,
                contingency_pct=contingency_pct,
                risk_exposure=risk_exposure,
                management_pct=management_pct,
            )

        baseline_tasks = _baseline_tasks(project, at)
        curve = (
            calc_cost.cash_flow_s_curve(baseline_tasks, at, samples=samples)
            if baseline_tasks
            else ()
        )
        planned_periods = _planned_periods(curve)
        limits_by_period = _parse_limits(limit)
        breaches = (
            calc_cost.funding_limit_reconciliation(planned_periods, limits_by_period)
            if limits_by_period
            else ()
        )

        financing_result = None
        if None not in (financing_principal, financing_rate, financing_periods):
            assert financing_principal is not None and financing_rate is not None
            assert financing_periods is not None
            financing_result = calc_cost.financing_cost(
                financing_principal, financing_rate, financing_periods, method=financing_method
            )

        periods = actual_periods(costs, at)
        run_rate_value = calc_cost.run_rate(periods, window) if periods else 0.0

        coq_result = None
        if None not in (prevention, appraisal, internal_failure, external_failure):
            assert prevention is not None and appraisal is not None
            assert internal_failure is not None and external_failure is not None
            coq_result = calc_quality.cost_of_quality(
                prevention, appraisal, internal_failure, external_failure
            )

        analogous_result = None
        if None not in (analogous_reference_value, analogous_reference_size, analogous_target_size):
            assert analogous_reference_value is not None and analogous_reference_size is not None
            assert analogous_target_size is not None
            analogous_result = estimating.analogous(
                analogous_reference_value,
                analogous_reference_size,
                analogous_target_size,
                analogous_adjustment,
            )

        parametric_result = None
        if None not in (parametric_rate, parametric_quantity):
            assert parametric_rate is not None and parametric_quantity is not None
            parametric_result = estimating.parametric(parametric_rate, parametric_quantity)

        three_point_result = None
        if None not in (three_point_optimistic, three_point_most_likely, three_point_pessimistic):
            assert three_point_optimistic is not None and three_point_most_likely is not None
            assert three_point_pessimistic is not None
            if three_point_method == "beta":
                three_point_result = estimating.three_point_beta(
                    three_point_optimistic,
                    three_point_most_likely,
                    three_point_pessimistic,
                    sigma=three_point_sigma,
                )
            else:
                three_point_result = estimating.three_point_triangular(
                    three_point_optimistic, three_point_most_likely, three_point_pessimistic
                )

        bottom_up_components = [
            estimating.parametric(1.0, value)
            for value in (bottom_up_component_1, bottom_up_component_2, bottom_up_component_3)
            if value is not None
        ]
        bottom_up_result = (
            estimating.bottom_up(bottom_up_components) if bottom_up_components else None
        )

        context = {
            "project": project,
            "as_of": at.isoformat(),
            "aggregation": aggregation,
            "reserve": {
                "works_base": round(works_base, 2),
                "stored_contingency": stored_contingency,
                "contingency_pct": contingency_pct,
                "risk_exposure": risk_exposure,
                "management_pct": management_pct,
                "result": reserve_result,
            },
            "curve": curve,
            "planned_periods": planned_periods,
            "limit_inputs": limit,
            "breaches": breaches,
            "financing": {
                "principal": financing_principal,
                "rate": financing_rate,
                "periods": financing_periods,
                "method": financing_method,
                "result": financing_result,
            },
            "samples": samples,
            "window": window,
            "actual_periods": periods,
            "run_rate": round(run_rate_value, 2),
            "cost_of_quality": {
                "prevention": prevention,
                "appraisal": appraisal,
                "internal_failure": internal_failure,
                "external_failure": external_failure,
                "result": coq_result,
            },
            "historical": _historical_reference(db, project, at),
            "analogous": {
                "reference_value": analogous_reference_value,
                "reference_size": analogous_reference_size,
                "target_size": analogous_target_size,
                "adjustment": analogous_adjustment,
                "result": analogous_result,
            },
            "parametric": {
                "rate": parametric_rate,
                "quantity": parametric_quantity,
                "result": parametric_result,
            },
            "three_point": {
                "optimistic": three_point_optimistic,
                "most_likely": three_point_most_likely,
                "pessimistic": three_point_pessimistic,
                "method": three_point_method,
                "sigma": three_point_sigma,
                "result": three_point_result,
            },
            "bottom_up": {
                "component_1": bottom_up_component_1,
                "component_2": bottom_up_component_2,
                "component_3": bottom_up_component_3,
                "result": bottom_up_result,
            },
            "provenance": {key: _provenance(at, key) for key in PROCESS_IDS},
            "stored_estimates": _stored_estimates(db, project, at),
            "estimate_form": _estimate_prefill(
                works_base,
                [
                    ("bottom_up", bottom_up_result),
                    ("three_point", three_point_result),
                    ("parametric", parametric_result),
                    ("analogous", analogous_result),
                ],
            ),
            "estimate_kinds": ESTIMATE_KINDS,
            # Every figure above is hypothetical. If one should become the plan, this
            # is the one link to the change boundary (driftless.web.change_boundary).
            "change_boundary": change_boundary(project_id, CHANGE_PROCESS_ID),
        }
        return TEMPLATES.TemplateResponse(request, "assist_cost.html", context)

    @router.post("/projects/{project_id}/assist/cost/estimate")
    def file_estimate(
        request: Request,
        project_id: int,
        db: Db,
        kind: Annotated[str, Form()],
        value: Annotated[float, Form()],
        low: Annotated[str, Form()] = "",
        high: Annotated[str, Form()] = "",
        basis: Annotated[str, Form()] = "",
        actor: Annotated[str, Form()] = "web",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """File one cost estimate scenario through the same boundary the JSON route
        uses — the page's one write; the budget itself still only changes through a
        change request."""
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.EstimateScenarioIn(
                project_id=project.id,
                target="cost",
                kind=kind,  # type: ignore[arg-type]
                value=value,
                low=float(low) if low.strip() else None,
                high=float(high) if high.strip() else None,
                basis=basis,
                actor=actor or "web",
                as_of=at,
            )
        except (ValidationError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        file_estimate_scenario(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/cost?as_of={at.isoformat()}", status_code=303
        )

    return router
