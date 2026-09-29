"""Agile evidence counted as PMP-style control coverage — the derived crosswalk.

``driftless/pmbok/crosswalk.py`` never copies a native fact: it reads
``models/agile.py`` (and ``Sprint``'s review/retrospective fields) directly and
answers the same ``present``/``healthy``/``detail`` question a native
``mapping.py`` resolver would, only when the native resolver (or the absence
of one) finds nothing. These tests exercise the module directly, then prove
the one seam it feeds — ``mapping.resolve``'s fallback, and the process state
a Scrum project reaches through it with no predictive row in sight.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    BacklogItem,
    Business,
    DefinitionOfDoneItem,
    Impediment,
    Portfolio,
    Project,
    ProjectRole,
    Release,
    Sprint,
)
from driftless.models import agile as agile_models
from driftless.pmbok import crosswalk, mapping
from driftless.pmbok import state as st
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.catalog import get as get_process

AS_OF = date(2026, 6, 1)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="Aurora",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="agile",
    )
    session.add(project)
    session.commit()
    return project


def test_every_equivalence_key_is_an_artifact_kind() -> None:
    assert set(crosswalk.EQUIVALENCES) <= ARTIFACT_KINDS


def test_every_agile_model_is_named_or_dispositioned() -> None:
    """Set-equal: every mapped class ``models/agile.py`` defines is either read by
    some equivalence's resolver, or carries an explicit ``NO_EQUIVALENCE`` reason."""
    mapped = {
        value
        for value in vars(agile_models).values()
        if isinstance(value, type)
        and getattr(value, "__module__", "") == agile_models.__name__
        and hasattr(value, "__tablename__")
    }
    assert mapped == crosswalk.NAMED_MODELS | set(crosswalk.NO_EQUIVALENCE)


def test_the_crosswalk_never_writes() -> None:
    source = crosswalk.__file__
    assert source is not None
    text = open(source).read()
    for forbidden in (".add(", ".flush(", ".merge(", ".delete("):
        assert forbidden not in text, f"crosswalk.py calls session{forbidden} — it must only read"


def test_requirements_documentation_from_described_backlog_items(
    session: Session, project: Project
) -> None:
    status = crosswalk.resolve("requirements_documentation", project, session, AS_OF)
    assert status is not None and not status.present

    session.add(
        BacklogItem(project=project, title="Colour grade", description="What done looks like")
    )
    session.commit()
    status = crosswalk.resolve("requirements_documentation", project, session, AS_OF)
    assert status is not None
    assert status.present and status.healthy


def test_project_schedule_from_a_dated_release(session: Session, project: Project) -> None:
    session.add(Release(project=project, name="Q1", target_date=None))
    session.commit()
    status = crosswalk.resolve("project_schedule", project, session, AS_OF)
    assert status is not None and not status.present

    session.add(Release(project=project, name="Q2", target_date=AS_OF + timedelta(days=30)))
    session.commit()
    status = crosswalk.resolve("project_schedule", project, session, AS_OF)
    assert status is not None and status.present


def test_scope_baseline_needs_both_committed_backlog_and_definition_of_done(
    session: Session, project: Project
) -> None:
    session.add(BacklogItem(project=project, title="Ship it", status="ready"))
    session.commit()
    status = crosswalk.resolve("scope_baseline", project, session, AS_OF)
    assert status is not None and not status.present, "no definition of done yet"

    session.add(DefinitionOfDoneItem(project=project, description="Reviewed and merged"))
    session.commit()
    status = crosswalk.resolve("scope_baseline", project, session, AS_OF)
    assert status is not None and status.present


def test_issue_log_from_impediments_waits_for_raised_on(session: Session, project: Project) -> None:
    session.add(
        Impediment(project=project, description="No licenses", raised_by="Ada", raised_on=AS_OF)
    )
    session.commit()
    assert not crosswalk.resolve("issue_log", project, session, AS_OF - timedelta(days=1)).present  # type: ignore[union-attr]
    status = crosswalk.resolve("issue_log", project, session, AS_OF)
    assert status is not None and status.present and not status.healthy  # still open


def test_lessons_learned_register_needs_a_held_and_noted_retrospective(
    session: Session, project: Project
) -> None:
    session.add(
        Sprint(
            project=project,
            name="Sprint 1",
            start_date=AS_OF - timedelta(days=14),
            end_date=AS_OF,
        )
    )
    session.commit()
    status = crosswalk.resolve("lessons_learned_register", project, session, AS_OF)
    assert status is not None and not status.present

    sprint = session.query(Sprint).one()
    sprint.retrospective_held_on = AS_OF
    sprint.retrospective_notes = "Pairing cut rework in half."
    session.commit()
    status = crosswalk.resolve("lessons_learned_register", project, session, AS_OF)
    assert status is not None and status.present


def test_resource_management_plan_from_project_roles(session: Session, project: Project) -> None:
    status = crosswalk.resolve("resource_management_plan", project, session, AS_OF)
    assert status is not None and not status.present

    session.add(ProjectRole(project=project, role="scrum_master", holder="Grace Hopper"))
    session.commit()
    status = crosswalk.resolve("resource_management_plan", project, session, AS_OF)
    assert status is not None and status.present


def test_work_performance_reports_freshness_follows_the_latest_sprint_review(
    session: Session, project: Project
) -> None:
    session.add(
        Sprint(
            project=project,
            name="Sprint 1",
            start_date=AS_OF - timedelta(days=30),
            end_date=AS_OF - timedelta(days=16),
            review_held_on=AS_OF - timedelta(days=16),
            review_notes="Demoed the pipeline.",
        )
    )
    session.commit()
    status = crosswalk.resolve("work_performance_reports", project, session, AS_OF)
    assert status is not None and status.present and not status.healthy  # stale, past cadence


def test_a_kind_with_no_equivalence_reads_none() -> None:
    assert crosswalk.resolve("cost_baseline", None, None, AS_OF) is None  # type: ignore[arg-type]


def test_mapping_resolve_falls_back_to_the_crosswalk_only_when_native_finds_nothing(
    session: Session, project: Project
) -> None:
    session.add(
        Impediment(project=project, description="Blocked", raised_by="Ada", raised_on=AS_OF)
    )
    session.commit()
    status = mapping.resolve("issue_log", project, session, AS_OF)
    assert status.present
    assert "agile crosswalk" in status.detail


def test_mapping_resolve_prefers_the_native_answer_when_it_is_present(
    session: Session, project: Project
) -> None:
    from driftless.models import Issue

    session.add(Issue(project=project, description="A native issue", raised_on=AS_OF))
    session.add(
        Impediment(project=project, description="Never read", raised_by="Ada", raised_on=AS_OF)
    )
    session.commit()
    status = mapping.resolve("issue_log", project, session, AS_OF)
    assert status.present
    assert "agile crosswalk" not in status.detail


def test_a_scrum_project_reaches_produced_through_the_crosswalk_alone(
    session: Session, project: Project
) -> None:
    """The F-C-style proof the plan calls for: a process whose one tracked
    required output is ``issue_log`` reads PRODUCED off impediments alone,
    with no ``Issue`` row anywhere in the store."""
    process = get_process("4.3")
    assert [
        k for k in process.outputs if mapping.is_tracked(k) and k not in process.optional_outputs
    ] == ["issue_log"]
    session.add(
        Impediment(project=project, description="Blocked", raised_by="Ada", raised_on=AS_OF)
    )
    session.commit()
    assert st.process_state(process, project, session, AS_OF) is st.ProcessState.PRODUCED
