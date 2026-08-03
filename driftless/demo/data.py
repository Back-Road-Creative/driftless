"""A pure builder for the ``driftless demo seed`` payload.

Every date derives from a single ``anchor`` by a fixed offset -- no
``date.today()``, no randomness -- so ``demo_payload(anchor)`` is identical
for a given anchor, and only the offsets move when the anchor moves.
``driftless.demo.cli.seed`` walks this shape and posts each row through the
API in FK order; nothing here talks to a database or the network.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

#: The fixed default anchor. Every offset in the payload is relative to it.
ANCHOR = date(2026, 7, 1)


def _task(name: str, status: str, done: int, estimate: float, who: str) -> dict[str, Any]:
    """``done`` is the percent complete every earned-value figure is recovered from (at 0
    the store reads EV 0, CPI 0, SPI 0); ``who`` the assignee the board shows it against."""
    effort = {"estimate": estimate, "estimate_unit": "hours", "assignee": who}
    return {"name": name, "status": status, "percent_complete": done, **effort}


def _risk(text: str, odds: float, impact: float, status: str, response: str) -> dict[str, Any]:
    exposure = {"probability": odds, "impact": impact}
    return {"description": text, "status": status, "response": response, **exposure}


def _milestone(anchor: date, name: str, offset: int, status: str, slip: int = 0) -> dict[str, Any]:
    """A commitment ``offset`` days from ``anchor``, baselined ``slip`` days earlier --
    so ``slip=0`` reads as on plan and only a ``missed`` one is a live slip."""
    on = anchor + timedelta(offset)
    dates = {"target_date": on, "baseline_date": on - timedelta(slip)}
    return {"name": name, "status": status, **dates}


def _dated(anchor: date, offset: int) -> str:
    """A date ``offset`` days from ``anchor``, already ISO -- the RAID and quality rows
    below post exactly as built, so the walk does no per-field conversion for them."""
    return (anchor + timedelta(days=offset)).isoformat()


def _issue(text: str, at: date, up: int, status: str, done: int | None = None) -> dict[str, Any]:
    raid: dict[str, Any] = {"raised_on": _dated(at, up), "status": status}
    raid["resolved_on"] = None if done is None else _dated(at, done)
    return {"description": text, **raid}


def _change(text: str, anchor: date, raised: int, status: str, origin: str) -> dict[str, Any]:
    """``origin`` is the PMBOK clause id of the process that raised the request —
    the seeder posts through the real API, so a non-catalog id is refused there."""
    return {
        "description": text,
        "raised_on": _dated(anchor, raised),
        "status": status,
        "origin_process_id": origin,
    }


def _quality(metric: str, target: float, actual: float, anchor: date, on: int) -> dict[str, Any]:
    """One reading. Lower is better -- an actual above target is out of tolerance --
    and a reading more than 30 days old is stale evidence, never green."""
    reading = {"target_value": target, "actual_value": actual}
    return {"metric": metric, "measured_on": _dated(anchor, on), **reading}


def _baseline(anchor: date, plan: tuple[tuple[str, int, int, float], ...]) -> dict[str, Any]:
    """An approved baseline: one line per ``(task name, start offset, finish
    offset, planned cost)``, offsets in days from ``anchor``. Approved a couple
    of months back, well before the earliest planned start."""
    lines = [
        {
            "task": name,
            "planned_start": anchor + timedelta(days=start),
            "planned_finish": anchor + timedelta(days=finish),
            "planned_cost": cost,
        }
        for name, start, finish, cost in plan
    ]
    return {
        "version": 1,
        "status": "approved",
        "approved_at": anchor - timedelta(days=60),
        "lines": lines,
    }


def _spend(anchor: date, entries: tuple[tuple[int, str, float], ...]) -> list[dict[str, Any]]:
    """Cost entries from ``(day offset from anchor, category, amount)`` -- every
    offset negative, so AC accrues before the as-of date the dashboard renders."""
    return [
        {"incurred_on": anchor + timedelta(days=offset), "category": category, "amount": amount}
        for offset, category, amount in entries
    ]


def demo_payload(anchor: date = ANCHOR) -> dict[str, Any]:
    """Build the demo store: 2 businesses, 1 program, 4 projects, mixed RAID and
    status data. Every statused project (not the no-data one) carries an approved
    baseline covering every one of their tasks, budget lines and cost entries
    spread over several weeks before ``anchor`` -- what makes the dashboard's
    S-curve, burn sparklines and portfolio treemap render with real shape. The
    no-data project carries none of that: RAG-unknown needs BAC == 0 (no
    baseline, no milestones, no status snapshot), so it stays baseline-less on
    purpose rather than merely snapshot-less.

    The statused three are one verdict each -- Rollout red (risk exposure past
    contingency, a missed milestone, quality out of tolerance), Archive amber
    (CPI 0.95, an approved change not re-baselined), Fleet green -- because a
    rollup all one colour reads as a broken import, not a portfolio. Progress,
    assignees, department ownership and the RAID/quality rows are there for the
    same reason: ``tests/test_demo_web.py`` walks every page and asserts it.

    Capacity is spread the same way and for the same reason. A person's ratio is
    their whole load against their own capacity, so ONE person over the line
    turns every project they hold work on red -- with both leads carrying
    everything, the spread above collapsed to red and no-data. The two part-time
    contractors are what keeps it honest: Theo is over (40 h against a 30 h
    week) on Rollout, which the risk exposure already makes red, and Nadia is
    over (24 h against 20 h) on the pilot, which reads no-data whatever its
    threats say. That leaves Dana at 20/40 and Priya at 30/40 -- clear -- so
    Archive stays amber on its cost and change signals and Fleet stays green."""
    rollout_tasks = [
        _task("Shoot schedule", "done", 100, 24.0, "Dana Ruiz"),
        _task("Rough cut", "in_progress", 55, 40.0, "Theo Marchetti"),
    ]
    archive_tasks = [
        _task("Scan backlog", "done", 100, 24.0, "Dana Ruiz"),
        _task("Metadata pass", "in_progress", 40, 20.0, "Dana Ruiz"),
    ]
    pilot_tasks = [
        _task("Inventory current routes", "blocked", 0, 8.0, "Nadia Halvorsen"),
        _task("Model fuel savings", "todo", 0, 16.0, "Nadia Halvorsen"),
    ]
    fleet_tasks = [
        _task("Telematics rollout", "done", 100, 60.0, "Priya Nair"),
        _task("Driver onboarding", "in_progress", 45, 30.0, "Priya Nair"),
    ]
    rollout = {
        "name": "Season 4 Rollout",
        "under_program": True,
        "no_data": False,
        "department": "Production",
        "rag": "red",
        "workstreams": [{"name": "Delivery", "tasks": rollout_tasks}],
        "risks": [_risk("Lead editor turnover mid-season", 0.9, 50_000.0, "open", "mitigate")],
        "milestones": [
            _milestone(anchor, "Premiere", -10, "pending"),
            _milestone(anchor, "Sizzle reel delivery", -24, "missed", slip=14),
        ],
        "issues": [_issue("Colourist unavailable for the grade window", anchor, -18, "open")],
        # 5.6 Control Scope: monitoring found the cut needs work the plan never held.
        "change_requests": [_change("Add two pickup shoot days", anchor, -25, "proposed", "5.6")],
        "quality_measurements": [_quality("Colour QC rejects per reel", 1.0, 3.0, anchor, -12)],
        "baseline": _baseline(
            anchor, (("Shoot schedule", -56, -21, 6_000.0), ("Rough cut", -21, 14, 9_000.0))
        ),
        "budget_lines": [
            {"category": "labour", "planned_amount": 12_000.0},
            {"category": "contingency", "planned_amount": 1_500.0},
        ],
        "cost_entries": _spend(
            anchor,
            (
                (-49, "labour", 2_500.0),
                (-35, "labour", 3_000.0),
                (-21, "labour", 2_800.0),
                (-7, "labour", 1_700.0),
            ),
        ),
    }
    archive = {
        "name": "Archive Digitization",
        "under_program": True,
        "no_data": False,
        "department": "Production",
        "rag": "amber",
        "workstreams": [{"name": "Delivery", "tasks": archive_tasks}],
        "risks": [_risk("Scanner throughput below spec", 0.1, 1_200.0, "mitigating", "mitigate")],
        "milestones": [_milestone(anchor, "Scanner acceptance", 21, "at_risk")],
        "issues": [_issue("Scan station down two days", anchor, -30, "resolved", -26)],
        # 5.5 Validate Scope: accepting scanned deliverables exposed the schema gap.
        "change_requests": [_change("Extend metadata schema", anchor, -20, "approved", "5.5")],
        "quality_measurements": [_quality("Scan error rate %", 2.0, 1.4, anchor, -6)],
        "baseline": _baseline(
            anchor, (("Scan backlog", -42, -14, 10_000.0), ("Metadata pass", -14, 28, 6_000.0))
        ),
        "budget_lines": [
            {"category": "labour", "planned_amount": 12_500.0},
            # Archive's amber is CPI and scope, never risk: this reserve covers its
            # one small open exposure (120), so the Risk evaluator reads green.
            # Without the line nothing is held, any open risk is uncovered -- red.
            {"category": "contingency", "planned_amount": 1_000.0},
        ],
        "cost_entries": _spend(
            anchor, ((-35, "labour", 5_500.0), (-21, "labour", 3_200.0), (-7, "labour", 4_300.0))
        ),
    }
    pilot = {
        "name": "Route Optimization Pilot",
        "under_program": False,
        "no_data": True,
        "department": "Operations",
        "workstreams": [{"name": "Delivery", "tasks": pilot_tasks}],
        "risks": [_risk("Fuel-price assumptions go stale", 0.2, 3_000.0, "open", "accept")],
        "milestones": [],
        "baseline": None,
        "budget_lines": [],
        "cost_entries": [],
    }
    fleet_mod = {
        "name": "Fleet Modernization",
        "under_program": False,
        "no_data": False,
        "department": "Operations",
        "rag": "green",
        "workstreams": [{"name": "Delivery", "tasks": fleet_tasks}],
        "risks": [
            _risk("Telematics vendor slips firmware", 0.3, 4_000.0, "closed", "avoid"),
            _risk("Depot wiring rework", 0.5, 2_000.0, "realised", "transfer"),
        ],
        "milestones": [_milestone(anchor, "Fleet go-live", -14, "met")],
        "issues": [_issue("Driver app login fails at two depots", anchor, -12, "open")],
        "quality_measurements": [_quality("Defects per 100 installs", 2.0, 1.1, anchor, -8)],
        "baseline": _baseline(
            anchor,
            (("Telematics rollout", -49, -14, 24_000.0), ("Driver onboarding", -14, 21, 16_000.0)),
        ),
        "budget_lines": [
            {"category": "labour", "planned_amount": 30_000.0},
            {"category": "materials", "planned_amount": 6_000.0},
        ],
        "cost_entries": _spend(
            anchor,
            (
                (-42, "labour", 9_000.0),
                (-28, "labour", 8_500.0),
                (-14, "materials", 6_000.0),
                (-7, "labour", 4_500.0),
            ),
        ),
    }
    dana = {"name": "Dana Ruiz", "role": "Producer", "capacity_hours": 40.0}
    theo = {"name": "Theo Marchetti", "role": "Assistant Editor", "capacity_hours": 30.0}
    priya = {"name": "Priya Nair", "role": "Ops Lead", "capacity_hours": 40.0}
    nadia = {"name": "Nadia Halvorsen", "role": "Route Analyst", "capacity_hours": 20.0}
    return {
        "anchor": anchor,
        "businesses": [
            {
                "name": "Anchor Point Studios",
                "departments": [{"name": "Production", "people": [dana, theo]}],
                "portfolios": [
                    {
                        "name": "Content Operations",
                        "program": "Studio Expansion",
                        "projects": [rollout, archive],
                    }
                ],
            },
            {
                "name": "Fieldstone Logistics",
                "departments": [{"name": "Operations", "people": [priya, nadia]}],
                "portfolios": [
                    {"name": "Fleet Programs", "program": None, "projects": [pilot, fleet_mod]}
                ],
            },
        ],
    }
