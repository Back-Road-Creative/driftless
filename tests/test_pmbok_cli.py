"""The ``driftless pmbok`` command lists and shows catalog processes.

Exercised through the top-level ``driftless`` CLI, so the registrar wiring is covered
too: filtering by area and group, a full-catalog listing, showing one process,
and a clean error on an unknown id — on stderr, exit 2, leaving stdout empty.
"""

import pytest

from driftless import cli


def test_processes_lists_the_whole_catalog(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "processes"]) == 0
    out = capsys.readouterr().out
    assert "49 process(es)." in out
    assert "4.1  Develop Project Charter" in out


def test_processes_filters_by_area(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "processes", "--area", "risk"]) == 0
    out = capsys.readouterr().out
    assert "7 process(es)." in out
    assert "11.1  Plan Risk Management" in out
    assert "Develop Project Charter" not in out


def test_processes_filters_by_group(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "processes", "--group", "planning"]) == 0
    out = capsys.readouterr().out
    assert "24 process(es)." in out


def test_processes_filters_by_area_and_group(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "processes", "--area", "integration", "--group", "closing"]) == 0
    out = capsys.readouterr().out
    assert "1 process(es)." in out
    assert "4.7  Close Project or Phase" in out


def test_show_prints_one_process_with_its_ittos(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "show", "4.1"]) == 0
    out = capsys.readouterr().out
    assert "Develop Project Charter" in out
    assert "inputs:" in out and "outputs:" in out
    assert "project_charter" in out


def test_show_rejects_an_unknown_id_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pmbok", "show", "99.9"]) == 2
    captured = capsys.readouterr()
    assert "error: no process with id '99.9'" in captured.err
    assert captured.out == ""


def test_an_invalid_area_choice_is_an_argparse_error() -> None:
    with pytest.raises(SystemExit):
        cli.main(["pmbok", "processes", "--area", "nonsense"])
