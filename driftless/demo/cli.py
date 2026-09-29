"""The ``driftless demo seed`` command: a small, deterministic demo store.

Walks the payload from ``driftless.demo.data`` and posts every row through the
API, never raw SQL, exactly like ``bin/driftless-import.py``. ``seed`` is pure
over an injected ``post``, so it runs against a live API or a fake in tests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from driftless.demo.data import ANCHOR, demo_payload

Post = Callable[[str, dict[str, Any]], int]
Patch = Callable[[str, dict[str, Any]], None]


def _on(anchor: date, offset: int) -> str:
    """``offset`` days from ``anchor``, ISO -- ``demo.data._dated``'s twin, for the
    rows this walk posts from offsets rather than dates."""
    return (anchor + timedelta(days=offset)).isoformat()


_COUNT_KEYS = (
    "businesses departments people department_services work_requests "
    "recurring_work service_levels operating_controls incidents improvements "
    "training_records artifact_links notes "
    "portfolios programs projects "
    "workstreams tasks task_dependencies risks milestones baselines baseline_lines "
    "budget_lines cost_entries status_snapshots issues change_requests "
    "quality_measurements strategic_objectives metric_definitions "
    "metric_observations scorecard_contributions "
    "requirements deliverables requirement_traces acceptance_records "
    "resource_types resource_breakdowns responsibility_assignments acquisitions "
    "team_assessments conflict_records conflict_actions "
    "releases sprints backlog_items project_roles definition_of_done_items impediments"
).split()

#: Per-project collections that post as built — dates already ISO, so the walk adds
#: only the FK, and a project naming none of them simply seeds none.
_PROJECT_RECORDS = ("issues", "change_requests", "quality_measurements")


def seed(post: Post, payload: dict[str, Any], patch: Patch) -> dict[str, int]:
    """Create the demo store in ``payload`` via ``post``; return per-level counts.

    Baselines land as drafts and are approved via ``patch`` only after their
    lines are in — the API freezes an approved baseline, lines included.
    """
    n = dict.fromkeys(_COUNT_KEYS, 0)
    for biz in payload["businesses"]:
        biz_id = post("/businesses", {"name": biz["name"]})
        n["businesses"] += 1
        # Departments and people come first, so a project can name the department
        # accountable for it and a task its assignee — by name in the payload, by
        # the id the API just handed back on the wire.
        dept_ids: dict[str, int] = {}
        person_ids: dict[str, int] = {}
        project_ids: dict[str, int] = {}
        for dept in biz["departments"]:
            dept_id = post("/departments", {"name": dept["name"], "business_id": biz_id})
            dept_ids[dept["name"]] = dept_id
            n["departments"] += 1
            for person in dept["people"]:
                person_ids[person["name"]] = post("/people", {**person, "department_id": dept_id})
                n["people"] += 1
            for record in dept.get("training_records", ()):
                row = dict(record)
                row["person_id"] = person_ids[row.pop("person")]
                post("/training-records", row)
                n["training_records"] += 1
            # The department's own operating records (driftless.models.operations):
            # a service catalog entry first, so a work request or SLA can name it by
            # id; a control before the one incident raised against it, same reason.
            service_ids: dict[str, int] = {}
            for service in dept.get("services", ()):
                service_ids[service["name"]] = post(
                    "/department-services", {**service, "department_id": dept_id}
                )
                n["department_services"] += 1
            for wr in dept.get("work_requests", ()):
                row = dict(wr)
                service_name = row.pop("service", None)
                if service_name is not None:
                    row["service_id"] = service_ids[service_name]
                post("/work-requests", {**row, "department_id": dept_id})
                n["work_requests"] += 1
            for rw in dept.get("recurring_work", ()):
                post("/recurring-work", {**rw, "department_id": dept_id})
                n["recurring_work"] += 1
            for sl in dept.get("service_levels", ()):
                row = dict(sl)
                service_name = row.pop("service", None)
                if service_name is not None:
                    row["service_id"] = service_ids[service_name]
                post("/service-levels", {**row, "department_id": dept_id})
                n["service_levels"] += 1
            for control in dept.get("controls", ()):
                incident = control.get("incident")
                body = {key: value for key, value in control.items() if key != "incident"}
                control_id = post("/operating-controls", {**body, "department_id": dept_id})
                n["operating_controls"] += 1
                if incident is not None:
                    post(
                        "/incidents",
                        {**incident, "department_id": dept_id, "control_id": control_id},
                    )
                    n["incidents"] += 1
            for improvement in dept.get("improvements", ()):
                post("/improvements", {**improvement, "department_id": dept_id})
                n["improvements"] += 1
            for link in dept.get("artifact_links", ()):
                post(
                    "/artifact-links",
                    {**link, "record_kind": "department", "record_id": str(dept_id)},
                )
                n["artifact_links"] += 1
            for note in dept.get("notes", ()):
                post(
                    "/notes",
                    {**note, "record_kind": "department", "record_id": str(dept_id)},
                )
                n["notes"] += 1
        for pf in biz["portfolios"]:
            pf_id = post("/portfolios", {"name": pf["name"], "business_id": biz_id})
            n["portfolios"] += 1
            prog_id = None
            if pf["program"] is not None:
                prog_id = post("/programs", {"name": pf["program"], "portfolio_id": pf_id})
                n["programs"] += 1
            for proj in pf["projects"]:
                body = {
                    "name": proj["name"],
                    "portfolio_id": pf_id,
                    "responsible_department_id": dept_ids[proj["department"]],
                }
                if "delivery_mode" in proj:
                    body["delivery_mode"] = proj["delivery_mode"]
                if proj["under_program"] and prog_id is not None:
                    body["program_id"] = prog_id
                proj_id = post("/projects", body)
                project_ids[proj["name"]] = proj_id
                n["projects"] += 1
                task_ids: dict[str, int] = {}
                for ws in proj["workstreams"]:
                    ws_id = post("/workstreams", {"name": ws["name"], "project_id": proj_id})
                    n["workstreams"] += 1
                    for task in ws["tasks"]:
                        row = dict(task, workstream_id=ws_id)
                        row["assignee_id"] = person_ids[row.pop("assignee")]
                        task_ids[task["name"]] = post("/tasks", row)
                        n["tasks"] += 1
                # Dependencies after every task in the project is in, so an edge may
                # cross workstreams; named by task name, resolved to the ids the
                # ``/tasks`` posts just handed back.
                for dep in proj.get("dependencies", ()):
                    post(
                        "/task-dependencies",
                        {
                            "predecessor_task_id": task_ids[dep["predecessor"]],
                            "successor_task_id": task_ids[dep["successor"]],
                            "kind": dep["kind"],
                            "lag_days": dep["lag_days"],
                        },
                    )
                    n["task_dependencies"] += 1
                for risk in proj["risks"]:
                    post("/risks", {**risk, "project_id": proj_id})
                    n["risks"] += 1
                for m in proj["milestones"]:
                    dates = {key: m[key].isoformat() for key in ("target_date", "baseline_date")}
                    post("/milestones", {**m, "project_id": proj_id, **dates})
                    n["milestones"] += 1
                for key in _PROJECT_RECORDS:
                    for record in proj.get(key, ()):
                        post("/" + key.replace("_", "-"), {**record, "project_id": proj_id})
                        n[key] += 1
                # Requirements first, so a deliverable's trace can name one by code;
                # deliverables in payload order, so a child's parent_wbs_code is
                # already in the map — this project's list is written parent-first.
                requirement_ids: dict[str, int] = {}
                for requirement in proj.get("requirements", ()):
                    requirement_ids[requirement["code"]] = post(
                        "/requirements", {**requirement, "project_id": proj_id, "actor": "demo"}
                    )
                    n["requirements"] += 1
                deliverable_ids: dict[str, int] = {}
                for deliverable in proj.get("deliverables", ()):
                    row = {
                        key: value
                        for key, value in deliverable.items()
                        if key not in ("parent_wbs_code", "trace_requirement", "accepted")
                    }
                    parent_wbs_code = deliverable.get("parent_wbs_code")
                    if parent_wbs_code is not None:
                        row["parent_id"] = deliverable_ids[parent_wbs_code]
                    deliverable_id = post("/deliverables", {**row, "project_id": proj_id})
                    deliverable_ids[deliverable["wbs_code"]] = deliverable_id
                    n["deliverables"] += 1
                    trace_requirement = deliverable.get("trace_requirement")
                    if trace_requirement is not None:
                        post(
                            "/requirement-traces",
                            {
                                "requirement_id": requirement_ids[trace_requirement],
                                "deliverable_id": deliverable_id,
                            },
                        )
                        n["requirement_traces"] += 1
                    accepted = deliverable.get("accepted")
                    if accepted is not None:
                        verified_offset, accepted_offset, actor, note = accepted
                        anchor: date = payload["anchor"]
                        post(
                            "/acceptance-records",
                            {
                                "deliverable_id": deliverable_id,
                                "verified_on": (
                                    anchor + timedelta(days=verified_offset)
                                ).isoformat(),
                                "accepted_on": (
                                    anchor + timedelta(days=accepted_offset)
                                ).isoformat(),
                                "actor": actor,
                                "note": note,
                            },
                        )
                        n["acceptance_records"] += 1
                # Resource records first the RBS depends on, then the RBS and the
                # RACI (which names a deliverable already in the map above), then
                # the acquisitions, assessments and conflicts that stand alone.
                anchor = payload["anchor"]
                resource_type_ids: dict[str, int] = {}
                for rt in proj.get("resource_types", ()):
                    resource_type_ids[rt["name"]] = post(
                        "/resource-types", {**rt, "project_id": proj_id}
                    )
                    n["resource_types"] += 1
                for node in proj.get("resource_breakdown", ()):
                    post(
                        "/resource-breakdowns",
                        {
                            "project_id": proj_id,
                            "resource_type_id": resource_type_ids[node["resource_type"]],
                            "quantity": node["quantity"],
                        },
                    )
                    n["resource_breakdowns"] += 1
                for assignment in proj.get("assignments", ()):
                    post(
                        "/responsibility-assignments",
                        {
                            "project_id": proj_id,
                            "person_id": person_ids[assignment["person"]],
                            "role": assignment["role"],
                            "deliverable_id": deliverable_ids[assignment["target_wbs_code"]],
                        },
                    )
                    n["responsibility_assignments"] += 1
                for acquisition in proj.get("acquisitions", ()):
                    fulfilled_offset = acquisition["fulfilled_offset"]
                    post(
                        "/acquisitions",
                        {
                            "project_id": proj_id,
                            "resource_type_id": resource_type_ids[acquisition["resource_type"]],
                            "source": acquisition["source"],
                            "requested_on": (
                                anchor + timedelta(days=acquisition["requested_offset"])
                            ).isoformat(),
                            "status": acquisition["status"],
                            "fulfilled_on": (
                                (anchor + timedelta(days=fulfilled_offset)).isoformat()
                                if fulfilled_offset is not None
                                else None
                            ),
                        },
                    )
                    n["acquisitions"] += 1
                for assessment in proj.get("team_assessments", ()):
                    post(
                        "/team-assessments",
                        {
                            "project_id": proj_id,
                            "assessed_on": (
                                anchor + timedelta(days=assessment["assessed_offset"])
                            ).isoformat(),
                            "dimension": assessment["dimension"],
                            "score": assessment["score"],
                            "actor": assessment["actor"],
                        },
                    )
                    n["team_assessments"] += 1
                for conflict in proj.get("conflicts", ()):
                    resolved_offset = conflict["resolved_offset"]
                    conflict_id = post(
                        "/conflict-records",
                        {
                            "project_id": proj_id,
                            "raised_on": (
                                anchor + timedelta(days=conflict["raised_offset"])
                            ).isoformat(),
                            "parties": conflict["parties"],
                            "approach": conflict["approach"],
                            "actor": conflict["actor"],
                            "resolved_on": (
                                (anchor + timedelta(days=resolved_offset)).isoformat()
                                if resolved_offset is not None
                                else None
                            ),
                        },
                    )
                    n["conflict_records"] += 1
                    action_owner = conflict.get("action_owner")
                    if action_owner is not None:
                        due_offset = conflict.get("action_due_offset")
                        post(
                            "/conflict-actions",
                            {
                                "conflict_id": conflict_id,
                                "owner_id": person_ids[action_owner],
                                "due_on": (
                                    (anchor + timedelta(days=due_offset)).isoformat()
                                    if due_offset is not None
                                    else None
                                ),
                            },
                        )
                        n["conflict_actions"] += 1
                # Agile execution records: the release first, so a sprint can name
                # it by the id the API just handed back; the rest stand alone.
                release_id = None
                release = proj.get("release")
                if release is not None:
                    release_id = post(
                        "/releases",
                        {
                            "project_id": proj_id,
                            "name": release["name"],
                            "target_date": _on(anchor, release["target_offset"]),
                            "status": release["status"],
                        },
                    )
                    n["releases"] += 1
                for sprint in proj.get("sprints", ()):
                    row = dict(sprint)
                    notes = row.pop("notes") or None
                    began, ended = row.pop("start_offset"), row.pop("end_offset")
                    closed = _on(anchor, ended) if notes else None
                    post(
                        "/sprints",
                        {
                            **row,
                            "project_id": proj_id,
                            "release_id": release_id,
                            "start_date": _on(anchor, began),
                            "end_date": _on(anchor, ended),
                            "review_held_on": closed,
                            "review_notes": notes,
                            "retrospective_held_on": closed,
                            "retrospective_notes": notes,
                        },
                    )
                    n["sprints"] += 1
                for item in proj.get("backlog_items", ()):
                    row = dict(item)
                    dates = {
                        key: None if offset is None else _on(anchor, offset)
                        for key, offset in (
                            ("created_on", row.pop("created_offset")),
                            ("started_on", row.pop("started_offset")),
                            ("done_on", row.pop("done_offset")),
                        )
                    }
                    post("/backlog-items", {**row, **dates, "project_id": proj_id})
                    n["backlog_items"] += 1
                for role in proj.get("project_roles", ()):
                    post("/project-roles", {**role, "project_id": proj_id})
                    n["project_roles"] += 1
                for done_means in proj.get("definition_of_done", ()):
                    post(
                        "/definition-of-done-items",
                        {"project_id": proj_id, "description": done_means},
                    )
                    n["definition_of_done_items"] += 1
                for imp in proj.get("impediments", ()):
                    row = dict(imp)
                    raised = row.pop("raised_offset")
                    resolved = row.pop("resolved_offset")
                    post(
                        "/impediments",
                        {
                            **row,
                            "project_id": proj_id,
                            "raised_on": _on(anchor, raised),
                            "resolved_on": None if resolved is None else _on(anchor, resolved),
                        },
                    )
                    n["impediments"] += 1
                baseline = proj["baseline"]
                if baseline is not None:
                    approved_at = baseline["approved_at"]
                    baseline_id = post(
                        "/baselines",
                        {"project_id": proj_id, "version": baseline["version"]},
                    )
                    n["baselines"] += 1
                    for line in baseline["lines"]:
                        post(
                            "/baseline-lines",
                            {
                                "baseline_id": baseline_id,
                                "task_id": task_ids[line["task"]],
                                "planned_start": line["planned_start"].isoformat(),
                                "planned_finish": line["planned_finish"].isoformat(),
                                "planned_cost": line["planned_cost"],
                            },
                        )
                        n["baseline_lines"] += 1
                    patch(
                        f"/baselines/{baseline_id}",
                        {
                            "status": baseline["status"],
                            "approved_at": approved_at.isoformat() if approved_at else None,
                        },
                    )
                for bl in proj["budget_lines"]:
                    post("/budget-lines", {**bl, "project_id": proj_id})
                    n["budget_lines"] += 1
                for ce in proj["cost_entries"]:
                    incurred_on = ce["incurred_on"].isoformat()
                    post("/cost-entries", {**ce, "project_id": proj_id, "incurred_on": incurred_on})
                    n["cost_entries"] += 1
                if not proj["no_data"]:
                    taken_on = payload["anchor"].isoformat()
                    snapshot = {"taken_on": taken_on, "rag_status": proj["rag"]}
                    post("/status-snapshots", {**snapshot, "project_id": proj_id})
                    n["status_snapshots"] += 1
        for objective in biz.get("scorecard", ()):
            objective_id = post(
                "/strategic-objectives",
                {
                    **{
                        key: objective[key]
                        for key in ("perspective", "name", "description", "owner", "status")
                        if key in objective
                    },
                    "business_id": biz_id,
                },
            )
            n["strategic_objectives"] += 1
            for metric in objective.get("metrics", ()):
                metric_id = post(
                    "/metric-definitions",
                    {
                        **{key: value for key, value in metric.items() if key != "observations"},
                        "objective_id": objective_id,
                    },
                )
                n["metric_definitions"] += 1
                for observation in metric.get("observations", ()):
                    post(
                        "/metric-observations",
                        {**observation, "metric_definition_id": metric_id},
                    )
                    n["metric_observations"] += 1
            for contribution in objective.get("contributions", ()):
                post(
                    "/scorecard-contributions",
                    {
                        **{key: value for key, value in contribution.items() if key != "project"},
                        "project_id": project_ids[contribution["project"]],
                        "objective_id": objective_id,
                    },
                )
                n["scorecard_contributions"] += 1
    return n


def _http_detail(exc: urllib.error.HTTPError) -> str:
    """The server's ``detail`` when the error body is JSON, else the HTTP reason."""
    try:
        body = json.load(exc)
    except (ValueError, AttributeError):
        return str(exc.reason)
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail) if detail else str(exc.reason)


