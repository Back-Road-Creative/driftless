"""A failed import says what landed, carries every task field, and exits 2.

One POST is one row and no transaction spans them, so a failure on row 3 of 5
leaves rows 1-2 created. These pin the compensating contract: the failure names
what landed, ``--skip`` re-runs only the rest, a task field the importer cannot
carry is refused rather than dropped, and a bad file is rc 2 with one line on
stderr instead of a traceback.
"""

import importlib.util
import io
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


def _captured_requests(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[Any]:
    """Intercept urlopen so the poster's real headers can be read off the request."""
    sent: list[Any] = []

    class _Answer:
        def __enter__(self) -> Any:
            return io.BytesIO(b'{"id": 1}')

        def __exit__(self, *exc: object) -> None:
            return None

    def _urlopen(request: Any) -> Any:
        sent.append(request)
        return _Answer()

    monkeypatch.setattr(module.urllib.request, "urlopen", _urlopen)
    return sent


def test_every_posted_row_carries_a_distinct_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct per row, so two legitimately identical rows stay two rows -- a key derived
    from payload CONTENT would swallow the second as a retry."""
    module = _load()
    sent = _captured_requests(monkeypatch, module)
    post = module._http_poster("http://x", "t", "import-a")

    post("/businesses", {"name": "One"})
    post("/businesses", {"name": "One"})

    keys = [request.headers["Idempotency-key"] for request in sent]
    assert len(keys) == 2 and keys[0] != keys[1]


def test_re_running_the_same_import_reproduces_the_same_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recovery property: an interrupted run re-run from the start sends the keys it
    already sent, so the store recognises those rows instead of duplicating them."""
    module = _load()
    first = _captured_requests(monkeypatch, module)
    poster = module._http_poster("http://x", "t", "import-a")
    poster("/businesses", {"name": "One"})
    poster("/businesses", {"name": "Two"})

    second = _captured_requests(monkeypatch, module)
    replay = module._http_poster("http://x", "t", "import-a")
    replay("/businesses", {"name": "One"})
    replay("/businesses", {"name": "Two"})

    assert [r.headers["Idempotency-key"] for r in first] == [
        r.headers["Idempotency-key"] for r in second
    ]


def test_skip_resumes_onto_the_keys_the_interrupted_run_would_have_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--skip N`` seeds the row counter, so a resumed run numbers rows the way the
    interrupted one did. Without that seeding it would restart at 0 and every remaining
    row would carry a fresh key -- silently reintroducing the duplicate."""
    module = _load()
    whole = _captured_requests(monkeypatch, module)
    full = module._http_poster("http://x", "t", "import-a")
    for name in ("One", "Two", "Three"):
        full("/businesses", {"name": name})

    rest = _captured_requests(monkeypatch, module)
    resumed = module._http_poster("http://x", "t", "import-a", 2)
    resumed("/businesses", {"name": "Three"})

    assert rest[0].headers["Idempotency-key"] == whole[2].headers["Idempotency-key"]


def test_a_different_id_imports_the_same_file_again_on_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliberate re-import must stay possible; the id is what separates it from a retry."""
    module = _load()
    sent = _captured_requests(monkeypatch, module)
    module._http_poster("http://x", "t", "import-a")("/businesses", {"name": "One"})
    module._http_poster("http://x", "t", "import-b")("/businesses", {"name": "One"})

    assert sent[0].headers["Idempotency-key"] != sent[1].headers["Idempotency-key"]


def test_the_default_import_id_follows_the_files_contents(tmp_path: Path) -> None:
    """Same bytes, same import; edited bytes are a different import, because its rows are
    no longer the ones already sent."""
    module = _load()
    one, two = tmp_path / "a.csv", tmp_path / "b.csv"
    one.write_text("name\nOne\n")
    two.write_text("name\nOne\n")

    assert module.import_id_for(one) == module.import_id_for(two)
    two.write_text("name\nTwo\n")
    assert module.import_id_for(one) != module.import_id_for(two)
