"""A gate is a thin sign-off bundle: readiness is computed from the ITTO process-state
engine, never stored, and passage is a ``SignOff`` row like any other subject
(``SIGNOFF_SUBJECTS`` learns ``"gate"``, ``driftless/models/governance.py``).

``driftless.pmbok.state.gate_readiness`` is exercised directly, and
``driftless.services.sign_offs.create_sign_off`` — the one write path — refuses a
non-waiving gate decision while the gate is not ready.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Gate, NarrativeArtifact, Portfolio, Project, Risk, SignOff
from driftless.pmbok import catalog, state as st
from driftless.services.sign_offs import create_sign_off

AS_OF = date(2026, 3, 31)

# 11.2 Identify Risks: outputs risk_register, risk_report, assumption_log — the same
# process tests/test_process_state.py drives PRODUCED with a Risk + an assumption_log.
IDENTIFY_RISKS = catalog.get("11.2")


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
    )
    session.add(project)
    session.commit()
    return project


def _payload(**overrides: object) -> s.SignOffIn:
    base: dict[str, object] = {
        "subject_kind": "gate",
        "subject_ref": "1",
        "decision": "accepted",
        "as_of": AS_OF,
    }
    return s.SignOffIn(**{**base, **overrides})  # type: ignore[arg-type]


def _produce_identify_risks(session: Session, project: Project) -> None:
    session.add(Risk(project=project, description="r", probability=0.3, impact=1000.0))
    session.add(NarrativeArtifact(project=project, kind="assumption_log", body="weather"))
    session.commit()


# ---- readiness -------------------------------------------------------------------


def test_a_gate_naming_no_processes_is_vacuously_ready(session: Session, project: Project) -> None:
    gate = Gate(project=project, name="Kickoff", position=1, required_processes="")
    session.add(gate)
    session.commit()
    ready, missing = st.gate_readiness(gate, project, session, AS_OF)
    assert ready is True and missing == ()


def test_a_gate_is_not_ready_until_its_required_process_is_produced(
    session: Session, project: Project
) -> None:
    gate = Gate(project=project, name="Planning", position=1, required_processes="11.2")
    session.add(gate)
    session.commit()

    ready, missing = st.gate_readiness(gate, project, session, AS_OF)
    assert ready is False and missing == ("11.2",)

    _produce_identify_risks(session, project)
    ready, missing = st.gate_readiness(gate, project, session, AS_OF)
    assert ready is True and missing == ()


def test_a_waived_required_process_still_counts_as_met(session: Session, project: Project) -> None:
    gate = Gate(project=project, name="Planning", position=1, required_processes="11.2")
    session.add(gate)
    session.add(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(IDENTIFY_RISKS, project),
            decision="waived",
        )
    )
    session.commit()
    ready, missing = st.gate_readiness(gate, project, session, AS_OF)
    assert ready is True and missing == ()


# ---- sign-off validation ----------------------------------------------------------


def test_a_gate_sign_off_is_refused_while_the_gate_is_not_ready(
    session: Session, project: Project
) -> None:
    gate = Gate(project=project, name="Planning", position=1, required_processes="11.2")
    session.add(gate)
    session.commit()

    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref=str(gate.id)), signed_by="jp"
        )
    assert excinfo.value.status_code == 422


def test_a_gate_sign_off_is_accepted_once_the_gate_is_ready(
    session: Session, project: Project
) -> None:
    gate = Gate(project=project, name="Planning", position=1, required_processes="11.2")
    session.add(gate)
    session.commit()
    _produce_identify_risks(session, project)

    row = create_sign_off(
        session, _payload(project_id=project.id, subject_ref=str(gate.id)), signed_by="jp"
    )
    assert (row.subject_kind, row.subject_ref, row.decision) == (
        "gate",
        st.gate_subject_ref(gate),
        "accepted",
    )
    assert st.gate_passed(gate, session, AS_OF) is True


def test_a_not_ready_gate_can_still_be_waived(session: Session, project: Project) -> None:
    gate = Gate(project=project, name="Planning", position=1, required_processes="11.2")
    session.add(gate)
    session.commit()

    row = create_sign_off(
        session,
        _payload(project_id=project.id, subject_ref=str(gate.id), decision="waived"),
        signed_by="jp",
    )
    assert row.decision == "waived"
    assert st.gate_passed(gate, session, AS_OF) is True


def test_a_gate_from_another_project_is_refused(session: Session, project: Project) -> None:
    other = Project(name="Other", portfolio=Portfolio(name="P2", business=Business(name="B2")))
    gate = Gate(project=other, name="Kickoff", position=1, required_processes="")
    session.add_all([other, gate])
    session.commit()

    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref=str(gate.id)), signed_by="jp"
        )
    assert excinfo.value.status_code == 404


def test_a_nonexistent_gate_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session, _payload(project_id=project.id, subject_ref="999999"), signed_by="jp"
        )
    assert excinfo.value.status_code == 404


def test_a_non_numeric_subject_ref_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(HTTPException) as excinfo:
        create_sign_off(
            session,
            _payload(project_id=project.id, subject_ref="not-an-id"),
            signed_by="jp",
        )
    assert excinfo.value.status_code == 422


def test_a_gate_sign_off_with_no_as_of_is_refused_by_the_schema() -> None:
    with pytest.raises(ValueError):
        s.SignOffIn(
            subject_kind="gate", subject_ref="1", decision="accepted", project_id=1, as_of=None
        )


def test_gate_is_in_the_schema_literal_and_the_model_vocabulary() -> None:
    from typing import get_args

    from driftless.models.governance import SIGNOFF_SUBJECTS

    assert "gate" in SIGNOFF_SUBJECTS
    assert "gate" in get_args(s.SignoffSubject)
