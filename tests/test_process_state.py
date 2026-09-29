"""The artifact mapping and the computed process-state engine.

Two things carry the design: the mapping answers presence/health from live rows
only for the kinds the store actually holds (and says "not tracked" for the
rest), and process state is a pure function of artifacts + the append-only
sign-off ledger — waived processes drop out of completeness, and a later ledger
entry overrides an earlier one, so nothing about a project's standing is stored
where it could drift.
"""

import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

import driftless
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    BudgetLine,
    Business,
    NarrativeArtifact,
    Portfolio,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    Risk,
    SignOff,
    Stakeholder,
    StatusSnapshot,
)
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

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


# ---- mapping -------------------------------------------------------------------


def test_untracked_kind_reports_not_tracked(session: Session, project: Project) -> None:
    status = mapping.resolve("business_case", project, session, AS_OF)
    assert status.present is False and status.detail == "not tracked"
    assert not mapping.is_tracked("business_case")


def test_cost_baseline_presence_follows_budget_lines(session: Session, project: Project) -> None:
    assert not mapping.resolve("cost_baseline", project, session, AS_OF).present
    session.add(BudgetLine(project=project, category="labour", planned_amount=1000.0))
    session.commit()
    status = mapping.resolve("cost_baseline", project, session, AS_OF)
    assert status.present and status.healthy


def test_status_report_freshness_is_relative_to_as_of(session: Session, project: Project) -> None:
    session.add(
        StatusSnapshot(project=project, taken_on=AS_OF - timedelta(days=3), rag_status="green")
    )
    session.commit()
    assert mapping.resolve("status_report", project, session, AS_OF).healthy
    # The same snapshot, judged much later, is present but stale.
    later = AS_OF + timedelta(days=60)
    stale = mapping.resolve("status_report", project, session, later)
    assert stale.present and not stale.healthy


def test_quality_report_health_tracks_tolerance(session: Session, project: Project) -> None:
    session.add(
        QualityMeasurement(
            project=project, metric="defects", target_value=1.0, actual_value=3.0, measured_on=AS_OF
        )
    )
    session.commit()
    assert not mapping.resolve("quality_report", project, session, AS_OF).healthy  # over tolerance
    session.add(
        QualityMeasurement(
            project=project, metric="defects", target_value=1.0, actual_value=0.5, measured_on=AS_OF
        )
    )
    session.commit()
    assert mapping.resolve(
        "quality_report", project, session, AS_OF
    ).healthy  # newest is in tolerance


def test_approved_baseline_agrees_with_the_shared_selector(
    session: Session, project: Project
) -> None:
    """``mapping._approved_baseline`` reads through ``_rows``'s batched query, never
    ``project.baselines`` — a different READ than :func:`adapters.plan_baseline` takes,
    kept separate on purpose (see its docstring). This pins the two down to the SAME
    RULE regardless: status filter, the null-``approved_at`` visibility policy, and the
    newest-version pick must agree for every draft/approved/undated/dated mix, at an
    as-of before and after the approval."""
    from driftless.assess.adapters import plan_baseline
    from driftless.models import Baseline

    draft = Baseline(project=project, version=2, status="draft")
    dated = Baseline(project=project, version=1, status="approved", approved_at=AS_OF)
    undated = Baseline(project=project, version=3, status="approved", approved_at=None)
    session.add_all([draft, dated, undated])
    session.commit()

    for as_of in (AS_OF - timedelta(days=1), AS_OF, AS_OF + timedelta(days=1)):
        got = mapping._approved_baseline(project, session, as_of)
        want = plan_baseline(project, as_of)
        assert (got is None) == (want is None)
        assert got is None or want is None or got.id == want.id


def test_scope_and_schedule_baselines_follow_an_approved_baseline(
    session: Session, project: Project
) -> None:
    from driftless.models import Baseline, BaselineLine, Deliverable, Task, Workstream

    assert not mapping.resolve("scope_baseline", project, session, AS_OF).present
    assert not mapping.resolve("schedule_baseline", project, session, AS_OF).present

    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours")
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline,
        task=task,
        planned_cost=1000.0,
        planned_start=date(2026, 1, 1),
        planned_finish=AS_OF,
    )
    session.add(line)
    # scope_baseline now needs a WBS alongside the approved baseline — module docstring.
    session.add(Deliverable(project=project, name="Grade", wbs_code="1"))
    session.commit()

    scope = mapping.resolve("scope_baseline", project, session, AS_OF)
    schedule = mapping.resolve("schedule_baseline", project, session, AS_OF)
    assert scope.present and scope.healthy and "v1" in scope.detail
    assert schedule.present and schedule.healthy


