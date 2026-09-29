"""The wizard engine offers exactly the kinds ``produce`` can make.

``WizardStep.producible`` used to mean "every *tracked* output kind", while producing
goes through ``wizard.cli``'s producer registry — ``produce`` raises ``KeyError`` for
anything else, which the browser form answers with HTTP 422. The two sets no longer
coincide: the work-performance kinds are *derived* — computed from stored inputs, so
they have nothing of their own to write and can never have a producer. That day was
boring, which is what these tests are for: a button the wizard draws is a button
``produce`` can honour, and a derived kind simply never becomes a button.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import catalog, mapping
from driftless.pmbok.model import ProcessGroup
from driftless.wizard import cli as wizard_cli
from driftless.wizard import engine
from tests.conftest import AS_OF

ONBOARDING = (ProcessGroup.INITIATING, ProcessGroup.PLANNING)


@pytest.fixture
def bare(db: Session) -> m.Project:
    """A project with nothing in it — every process still to do."""
    proj = m.Project(name="Bare", portfolio=m.Portfolio(name="P", business=m.Business(name="B")))
    db.add(proj)
    db.commit()
    return proj


def _derived(project: m.Project, session: Session, as_of: date) -> mapping.ArtifactStatus:
    """A resolver with nothing to write: what a derived kind's resolver looks like."""
    return mapping.ArtifactStatus("project_charter", True, True, "derived from the store")


def test_every_kind_a_step_offers_is_one_produce_can_make(
    db: Session, bare: m.Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    offers = set(wizard_cli.producible_kinds())
    for process in catalog.PROCESSES:
        step = engine._step_for(process, bare, db, AS_OF)
        assert set(step.producible) <= offers, f"{process.id} offers what produce() refuses"

    # A tracked-but-unproducible kind — a derived resolver — must not become a button.
    monkeypatch.setitem(mapping.RESOLVERS, "project_charter", _derived)
    step = engine._step_for(catalog.get("4.1"), bare, db, AS_OF)
    assert "project_charter" not in step.producible
    assert set(step.producible) <= offers


def test_next_step_offers_a_process_with_nothing_producible_as_derived(
    db: Session, bare: m.Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process with nothing producible is no longer a dead end that gets skipped
    — it is the step itself, honestly labelled, so a reader learns it is derived
    (or, with nothing tracked either, reference) rather than never seeing it."""
    first = engine.next_step(db, bare, AS_OF, ONBOARDING)
    assert first is not None and first.producible and first.kind == "form"

    # Take away everything the first step could make: it is still the step
    # ``next_step`` returns, just relabelled — nothing to skip past.
    rest = tuple(k for k in wizard_cli.producible_kinds() if k not in first.outputs)
    monkeypatch.setattr(wizard_cli, "producible_kinds", lambda: rest)
    still = engine.next_step(db, bare, AS_OF, ONBOARDING)
    assert still is not None
    assert still.process_id == first.process_id
    assert not still.producible
    assert still.kind == "derived"


def test_every_producer_names_a_kind_the_store_can_resolve() -> None:
    """The durable direction: a producer for a kind the store cannot resolve would write
    rows no completeness figure counts. Its converse — every tracked kind having a
    producer — held only until the first derived resolver, and that line was deleted when
    the work-performance chain landed rather than propped up with a stub producer.
    """
    assert set(wizard_cli.producible_kinds()) <= set(mapping.RESOLVERS)
    derived = set(mapping.RESOLVERS) - set(wizard_cli.producible_kinds())
    assert derived == {
        "accepted_deliverables",
        "activity_attributes",
        "change_requests",
        "project_communications",
        "project_management_plan",
        "project_team_assignments",
        "risk_report",
        "schedule_data",
        "verified_deliverables",
        "work_performance_information",
        "work_performance_reports",
    }, (
        f"{sorted(derived)} resolve but nothing produces them — correct for a kind "
        "computed from stored inputs, an oversight for anything else"
    )
