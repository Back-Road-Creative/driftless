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


def _task(
    name: str, status: str, done: int, estimate: float, who: str, unit: str = "hours"
) -> dict[str, Any]:
    """``done`` is the percent complete every earned-value figure is recovered from (at 0
    the store reads EV 0, CPI 0, SPI 0); ``who`` the assignee the board shows it against.
    ``unit`` routes it: ``flow_facts.remaining_points`` counts only point-estimated open
    tasks, ``assess.evaluators.resource`` only hour-estimated ones against capacity."""
    effort = {"estimate": estimate, "estimate_unit": unit, "assignee": who}
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


def _dependency(
    predecessor: str, successor: str, kind: str = "FS", lag_days: int = 0
) -> dict[str, Any]:
    """One typed precedence edge, both ends named the way ``_baseline``'s lines name
    a task -- resolved to ids only once the walk has posted the tasks, so a rename
    fails loudly instead of pointing the edge somewhere else."""
    return {
        "predecessor": predecessor,
        "successor": successor,
        "kind": kind,
        "lag_days": lag_days,
    }


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


def _requirement(code: str, statement: str, category: str, priority: str) -> dict[str, Any]:
    return {"code": code, "statement": statement, "category": category, "priority": priority}


def _deliverable(
    wbs_code: str,
    name: str,
    status: str,
    parent_wbs_code: str | None = None,
    trace_requirement: str | None = None,
    accepted: tuple[int, int, str, str] | None = None,
) -> dict[str, Any]:
    """One WBS node. ``accepted`` is ``(verified offset, accepted offset, actor, note)``
    from the project's anchor, resolved to dates only once the walk has one in hand —
    the same reason ``_baseline``'s lines take offsets rather than dates."""
    row: dict[str, Any] = {"wbs_code": wbs_code, "name": name, "status": status}
    if parent_wbs_code is not None:
        row["parent_wbs_code"] = parent_wbs_code
    if trace_requirement is not None:
        row["trace_requirement"] = trace_requirement
    if accepted is not None:
        row["accepted"] = accepted
    return row


def _resource_type(name: str, kind: str, unit: str, rate: float) -> dict[str, Any]:
    return {"name": name, "kind": kind, "unit": unit, "rate": rate}


def _assignment(person: str, role: str, target_wbs_code: str) -> dict[str, Any]:
    """One RACI line. ``target_wbs_code`` names the deliverable by its WBS code,
    resolved to an id only once the walk has the deliverable map in hand — the
    same offset-until-resolved shape ``_deliverable``'s ``trace_requirement`` uses."""
    return {"person": person, "role": role, "target_wbs_code": target_wbs_code}


def _acquisition(
    resource_type: str,
    source: str,
    requested_offset: int,
    status: str,
    fulfilled_offset: int | None,
) -> dict[str, Any]:
    return {
        "resource_type": resource_type,
        "source": source,
        "requested_offset": requested_offset,
        "status": status,
        "fulfilled_offset": fulfilled_offset,
    }


def _team_assessment(
    assessed_offset: int, dimension: str, score: float, actor: str
) -> dict[str, Any]:
    return {
        "assessed_offset": assessed_offset,
        "dimension": dimension,
        "score": score,
        "actor": actor,
    }


def _conflict(
    raised_offset: int,
    parties: str,
    approach: str,
    actor: str,
    resolved_offset: int | None = None,
    action_owner: str | None = None,
    action_due_offset: int | None = None,
) -> dict[str, Any]:
    """One conflict, with an optional single follow-up action. ``action_owner``
    is a person name; absent, the conflict is logged with no action yet."""
    row: dict[str, Any] = {
        "raised_offset": raised_offset,
        "parties": parties,
        "approach": approach,
        "actor": actor,
        "resolved_offset": resolved_offset,
    }
    if action_owner is not None:
        row["action_owner"] = action_owner
        row["action_due_offset"] = action_due_offset
    return row


def _sprint(
    name: str, start: int, end: int, committed: int, completed: int, goal: str, notes: str = ""
) -> dict[str, Any]:
    """One iteration -- a ``Sprint`` row, which is what an iteration IS here
    (``models.agile`` module docstring). Offsets are days from the project's anchor;
    ``notes`` given, the review and the retrospective are both recorded on its last
    day, which is the evidence a closed iteration leaves behind."""
    return {
        "name": name,
        "start_offset": start,
        "end_offset": end,
        "committed_points": committed,
        "completed_points": completed,
        "goal": goal,
        "notes": notes,
    }


