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
from datetime import date
from typing import Any

from driftless.demo.data import ANCHOR, demo_payload

Post = Callable[[str, dict[str, Any]], int]
Patch = Callable[[str, dict[str, Any]], None]

_COUNT_KEYS = (
    "businesses departments people portfolios programs projects "
    "workstreams tasks risks milestones baselines baseline_lines "
    "budget_lines cost_entries status_snapshots issues change_requests "
    "quality_measurements"
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
        for dept in biz["departments"]:
            dept_id = post("/departments", {"name": dept["name"], "business_id": biz_id})
            dept_ids[dept["name"]] = dept_id
            n["departments"] += 1
            for person in dept["people"]:
                person_ids[person["name"]] = post("/people", {**person, "department_id": dept_id})
                n["people"] += 1
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
                if proj["under_program"] and prog_id is not None:
                    body["program_id"] = prog_id
                proj_id = post("/projects", body)
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
