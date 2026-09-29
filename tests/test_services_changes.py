"""Preview/apply/confirm: the write happens once, through the existing
service, and preview never touches the store."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api import schemas as s
from driftless.models import SignOff, StatusSnapshot
from driftless.services.changes import (
    Confirmed,
    Preview,
    SignOffChange,
    StatusSnapshotChange,
    apply,
    confirm,
    preview,
)

AS_OF = date(2026, 3, 31)


def _project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add(proj)
    db.commit()
    return proj


def test_preview_of_a_status_snapshot_writes_nothing(db: Session) -> None:
    project = _project(db)
    change = StatusSnapshotChange(
        s.StatusSnapshotIn(project_id=project.id, taken_on=AS_OF, rag_status="green")
    )
    result = preview(db, change)
    assert result == Preview("status_snapshot", ("status_snapshot",))
    assert db.query(StatusSnapshot).count() == 0


def test_apply_of_a_status_snapshot_writes_through_the_service(db: Session) -> None:
    project = _project(db)
    change = StatusSnapshotChange(
        s.StatusSnapshotIn(project_id=project.id, taken_on=AS_OF, rag_status="amber")
    )
    result = apply(db, change, actor="tester")
    assert result.kind == "status_snapshot"
    rows = db.query(StatusSnapshot).all()
    assert [r.id for r in rows] == list(result.row_ids["status_snapshot"])
    assert rows[0].rag_status == "amber"
    # neither model this service writes carries row_revision.
    assert result.revisions["status_snapshot"] == (None,)


def test_preview_of_a_sign_off_writes_nothing(db: Session) -> None:
    project = _project(db)
    change = SignOffChange(
        s.SignOffIn(
            project_id=project.id,
            subject_kind="process",
            subject_ref="process:1.1:project:1",
            decision="waived",
            as_of=AS_OF,
        )
    )
    result = preview(db, change)
    assert result == Preview("sign_off", ("sign_off",))
    assert db.query(SignOff).count() == 0


def test_apply_of_a_sign_off_stamps_the_actor_never_the_payload(db: Session) -> None:
    project = _project(db)
    change = SignOffChange(
        s.SignOffIn(
            project_id=project.id,
            subject_kind="process",
            subject_ref="process:1.1:project:1",
            decision="waived",
            signed_by="whoever-the-request-claimed",
            as_of=AS_OF,
        )
    )
    result = apply(db, change, actor="real-signer")
    row = db.get(SignOff, result.row_ids["sign_off"][0])
    assert row is not None
    assert row.signed_by == "real-signer"


def test_confirm_stamps_the_actor_and_never_mutates(db: Session) -> None:
    project = _project(db)
    change = StatusSnapshotChange(
        s.StatusSnapshotIn(project_id=project.id, taken_on=AS_OF, rag_status="green")
    )
    applied = apply(db, change, actor="tester")
    first = confirm(db, applied, actor="reviewer-a")
    second = confirm(db, applied, actor="reviewer-b")
    assert isinstance(first, Confirmed) and isinstance(second, Confirmed)
    assert first.actor == "reviewer-a"
    assert second.actor == "reviewer-b"
    assert first != second  # a second look is a new record, never an edit


def test_an_unknown_change_kind_is_refused() -> None:
    with pytest.raises(TypeError):
        apply(None, object(), actor="tester")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        preview(None, object())  # type: ignore[arg-type]
