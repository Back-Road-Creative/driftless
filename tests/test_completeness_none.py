"""``completeness`` says "nothing to assess" as ``None`` — never as a fake 0.0
(F-T8: the ``0.0`` mutation survived the whole suite). ``pages.pct`` renders
``None`` as "n/a" and a real 0.0 as "0%", and the feed flags ``None`` as
"nothing assessable yet", so both sides of the boundary are pinned here."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Portfolio, Project, SignOff
from driftless.pmbok import catalog
from driftless.pmbok import state as st

AS_OF = date(2026, 3, 31)


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


def test_completeness_is_none_when_every_process_is_waived(
    session: Session, project: Project
) -> None:
    """Waiving the whole catalog empties the denominator: n/a, never a fake 0%."""
    session.add_all(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(process, project),
            decision="waived",
        )
        for process in catalog.PROCESSES
    )
    session.commit()
    assert st.completeness(project, session, AS_OF) is None


def test_completeness_is_zero_not_none_when_assessable_work_exists(
    session: Session, project: Project
) -> None:
    """The other side of the boundary: a project that has done nothing scores a real 0.0."""
    assert st.completeness(project, session, AS_OF) == 0.0
