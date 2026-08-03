"""The sign-off ledger is bounded by the as-of being asked about (F-C3/F-P4/F-P10):
a decision recorded against a later assessment date must not rewrite an earlier
page, feed or trend point — cached or uncached, and the process cache loads only
the scope's projects' rows while the threat scope is public API."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.assess import engine
from driftless.assess.model import Threat
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Portfolio, Project, SignOff
from driftless.pmbok import catalog
from driftless.pmbok import state as st

JAN, DECIDED, AS_OF = date(2026, 1, 1), date(2026, 3, 1), date(2026, 3, 31)
IDENTIFY_RISKS = catalog.get("11.2")


@pytest.fixture
def session() -> Iterator[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    with new_session_factory(engine_)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
    )
    session.add(project)
    session.commit()
    return project


def _threat(project: Project) -> Threat:
    """A cost threat as the evaluators shape one; suppression reads only id and score."""
    ref = st.threat_subject_ref("cost", project.id)
    return Threat(ref, "cost", "red", 3.75, "CPI slipping.", f"project:{project.id}")


def _threat_sign_off(project: Project, threat: Threat) -> SignOff:
    return SignOff(
        project=project,
        subject_kind="threat",
        subject_ref=threat.id,
        decision="accepted",
        signal=threat.score,
        as_of=DECIDED,
    )


def test_a_threat_sign_off_cannot_rewrite_an_earlier_as_of(
    session: Session, project: Project
) -> None:
    """F-C3: one accepted threat used to vanish from ``/threats?as_of=2020-01-01`` too."""
    threat = _threat(project)
    session.add(_threat_sign_off(project, threat))
    session.commit()
    assert engine.is_suppressed(session, threat, AS_OF), "on/after its as-of it suppresses"
    assert not engine.is_suppressed(session, threat, JAN), "March must not rewrite January"


def test_a_process_sign_off_cannot_rewrite_an_earlier_as_of(
    session: Session, project: Project
) -> None:
    """F-C3: one 2026 sign-off moved a 2020 process map from 9% to 13% — cached or not."""
    jan_share = st.completeness(project, session, JAN)
    session.add(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(IDENTIFY_RISKS, project),
            decision="accepted",
            as_of=DECIDED,
        )
    )
    session.commit()

    def states() -> tuple[st.ProcessState, st.ProcessState]:
        return (
            st.process_state(IDENTIFY_RISKS, project, session, JAN),
            st.process_state(IDENTIFY_RISKS, project, session, AS_OF),
        )

    assert states() == (st.ProcessState.NOT_STARTED, st.ProcessState.SIGNED_OFF)
    with st.prefetched(session, [project]):
        assert states() == (st.ProcessState.NOT_STARTED, st.ProcessState.SIGNED_OFF), (
            "one scope must answer every as-of like the uncached path (the trend asks two)"
        )
    assert st.completeness(project, session, JAN) == jan_share, (
        "a later decision changed an earlier as-of's completeness"
    )


def test_the_process_prefetch_loads_only_the_scopes_projects(
    session: Session, project: Project
) -> None:
    """F-P4: a hub page opens the scope for ONE project; the ledger grows with the store."""
    other = Project(name="Other", portfolio=project.portfolio)
    session.add(other)
    session.commit()
    ours = st.process_subject_ref(IDENTIFY_RISKS, project)
    theirs = st.process_subject_ref(IDENTIFY_RISKS, other)
    for proj, ref in ((project, ours), (other, theirs)):
        session.add(
            SignOff(project=proj, subject_kind="process", subject_ref=ref, decision="waived")
        )
    session.commit()
    with st.prefetched(session, [project]):
        assert st.latest_sign_off(session, "process", ours) is not None
        assert st.latest_sign_off(session, "process", theirs) is None, (
            "an out-of-scope project's rows were loaded: the prefetch is not project-bounded"
        )
    assert st.latest_sign_off(session, "process", theirs) is not None, "uncached reads see it"


def test_the_threat_sign_off_scope_is_public_and_honours_as_of(
    session: Session, project: Project
) -> None:
    """F-P10: report runs open the batching scope themselves; answers match uncached."""
    threat = _threat(project)
    session.add(_threat_sign_off(project, threat))
    session.commit()
    with engine.threat_sign_offs(session):
        assert not engine.is_suppressed(session, threat, JAN)
        assert engine.is_suppressed(session, threat, AS_OF)
