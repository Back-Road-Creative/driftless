"""A failed import says what landed, carries every task field, and exits 2.

One POST is one row and no transaction spans them, so a failure on row 3 of 5
leaves rows 1-2 created. These pin the compensating contract: the failure names
what landed, ``--skip`` re-runs only the rest, a task field the importer cannot
carry is refused rather than dropped, and a bad file is rc 2 with one line on
stderr instead of a traceback.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "driftless-import.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_import", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _post_failing_at(calls: list[tuple[str, dict[str, Any]]], nth: int) -> Any:
    """A ``post`` that records calls and raises on the ``nth`` one (1-based)."""

    def post(path: str, payload: dict[str, Any]) -> int:
        if len(calls) + 1 == nth:
            raise RuntimeError("HTTP 500 from the API")
        calls.append((path, payload))
        return len(calls)

    return post


_ROWS = [{"name": f"Task {n}", "workstream_id": "1"} for n in range(1, 6)]


def test_a_failed_row_names_exactly_what_landed() -> None:
    module = _load()
    calls: list[tuple[str, dict[str, Any]]] = []

    with pytest.raises(module.PartialImport) as caught:
        module.import_csv(_post_failing_at(calls, 3), "tasks", _ROWS)

    assert caught.value.counts == {"tasks": 2}
    assert [payload["name"] for _, payload in calls] == ["Task 1", "Task 2"]
    assert "HTTP 500" in str(caught.value)


def test_a_rerun_skipping_what_landed_does_not_duplicate_it() -> None:
    module = _load()
    calls: list[tuple[str, dict[str, Any]]] = []

    counts = module.import_csv(_post_failing_at(calls, 0), "tasks", _ROWS, skip=2)

    assert counts == {"tasks": 5}
    assert [payload["name"] for _, payload in calls] == ["Task 3", "Task 4", "Task 5"]
    with pytest.raises(ValueError, match="past the end"):
        module.import_csv(_post_failing_at([], 0), "tasks", _ROWS, skip=6)


def test_a_failed_json_walk_names_every_level_that_landed() -> None:
    module = _load()
    sample = json.loads((_SCRIPT.parent / "sample-import.json").read_text(encoding="utf-8"))
    calls: list[tuple[str, dict[str, Any]]] = []

    with pytest.raises(module.PartialImport) as caught:
        module.import_data(_post_failing_at(calls, 6), sample)

    levels = ("businesses", "portfolios", "projects", "workstreams", "tasks")
    assert caught.value.counts == dict.fromkeys(levels, 1)


def _hierarchy(task: dict[str, Any]) -> dict[str, Any]:
    """The smallest business -> ... -> workstream nesting that carries ``task``."""
    project = {"name": "Pr", "workstreams": [{"name": "W", "tasks": [task]}]}
    return {"businesses": [{"name": "B", "portfolios": [{"name": "P", "projects": [project]}]}]}


def test_a_json_task_carries_every_field_the_csv_path_accepts() -> None:
    module = _load()
    calls: list[tuple[str, dict[str, Any]]] = []
    task = {"name": "Colour grade", "percent_complete": 25, "status": "in_progress"}

    module.import_data(_post_failing_at(calls, 0), _hierarchy(task))

    assert calls[-1] == ("/tasks", {**task, "estimate_unit": "hours", "workstream_id": 4})


@pytest.mark.parametrize(
    ("field", "message"),
    [("owner", "unknown field 'owner'"), ("workstream_id", "comes from the parent workstream")],
)
def test_a_json_task_field_the_importer_would_drop_is_refused(field: str, message: str) -> None:
    module = _load()
    with pytest.raises(ValueError, match=message):
        module.import_data(_post_failing_at([], 0), _hierarchy({"name": "Colour grade", field: 7}))


def test_a_bad_file_exits_2_with_one_line_and_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    missing = tmp_path / "nope.json"
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    unknown = tmp_path / "rows.csv"
    unknown.write_text("name,workstream_id,owner\nMix,1,JP\n", encoding="utf-8")

    for argv, needle in (
        ([str(missing)], "nope.json"),
        ([str(broken)], "broken.json is not valid json"),
        ([str(unknown), "--csv", "tasks"], "unknown column 'owner'"),
    ):
        assert module.main(argv, post=_post_failing_at([], 0)) == 2
        lines = capsys.readouterr().err.strip().splitlines()
        assert len(lines) == 1, lines
        assert lines[0].startswith("error: ") and needle in lines[0].lower()


def test_the_cli_prints_a_machine_readable_record_of_what_landed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    rows = tmp_path / "rows.csv"
    rows.write_text(
        "name,workstream_id\n" + "".join(f"Task {n},1\n" for n in range(1, 6)), encoding="utf-8"
    )

    rc = module.main([str(rows), "--csv", "tasks"], post=_post_failing_at([], 3))

    assert rc == 2
    lines = capsys.readouterr().err.strip().splitlines()
    assert json.loads(lines[1].removeprefix("landed: ")) == {"tasks": 2}
    assert "--skip 2" in lines[2]
