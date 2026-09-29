"""Each knowledge-area evaluator, driven to the condition it is meant to catch.

One focused case per evaluator: seed exactly the signal §6 describes and assert
the RAG verdict, that a threat is raised with actions drawn from the PMBOK
techniques, and — where it matters — the healthy path stays green.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless.assess.evaluators import (
    communications,
    cost,
    procurement,
    quality,
    resource,
    risk,
    schedule,
    scope,
    stakeholder,
)
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    BudgetLine,
    Business,
    ChangeRequest,
    CostEntry,
    Milestone,
    Person,
    Portfolio,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    QualityMetric,
    Risk,
    Stakeholder,
    StatusSnapshot,
    Task,
    Workstream,
)
from driftless.pmbok import mapping

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


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


def _assert_threat(assessment: object, kind: str, severity: str) -> None:
    a = assessment
    assert a.status == severity, f"{kind}: expected {severity}, got {a.status}"  # type: ignore[attr-defined]
    assert a.threats and a.threats[0].kind == kind  # type: ignore[attr-defined]
    assert a.threats[0].severity == severity  # type: ignore[attr-defined]
    assert a.actions, f"{kind}: a non-green assessment recommends actions"  # type: ignore[attr-defined]


def test_schedule_red_on_a_missed_milestone(session: Session, project: Project) -> None:
    session.add(Milestone(project=project, name="Cut locked", target_date=AS_OF, status="missed"))
    session.commit()
    _assert_threat(schedule.evaluate(session, project, AS_OF), "schedule", "red")


def test_schedule_green_when_a_met_milestone_landed_late(
    session: Session, project: Project
) -> None:
    """An achieved milestone is delivery, not a live slip — even if it was late."""
    session.add(
        Milestone(
            project=project,
            name="Cut locked",
            target_date=AS_OF,
            baseline_date=date(2026, 1, 1),
            status="met",
        )
    )
    session.commit()
    assert schedule.evaluate(session, project, AS_OF).status == "green"


def test_schedule_names_the_slipped_milestone_in_the_threat(
    session: Session, project: Project
) -> None:
    """The threat must say WHICH milestone slipped, not merely how many."""
    session.add(Milestone(project=project, name="Cut locked", target_date=AS_OF, status="missed"))
    session.commit()
    assessment = schedule.evaluate(session, project, AS_OF)
    description = assessment.threats[0].description
    assert "Cut locked" in description
    assert "1 milestone slipped" in description and "(s)" not in description, (
        "a real singular, never the milestone(s) shorthand"
    )
    assert "n/a" not in description and "SPI no data yet" in description, (
        "an undefined SPI reads as words, not database jargon"
    )
    session.add(Milestone(project=project, name="Colour", target_date=AS_OF, status="missed"))
    session.commit()
    assert (
        "2 milestones slipped" in schedule.evaluate(session, project, AS_OF).threats[0].description
    )


def test_scope_amber_on_an_approved_change_not_rebaselined(
    session: Session, project: Project
) -> None:
    session.add(
        ChangeRequest(project=project, description="add a pass", raised_on=JAN, status="approved")
    )
    session.commit()
    _assert_threat(scope.evaluate(session, project, AS_OF), "scope", "amber")


def test_risk_red_when_exposure_outruns_contingency(session: Session, project: Project) -> None:
    """Red needs a reserve to outrun: a 20,000 plan holding 1,000 back against an
    exposure of 5,000. The bare fixture used to read red on its own, because a
    project with no plan has no budget and so no reserve — which the evaluator now
    answers "nothing to assess" to rather than calling every open risk uncovered."""
    task = Task(
        name="Grade",
        workstream=Workstream(name="Post", project=project),
        estimate_unit="hours",
        percent_complete=0,
    )
    session.add(
        BaselineLine(
            baseline=Baseline(project=project, version=1, status="approved"),
            task=task,
            planned_start=JAN,
            planned_finish=AS_OF,
            planned_cost=20_000.0,
        )
    )
    session.add(BudgetLine(project=project, category="contingency", planned_amount=1_000.0))
    session.add(Risk(project=project, description="drone loss", probability=0.5, impact=10_000.0))
    session.commit()
    _assert_threat(risk.evaluate(session, project, AS_OF), "risk", "red")


def test_stakeholder_amber_on_a_disengaged_power_player(session: Session, project: Project) -> None:
    session.add(Stakeholder(project=project, name="Exec", influence="high", interest="low"))
    session.commit()
    _assert_threat(stakeholder.evaluate(session, project, AS_OF), "stakeholder", "amber")


def test_communications_amber_when_no_report_exists(session: Session, project: Project) -> None:
    _assert_threat(communications.evaluate(session, project, AS_OF), "communications", "amber")
    # A fresh report clears it.
    session.add(StatusSnapshot(project=project, taken_on=AS_OF, rag_status="green"))
    session.commit()
    assert communications.evaluate(session, project, AS_OF).status == "green"


def test_resource_red_on_over_allocation(session: Session, project: Project) -> None:
    person = Person(name="Sam", capacity_hours=40.0)
    stream = Workstream(name="Post", project=project)
    session.add(
        Task(
            name="Grade",
            workstream=stream,
            estimate_unit="hours",
            estimate=60.0,
            status="in_progress",
            assignee=person,
        )
    )
    session.commit()
    _assert_threat(resource.evaluate(session, project, AS_OF), "resource", "red")


def test_resource_amber_on_tight_but_not_over_allocation(
    session: Session, project: Project
) -> None:
    """Between the amber and red ratios (0.8 < ratio <= 1.0): allocation is
    getting tight, but no one is actually over-committed yet — the ``who_text``
    branch ``test_resource_red_on_over_allocation`` never reaches."""
    person = Person(name="Sam", capacity_hours=40.0)
    stream = Workstream(name="Post", project=project)
    session.add(
        Task(
            name="Grade",
            workstream=stream,
            estimate_unit="hours",
            estimate=36.0,  # 36 / 40 = 0.9: over the 0.8 amber line, under the 1.0 red one
            status="in_progress",
            assignee=person,
        )
    )
    session.commit()
    assessment = resource.evaluate(session, project, AS_OF)
    _assert_threat(assessment, "resource", "amber")
    assert "allocation getting tight" in assessment.threats[0].description


def test_person_task_load_counts_one_persons_open_hour_tasks(
    session: Session, project: Project
) -> None:
    """The single-person read ``person_task_loads`` batches: same
    ``_OPEN_HOUR_TASK`` filter, one person's count and remaining hours."""
    person = Person(name="Sam", capacity_hours=40.0)
    stream = Workstream(name="Post", project=project)
    session.add(
        Task(
            name="Grade",
            workstream=stream,
            estimate_unit="hours",
            estimate=6.0,
            status="in_progress",
            assignee=person,
        )
    )
    session.add(
        Task(
            name="Deliver",
            workstream=stream,
            estimate_unit="hours",
            estimate=2.0,
            status="done",  # closed work does not count against open load
            assignee=person,
        )
    )
    session.commit()
    count, hours = resource.person_task_load(session, person.id)
    assert (count, hours) == (1, 6.0)


