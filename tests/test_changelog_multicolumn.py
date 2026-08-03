"""A multi-column update logs every moved column — and only the moved ones.

The base contract tests (``tests/test_changelog.py``) move exactly one column per
update, so a regression that dropped columns from ``detail["changed"]`` — say, logging
only the first changed attribute — would pass the whole suite while silently thinning
the audit trail. These tests close that hole: one flush that moves three columns must
produce one update row whose ``changed`` map names all three with truthful old/new
values, and a rewrite-with-the-same-value mixed into the same flush must stay out.
"""

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import Business, Portfolio, Project


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory session whose factory has change logging activated."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as db:
        yield db


def _project(session: Session) -> Project:
    portfolio = Portfolio(name="Content Brands", business=Business(name="BRC"))
    project = Project(name="Site Refresh", portfolio=portfolio, status_note="drafting")
    session.add(project)
    session.commit()
    return project


def _last_update_detail(session: Session) -> dict[str, dict[str, object]]:
    row = session.scalars(select(ChangeLog).order_by(ChangeLog.id.desc())).first()
    assert row is not None and row.operation == "update"
    changed: dict[str, dict[str, object]] = json.loads(row.detail)["changed"]
    return changed


def test_an_update_moving_three_columns_logs_all_three_with_old_and_new(
    session: Session,
) -> None:
    project = _project(session)

    project.name = "Site Rebuild"
    project.delivery_mode = "agile"
    project.status_note = "kicked off"
    session.commit()

    assert _last_update_detail(session) == {
        "name": {"old": "Site Refresh", "new": "Site Rebuild"},
        "delivery_mode": {"old": "predictive", "new": "agile"},
        "status_note": {"old": "drafting", "new": "kicked off"},
    }


def test_a_same_value_rewrite_mixed_into_a_multi_column_update_is_not_logged(
    session: Session,
) -> None:
    project = _project(session)

    project.name = "Site Refresh"  # rewritten with the value it already holds
    project.delivery_mode = "hybrid"
    project.status_note = None
    session.commit()

    assert _last_update_detail(session) == {
        "delivery_mode": {"old": "predictive", "new": "hybrid"},
        "status_note": {"old": "drafting", "new": None},
    }