def _backlog_item(
    title: str,
    points: int,
    status: str,
    priority: str,
    created: int,
    started: int | None = None,
    done: int | None = None,
) -> dict[str, Any]:
    """One board card: ``status`` is what WIP and the CFD bands are counted off, and
    the three offsets (days from the project's anchor) are the effective-time dates
    ``pmbok.flow_facts`` reads -- what makes cycle time, lead time and the trailing
    week's throughput real at a FIXED anchor instead of collapsing to ``date.min``.

    ``started``/``done`` stay ``None`` for a card that has not reached that state, so
    the seed never claims a start for unstarted work; ``created <= started <= done``,
    which is what ``BacklogItem``'s CHECK requires.
    """
    return {
        "title": title,
        "story_points": points,
        "status": status,
        "priority": priority,
        "created_offset": created,
        "started_offset": started,
        "done_offset": done,
    }


def _impediment(
    text: str, who: str, raised: int, resolved: int | None, status: str
) -> dict[str, Any]:
    """A blocker against the team, offsets in days from the project's anchor."""
    return {
        "description": text,
        "raised_by": who,
        "raised_offset": raised,
        "resolved_offset": resolved,
        "status": status,
    }


def _department_ops(
    anchor: date,
    service_name: str,
    service_owner: str,
    service_note: str,
    requester: str,
    control_name: str,
    control_owner: str,
    control_note: str,
    incident_text: str,
    improvement_what: str,
    improvement_why: str,
    improvement_owner: str,
) -> dict[str, Any]:
    """One department's operating records (``driftless.models.operations``): a
    service, a work request already under way, a weekly recurring check, a
    service level against the same service, a control with the one incident
    raised against it, a proposed improvement, and the runbook link filed on
    the department (``ArtifactLink``) with the handover note beside it
    (``Note``) -- one row per table, so
    every section of the department drill page has something real on it
    (``tests/test_demo_web.py``)."""
    return {
        "services": [{"name": service_name, "owner": service_owner, "description": service_note}],
        "work_requests": [
            {
                "service": service_name,
                "requester": requester,
                "raised_on": _dated(anchor, -18),
                "priority": "high",
                "status": "in_progress",
                "started_on": _dated(anchor, -14),
            }
        ],
        "recurring_work": [
            {
                "name": f"{service_name} weekly check",
                "cadence": "weekly",
                "owner": service_owner,
                "next_due_on": _dated(anchor, 7),
            }
        ],
        "service_levels": [
            {"service": service_name, "measure": "turnaround_hours", "target": 48.0}
        ],
        "controls": [
            {
                "name": control_name,
                "owner": control_owner,
                "description": control_note,
                "incident": {
                    "description": incident_text,
                    "severity": "medium",
                    "raised_on": _dated(anchor, -21),
                    "status": "resolved",
                    "resolved_on": _dated(anchor, -19),
                },
            }
        ],
        "improvements": [
            {
                "what": improvement_what,
                "why": improvement_why,
                "owner": improvement_owner,
                "status": "in_progress",
            }
        ],
        "artifact_links": [
            {
                "title": f"{service_name} runbook",
                "uri": "https://wiki.example.com/runbooks/"
                + service_name.lower().replace(" ", "-"),
                "actor": service_owner,
                "as_of": _dated(anchor, -14),
            }
        ],
        "notes": [
            {
                "body": f"{service_name} on-call handover moved to Mondays.",
                "actor": service_owner,
                "as_of": _dated(anchor, -7),
            }
        ],
    }