def _run_seed(
    args: argparse.Namespace,
    urlopen: Callable[[urllib.request.Request], Any] | None = None,
) -> int:
    """Probe the store, then seed it — refusing anything that could not be undone.

    A populated store is refused without ``--force``: the API's delete-integrity
    guards (approved baselines, parents with children) make a duplicate demo
    unremovable, so the mistake must be caught before the first POST. Network
    failures come back as a one-line message and a non-zero exit, not a traceback.

    ``urlopen`` defaults to ``urllib.request.urlopen`` looked up at call time —
    never bound early, so a test that monkeypatches the module attribute (as the
    admin-guide doc test does) is honoured.
    """
    if not args.token:
        print("demo seed: no API token — pass --token or set DRIFTLESS_API_TOKEN", file=sys.stderr)
        return 2
    open_url = urllib.request.urlopen if urlopen is None else urlopen

    def call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            args.base_url.rstrip("/") + path,
            # A body-less probe still sends bytes: every request this command
            # makes carries a payload, empty or not, so one wire shape serves all.
            data=b"" if body is None else json.dumps(body).encode(),
            headers={"content-type": "application/json", "authorization": f"Bearer {args.token}"},
            method=method,
        )
        with open_url(request) as response:  # noqa: S310 - operator-supplied URL
            return json.load(response)

    def post(path: str, body: dict[str, Any]) -> int:
        return int(call("POST", path, body)["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        call("PATCH", path, body)

    try:
        existing = call("GET", "/businesses")
        if existing and not args.force:
            print(
                f"demo seed: the store at {args.base_url} already holds "
                f"{len(existing)} business(es); a second seed would duplicate the demo and "
                "the API's integrity guards refuse the cleanup. Pass --force to seed anyway.",
                file=sys.stderr,
            )
            return 1
        counts = seed(post, demo_payload(args.anchor), patch)
    except urllib.error.HTTPError as exc:
        print(f"demo seed: {exc.url}: HTTP {exc.code}: {_http_detail(exc)}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"demo seed: cannot reach {args.base_url}: {exc.reason}", file=sys.stderr)
        return 1
    print("Seeded: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


def add_demo_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``demo`` command onto a parent's subparsers."""
    demo = commands.add_parser("demo", help="populate a running instance with a demo store")
    sub = demo.add_subparsers(dest="demo_command", required=True)

    seed_cmd = sub.add_parser("seed", help="create the demo store through the validated API")
    seed_cmd.add_argument("--base-url", default="http://127.0.0.1:8000")
    seed_cmd.add_argument("--token", default=os.environ.get("DRIFTLESS_API_TOKEN", ""))
    seed_cmd.add_argument("--anchor", type=date.fromisoformat, default=ANCHOR, metavar="YYYY-MM-DD")
    seed_cmd.add_argument(
        "--force",
        action="store_true",
        help="seed even if the store already holds businesses (duplicates cannot be deleted)",
    )
    seed_cmd.set_defaults(handler=_run_seed)
