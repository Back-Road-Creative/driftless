"""Shared report-test fixtures: a throwaway SQLite session and one seeded project
(BAC 1000, EV 500, AC 400 -> CPI 1.25) so every report test reads one figure set."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.db import Base, new_engine, new_session_factory

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="GMS", project=proj)
    task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=50)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=400.0))
    db.commit()
    return proj
