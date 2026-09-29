"""``next_step`` walks every catalog process now — none is invisible to it.

A process the wizard cannot produce an output for used to be skipped as a dead
end; now it is returned as a ``derived`` or ``reference`` step (see
``WizardStep.kind``) instead. The completion proof: waiving every process ahead
of one in lifecycle order and asking ``next_step`` for the next one lands on
exactly that process, whatever its kind — proven for every process the catalog
holds, not a sample of it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import catalog
from driftless.pmbok import state as st
from driftless.pmbok.model import Process, ProcessGroup
from driftless.wizard import engine
from tests.conftest import AS_OF

#: The lifecycle order ``next_step`` itself walks — group first, catalog order
#: within a group — not the catalog's own area order, which interleaves groups.
_LIFECYCLE_ORDER = tuple(process for group in ProcessGroup for process in catalog.by_group(group))


def _waive(session: Session, project: m.Project, process: Process) -> None:
    session.add(
        m.SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(process, project),
            decision="waived",
        )
    )


@pytest.fixture
def bare(db: Session) -> m.Project:
    """A project with nothing in it — the shared ``project`` fixture is pre-seeded
    with a baseline and cost entry, which would let processes downstream of this
    test's waivers resolve done on their own and mask what is being proven here."""
    proj = m.Project(name="Bare", portfolio=m.Portfolio(name="P", business=m.Business(name="B")))
    db.add(proj)
    db.commit()
    return proj


@pytest.mark.parametrize("process", _LIFECYCLE_ORDER, ids=lambda p: p.id)
def test_next_step_can_return_every_catalog_process(
    db: Session, bare: m.Project, process: Process
) -> None:
    for earlier in _LIFECYCLE_ORDER:
        if earlier.id == process.id:
            break
        _waive(db, bare, earlier)
    db.commit()
    step = engine.next_step(db, bare, AS_OF)
    assert step is not None
    assert step.process_id == process.id


def test_step_kind_follows_producibility_then_assessability() -> None:
    """The one rule ``WizardStep.kind`` follows, re-derived here rather than
    pinned to a count: a process with a producible output is a ``form`` step; one
    with none but a tracked required output is ``derived``; one with no tracked
    output at all is ``reference``."""
    for process in catalog.PROCESSES:
        kind = engine._step_kind(process)
        if engine._producible(process):
            assert kind == "form"
        elif st.is_assessable(process):
            assert kind == "derived"
        else:
            assert kind == "reference"