def test_quality_red_out_of_tolerance_amber_when_unmeasured(
    session: Session, project: Project
) -> None:
    assert quality.evaluate(session, project, AS_OF).status == "amber"  # unmeasured is a gap
    session.add(
        QualityMeasurement(
            project=project, metric="defects", target_value=1.0, actual_value=3.0, measured_on=AS_OF
        )
    )
    session.commit()
    _assert_threat(quality.evaluate(session, project, AS_OF), "quality", "red")


@pytest.mark.parametrize(
    ("direction", "lower", "upper", "actual"),
    [
        ("lower_is_better", None, 2.0, 3.0),
        ("higher_is_better", 99.9, None, 99.0),
        ("target_band", 18.0, 24.0, 25.0),
    ],
)
def test_quality_red_uses_a_linked_metric_direction(
    session: Session,
    project: Project,
    direction: str,
    lower: float | None,
    upper: float | None,
    actual: float,
) -> None:
    metric = QualityMetric(
        project=project,
        name="service_level",
        direction=direction,
        lower_bound=lower,
        upper_bound=upper,
    )
    session.add(metric)
    session.flush()
    session.add(
        QualityMeasurement(
            project=project,
            quality_metric=metric,
            metric="service_level",
            target_value=upper if upper is not None else lower,
            actual_value=actual,
            measured_on=AS_OF,
        )
    )
    session.commit()
    _assert_threat(quality.evaluate(session, project, AS_OF), "quality", "red")


def test_quality_amber_when_evidence_is_stale(session: Session, project: Project) -> None:
    session.add(
        QualityMeasurement(
            project=project,
            metric="defects",
            target_value=1.0,
            actual_value=0.5,
            measured_on=AS_OF - timedelta(days=90),
        )
    )
    session.commit()
    assert quality.evaluate(session, project, AS_OF).status == "amber"


