"""The as-of contract, proved end to end: for a fixed as-of, a rendered document
must be byte-identical before and after a REAL, later-dated mutation lands
through the validated API. Four record kinds now guarantee this because they
gate on their own stored date rather than the wall clock -- a quality
measurement's ``measured_on``, a sign-off's ``as_of``, PMBOK baseline
selection's ``approved_at`` (``driftless.pmbok.mapping._approved_baseline``),
and the EVM adapter's own baseline selection (``driftless.assess.adapters.
plan_baseline``, fixed alongside its pin below) -- and nothing in the suite
proved any of it before this file. ``assert_history_survives`` is the reusable
harness, reused below by the scorecard metric definition's own effective date
(``driftless.assess.adapters.metric_definition_as_of``) -- the last known break.

Every pin's mutation is dated strictly AFTER the as-of it renders against, so
the property under test is effective time, not merely "nothing happened"."""

import itertools
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import catalog, state
from driftless.report import cli, render_document
from driftless.web.scorecard import scorecard_rows

AS_OF = date(2026, 3, 31)


def assert_history_survives(
    render: Callable[[], object], mutate: Callable[[], None], claim: str
) -> None:
    """Render, apply ``mutate()``, render again: require identical output.

    ``render`` closes over whatever one pin needs -- a session, a project, an
    as-of, a document slug, or a whole output tree under ``report all`` -- and
    returns anything comparable with ``==`` (a document's Markdown string, or a
    dict of relative path to bytes for a rendered tree). ``mutate`` performs
    ONE real, later-dated write through the product's own validated operation,
    never a hand-written row edit. ``claim`` names, in plain words, the
    invariant a mismatch would violate, so a failure explains itself instead of
    dumping a text diff nobody can read.
    """
    before = render()
    mutate()
    after = render()
    assert before == after, (
        f"{claim} -- rendering the same as-of before and after the mutation "
        "produced different output: a later write changed history"
    )


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """A ``TestClient`` wired to the SAME session the ``db``/``project`` fixtures
    use, so a pin's mutation lands through the real validated API rather than a
    second write path bypassing it."""
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def test_a_later_quality_measurement_does_not_change_an_earlier_as_of_process_map(
    db: Session, project: m.Project, client: TestClient
) -> None:
    """Process 8.2 Manage Quality reads ``quality_report`` through
    ``pmbok.mapping._quality_report``, which already gates on ``measured_on <=
    as_of``: a reading dated after the render must stay invisible to it."""

    def render() -> str:
        return render_document("process-map", db, project, AS_OF)

    def mutate() -> None:
        response = client.post(
            "/quality-measurements",
            json={
                "project_id": project.id,
                "metric": "defect rate",
                "target_value": 2.0,
                "actual_value": 9.0,
                "measured_on": (AS_OF + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text

    assert_history_survives(
        render,
        mutate,
        "a quality measurement dated after the as-of must not repaint 8.2 Manage "
        "Quality on an earlier process map",
    )


def test_a_later_sign_off_does_not_change_an_earlier_as_of_process_map(
    db: Session, project: m.Project, client: TestClient
) -> None:
    """``pmbok.state.current_sign_off`` gates a process decision on its own
    ``as_of``, never on ``signed_at``: a decision judged against a later date
    must stay invisible to an earlier process map."""
    process = catalog.get("4.3")
    subject_ref = state.process_subject_ref(process, project)

    def render() -> str:
        return render_document("process-map", db, project, AS_OF)

    def mutate() -> None:
        response = client.post(
            "/sign-offs",
            json={
                "project_id": project.id,
                "subject_kind": "process",
                "subject_ref": subject_ref,
                "decision": "waived",
                "as_of": (AS_OF + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text

    assert_history_survives(
        render,
        mutate,
        "a process sign-off judged against a later as-of must not repaint 4.3 "
        "Direct and Manage Project Work on an earlier process map",
    )


def test_a_later_approved_baseline_does_not_change_an_earlier_as_of_process_map(
    db: Session, project: m.Project, client: TestClient
) -> None:
    """``pmbok.mapping._approved_baseline`` -- the resolver 5.4 Create Scope
    Baseline and 6.6's baselined-schedule read through -- already gates on
    ``approved_at <= as_of``: a v2 approved after the render's as-of must not
    pre-empt v1 as the plan of record. This is deliberately NOT the
    ``scope-baseline`` document, which still selects the newest APPROVED
    baseline with no ``approved_at`` gate at all -- a known break left for a
    later PR. ``adapters.plan_baseline`` is pinned separately below, now that
    it gates on ``approved_at`` too."""

    def render() -> str:
        return render_document("process-map", db, project, AS_OF)

    def mutate() -> None:
        response = client.post(
            "/baselines",
            json={
                "project_id": project.id,
                "version": 2,
                "status": "approved",
                "approved_at": datetime(2026, 4, 15, 9, 0).isoformat(),
            },
        )
        assert response.status_code == 201, response.text

    assert_history_survives(
        render,
        mutate,
        "a baseline approved after the as-of must not pre-empt the earlier plan "
        "of record on the process map",
    )


def test_a_later_approved_baseline_does_not_change_an_earlier_as_of_cost_report(
    db: Session, project: m.Project, client: TestClient
) -> None:
    """``adapters.plan_baseline`` -- the resolver every earned-value figure flows
    through (``gather.project_evm`` -> ``adapters.snapshot_from``) -- now gates on
    ``approved_at <= as_of`` too: a v2 approved after the render's as-of must not
    pre-empt v1 as the Cost Report's plan of record."""

    def render() -> str:
        return render_document("cost-evm", db, project, AS_OF)

    def mutate() -> None:
        response = client.post(
            "/baselines",
            json={
                "project_id": project.id,
                "version": 2,
                "status": "approved",
                "approved_at": datetime(2026, 4, 15, 9, 0).isoformat(),
            },
        )
        assert response.status_code == 201, response.text

    assert_history_survives(
        render,
        mutate,
        "a baseline approved after the as-of must not pre-empt the earlier plan "
        "of record on the Cost Report",
    )


def test_a_later_metric_definition_version_does_not_change_an_earlier_as_of_scorecard(
    db: Session, project: m.Project
) -> None:
    """``metric_definition_as_of`` gates on ``effective_from <= as_of``: a threshold
    tightened after a render's as-of is not the definition of record for it."""
    objective = m.StrategicObjective(
        business=project.portfolio.business, perspective="financial", name="Sustain margin"
    )
    spec: dict[str, Any] = dict(
        objective=objective,
        name="Operating margin",
        direction="higher_is_better",
        unit="percent",
        cadence_days=30,
    )
    metric = m.ScorecardMetricDefinition(
        **spec, target_value=20, amber_threshold=15, red_threshold=10
    )
    db.add(m.ScorecardMetricObservation(metric_definition=metric, observed_on=AS_OF, value=21))
    db.commit()

    def render() -> tuple[dict[str, Any], ...]:
        return scorecard_rows(db, AS_OF)

    def mutate() -> None:
        db.add(
            m.ScorecardMetricDefinition(
                **spec,
                target_value=90,
                amber_threshold=80,
                red_threshold=70,
                effective_from=AS_OF + timedelta(days=1),
            )
        )
        db.commit()

    assert_history_survives(
        render, mutate, "a version effective after the as-of must not repaint an earlier render"
    )

    # Pins the design choice: grading reads the version effective at the REPORT's
    # as-of, not the observation's own date, and does not orphan its reading.
    later = scorecard_rows(db, AS_OF + timedelta(days=60))
    row = next(o for r in later for o in r["objectives"] if o["name"] == "Sustain margin")
    graded = next(e for e in row["metrics"] if e["name"] == "Operating margin")
    assert graded["evaluation"].status == "red", "the superseded row's reading was orphaned"


def _seed_single_project_db(tmp_path: Path) -> str:
    """A one-project store (BAC 1000, EV 500, AC 400) at its own SQLite file, so
    ``report all`` can run twice against it -- once before, once after a
    mutation posts through the API -- as two independent CLI invocations do."""
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
        proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
        stream = m.Workstream(name="GMS", project=proj)
        task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=50)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
        line.planned_start, line.planned_finish = date(2026, 1, 31), AS_OF
        session.add(line)
        session.add(
            m.CostEntry(
                project=proj, category="labour", incurred_on=date(2026, 1, 31), amount=400.0
            )
        )
        session.commit()
    return url


def test_report_all_at_an_early_as_of_survives_a_later_dated_quality_measurement(
    tmp_path: Path,
) -> None:
    """The whole-store contract: ``report all`` regenerates every document for
    every project. A quality measurement posted through the real API, dated
    after the as-of, must not change one byte of a tree rendered at it -- proved
    by rendering into a fresh output tree each time and comparing them."""
    url = _seed_single_project_db(tmp_path)
    trees = itertools.count()

    def render() -> dict[Path, bytes]:
        out = tmp_path / f"reports-{next(trees)}"
        rc = cli.main(
            ["report", "all", "--as-of", AS_OF.isoformat(), "--out", str(out), "--db-url", url]
        )
        assert rc == 0
        files = {p.relative_to(out): p.read_bytes() for p in sorted(out.rglob("*.md"))}
        assert files  # something was written
        return files

    def mutate() -> None:
        engine = new_engine(url)
        with new_session_factory(engine)() as session:
            real_app.dependency_overrides[get_session] = lambda: session
            try:
                with TestClient(real_app) as test_client:
                    project_id = (
                        session.scalars(select(m.Project).where(m.Project.name == "GMS")).one().id
                    )
                    response = test_client.post(
                        "/quality-measurements",
                        json={
                            "project_id": project_id,
                            "metric": "defect rate",
                            "target_value": 2.0,
                            "actual_value": 9.0,
                            "measured_on": (AS_OF + timedelta(days=1)).isoformat(),
                        },
                    )
                    assert response.status_code == 201, response.text
            finally:
                real_app.dependency_overrides.clear()

    assert_history_survives(
        render,
        mutate,
        "a store-wide `report all` at a fixed as-of must not change when a "
        "later-dated quality measurement lands through the API in between",
    )
