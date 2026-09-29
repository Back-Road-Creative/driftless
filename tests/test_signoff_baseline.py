"""A sign-off can reference a baseline version — through the one write path.

``SIGNOFF_SUBJECTS`` learns ``"baseline"`` (``driftless/models/governance.py``), and
``driftless.services.sign_offs.create_sign_off`` validates that ``subject_ref`` names a
real ``Baseline`` row belonging to the sign-off's own ``project_id`` and sitting in a
status a decision can actually be recorded against (``"approved"`` or ``"superseded"``
— a ``"draft"`` has not been approved yet, so there is nothing to sign off on).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Baseline, Business, Portfolio, Project, SignOff
from driftless.services.sign_offs import create_sign_off


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()
    return project


def _payload(**overrides: object) -> s.SignOffIn:
    base = {"subject_kind": "baseline", "subject_ref": "1", "decision": "accepted"}
    return s.SignOffIn(**{**base, **overrides})  # type: ignore[arg-type]


def test_a_sign_off_on_an_approved_baseline_is_accepted_and_listed(
    session: Session, project: Project
) -> None:
    baseline = Baseline(project=project, version=1, status="approved")
    session.add(baseline)
    session.commit()

    row = create_sign_off(
        session,
        _payload(project_id=project.id, subject_ref=str(baseline.id)),
        signed_by="jp",
    )

    assert (row.subject_kind, row.subject_ref, row.decision) == (
        "baseline",
        str(baseline.id),
        "accepted",
    )
    assert session.query(SignOff).one().id == row.id


def test_a_sign_off_on_a_superseded_baseline_is_also_accepted(
    session: Session, project: Project
) -> None:
    baseline = Baseline(project=project, version=1, status="superseded")
    session.add(baseline)
    session.commit()

    row = create_sign_off(
        session,
        _payload(project_id=project.id, subject_ref=str(baseline.id)),
        signed_by="jp",
    )
    assert row.decision == "accepted"


def test_a_sign_off_on_a_draft_baseline_is_refused(session: Session, project: Project) -> None:
    baseline = Baseline(project=project, version=1, status="draft")
    session.add(baseline)
    session.commit()

    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref=str(baseline.id)), signed_by="jp"
        )
    assert excinfo.value.status_code == 422


def test_a_baseline_from_another_project_is_refused(session: Session, project: Project) -> None:
    other = Project(
        name="Other",
        portfolio=Portfolio(name="P2", business=Business(name="B2")),
        delivery_mode="predictive",
    )
    baseline = Baseline(project=other, version=1, status="approved")
    session.add_all([other, baseline])
    session.commit()

    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref=str(baseline.id)), signed_by="jp"
        )
    assert excinfo.value.status_code == 404


def test_a_nonexistent_baseline_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref="999999"), signed_by="jp"
        )
    assert excinfo.value.status_code == 404


def test_a_baseline_sign_off_with_no_project_id_is_refused(session: Session) -> None:
    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(session, _payload(project_id=None, subject_ref="1"), signed_by="jp")
    assert excinfo.value.status_code == 422


def test_a_non_numeric_subject_ref_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref="not-an-id"), signed_by="jp"
        )
    assert excinfo.value.status_code == 422


def test_baseline_is_in_the_schema_literal_and_the_model_vocabulary() -> None:
    from typing import get_args

    from driftless.models.governance import SIGNOFF_SUBJECTS

    assert "baseline" in SIGNOFF_SUBJECTS
    assert "baseline" in get_args(s.SignoffSubject)