def test_scope_baseline_without_lines_is_present_but_unhealthy(
    session: Session, project: Project
) -> None:
    from driftless.models import Baseline

    session.add(Baseline(project=project, version=1, status="approved"))
    session.commit()
    status = mapping.resolve("scope_baseline", project, session, AS_OF)
    assert status.present and not status.healthy and "no lines" in status.detail


def test_status_report_absent_when_no_snapshot(session: Session, project: Project) -> None:
    status = mapping.resolve("status_report", project, session, AS_OF)
    assert not status.present and status.detail == "no status snapshot"


def test_work_performance_reports_answer_as_the_status_series_does(
    session: Session, project: Project
) -> None:
    """The catalog's name for the periodic report and the ``status_report`` record name
    are one behaviour, so the artifact a process owes can never disagree with the
    series the Communications evaluator reads."""
    assert mapping.is_tracked("work_performance_reports")
    session.add(StatusSnapshot(project=project, taken_on=AS_OF - timedelta(days=3)))
    session.commit()
    report = mapping.resolve("work_performance_reports", project, session, AS_OF)
    record = mapping.resolve("status_report", project, session, AS_OF)
    assert report.kind == "work_performance_reports" and report.present and report.healthy
    assert report.detail == record.detail and (record.present, record.healthy) == (True, True)


def test_project_communications_is_the_note_a_snapshot_carries(
    session: Session, project: Project
) -> None:
    """The work-performance reports' table, judged on the column they ignore: ``note`` is
    nullable, so a snapshot without one is a number filed, not a communication made. Health is
    the NOTED ones' cadence, and a note dated after as-of has not been sent yet."""
    kind = "project_communications"
    assert mapping.is_tracked(kind)
    session.add(StatusSnapshot(project=project, taken_on=AS_OF - timedelta(days=3)))
    session.commit()
    filed = mapping.resolve(kind, project, session, AS_OF)
    assert mapping.resolve("work_performance_reports", project, session, AS_OF).healthy
    assert not filed.present and filed.detail == "no noted status snapshot"
    session.add(
        StatusSnapshot(project=project, taken_on=AS_OF - timedelta(days=1), note="sponsor briefed")
    )
    session.commit()
    told = mapping.resolve(kind, project, session, AS_OF)
    assert told.present and told.healthy and told.detail == "1 of 2 snapshot(s) noted"

    earlier = mapping.resolve(kind, project, session, AS_OF - timedelta(days=2))
    assert not earlier.present, "a note dated after as-of has not been sent yet"
    quiet = mapping.resolve(kind, project, session, AS_OF + timedelta(days=60))
    assert quiet.present and not quiet.healthy and quiet.detail.endswith(" (stale)")


def test_work_performance_information_needs_a_plan_and_dated_actuals(
    session: Session, project: Project
) -> None:
    """Work performance data read in the context of the plan: neither half alone is
    information, and information nothing has refreshed inside the reporting cadence
    is present but stale — the same freshness rule the status series carries."""
    from driftless.models import Baseline, BaselineLine, CostEntry, Task, Workstream

    kind, spent = "work_performance_information", AS_OF - timedelta(days=3)
    assert mapping.is_tracked(kind)
    assert mapping.resolve(kind, project, session, AS_OF).detail == "no plan to measure against"

    stream = Workstream(name="Post", project=project)
    line = BaselineLine(
        baseline=Baseline(project=project, version=1, status="approved"),
        task=Task(name="Grade", workstream=stream, estimate_unit="hours"),
        planned_cost=1000.0,
    )
    line.planned_start, line.planned_finish = date(2026, 1, 1), AS_OF
    session.add(line)
    session.commit()
    planned = mapping.resolve(kind, project, session, AS_OF)
    assert not planned.present and planned.detail == "plan but no actuals"

    session.add(CostEntry(project=project, category="labour", incurred_on=spent, amount=800.0))
    session.commit()
    fresh = mapping.resolve(kind, project, session, AS_OF)
    assert fresh.present and fresh.healthy
    assert fresh.detail == f"plan + actuals to {spent.isoformat()}"
    # Judged much later: still a plan, still actuals, nothing measured inside the
    # cadence — so the information is present and stale, never healthy.
    stale = mapping.resolve(kind, project, session, AS_OF + timedelta(days=60))
    assert stale.present and not stale.healthy and stale.detail.endswith(" (stale)")


