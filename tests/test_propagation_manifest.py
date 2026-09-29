"""Each native change alters every consumer the manifest declares reachable —
and the manifest, not this file, says which family a change kind cannot
reach and why. A family missing from both the "differs" set and
``UNAFFECTED_BY_CHANGE`` is a silent gap: this file fails on it rather than
letting it pass by omission.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api import schemas as s
from driftless.pmbok import catalog, state
from driftless.pmbok.consumers import CONSUMERS, UNAFFECTED_BY_CHANGE
from driftless.services.changes import (
    CHANGE_KINDS,
    Change,
    SignOffChange,
    StatusSnapshotChange,
    apply,
    preview,
)

AS_OF = date(2026, 3, 31)


def _bare_project(db: Session) -> m.Project:
    """A project with no artifacts, baseline or milestones — the emptiest
    leaf the manifest's readers can be pointed at, so a change kind's effect
    is never masked by something else already having produced the same state."""
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="Bare", portfolio=portfolio, delivery_mode="predictive")
    db.add(proj)
    db.commit()
    return proj


def _family_readings(db: Session, project: m.Project, as_of: date) -> dict[str, object]:
    return {
        family: tuple(reader(db, project, as_of) for reader in readers)
        for family, readers in CONSUMERS.items()
    }


def _assert_manifest_covers(kind: str) -> None:
    """Every unaffected entry for ``kind`` names a family the manifest still has —
    the guard against a family that was retired but left in ``UNAFFECTED_BY_CHANGE``."""
    stale = set(UNAFFECTED_BY_CHANGE.get(kind, {})) - set(CONSUMERS)
    assert not stale, f"{kind} declares unaffected families no longer in CONSUMERS: {stale}"


def _assert_propagates(db: Session, project: m.Project, change: Change, kind: str) -> None:
    assert kind in CHANGE_KINDS
    _assert_manifest_covers(kind)
    unaffected = UNAFFECTED_BY_CHANGE.get(kind, {})

    before = _family_readings(db, project, AS_OF)
    predicted = preview(db, change)
    applied = apply(db, change, actor="tester")
    assert set(predicted.would_touch) == set(applied.row_ids)
    for table, ids in applied.row_ids.items():
        assert predicted.would_touch.count(table) == len(ids)
    after = _family_readings(db, project, AS_OF)

    for family in CONSUMERS:
        if family in unaffected:
            assert before[family] == after[family], (
                f"{kind} was declared unaffected in {family} but the reading changed"
            )
        else:
            assert before[family] != after[family], (
                f"{kind} should reach {family} (or declare it unaffected, with a reason, "
                "in UNAFFECTED_BY_CHANGE)"
            )


def test_a_status_snapshot_reaches_its_declared_families(db: Session) -> None:
    project = _bare_project(db)
    change = StatusSnapshotChange(
        s.StatusSnapshotIn(project_id=project.id, taken_on=AS_OF, rag_status="green")
    )
    _assert_propagates(db, project, change, "status_snapshot")


def test_a_process_sign_off_reaches_its_declared_families(db: Session) -> None:
    project = _bare_project(db)
    process = next(p for p in catalog.PROCESSES if state.is_assessable(p))
    change = SignOffChange(
        s.SignOffIn(
            project_id=project.id,
            subject_kind="process",
            subject_ref=state.process_subject_ref(process, project),
            decision="waived",
            as_of=AS_OF,
        )
    )
    _assert_propagates(db, project, change, "sign_off")


def test_every_change_kind_is_exercised_above() -> None:
    """A third change kind added to ``changes.py`` with no test here is a gap
    the manifest test suite itself must not go quiet about."""
    exercised = {"status_snapshot", "sign_off"}
    assert exercised == set(CHANGE_KINDS)