def test_quality_stale_after_derives_from_the_recency_constant() -> None:
    """Not an independent copy of ``mapping.QUALITY_RECENCY_DAYS`` -- derived from
    it, so loosening the recency policy can't desync this evaluator's staleness
    read from the artifact mapping's."""
    assert quality._STALE_AFTER == timedelta(days=mapping.QUALITY_RECENCY_DAYS)


def test_quality_staleness_is_per_metric_not_global(session: Session, project: Project) -> None:
    """A fresh reading of one metric must not mask another metric gone stale."""
    session.add_all(
        [
            QualityMeasurement(
                project=project,
                metric="defects",
                target_value=1.0,
                actual_value=0.5,
                measured_on=AS_OF,
            ),
            QualityMeasurement(
                project=project,
                metric="coverage",
                target_value=1.0,
                actual_value=0.5,
                measured_on=AS_OF - timedelta(days=90),
            ),
        ]
    )
    session.commit()
    assessment = quality.evaluate(session, project, AS_OF)
    assert assessment.status == "amber"
    assert "coverage" in assessment.threats[0].description


def _seed_cost(session: Session, project: Project, *, percent_complete: int, spend: float) -> None:
    """One baselined task (BAC 1000, window JAN->AS_OF) plus one cost entry.

    EV = 1000 x percent_complete/100 and AC = spend, so CPI = EV/AC is dialled
    by the two knobs — the lever the cost evaluator's RAG bands turn on.
    """
    stream = Workstream(name="Post", project=project)
    task = Task(
        name="Grade",
        workstream=stream,
        estimate_unit="hours",
        percent_complete=percent_complete,
    )
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=spend))
    session.commit()


def test_cost_amber_when_cpi_slips_below_one_but_above_the_red_line(
    session: Session, project: Project
) -> None:
    """CPI 0.95 (0.9 <= CPI < 1.0) is a warning, not a breach — amber, not red.

    Regression guard: VAC is negative for every CPI < 1.0, so folding VAC < 0
    into the red predicate made the whole amber band unreachable — a CPI-0.95
    project read red, contradicting the module's documented bands.
    """
    _seed_cost(session, project, percent_complete=95, spend=1000.0)  # CPI = 950/1000 = 0.95
    _assert_threat(cost.evaluate(session, project, AS_OF), "cost", "amber")


def test_cost_red_when_cpi_breaches_the_red_line(session: Session, project: Project) -> None:
    _seed_cost(session, project, percent_complete=80, spend=1000.0)  # CPI = 800/1000 = 0.80
    _assert_threat(cost.evaluate(session, project, AS_OF), "cost", "red")


def test_cost_green_when_spending_under_budget(session: Session, project: Project) -> None:
    _seed_cost(session, project, percent_complete=100, spend=800.0)  # CPI = 1000/800 = 1.25
    assert cost.evaluate(session, project, AS_OF).status == "green"


def test_procurement_red_on_a_dispute(session: Session, project: Project) -> None:
    session.add(
        ProcurementAgreement(project=project, vendor="DronesRUs", status="disputed", start_date=JAN)
    )
    session.commit()
    _assert_threat(procurement.evaluate(session, project, AS_OF), "procurement", "red")


def test_procurement_amber_on_a_lapsed_active_agreement(session: Session, project: Project) -> None:
    session.add(
        ProcurementAgreement(
            project=project,
            vendor="OldCo",
            status="active",
            start_date=JAN,
            end_date=AS_OF - timedelta(days=1),
        )
    )
    session.commit()
    assert procurement.evaluate(session, project, AS_OF).status == "amber"


def test_procurement_red_on_contracted_spend_over_budget(
    session: Session, project: Project
) -> None:
    session.add(
        ProcurementAgreement(
            project=project, vendor="BigCo", status="active", amount=2_000.0, start_date=JAN
        )
    )
    session.add(BudgetLine(project=project, category="services", planned_amount=1_000.0))
    session.commit()
    result = procurement.evaluate(session, project, AS_OF)
    assert result.status == "red"
    assert "exceeds budget" in result.threats[0].description


def test_procurement_is_green_with_a_healthy_agreement_on_record(
    session: Session, project: Project
) -> None:
    """Agreements exist but none is disputed, lapsed or over budget — green, not
    the ``not_applicable`` coverage a project with no agreements at all reads."""
    session.add(
        ProcurementAgreement(project=project, vendor="GoodCo", status="closed", start_date=JAN)
    )
    session.commit()
    result = procurement.evaluate(session, project, AS_OF)
    assert result.status == "green"
    assert result.coverage == "measured"