def test_activity_attributes_are_the_task_register_and_health_is_the_estimate(
    session: Session, project: Project
) -> None:
    """A task IS the scheduled activity, so presence is "there are tasks". Health is
    the estimate: an activity nobody sized cannot be sequenced or loaded against
    capacity, so a half-sized register reads present-and-unhealthy, never a tick."""
    from driftless.models import Task, Workstream

    kind = "activity_attributes"
    assert mapping.is_tracked(kind)
    assert mapping.resolve(kind, project, session, AS_OF).detail == "no activities"

    stream = Workstream(name="Post", project=project)
    session.add(Task(name="Grade", workstream=stream, estimate_unit="hours", estimate=8.0))
    session.commit()
    sized = mapping.resolve(kind, project, session, AS_OF)
    assert sized.present and sized.healthy and sized.detail == "1 activity(ies)"

    session.add(Task(name="Mix", workstream=stream, estimate_unit="hours"))
    session.commit()
    partial = mapping.resolve(kind, project, session, AS_OF)
    assert partial.present and not partial.healthy
    assert partial.detail == "2 activity(ies) (1 unestimated)"


def test_team_assignments_are_present_once_somebody_owns_work(
    session: Session, project: Project
) -> None:
    """``Task.assignee_id`` IS the assignment record. Present once one task names
    somebody; healthy only when nobody is unowned, because an unassigned task is work
    no person has accepted — so the detail names the shortfall."""
    from driftless.models import Department, Person, Task, Workstream

    kind = "project_team_assignments"
    assert mapping.is_tracked(kind)
    stream = Workstream(name="Post", project=project)
    owned = Task(name="Mix", workstream=stream, estimate_unit="hours", estimate=4.0)
    session.add_all([owned, Task(name="Grade", workstream=stream, estimate=8.0)])
    session.commit()
    assert mapping.resolve(kind, project, session, AS_OF).detail == "nobody assigned"

    unit = Department(name="Post", business=project.portfolio.business)
    editor = Person(name="Ada", department=unit, capacity_hours=40.0)
    owned.assignee = editor
    session.commit()
    partial = mapping.resolve(kind, project, session, AS_OF)
    assert partial.present and not partial.healthy
    assert partial.detail == "1 of 2 task(s) assigned"

    for task in stream.tasks:
        task.assignee = editor
    session.commit()
    assert mapping.resolve(kind, project, session, AS_OF).healthy


def test_the_task_reads_batch_through_the_one_prefetch_scope(
    session: Session, project: Project
) -> None:
    """``Task`` hangs off ``Workstream``, so it cannot go through ``_rows`` — but it
    goes through the SAME cache, which is what makes it fail closed: a project the
    scope never covered raises rather than reading as one with no work at all."""
    from driftless.models import Task, Workstream

    outsider = Project(name="Fleet", portfolio=project.portfolio)
    session.add(Task(name="Grade", workstream=Workstream(name="Post", project=project)))
    session.add(outsider)
    session.commit()
    with mapping.prefetched(session, [project]):
        assert mapping.resolve("activity_attributes", project, session, AS_OF).present
        with pytest.raises(LookupError, match="outside the open prefetched scope"):
            mapping.resolve("project_team_assignments", outsider, session, AS_OF)


def test_agreements_health_flags_a_dispute(session: Session, project: Project) -> None:
    session.add(
        ProcurementAgreement(project=project, vendor="V", status="disputed", start_date=AS_OF)
    )
    session.commit()
    status = mapping.resolve("agreements", project, session, AS_OF)
    assert status.present and not status.healthy


def test_narrative_presence_needs_a_non_empty_body(session: Session, project: Project) -> None:
    session.add(NarrativeArtifact(project=project, kind="assumption_log", body="   "))
    session.commit()
    assert not mapping.resolve("assumption_log", project, session, AS_OF).present
    session.add(NarrativeArtifact(project=project, kind="eef", body="cloud-first"))
    session.commit()
    assert mapping.resolve("enterprise_environmental_factors", project, session, AS_OF).present


