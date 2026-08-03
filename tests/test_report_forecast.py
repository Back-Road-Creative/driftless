"""The Forecast Report equals calc: the EVM completion figures and the contingency
shortfall in the Markdown are the ones ``driftless.calc`` computes from the seeded
rows — formatted, never recomputed."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess.exposure import contingency_assessment
from driftless.calc import forecast as fc
from driftless.report import gather, render_document
from driftless.report.documents import forecast as forecast_doc

AS_OF = date(2026, 3, 31)
SPRINT_LENGTH_DAYS = 15  # 01-01..01-15 is fifteen days: both endpoints are worked


def _seed(db: Session, project: m.Project) -> None:
    db.add(m.BudgetLine(project=project, category="contingency", planned_amount=60.0))
    db.add(m.Risk(project=project, description="Vendor slip", probability=0.5, impact=200.0))
    db.add(
        m.Milestone(
            project=project,
            name="Beta",
            target_date=date(2026, 5, 1),
            baseline_date=date(2026, 4, 1),
            status="at_risk",
        )
    )
    # a second project's milestones must never bleed into GMS's forecast
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(m.Milestone(project=rival, name="Rival Gate", target_date=date(2026, 5, 1)))
    db.commit()


def _expected_contingency(db: Session, project: m.Project) -> fc.ContingencyAssessment:
    """The assessment the document must print — asked of the engine, not restated here."""
    costs = gather.project_costs(db).get(project.id, [])
    snap = gather.project_evm(project, costs, AS_OF)
    return contingency_assessment(db, project, snap, AS_OF)


def test_predictive_forecast_equals_calc(db: Session, project: m.Project) -> None:
    _seed(db, project)
    costs = gather.project_costs(db).get(project.id, [])
    snap = gather.project_evm(project, costs, AS_OF)
    doc = render_document("forecast", db, project, AS_OF)

    assert AS_OF.isoformat() in doc
    for figure in (snap.eac, snap.etc, snap.vac):
        assert figure is not None  # this fixture defines every EVM figure
        assert f"{figure:.2f}" in doc
    assert "Beta" in doc and "30" in doc  # milestone slip = 05-01 minus 04-01
    assert "Rival Gate" not in doc, "another project's milestones must not bleed in"
    assert f"{_expected_contingency(db, project).shortfall:.2f}" in doc


def test_forecast_regenerates_byte_identically(db: Session, project: m.Project) -> None:
    _seed(db, project)
    assert render_document("forecast", db, project, AS_OF) == render_document(
        "forecast", db, project, AS_OF
    )


def _agile_project(db: Session, mode: str) -> m.Project:
    """A ``mode`` project with three completed sprints and point-estimate tasks; no
    baseline or costs, so the agile branch stands on its own maths."""
    portfolio = m.Portfolio(name="Agile", business=m.Business(name="BRC-Agile"))
    proj = m.Project(name="AgileGMS", portfolio=portfolio, delivery_mode=mode)
    stream = m.Workstream(name="Epic", project=proj)
    db.add(m.Task(name="A", workstream=stream, estimate_unit="points", estimate=8.0, status="todo"))
    db.add(
        m.Task(
            name="B", workstream=stream, estimate_unit="points", estimate=5.0, status="in_progress"
        )
    )
    db.add(
        m.Task(name="C", workstream=stream, estimate_unit="points", estimate=99.0, status="done")
    )
    db.add(m.Task(name="D", workstream=stream, estimate_unit="hours", estimate=3.0, status="todo"))
    for i, (start, end, pts) in enumerate(
        (
            (date(2026, 1, 1), date(2026, 1, 15), 10),
            (date(2026, 1, 16), date(2026, 1, 30), 20),
            (date(2026, 1, 31), date(2026, 2, 14), 30),
        )
    ):
        db.add(
            m.Sprint(
                project=proj,
                name=f"S{i}",
                start_date=start,
                end_date=end,
                committed_points=pts,
                completed_points=pts,
            )
        )
    db.commit()
    return proj


def _expected_band(project: m.Project) -> fc.CompletionBand:
    """The band the document must equal — same history and remaining points, direct from
    calc. Every sprint ``_agile_project`` seeds is ``SPRINT_LENGTH_DAYS`` long, stated
    once as a constant rather than recomputed from the dates: restating the report's own
    date arithmetic here would make this helper agree with any change to it, which is how
    the off-by-one it once shared went unnoticed."""
    history = [
        fc.Sprint(
            s.name,
            ended_on=s.end_date,
            completed_points=s.completed_points,
            length_days=SPRINT_LENGTH_DAYS,
        )
        for s in project.sprints
        if s.end_date <= AS_OF and s.end_date > s.start_date
    ]
    remaining = sum(
        t.estimate
        for w in project.workstreams
        for t in w.tasks
        if t.estimate_unit == "points" and t.status != "done" and t.estimate is not None
    )
    return fc.forecast_completion(history, remaining, AS_OF)


def test_sprint_length_counts_both_its_endpoints(db: Session, project: m.Project) -> None:
    """A sprint running 01-01 to 01-14 is fourteen days long, not thirteen — the first
    and the last day are both worked, the same inclusive window ``calc.evm`` measures a
    baseline task over and the same fortnight ``calc.forecast.Sprint`` defaults to. One
    day short per sprint pulled every band date early."""
    db.add(
        m.Sprint(
            project=project,
            name="Fortnight",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
            completed_points=10,
        )
    )
    db.commit()

    (sprint,) = forecast_doc._sprint_history(project, AS_OF)
    assert sprint.length_days == 14


def test_agile_band_dates_are_the_dates_written_here(db: Session) -> None:
    """The band's three dates, spelled out rather than recomputed. Thirteen points
    remain (8 todo + 5 in progress) against velocities of 30 best / 20 likely / 10
    worst over 15-day sprints: one more sprint for best and likely, two for worst,
    counted from 2026-03-31. A literal is the only expectation an implementation
    change cannot quietly carry with it."""
    project = _agile_project(db, "agile")
    band = _expected_band(project)
    document = render_document("forecast", db, project, AS_OF)

    assert (band.best, band.likely, band.worst) == (
        date(2026, 4, 15),
        date(2026, 4, 15),
        date(2026, 4, 30),
    )
    assert "2026-04-15" in document and "2026-04-30" in document


def test_agile_velocity_band_equals_calc(db: Session) -> None:
    project = _agile_project(db, "agile")
    band = _expected_band(project)
    doc = render_document("forecast", db, project, AS_OF)

    assert "agile delivery" in doc
    assert "Completion forecast (EVM)" not in doc  # predictive section is agile's alternative
    for velocity in (band.velocity_best, band.velocity_likely, band.velocity_worst):
        assert f"{velocity:.2f}" in doc
    for finish in (band.best, band.likely, band.worst):
        assert finish is not None  # every seeded velocity is > 0
        assert finish.isoformat() in doc


def test_agile_forecast_regenerates_byte_identically(db: Session) -> None:
    project = _agile_project(db, "agile")
    assert render_document("forecast", db, project, AS_OF) == render_document(
        "forecast", db, project, AS_OF
    )


def test_forecast_skips_a_legacy_same_day_sprint_row(db: Session) -> None:
    """A same-day sprint is DB-legal (the CHECK allows ``>=``) but can only reach
    the store as a legacy row predating the API's create/patch refusal; the
    document must skip it — a single day carries no velocity information — rather
    than let it drag the window's average sprint length down to one day."""
    project = _agile_project(db, "agile")
    db.add(
        m.Sprint(
            project=project,
            name="Legacy",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            completed_points=999,
        )
    )
    db.commit()
    band = _expected_band(project)
    doc = render_document("forecast", db, project, AS_OF)

    assert "999.00" not in doc  # the legacy row never enters the velocity window
    for velocity in (band.velocity_best, band.velocity_likely, band.velocity_worst):
        assert f"{velocity:.2f}" in doc


def test_hybrid_shows_both_evm_and_velocity_band(db: Session) -> None:
    project = _agile_project(db, "hybrid")
    band = _expected_band(project)
    doc = render_document("forecast", db, project, AS_OF)

    assert "Completion forecast (EVM)" in doc  # the predictive section still renders
    assert f"{band.velocity_likely:.2f}" in doc  # and the velocity band alongside it
    assert band.likely is not None
    assert band.likely.isoformat() in doc