def test_a_healthy_project_is_green_across_the_board(session: Session, project: Project) -> None:
    """No triggering signals -> every evaluator here reads green (or the documented amber)."""
    assert schedule.evaluate(session, project, AS_OF).status == "green"
    assert scope.evaluate(session, project, AS_OF).status == "green"
    assert risk.evaluate(session, project, AS_OF).status == "green"
    assert stakeholder.evaluate(session, project, AS_OF).status == "green"
    assert resource.evaluate(session, project, AS_OF).status == "green"
    assert procurement.evaluate(session, project, AS_OF).status == "green"


def test_schedule_baseline_line_helps_but_stays_green(session: Session, project: Project) -> None:
    """A clean baseline with progress keeping pace does not raise a schedule threat."""
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=100)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.commit()
    assert schedule.evaluate(session, project, AS_OF).status == "green"


def test_schedule_score_keeps_spi_and_slip_in_one_unit(session: Session, project: Project) -> None:
    """Near-total schedule collapse must outrank one slipped milestone (F-C5).

    The score used to add a raw milestone COUNT to the 1−SPI fraction, so SPI
    0.10 with no slips (0.9) ranked BELOW SPI 1.00 with a single slipped
    milestone (1.0) on the threat board. Slip is now the slipped SHARE of the
    milestone list — the same fractions-of-schedule-lost unit as 1 − SPI.
    """
    _seed_cost(session, project, percent_complete=10, spend=100.0)  # SPI = 100/1000 = 0.10
    collapse = schedule.evaluate(session, project, AS_OF)

    slipping = Project(name="Slip", portfolio=project.portfolio, delivery_mode="predictive")
    task = Task(
        name="Cut",
        workstream=Workstream(name="Post", project=slipping),
        estimate_unit="hours",
        percent_complete=100,
    )
    session.add(
        BaselineLine(
            baseline=Baseline(project=slipping, version=1, status="approved"),
            task=task,
            planned_start=JAN,
            planned_finish=AS_OF,
            planned_cost=1000.0,  # SPI = 1000/1000 = 1.00
        )
    )
    session.add(Milestone(project=slipping, name="M1", target_date=AS_OF, status="missed"))
    session.add_all(
        Milestone(project=slipping, name=f"M{i}", target_date=AS_OF, status="met")
        for i in (2, 3, 4)
    )
    session.commit()
    slipped = schedule.evaluate(session, slipping, AS_OF)

    assert collapse.status == "red" and slipped.status == "red"
    assert collapse.risk_score > slipped.risk_score, "SPI 0.10 outranks 1 slipped milestone of 4"
    assert slipped.threats[0].score > 0.0, "a red threat at 0.0 could be signed off forever"


def test_risk_covered_exactly_at_the_reserve_is_not_red(session: Session, project: Project) -> None:
    """Exposure exactly equal to the reserve is covered — amber, never red (F-C8).

    The engine used to pass held/remaining as a RATE and multiply back; the
    float round-trip (486128.75 → 486128.74999999994) flipped ``covered`` to
    False at the boundary, raising a red threat at score 0.0 — which one
    sign-off then suppressed forever, since no regression beats a 0.0 signal.
    The absolute reserve is carried through now.
    """
    task = Task(
        name="Grade",
        workstream=Workstream(name="Post", project=project),
        estimate_unit="hours",
        percent_complete=0,
    )
    session.add(
        BaselineLine(
            baseline=Baseline(project=project, version=1, status="approved"),
            task=task,
            planned_start=JAN,
            planned_finish=AS_OF,
            # remaining = BAC − AC = 690,000 — a divisor for which the old
            # (486128.75 / r) * r round-trip lands at 486128.74999999994.
            planned_cost=690_000.0,
        )
    )
    session.add(BudgetLine(project=project, category="contingency", planned_amount=486_128.75))
    # Exposure 0.5 × 972,257.50 = 486,128.75 exactly — the reserve to the cent.
    session.add(Risk(project=project, description="boundary", probability=0.5, impact=972_257.50))
    session.commit()
    assessment = risk.evaluate(session, project, AS_OF)
    assert assessment.status == "amber", "covered to the cent is not a breach"
    assert assessment.threats and assessment.threats[0].score > 0.0