def test_the_plan_of_plans_is_all_ten_subsidiary_plans_or_it_is_not_one(
    session: Session, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A composite with no body of its own: storing one would restate the plans it binds, so it
    rolls up ``SUBSIDIARY_PLANS`` through the very resolvers those ten plans use. Present is ALL
    ten, never any: 4.2's only required output is this, so "any" reads PRODUCED off one plan."""
    kind = "project_management_plan"
    assert mapping.is_tracked(kind) and len(mapping.SUBSIDIARY_PLANS) == 10
    assert mapping.resolve(kind, project, session, AS_OF).detail == "0 of 10 subsidiary plans"
    for name in mapping.SUBSIDIARY_PLANS[:-1]:
        session.add(NarrativeArtifact(project=project, kind=name, body=f"{name} prose"))
    session.commit()
    short = mapping.resolve(kind, project, session, AS_OF)
    assert not short.present and short.detail == "9 of 10 subsidiary plans"
    last = mapping.SUBSIDIARY_PLANS[-1]
    session.add(NarrativeArtifact(project=project, kind=last, body="engagement prose"))
    session.commit()
    whole = mapping.resolve(kind, project, session, AS_OF)
    assert whole.present and whole.healthy and whole.detail == "10 of 10 subsidiary plans"
    # Read through RESOLVERS, so a subsidiary plan's own answer is the composite's too.
    monkeypatch.setitem(mapping.RESOLVERS, last, _fixed(False))
    assert mapping.resolve(kind, project, session, AS_OF).detail == "9 of 10 subsidiary plans"


# ---- process state -------------------------------------------------------------

IDENTIFY_RISKS = catalog.get("11.2")  # outputs: risk_register, risk_report, assumption_log
IDENTIFY_STAKEHOLDERS = catalog.get("13.1")  # outputs: stakeholder_register, change_requests


def test_a_bare_project_has_not_started_its_tracked_processes(
    session: Session, project: Project
) -> None:
    assert st.process_state(IDENTIFY_RISKS, project, session, AS_OF) is st.ProcessState.NOT_STARTED


def test_partial_then_full_outputs_move_a_process_through_its_states(
    session: Session, project: Project
) -> None:
    session.add(Risk(project=project, description="r", probability=0.3, impact=1000.0))
    session.commit()
    # risk_register present, assumption_log absent -> in progress.
    assert st.process_state(IDENTIFY_RISKS, project, session, AS_OF) is st.ProcessState.IN_PROGRESS

    session.add(NarrativeArtifact(project=project, kind="assumption_log", body="drone weather"))
    session.commit()
    assert st.process_state(IDENTIFY_RISKS, project, session, AS_OF) is st.ProcessState.PRODUCED


def test_waiving_a_process_and_signing_one_off(session: Session, project: Project) -> None:
    ref = st.process_subject_ref(IDENTIFY_STAKEHOLDERS, project)
    session.add(
        SignOff(project=project, subject_kind="process", subject_ref=ref, decision="waived")
    )
    session.commit()
    assert (
        st.process_state(IDENTIFY_STAKEHOLDERS, project, session, AS_OF) is st.ProcessState.WAIVED
    )

    ref2 = st.process_subject_ref(IDENTIFY_RISKS, project)
    session.add(
        SignOff(project=project, subject_kind="process", subject_ref=ref2, decision="accepted")
    )
    session.commit()
    assert st.process_state(IDENTIFY_RISKS, project, session, AS_OF) is st.ProcessState.SIGNED_OFF


def test_the_latest_ledger_entry_wins(session: Session, project: Project) -> None:
    ref = st.process_subject_ref(IDENTIFY_STAKEHOLDERS, project)
    early = SignOff(
        project=project,
        subject_kind="process",
        subject_ref=ref,
        decision="waived",
        signed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    late = SignOff(
        project=project,
        subject_kind="process",
        subject_ref=ref,
        decision="rejected",
        signed_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    session.add_all([early, late])
    session.commit()
    # 'rejected' is not a done/waived decision, so state falls back to artifacts:
    # no stakeholder register yet -> NOT_STARTED, i.e. the waiver was overridden.
    assert (
        st.process_state(IDENTIFY_STAKEHOLDERS, project, session, AS_OF)
        is st.ProcessState.NOT_STARTED
    )


def test_completeness_excludes_waived_and_untracked(session: Session, project: Project) -> None:
    empty = st.completeness(project, session, AS_OF)
    assert empty == 0.0  # assessable processes exist, none produced yet

    # Produce one process's tracked outputs, waive another.
    session.add(Stakeholder(project=project, name="Sponsor"))
    session.add(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(IDENTIFY_RISKS, project),
            decision="waived",
        )
    )
    session.commit()
    after = st.completeness(project, session, AS_OF)
    assert after is not None and after > 0.0


def test_process_states_cover_the_whole_catalog(session: Session, project: Project) -> None:
    states = st.project_process_states(project, session, AS_OF)
    assert len(states) == len(catalog.PROCESSES) == 49
    assert all(isinstance(state, st.ProcessState) for _, state in states)


def test_the_state_map_regenerates_identically(session: Session, project: Project) -> None:
    """Computed, never stored, and clock-free: the same store gives the same map."""
    session.add(Risk(project=project, description="r", probability=0.2, impact=500.0))
    session.commit()
    first = [(p.id, s.value) for p, s in st.project_process_states(project, session, AS_OF)]
    second = [(p.id, s.value) for p, s in st.project_process_states(project, session, AS_OF)]
    assert first == second


# ---- optional (conditional) outputs ---------------------------------------------

FAKE_REQUIRED = "fake_required_output"
FAKE_OPTIONAL = "fake_optional_output"


def _synthetic(outputs: tuple[str, ...], optional: tuple[str, ...] = ()) -> Process:
    """A catalog-shaped process outside the real numbering, for state tests."""
    return Process(
        id="99.1",
        name="Synthetic",
        group=ProcessGroup.EXECUTING,
        area=KnowledgeArea.INTEGRATION,
        inputs=(),
        tools_techniques=(),
        outputs=outputs,
        optional_outputs=optional,
    )


def _fixed(present: bool) -> mapping.Resolver:
    def resolver(project: Project, session: Session, as_of: date) -> mapping.ArtifactStatus:
        return mapping.ArtifactStatus("fake", present, present, "synthetic")

    return resolver


def test_a_present_optional_output_does_not_demote_a_produced_process(
    session: Session, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_REQUIRED, _fixed(True))
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_OPTIONAL, _fixed(True))
    process = _synthetic((FAKE_REQUIRED, FAKE_OPTIONAL), optional=(FAKE_OPTIONAL,))
    assert st.process_state(process, project, session, AS_OF) is st.ProcessState.PRODUCED


def test_an_absent_optional_output_does_not_block_produced(
    session: Session, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unit's point: a conditional output a process never raised is not missing
    work, so gaining a resolver for it must not drag emitters out of PRODUCED."""
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_REQUIRED, _fixed(True))
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_OPTIONAL, _fixed(False))
    process = _synthetic((FAKE_REQUIRED, FAKE_OPTIONAL), optional=(FAKE_OPTIONAL,))
    assert st.process_state(process, project, session, AS_OF) is st.ProcessState.PRODUCED


def test_an_only_optional_tracked_output_is_not_assessable_and_stays_not_started(
    session: Session, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that could never honestly reach PRODUCED must not enter
    completeness denominators, even when its optional output is present."""
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_OPTIONAL, _fixed(True))
    process = _synthetic((FAKE_OPTIONAL,), optional=(FAKE_OPTIONAL,))
    assert not st.is_assessable(process)
    assert st.process_state(process, project, session, AS_OF) is st.ProcessState.NOT_STARTED


def test_a_present_optional_output_lifts_an_otherwise_empty_process_to_in_progress(
    session: Session, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence of activity, but never a promotion to PRODUCED."""
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_REQUIRED, _fixed(False))
    monkeypatch.setitem(mapping.RESOLVERS, FAKE_OPTIONAL, _fixed(True))
    process = _synthetic((FAKE_REQUIRED, FAKE_OPTIONAL), optional=(FAKE_OPTIONAL,))
    assert st.process_state(process, project, session, AS_OF) is st.ProcessState.IN_PROGRESS


# ---- prefetch scopes -----------------------------------------------------------


def test_nesting_the_prefetch_scope_leaves_the_outer_block_whole(
    session: Session, project: Project
) -> None:
    """A nested scope must be a no-op for the block around it — both halves.

    The regression this pins had a loud half and a quiet one. Loud: the inner exit
    removed the key outright, so the OUTER block's exit raised ``KeyError`` — a 500
    handed to whoever hoists one scope over two batched calls. Quiet, and worse: the
    outer block had already lost its cache at the inner exit, so every later
    ``latest_sign_off`` silently went back to a per-subject query. Stopping the raise
    alone would leave that, and no row count or return value would ever show it — so
    the second assertion below is the one that matters.
    """
    signed = st.process_subject_ref(IDENTIFY_RISKS, project)
    session.add(
        SignOff(project=project, subject_kind="process", subject_ref=signed, decision="accepted")
    )
    session.commit()
    unsigned = st.process_subject_ref(IDENTIFY_STAKEHOLDERS, project)

    with st.prefetched(session, [project]):
        assert st.latest_sign_off(session, "process", unsigned) is None

        with st.prefetched(session, [project]):
            pass  # the inner exit must not disturb the block it is sitting inside

        # A row written after the scope opened is deliberately invisible to that
        # scope, so answering None for it here proves the OUTER cache is still the
        # one serving reads — a scope that had fallen back to per-subject queries
        # would see the new row and answer with it.
        session.add(
            SignOff(
                project=project, subject_kind="process", subject_ref=unsigned, decision="waived"
            )
        )
        session.commit()
        assert st.latest_sign_off(session, "process", unsigned) is None
        assert st.latest_sign_off(session, "process", signed) is not None
    # Leaving the outer block without raising is the other half of the assertion.


def _session_scopes() -> list[tuple[str, Any]]:
    """Every context manager in the package that scopes something onto a Session.

    Found by walking the package — any ``@contextmanager`` whose first parameter is
    the session — rather than by listing the scopes that exist today, so the one
    written next is covered on the day it is written rather than when someone
    remembers to add it here.
    """
    scopes: list[tuple[str, Any]] = []
    for info in pkgutil.walk_packages(driftless.__path__, f"{driftless.__name__}."):
        module = importlib.import_module(info.name)
        for name, obj in vars(module).items():
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            inner = getattr(obj, "__wrapped__", None)  # @contextmanager keeps the generator here
            if inner is None or not inspect.isgeneratorfunction(inner):
                continue
            first = next(iter(inspect.signature(obj).parameters.values()), None)
            if first is not None and first.annotation in (Session, "Session"):
                scopes.append((f"{module.__name__}.{name}", obj))
    return scopes


def _open(scope: Any, session: Session, project: Project) -> AbstractContextManager[None]:
    """Enter a discovered scope, binding its arguments off their annotations.

    An argument shape this cannot bind fails rather than skips: a scope the gate
    below cannot open is a scope the gate below is not covering, and that should be
    visible the moment it is added.
    """
    kwargs: dict[str, Any] = {}
    for name, param in inspect.signature(scope).parameters.items():
        if param.annotation in (Session, "Session"):
            kwargs[name] = session
        elif "Project" in str(param.annotation):
            kwargs[name] = [project]
        else:
            raise AssertionError(f"cannot bind {name}: {param.annotation} — teach _open about it")
    result: AbstractContextManager[None] = scope(**kwargs)
    return result


def test_every_session_scope_survives_being_nested(session: Session, project: Project) -> None:
    """No scope in the package may raise when one of its own kind nests inside it.

    Batching here grows by hoisting a scope over calls that already open their own —
    exactly what turns a leaf scope into an outer one — so nest-safety is a property
    of the whole class, not of the three that happen to exist. Each is opened twice
    and both exits must be clean.

    Cleanness is the floor, not the ceiling: ``pmbok.mapping`` and ``pmbok.state``
    restore the outer cache, while ``assess.adapters`` deliberately pops it and
    degrades to per-project queries (its docstring says so). The scopes do not all
    make the same promise, so this gate asserts only the one they share; whether an
    outer cache SURVIVES is asserted per scope — ``state``'s in the test above.
    """
    scopes = _session_scopes()
    names = [name for name, _ in scopes]
    assert "driftless.pmbok.state.prefetched" in names, f"walk found only {names}"
    for name, scope in scopes:
        try:
            with _open(scope, session, project), _open(scope, session, project):
                pass
        except KeyError as exc:  # the shape a non-re-entrant teardown fails in
            pytest.fail(f"{name} is not nest-safe: KeyError {exc}")