def demo_payload(anchor: date = ANCHOR) -> dict[str, Any]:
    """Build the demo store: 2 businesses, 1 program, 4 projects, mixed RAID and
    status data. Every statused project (not the no-data one) carries an approved
    baseline covering every one of their tasks, budget lines and cost entries
    spread over several weeks before ``anchor`` -- what makes the dashboard's
    S-curve, burn sparklines and portfolio treemap render with real shape. The
    no-data project carries none of that: RAG-unknown needs BAC == 0 (no
    baseline, no milestones, no status snapshot), so it stays baseline-less on
    purpose rather than merely snapshot-less.

    Rollout also carries the schedule the gantt page is demonstrated on: nine
    tasks across the whole post-production chain, ten typed dependencies between
    them (one start-to-start, the rest finish-to-start) and five milestones, so
    the page draws a network with a critical path and two tasks holding float.
    Only its two original tasks carry planned cost, so the chain moves no
    earned-value figure -- BAC, EV, AC, CPI and SPI read exactly as before.

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
    week) on Rollout -- 80 h once the post-production chain above is his, which
    only deepens a red the risk exposure already forced -- and Nadia is
    over (24 h against 20 h) on the pilot, which reads no-data whatever its
    threats say. That leaves Dana at 20/40 and Priya at 30/40 -- clear -- so
    Archive stays amber on its cost and change signals and Fleet stays green."""
    # Post-production, front to back: enough of the real chain that the gantt draws a
    # schedule rather than two bars. Only the two original tasks carry planned cost
    # (in ``_baseline`` below), so the whole chain holds schedule windows without
    # moving BAC, EV, CPI or SPI a cent -- the shape the hybrid project's cost-free
    # task already set. The open ones sit on Theo, who the resource story already
    # has over his week, so no OTHER project's verdict moves; Dana takes the two a
    # producer actually does.
    rollout_tasks = [
        _task("Shoot schedule", "done", 100, 24.0, "Dana Ruiz"),
        _task("Dailies review", "done", 100, 12.0, "Dana Ruiz"),
        _task("Assembly edit", "done", 100, 16.0, "Theo Marchetti"),
        _task("Rough cut", "in_progress", 55, 40.0, "Theo Marchetti"),
        _task("Music clearance", "in_progress", 30, 8.0, "Dana Ruiz"),
        _task("Colour grade", "todo", 0, 18.0, "Theo Marchetti"),
        _task("Sound mix", "todo", 0, 12.0, "Theo Marchetti"),
        _task("Broadcast QC", "todo", 0, 6.0, "Theo Marchetti"),
        _task("Delivery to network", "todo", 0, 4.0, "Theo Marchetti"),
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
        # Point-estimated: the scope the release forecast burns down, not hours load.
        _task("Driver app iteration scope", "in_progress", 30, 21.0, "Priya Nair", unit="points"),
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
            _milestone(anchor, "Principal photography wrap", -21, "met"),
            # offset=-10, slip defaults to 0: baseline_date == target_date. This is
            # inert for the demo's slip signal -- assess.evaluators.schedule.
            # milestone_slipped() only fires on status=="missed" or
            # target_date > baseline_date, neither true here. Confirmed by
            # tests/test_demo_seed_premiere_baseline.py. The -10 is only Premiere's
            # calendar placement (before the anchor, after the wrap milestone above);
            # the demo's live slip comes from "Sizzle reel delivery" below
            # (status="missed", slip=14), which the Schedule Report, the assist
            # surfaces, and the schedule evaluator all key off instead. Do not add a
            # slip= here to "fix" this without checking with JP first -- it would
            # change the demo's visible threat set.
            _milestone(anchor, "Premiere", -10, "pending"),
            _milestone(anchor, "Sizzle reel delivery", -24, "missed", slip=14),
            _milestone(anchor, "Picture lock", 14, "pending"),
            _milestone(anchor, "Network delivery accepted", 46, "pending"),
        ],
        "issues": [_issue("Colourist unavailable for the grade window", anchor, -18, "open")],
        # 5.6 Control Scope: monitoring found the cut needs work the plan never held.
        "change_requests": [_change("Add two pickup shoot days", anchor, -25, "proposed", "5.6")],
        "quality_measurements": [_quality("Colour QC rejects per reel", 1.0, 3.0, anchor, -12)],
        # 5.4 Create WBS: the requirements/WBS worksheet needs something real to
        # show — one requirement, a two-node WBS, a trace between them and the
        # acceptance the root's finished node already earned.
        "requirements": [
            _requirement(
                "REQ-1",
                "Deliver a broadcast-ready cut in time for premiere",
                "business",
                "must_have",
            )
        ],
        "deliverables": [
            _deliverable("1", "Season 4 cut", "in_progress"),
            _deliverable(
                "1.1",
                "Shoot schedule",
                "accepted",
                parent_wbs_code="1",
                trace_requirement="REQ-1",
                accepted=(-5, -3, "Dana Ruiz", "Matches the approved shot list"),
            ),
        ],
        # 9.2 Acquire Resources: the team assist page needs something real to show
        # — one resource type, an RBS node over it, a RACI line against the root
        # deliverable, an acquisition, an assessment reading and a conflict with
        # its one follow-up action.
        "resource_types": [_resource_type("Colourist", "people", "hours", 85.0)],
        "resource_breakdown": [{"resource_type": "Colourist", "quantity": 1.0}],
        "assignments": [_assignment("Dana Ruiz", "accountable", "1")],
        "acquisitions": [_acquisition("Colourist", "external", -45, "fulfilled", -40)],
        "team_assessments": [_team_assessment(-14, "Performing", 82.0, "demo")],
        "conflicts": [
            _conflict(
                -18,
                "Colourist, Sound mixer",
                "compromise",
                "demo",
                action_owner="Dana Ruiz",
                action_due_offset=-10,
            )
        ],
        "baseline": _baseline(
            anchor,
            (
                ("Shoot schedule", -56, -21, 6_000.0),
                ("Dailies review", -49, -35, 0.0),
                ("Assembly edit", -35, -21, 0.0),
                ("Rough cut", -21, 14, 9_000.0),
                ("Music clearance", -14, 21, 0.0),
                ("Colour grade", 14, 28, 0.0),
                ("Sound mix", 14, 25, 0.0),
                ("Broadcast QC", 28, 40, 0.0),
                ("Delivery to network", 40, 46, 0.0),
            ),
        ),
        # The network the schedule assistant reads: the shoot feeds the cut, the cut
        # feeds grade and mix in parallel, and everything converges on the broadcast
        # QC pass. Dailies start a week into the shoot (start-to-start, lag 7) rather
        # than waiting for it, so the demo carries a relationship that is not
        # finish-to-start. Grade is the longer of the two parallel legs, so the mix
        # carries float and the grade does not; clearance runs wide of both, so its
        # float is large -- a critical path and real slack, not a flat list.
        "dependencies": [
            _dependency("Shoot schedule", "Dailies review", "SS", 7),
            _dependency("Dailies review", "Assembly edit"),
            _dependency("Assembly edit", "Rough cut"),
            _dependency("Shoot schedule", "Rough cut"),
            _dependency("Rough cut", "Colour grade"),
            _dependency("Rough cut", "Sound mix"),
            _dependency("Colour grade", "Broadcast QC"),
            _dependency("Sound mix", "Broadcast QC"),
            _dependency("Music clearance", "Broadcast QC"),
            _dependency("Broadcast QC", "Delivery to network"),
        ],
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
        # The adaptive half of the demo: every other project runs predictive, which left
        # every flow surface demonstrating its empty state. Three closed iterations is
        # what a velocity band needs (``calc.forecast`` rolls the last three), one in
        # flight is what burndown and burnup draw over, and a board with cards in every
        # state is what WIP and the CFD bands are counted off. ``hybrid`` rather than
        # ``agile`` because the flow reads gate on "agile or hybrid" while
        # ``api.rules._UNIT_FOR_MODE`` still lets it keep hour-estimated tasks.
        "delivery_mode": "hybrid",
        "release": {"name": "Driver App 2.0", "target_offset": 32, "status": "planned"},
        "sprints": [
            _sprint("Sprint 12", -56, -43, 20, 18, "Telematics data lands in the driver app."),
            _sprint(
                "Sprint 13",
                -42,
                -29,
                20,
                21,
                "Offline routes survive a depot dead zone.",
                "Depot leads accepted the offline cache; fuel log deferred.",
            ),
            _sprint(
                "Sprint 14",
                -28,
                -15,
                22,
                19,
                "Fuel logging replaces the paper sheet.",
                "Two cards carried over; the team is capping WIP at three.",
            ),
            _sprint("Sprint 15", -14, 4, 20, 8, "Depot handover runs without a phone call."),
        ],
        # The dates trace the same story the sprint reviews above tell: check-in and
        # the offline cache closed inside Sprint 13, the fuel log was deferred there,
        # picked up in Sprint 14, carried over and finished four days before the
        # anchor -- one completion inside the trailing week, and three visibly
        # different cycle times rather than one number repeated three ways.
        "backlog_items": [
            _backlog_item("Driver check-in flow", 5, "done", "must_have", -45, -40, -34),
            _backlog_item("Offline route cache", 8, "done", "must_have", -44, -37, -30),
            _backlog_item("Fuel log capture", 3, "done", "should_have", -40, -26, -4),
            _backlog_item("Depot handover screen", 5, "in_progress", "must_have", -35, -10),
            _backlog_item("Push notification opt-in", 3, "in_progress", "should_have", -32, -6),
            _backlog_item("Vehicle defect report", 8, "ready", "should_have", -28),
            _backlog_item("Shift summary export", 5, "ready", "could_have", -21),
            _backlog_item("Multi-language labels", 13, "proposed", "could_have", -16),
        ],
        "project_roles": [
            {"role": "product_owner", "holder": "Priya Nair"},
            {"role": "scrum_master", "holder": "Nadia Halvorsen"},
        ],
        "definition_of_done": [
            "Accepted by a depot lead on a real handset, not a simulator.",
            "Works offline for a full shift and reconciles on reconnect.",
        ],
        "impediments": [
            _impediment(
                "Test handsets locked to old firmware", "Nadia Halvorsen", -20, -13, "resolved"
            ),
            _impediment(
                "No depot willing to pilot the handover screen", "Priya Nair", -6, None, "open"
            ),
        ],
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
            (
                ("Telematics rollout", -49, -14, 24_000.0),
                ("Driver onboarding", -14, 21, 16_000.0),
                # Points, never money: holds the window without moving BAC or CPI.
                ("Driver app iteration scope", -14, 4, 0.0),
            ),
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
    production_ops = _department_ops(
        anchor,
        service_name="Colour grading",
        service_owner="Dana Ruiz",
        service_note="Post-production colour pass for every deliverable.",
        requester="Theo Marchetti",
        control_name="Dual sign-off on vendor payments",
        control_owner="Dana Ruiz",
        control_note="A second producer signs off any payment over $2,000.",
        incident_text="A vendor payment cleared without the second signature",
        improvement_what="Automate the render-farm licence check",
        improvement_why="A licence lapsed mid-season and stalled the rough cut",
        improvement_owner="Dana Ruiz",
    )
    operations_ops = _department_ops(
        anchor,
        service_name="Route dispatch",
        service_owner="Priya Nair",
        service_note="Assigns each day's routes and confirms driver capacity.",
        requester="Nadia Halvorsen",
        control_name="Fuel card reconciliation",
        control_owner="Priya Nair",
        control_note="Every fuel card charge is matched against its assigned route weekly.",
        incident_text="A fuel card was charged outside its assigned route",
        improvement_what="Add geofencing to fuel cards",
        improvement_why="Off-route fuel use went unnoticed for a week",
        improvement_owner="Priya Nair",
    )
    return {
        "anchor": anchor,
        "businesses": [
            {
                "name": "Anchor Point Studios",
                "departments": [
                    {
                        "name": "Production",
                        "people": [dana, theo],
                        # 9.2 Acquire Resources: a person's own training ledger, so
                        # the team assist page's "who lacks what" has a filled half.
                        "training_records": [
                            {
                                "person": "Dana Ruiz",
                                "topic": "Colour grading refresher",
                                "completed_on": _dated(anchor, -60),
                            }
                        ],
                        **production_ops,
                    }
                ],
                "scorecard": [
                    {
                        "perspective": "financial",
                        "name": "Protect delivery margin",
                        "owner": "Dana Ruiz",
                        "metrics": [
                            {
                                "name": "Gross margin",
                                "direction": "higher_is_better",
                                "unit": "percent",
                                "target_value": 90.0,
                                "amber_threshold": 80.0,
                                "red_threshold": 70.0,
                                "cadence_days": 30,
                                "observations": [
                                    {
                                        "observed_on": _dated(anchor, -5),
                                        "value": 86.0,
                                        "evidence_note": "Month-end close",
                                    }
                                ],
                            }
                        ],
                        "contributions": [
                            {
                                "project": "Season 4 Rollout",
                                "contribution_type": "direct",
                                "rationale": "Controls production rework.",
                            },
                            {
                                "project": "Archive Digitization",
                                "contribution_type": "supporting",
                                "rationale": "Protects the shared delivery margin.",
                            },
                        ],
                    },
                    {
                        "perspective": "customer_stakeholder",
                        "name": "Keep stakeholders informed",
                        "owner": "Theo Marchetti",
                        "metrics": [
                            {
                                "name": "Open escalations",
                                "direction": "lower_is_better",
                                "unit": "count",
                                "target_value": 1.0,
                                "amber_threshold": 2.0,
                                "red_threshold": 4.0,
                                "cadence_days": 14,
                                "observations": [
                                    {
                                        "observed_on": _dated(anchor, -3),
                                        "value": 5.0,
                                        "evidence_note": "Stakeholder review",
                                    }
                                ],
                            }
                        ],
                        "contributions": [
                            {
                                "project": "Season 4 Rollout",
                                "contribution_type": "direct",
                                "rationale": "Makes release risk visible.",
                            }
                        ],
                    },
                    {
                        "perspective": "internal_operations",
                        "name": "Ship reliably",
                        "owner": "Dana Ruiz",
                        "metrics": [
                            {
                                "name": "Release checklist completion",
                                "direction": "higher_is_better",
                                "unit": "percent",
                                "target_value": 95.0,
                                "amber_threshold": 85.0,
                                "red_threshold": 70.0,
                                "cadence_days": 30,
                                "observations": [
                                    {
                                        "observed_on": _dated(anchor, -4),
                                        "value": 98.0,
                                        "evidence_note": "Release audit",
                                    }
                                ],
                            },
                            {
                                "name": "Escaped defects",
                                "direction": "lower_is_better",
                                "unit": "count",
                                "target_value": 1.0,
                                "amber_threshold": 2.0,
                                "red_threshold": 4.0,
                                "cadence_days": 30,
                                "observations": [
                                    {
                                        "observed_on": _dated(anchor, -4),
                                        "value": 5.0,
                                        "evidence_note": "Quality review",
                                    }
                                ],
                            },
                        ],
                        "contributions": [
                            {
                                "project": "Season 4 Rollout",
                                "contribution_type": "direct",
                                "rationale": "Improves the release gate.",
                            }
                        ],
                    },
                    {
                        "perspective": "people_capability",
                        "name": "Build delivery capability",
                        "owner": "Theo Marchetti",
                        "metrics": [
                            {
                                "name": "Cross-trained roles",
                                "direction": "higher_is_better",
                                "unit": "percent",
                                "target_value": 80.0,
                                "amber_threshold": 60.0,
                                "red_threshold": 40.0,
                                "cadence_days": 60,
                                "observations": [],
                            }
                        ],
                        "contributions": [
                            {
                                "project": "Archive Digitization",
                                "contribution_type": "supporting",
                                "rationale": "Creates repeatable team practice.",
                            }
                        ],
                    },
                ],
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
                "departments": [{"name": "Operations", "people": [priya, nadia], **operations_ops}],
                "scorecard": [
                    {
                        "perspective": "internal_operations",
                        "name": "Reduce fleet waste",
                        "owner": "Priya Nair",
                        "metrics": [
                            {
                                "name": "Fuel savings",
                                "direction": "higher_is_better",
                                "unit": "percent",
                                "target_value": 12.0,
                                "amber_threshold": 8.0,
                                "red_threshold": 4.0,
                                "cadence_days": 30,
                                "observations": [
                                    {
                                        "observed_on": _dated(anchor, -6),
                                        "value": 10.0,
                                        "evidence_note": "Fleet operations review",
                                    }
                                ],
                            }
                        ],
                        "contributions": [
                            {
                                "project": "Fleet Modernization",
                                "contribution_type": "direct",
                                "rationale": "Delivers the telematics improvement.",
                            },
                            {
                                "project": "Route Optimization Pilot",
                                "contribution_type": "supporting",
                                "rationale": "Tests the savings model.",
                            },
                        ],
                    }
                ],
                "portfolios": [
                    {"name": "Fleet Programs", "program": None, "projects": [pilot, fleet_mod]}
                ],
            },
        ],
    }
