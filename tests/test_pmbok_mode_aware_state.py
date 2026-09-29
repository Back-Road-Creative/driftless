"""A control's completeness reads the evidence its tailoring mode names.

Follow-up to the hybrid tailoring wave (``driftless/pmbok/tailoring.py``), which was
presentation-only: it labelled a Monitoring & Controlling control's mode and reason but
never touched what ``driftless.pmbok.state`` actually counted as evidence for it. This
module proves the two are wired together — a control's ``ControlMode`` decides whether
``mapping.resolve`` may fall back off its native rows at all (``state._allow_crosswalk``),
and which evidence the fallback reads (agile or operations) is
``driftless.pmbok.crosswalk``'s own ``project.delivery_mode`` branch, one seam, never a
second state rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    BacklogItem,
    Business,
    Department,
    Incident,
    Portfolio,
    Project,
    RecurringWork,
    ServiceLevel,
    Sprint,
)
from driftless.models import operations as operations_models
from driftless.pmbok import crosswalk, mapping
from driftless.pmbok import state as st
from driftless.pmbok.catalog import get as get_process

AS_OF = date(2026, 6, 1)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


def test_every_operations_model_is_named_or_dispositioned() -> None:
    """Set-equal, the same partition ``NAMED_MODELS``/``NO_EQUIVALENCE`` draws
    for ``models/agile.py``: every mapped class ``models/operations.py`` defines
    is either read by an operations equivalence, or carries an explicit reason
    it is not."""
    mapped = {
        value
        for value in vars(operations_models).values()
        if isinstance(value, type)
        and getattr(value, "__module__", "") == operations_models.__name__
        and hasattr(value, "__tablename__")
    }
    assert mapped == crosswalk.OPERATIONS_NAMED_MODELS | set(crosswalk.OPERATIONS_NO_EQUIVALENCE)


def test_scrum_project_reaches_produced_on_schedule_and_scope_controls_through_the_crosswalk(
    session: Session,
) -> None:
    """A Scrum project with sprint/backlog evidence and NO predictive artifacts reads
    its scope (5.5, 5.6) and schedule (6.6) controls PRODUCED under the adaptive
    profile its own ``delivery_mode`` selects. Flipping ``delivery_mode`` back to
    ``predictive`` over the SAME rows reads them NOT PRODUCED — the mode is what
    changes the reading, not the rows."""
    project = Project(
        name="Aurora",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="agile",
    )
    session.add(project)
    session.add(BacklogItem(project=project, title="Ship it", status="ready"))
    session.add(
        Sprint(
            project=project,
            name="Sprint 1",
            start_date=AS_OF - timedelta(days=10),
            end_date=AS_OF - timedelta(days=3),
            committed_points=8,
            completed_points=5,
            review_held_on=AS_OF - timedelta(days=3),
            review_notes="Demoed the pipeline.",
        )
    )
    session.commit()

    scope_and_schedule = [get_process(pid) for pid in ("5.5", "5.6", "6.6")]
    for process in scope_and_schedule:
        assert st.process_state(process, project, session, AS_OF) is st.ProcessState.PRODUCED, (
            process.id
        )

    project.delivery_mode = "predictive"
    session.commit()
    for process in scope_and_schedule:
        assert st.process_state(process, project, session, AS_OF) is not st.ProcessState.PRODUCED, (
            process.id
        )


def test_operations_project_reaches_produced_from_service_level_and_incident_rows(
    session: Session,
) -> None:
    """An operations-cadence project (department service work, no sprint and no
    baseline anywhere) reads its monitoring controls PRODUCED off the department's
    own service levels, incidents and recurring work."""
    business = Business(name="BRC")
    department = Department(name="Delivery", business=business)
    project = Project(
        name="Support Desk",
        portfolio=Portfolio(name="Operations", business=business),
        delivery_mode="operations",
        responsible_department=department,
    )
    session.add(project)
    session.add(ServiceLevel(department=department, measure="response time", target=4.0))
    session.add(
        Incident(
            department=department,
            description="Ticket queue backed up",
            raised_on=AS_OF - timedelta(days=1),
        )
    )
    session.add(
        RecurringWork(department=department, name="Weekly triage", cadence="weekly", owner="Ada")
    )
    session.commit()

    for process_id in ("5.5", "5.6", "6.6"):
        process = get_process(process_id)
        assert st.process_state(process, project, session, AS_OF) is st.ProcessState.PRODUCED, (
            process_id
        )


def test_a_predictive_baseline_control_never_reads_the_crosswalk_even_with_full_agile_evidence(
    session: Session,
) -> None:
    """The mode-aware fix itself: a hybrid project's Control Costs (7.4) stays on
    ``PREDICTIVE_BASELINE`` in every hybrid profile — it must read NOT_STARTED off
    no baseline, never PRODUCED off the SAME project's agile evidence, even though
    Control Schedule (6.6, ``ADAPTIVE_COMMITMENT`` in hybrid) reads PRODUCED off
    exactly that evidence. Before ``state._allow_crosswalk`` existed,
    ``mapping.resolve`` only gated the fallback on ``delivery_mode != predictive``,
    so 7.4 would have read PRODUCED here too — the bug this wave closes."""
    project = Project(
        name="Riverbend",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="hybrid",
    )
    session.add(project)
    session.add(
        Sprint(
            project=project,
            name="Sprint 1",
            start_date=AS_OF - timedelta(days=10),
            end_date=AS_OF - timedelta(days=3),
            committed_points=8,
            completed_points=5,
            review_held_on=AS_OF - timedelta(days=3),
            review_notes="Demoed the pipeline.",
        )
    )
    session.commit()

    control_costs = get_process("7.4")
    from driftless.pmbok import tailoring

    assert (
        tailoring.control_tailoring("7.4", "hybrid").mode
        is tailoring.ControlMode.PREDICTIVE_BASELINE
    )
    assert (
        tailoring.control_tailoring("6.6", "hybrid").mode
        is tailoring.ControlMode.ADAPTIVE_COMMITMENT
    )

    assert st.process_state(control_costs, project, session, AS_OF) is st.ProcessState.NOT_STARTED
    control_schedule = get_process("6.6")
    assert st.process_state(control_schedule, project, session, AS_OF) is st.ProcessState.PRODUCED

    # mapping.resolve's own seam, exercised directly: the SAME kind, on the SAME
    # project and rows, answers differently only by ``allow_crosswalk``.
    blocked = mapping.resolve(
        "work_performance_information", project, session, AS_OF, allow_crosswalk=False
    )
    allowed = mapping.resolve(
        "work_performance_information", project, session, AS_OF, allow_crosswalk=True
    )
    assert not blocked.present
    assert allowed.present
    assert "agile crosswalk" in allowed.detail
