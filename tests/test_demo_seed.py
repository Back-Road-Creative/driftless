"""The demo seed walk posts every row through the validated API, in FK order.

Driven against a fake ``post`` that records calls and hands back incrementing
ids -- no live HTTP, matching ``tests/test_import_script.py``'s pattern.
"""

from typing import Any

from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload


def _run() -> tuple[list[tuple[str, dict[str, Any]]], dict[str, int]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    approvals: list[str] = []
    ids = iter(range(1, 1000))

    def post(path: str, body: dict[str, Any]) -> int:
        calls.append((path, dict(body)))
        return next(ids)

    counts = seed(post, demo_payload(ANCHOR), lambda path, _body: approvals.append(path))
    assert len(approvals) == counts["baselines"], "every baseline is approved, by PATCH, last"
    return calls, counts


def test_seed_creates_parents_before_children_and_carries_their_ids() -> None:
    calls, _ = _run()
    order = [path for path, _ in calls]
    assert order.index("/businesses") < order.index("/departments") < order.index("/people")
    assert order.index("/businesses") < order.index("/portfolios") < order.index("/programs")
    assert order.index("/programs") < order.index("/projects") < order.index("/workstreams")
    assert order.index("/workstreams") < order.index("/tasks")
    assert order.index("/projects") < order.index("/risks") < order.index("/milestones")

    departments = [body for path, body in calls if path == "/departments"]
    assert departments[0]["business_id"] == 1  # first business created is id 1
    # The program link lands on exactly the projects the payload marks, read off
    # the payload rather than a hard count — the walk's property, not the data's.
    projects = [body for path, body in calls if path == "/projects"]
    under = sum(
        p["under_program"]
        for b in demo_payload(ANCHOR)["businesses"]
        for pf in b["portfolios"]
        for p in pf["projects"]
    )
    assert sum("program_id" in body for body in projects) == under
    assert 0 < under < len(projects)  # and at least one hangs straight off its portfolio


def test_seed_counts_match_calls_and_skips_the_no_data_project() -> None:
    calls, counts = _run()
    by_path: dict[str, int] = {}
    for path, _ in calls:
        by_path[path] = by_path.get(path, 0) + 1
    for key, value in counts.items():  # every count key names its path, "_" for "-"
        assert value == by_path["/" + key.replace("_", "-")]
    assert (
        by_path["/status-snapshots"] == by_path["/projects"] - 1
    )  # the no-data project is skipped


def test_seed_creates_baseline_and_cost_rows_fk_ordered() -> None:
    calls, _ = _run()
    order = [path for path, _ in calls]
    assert order.index("/tasks") < order.index("/baselines") < order.index("/baseline-lines")
    assert order.index("/projects") < order.index("/budget-lines")
    assert order.index("/projects") < order.index("/cost-entries")


def test_seed_baseline_lines_resolve_to_the_matching_posted_task_id() -> None:
    """Each baseline line's ``task_id`` is the id the ``/tasks`` POST for the
    SAME-named task actually got back -- the walk resolves by name, not luck."""
    calls, _ = _run()
    task_id_by_name = {
        body["name"]: i + 1 for i, (path, body) in enumerate(calls) if path == "/tasks"
    }
    payload = demo_payload(ANCHOR)
    expected = [
        (task_id_by_name[line["task"]], line["planned_cost"])
        for b in payload["businesses"]
        for pf in b["portfolios"]
        for p in pf["projects"]
        if p["baseline"] is not None
        for line in p["baseline"]["lines"]
    ]
    actual = [
        (body["task_id"], body["planned_cost"]) for path, body in calls if path == "/baseline-lines"
    ]
    assert actual == expected


def test_seed_is_deterministic_across_two_runs() -> None:
    calls_a, counts_a = _run()
    calls_b, counts_b = _run()
    assert calls_a == calls_b
    assert counts_a == counts_b
