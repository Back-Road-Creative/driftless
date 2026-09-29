"""``driftless.interchange.viva_goals``: parse a Viva Goals OKR CSV export
into objectives and key results, and write them through the CLI onto the
project's business scorecard — idempotent, deterministic, and refusing a
layout it does not recognise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import cli
from driftless.db import Base, new_engine, new_session_factory
from driftless.interchange.viva_goals import (
    MissingColumn,
    import_viva_goals,
    parse_viva_goals_csv,
)
from driftless.models import Business, Portfolio, Project
from driftless.models.scorecard import (
    ScorecardMetricDefinition,
    ScorecardMetricObservation,
    StrategicObjective,
)

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "interchange" / "viva-goals-sample.csv"


def test_parse_viva_goals_csv_reads_objectives_and_key_results_sorted() -> None:
    scorecard = parse_viva_goals_csv(SAMPLE)

    assert [o.title for o in scorecard.objectives] == ["Grow customer retention"]
    assert [(k.objective_title, k.title) for k in scorecard.key_results] == [
        ("Grow customer retention", "Cut support ticket backlog"),
        ("Grow customer retention", "Raise 90-day retention rate"),
    ]
    retention = scorecard.key_results[1]
    assert retention.target == 90
    assert retention.current == 82


def test_parse_viva_goals_csv_refuses_missing_required_column(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("Title,Type,Owner,Aligned To,Target Value,Current Value\nX,Objective,,,,\n")
    with pytest.raises(MissingColumn, match="Due Date"):
        parse_viva_goals_csv(path)


def test_parse_viva_goals_csv_skips_blank_title_and_incomplete_key_result(
    tmp_path: Path,
) -> None:
    path = tmp_path / "edge.csv"
    path.write_text(
        "Title,Type,Owner,Aligned To,Target Value,Current Value,Due Date\n"
        ",Objective,,,,,\n"
        "Untargeted KR,Key Result,,Some Objective,,5,2026-12-31\n"
    )
    scorecard = parse_viva_goals_csv(path)
    assert scorecard.objectives == ()
    assert scorecard.key_results == ()


def _seed_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        session.add(
            Project(name="Retention", portfolio=Portfolio(name="P", business=Business(name="B")))
        )
        session.commit()
    return url


def test_import_viva_goals_cli_writes_objectives_metrics_and_observations(
    tmp_path: Path,
) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(["import", "viva-goals", str(SAMPLE), "--project", "Retention", "--db-url", url])
    assert rc == 0

    session: Session = new_session_factory(new_engine(url))()
    try:
        objectives = list(session.scalars(select(StrategicObjective)))
        assert [o.name for o in objectives] == ["Grow customer retention"]
        assert objectives[0].perspective == "internal_operations"

        metrics = list(session.scalars(select(ScorecardMetricDefinition)))
        assert {m.name for m in metrics} == {
            "Raise 90-day retention rate",
            "Cut support ticket backlog",
        }
        retention_metric = next(m for m in metrics if m.name == "Raise 90-day retention rate")
        assert retention_metric.target_value == 90

        observations = list(session.scalars(select(ScorecardMetricObservation)))
        assert len(observations) == 2
        assert {o.value for o in observations} == {82, 15}
    finally:
        session.close()


def test_import_viva_goals_is_idempotent_on_reimport(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    args = ["import", "viva-goals", str(SAMPLE), "--project", "Retention", "--db-url", url]
    assert cli.main(args) == 0
    assert cli.main(args) == 0

    session: Session = new_session_factory(new_engine(url))()
    try:
        assert session.scalar(select(StrategicObjective)) is not None
        assert len(list(session.scalars(select(StrategicObjective)))) == 1
        assert len(list(session.scalars(select(ScorecardMetricDefinition)))) == 2
        assert len(list(session.scalars(select(ScorecardMetricObservation)))) == 2
    finally:
        session.close()


def test_import_viva_goals_skips_key_result_with_no_current_value(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    path = tmp_path / "no-current.csv"
    path.write_text(
        "Title,Type,Owner,Aligned To,Target Value,Current Value,Due Date\n"
        "Grow retention,Objective,,,,,\n"
        "Not started yet,Key Result,,Grow retention,50,,2026-12-31\n"
    )
    scorecard = parse_viva_goals_csv(path)

    engine = new_engine(url)
    with new_session_factory(engine)() as session:
        project = session.scalar(select(Project))
        assert project is not None
        result = import_viva_goals(session, project, scorecard)
        session.commit()

    assert result.objectives_created == 1
    assert result.metrics_created == 1
    assert result.observations_created == 0

    with new_session_factory(engine)() as session:
        assert list(session.scalars(select(ScorecardMetricObservation))) == []


def test_import_viva_goals_dry_run_on_existing_data_reports_new_observation(
    tmp_path: Path,
) -> None:
    url = _seed_db(tmp_path)
    engine = new_engine(url)
    with new_session_factory(engine)() as session:
        project = session.scalar(select(Project))
        assert project is not None
        import_viva_goals(session, project, parse_viva_goals_csv(SAMPLE))
        session.commit()

    changed = tmp_path / "changed-current.csv"
    changed.write_text(
        "Title,Type,Owner,Aligned To,Target Value,Current Value,Due Date\n"
        "Grow customer retention,Objective,Sample Owner,,,,\n"
        "Raise 90-day retention rate,Key Result,Sample Owner,"
        "Grow customer retention,90,85,2026-12-31\n"
    )
    with new_session_factory(engine)() as session:
        project = session.scalar(select(Project))
        assert project is not None
        result = import_viva_goals(session, project, parse_viva_goals_csv(changed), dry_run=True)

    assert result.objectives_created == 0
    assert result.metrics_created == 0
    assert result.observations_created == 1
    with new_session_factory(engine)() as session:
        assert len(list(session.scalars(select(ScorecardMetricObservation)))) == 2


def test_import_viva_goals_skips_key_result_with_unknown_objective(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    path = tmp_path / "orphan.csv"
    path.write_text(
        "Title,Type,Owner,Aligned To,Target Value,Current Value,Due Date\n"
        "Orphan KR,Key Result,,No Such Objective,50,10,2026-12-31\n"
    )
    scorecard = parse_viva_goals_csv(path)

    engine = new_engine(url)
    with new_session_factory(engine)() as session:
        project = session.scalar(select(Project))
        assert project is not None
        result = import_viva_goals(session, project, scorecard)

    assert (result.objectives_created, result.metrics_created, result.observations_created) == (
        0,
        0,
        0,
    )


def test_import_viva_goals_dry_run_writes_nothing(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(
        [
            "import",
            "viva-goals",
            str(SAMPLE),
            "--project",
            "Retention",
            "--db-url",
            url,
            "--dry-run",
        ]
    )
    assert rc == 0

    engine = new_engine(url)
    session: Session = new_session_factory(engine)()
    try:
        assert list(session.scalars(select(StrategicObjective))) == []
        assert list(session.scalars(select(ScorecardMetricDefinition))) == []
        assert list(session.scalars(select(ScorecardMetricObservation))) == []
    finally:
        session.close()

    with new_session_factory(engine)() as session:
        project = session.scalar(select(Project))
        assert project is not None
        result = import_viva_goals(session, project, parse_viva_goals_csv(SAMPLE), dry_run=True)
    assert (result.objectives_created, result.metrics_created, result.observations_created) == (
        1,
        2,
        2,
    )
