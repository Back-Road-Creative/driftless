"""Edge cases and CLI error paths for both importers: malformed rows a real
export can contain (a task missing its name, an unparseable duration, a
predecessor link missing its own uid, a blank line in an XER file) are
skipped rather than guessed at, and the CLI's own guard clauses (no database
URL, no such project) are exercised directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from driftless import cli
from driftless.interchange.cli import _open
from driftless.interchange.msproject import parse_msproject_xml
from driftless.interchange.xer import parse_xer

_MSPDI_NS = "http://schemas.microsoft.com/project"

_MALFORMED_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="{_MSPDI_NS}">
  <Tasks>
    <Task>
      <UID>1</UID>
      <ID>1</ID>
      <Name>Kickoff</Name>
      <Duration></Duration>
    </Task>
    <Task>
      <UID>2</UID>
      <ID>2</ID>
      <Name>Odd Duration</Name>
      <Duration>P1D</Duration>
      <PredecessorLink>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>3</UID>
      <ID>3</ID>
    </Task>
  </Tasks>
</Project>
"""


def test_parse_msproject_xml_skips_unnameable_and_unmeasurable_rows(tmp_path: Path) -> None:
    path = tmp_path / "malformed.xml"
    path.write_text(_MALFORMED_XML)
    schedule = parse_msproject_xml(path)
    # task 3 has no <Name> and is dropped; the other two keep a duration of 0
    # rather than guessing at an empty or unrecognised duration string
    assert {t.external_id for t in schedule.tasks} == {"1", "2"}
    assert {t.duration_days for t in schedule.tasks} == {0}
    # the predecessor link with no <PredecessorUID> is dropped, not guessed
    assert schedule.dependencies == ()


_XER_WITH_BLANK_LINE = """%T\tTASK
%F\ttask_id\ttask_code\ttask_name\ttarget_drtn_hr_cnt
%R\t1\tA1\tOnly\t8

%E
"""


def test_parse_xer_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "blank.xer"
    path.write_text(_XER_WITH_BLANK_LINE)
    schedule = parse_xer(path)
    assert [t.external_id for t in schedule.tasks] == ["1"]


def test_open_refuses_with_no_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRIFTLESS_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DB_URL", raising=False)
    with pytest.raises(SystemExit, match="no database URL"):
        _open(None)


def test_import_cli_reports_unknown_project(tmp_path: Path) -> None:
    from driftless.db import Base, new_engine

    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    Base.metadata.create_all(new_engine(url))
    sample = Path(__file__).resolve().parent / "fixtures" / "interchange" / "msproject-sample.xml"
    rc = cli.main(["import", "msproject", str(sample), "--project", "Nonexistent", "--db-url", url])
    assert rc == 2
