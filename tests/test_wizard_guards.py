"""Wizard baseline guards.

F-D2: a wizard-seeded approved vN+1 silently becomes the plan of record
(``plan_baseline`` is max(version) over approved rows) and cannot be repaired
through the API — so the producer refuses while an approved baseline exists.
F-D4: per-row commits left a committed partial baseline on a mid-write failure —
so the four rows land on ONE commit, and a failure commits nothing.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless import cli
from driftless.api import schemas as s
from driftless.assess.adapters import plan_baseline
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import Baseline, Business, Portfolio, Project, Task, Workstream
from driftless.wizard.cli import AlreadyBaselined, produce
from tests.conftest import AS_OF


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'guards.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)
    register_changelog(made)  # wizard writes are audited, exactly like the API's
    return made


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as db:
        yield db


def _project(db: Session) -> Project:
    project = Project(
        name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
    )
    db.add(project)
    db.commit()
    return project


@pytest.mark.parametrize("kind", ["scope_baseline", "schedule_baseline"])
def test_produce_refuses_while_an_approved_baseline_exists(session: Session, kind: str) -> None:
    """A second apply must not file the approved v2 that would replace the plan."""
    project = _project(session)
    produce(session, project, kind, {"planned_cost": 250_000.0}, AS_OF)

    with pytest.raises(AlreadyBaselined, match="approved"):
        produce(session, project, kind, {}, AS_OF)

    versions = session.scalars(
        select(Baseline.version).where(Baseline.project_id == project.id)
    ).all()
    assert versions == [1], f"the refusal still wrote a baseline: versions {versions}"
    plan = plan_baseline(project)
    assert plan is not None and plan.version == 1
    assert sum(line.planned_cost for line in plan.lines) == 250_000.0


def test_a_draft_baseline_does_not_block_onboarding(session: Session) -> None:
    """A draft is a proposal, not the plan — only an *approved* row refuses."""
    project = _project(session)
    session.add(Baseline(project_id=project.id, version=1, status="draft"))
    session.commit()

    produce(session, project, "scope_baseline", {"planned_cost": "1000"}, AS_OF)
    plan = plan_baseline(project)
    assert plan is not None and plan.version == 2, "the draft blocked the first real plan"


def test_wizard_cli_apply_refuses_when_a_plan_of_record_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``wizard apply --kind scope_baseline`` against an approved project exits 2
    and writes no v2 row — the CLI currency of the same refusal."""
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        _project(db)

    argv = ["wizard", "apply", "--project", "GMS", "--kind", "scope_baseline", "--field",
            "planned_cost=1000", "--as-of", AS_OF.isoformat(), "--db-url", url]  # fmt: skip
    assert cli.main(argv) == 0, "onboarding's first baseline should land"
    assert cli.main(argv) == 2, "the second apply exited 0 — it filed a new plan"
    assert "approved" in capsys.readouterr().err

    with new_session_factory(engine)() as db:
        assert db.scalars(select(Baseline.version)).all() == [1]


def test_a_mid_write_failure_commits_no_partial_baseline(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure on the fourth row leaves NO committed workstream, task or baseline —
    and no ChangeLog entries claiming those writes happened."""

    def boom(**_: object) -> None:
        raise RuntimeError("forced failure building the baseline line")

    with factory() as db:
        project = _project(db)
        monkeypatch.setattr(s, "BaselineLineIn", boom)
        with pytest.raises(RuntimeError):
            produce(db, project, "scope_baseline", {"planned_cost": "1000"}, AS_OF)

    with factory() as check:
        for model in (Workstream, Task, Baseline):
            rows = check.scalars(select(model)).all()
            assert not rows, f"a mid-write failure committed {model.__name__} rows: {rows}"
        logged = {
            row.table_name
            for row in check.scalars(select(ChangeLog).where(ChangeLog.operation == "insert"))
        }
        assert not ({"workstream", "task", "baseline"} & logged), (
            f"the audit trail records inserts the store does not hold: {logged}"
        )


def test_a_successful_baseline_lands_whole_for_a_later_session(
    factory: sessionmaker[Session],
) -> None:
    """The one commit really commits: a fresh session sees all four rows, and the
    ChangeLog audited every one of them."""
    with factory() as db:
        row_id = produce(db, _project(db), "scope_baseline", {"planned_cost": "1000"}, AS_OF)

    with factory() as check:
        baseline = check.get(Baseline, row_id)
        assert baseline is not None and baseline.status == "approved"
        (line,) = baseline.lines
        assert line.task.workstream.name == "Delivery"
        logged = {
            row.table_name
            for row in check.scalars(select(ChangeLog).where(ChangeLog.operation == "insert"))
        }
        assert {"workstream", "task", "baseline", "baseline_line"} <= logged
