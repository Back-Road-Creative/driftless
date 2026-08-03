"""The data importer walks the JSON hierarchy and posts each level in order.

The importer is a pure function over an injected ``post`` callable, so this
drives it with a recorder instead of a live API and checks the counts, the
paths, and that each child carries its parent's freshly-created id. The CSV mode
is driven the same way: one flat record per row, posted to the same validated
endpoints, with every bad file refused before the first POST goes out.
"""

import csv
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "driftless-import.py"

Call = tuple[str, dict[str, Any]]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_import", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recorder() -> tuple[list[Call], Any]:
    """A ``post`` that records every call and hands back ascending ids."""
    calls: list[Call] = []
    ids = iter(range(1, 100))

    def post(path: str, payload: dict[str, Any]) -> int:
        calls.append((path, payload))
        return next(ids)

    return calls, post


def test_import_data_posts_the_hierarchy_in_order() -> None:
    module = _load()
    sample = json.loads((_SCRIPT.parent / "sample-import.json").read_text(encoding="utf-8"))

    calls: list[tuple[str, dict[str, Any]]] = []
    ids = iter(range(1, 100))

    def post(path: str, payload: dict[str, Any]) -> int:
        calls.append((path, payload))
        return next(ids)

    counts = module.import_data(post, sample)

    assert counts == {"businesses": 1, "portfolios": 1, "projects": 1, "workstreams": 1, "tasks": 2}
    paths = [path for path, _ in calls]
    assert paths == ["/businesses", "/portfolios", "/projects", "/workstreams", "/tasks", "/tasks"]
    # The portfolio carries the business id the business POST returned (1).
    assert calls[1][1]["business_id"] == 1
    assert calls[2][1]["portfolio_id"] == 2
    assert calls[4][1]["workstream_id"] == 4 and calls[4][1]["estimate"] == 40


def test_import_data_is_empty_safe() -> None:
    module = _load()
    assert module.import_data(lambda p, b: 0, {}) == {
        "businesses": 0,
        "portfolios": 0,
        "projects": 0,
        "workstreams": 0,
        "tasks": 0,
    }


def test_import_csv_posts_every_sample_task_row() -> None:
    module = _load()
    calls, post = _recorder()
    with (_SCRIPT.parent / "sample-tasks.csv").open(newline="", encoding="utf-8") as handle:
        counts = module.import_csv(post, "tasks", csv.DictReader(handle))

    assert counts == {"tasks": 3}
    assert [path for path, _ in calls] == ["/tasks", "/tasks", "/tasks"]
    assert calls[0][1] == {
        "name": "Colour grade",
        "workstream_id": 1,
        "status": "in_progress",
        "estimate": 40.0,
        "estimate_unit": "hours",
        "percent_complete": 25,
        # The sample carries actual_effort on this row and leaves it blank on the others, so
        # the shipped example exercises both halves of a column the importer has always
        # accepted: 52.5 hours spent against a 40-hour estimate.
        "actual_effort": 52.5,
    }
    # A blank optional cell is omitted from the payload, never posted as "" — actual_effort
    # included, which is why the sample leaves it empty here rather than everywhere.
    assert calls[2][1] == {
        "name": "Deliver master",
        "workstream_id": 1,
        "status": "todo",
        "estimate_unit": "hours",
    }


_KIND_ROWS: dict[str, tuple[dict[str, str], Call]] = {
    "risks": (
        {
            "project_id": "3",
            "description": "Lead editor unavailable",
            "probability": "0.3",
            "impact": "5000",
            "owner": "JP",
        },
        (
            "/risks",
            {
                "project_id": 3,
                "description": "Lead editor unavailable",
                "probability": 0.3,
                "impact": 5000.0,
                "owner": "JP",
            },
        ),
    ),
    "costs": (
        {"project_id": "3", "category": "labour", "incurred_on": "2026-07-01", "amount": "1250.50"},
        (
            "/cost-entries",
            {"project_id": 3, "category": "labour", "incurred_on": "2026-07-01", "amount": 1250.5},
        ),
    ),
    "milestones": (
        {
            "project_id": "3",
            "name": "Rough cut locked",
            "target_date": "2026-08-15",
            "status": "met",
        },
        (
            "/milestones",
            {
                "project_id": 3,
                "name": "Rough cut locked",
                "target_date": "2026-08-15",
                "status": "met",
            },
        ),
    ),
}


def test_import_csv_posts_each_kind_to_its_own_endpoint() -> None:
    module = _load()
    for kind, (row, expected) in _KIND_ROWS.items():
        calls, post = _recorder()
        assert module.import_csv(post, kind, [row]) == {kind: 1}
        assert calls == [expected]


@pytest.mark.parametrize(
    ("kind", "row", "message"),
    [
        ("tasks", {"name": "Mix", "workstream_id": "1", "owner": "JP"}, "unknown column 'owner'"),
        ("tasks", {"name": "Mix"}, "required column 'workstream_id' is missing or empty"),
        ("tasks", {"name": "Mix", "workstream_id": ""}, "required column 'workstream_id'"),
        ("tasks", {"name": "Mix", "workstream_id": "one"}, "column 'workstream_id' value 'one'"),
        (
            "costs",
            {"project_id": "3", "category": "labour", "incurred_on": "07/01/26", "amount": "5"},
            "column 'incurred_on' value '07/01/26'",
        ),
        ("sprints", {"name": "S1"}, "unknown --csv kind 'sprints'"),
    ],
)
def test_import_csv_refuses_a_bad_file(kind: str, row: dict[str, str], message: str) -> None:
    module = _load()
    calls, post = _recorder()
    with pytest.raises(ValueError, match=re.escape(message)):
        module.import_csv(post, kind, [row])
    assert calls == []


def test_import_csv_posts_nothing_when_a_later_row_is_bad() -> None:
    """Every row is coerced before the first POST, so a bad file lands nothing."""
    module = _load()
    calls, post = _recorder()
    rows = [{"name": "Good", "workstream_id": "1"}, {"name": "Bad", "workstream_id": "x"}]
    with pytest.raises(ValueError, match="row 3"):
        module.import_csv(post, "tasks", rows)
    assert calls == []
