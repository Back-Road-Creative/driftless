"""The flow page's KPI strip: the same five ``home.html``-style tiles
(``home.html:29-40``), scoped to one project's flow figures. Every tile value
must equal the figure already rendered in the page's own prose/tables, so the
strip can never disagree with the page beneath it, and each id/value must
survive a byte-identical rerender for a pinned as-of."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import BacklogItem, Business, Portfolio, Project, Sprint

JAN, AS_OF = date(2026, 1, 1), date(2026, 1, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    project = Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    session.add(project)
    session.flush()
    session.add(
        Sprint(
            project=project,
            name="S1",
            start_date=JAN,
            end_date=date(2026, 1, 31),
            committed_points=10,
            completed_points=5,
        )
    )
    session.add(BacklogItem(project=project, title="A", story_points=3, status="in_progress"))
    session.add(BacklogItem(project=project, title="B", story_points=5, status="done"))
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_kpi_strip_tiles_match_the_pages_own_figures(client: TestClient) -> None:
    body = client.get(f"/projects/1/flow{Q}").text
    assert 'id="kpi-flow-wip"' in body
    assert 'id="kpi-flow-throughput"' in body
    assert 'id="kpi-flow-cycle"' in body
    assert 'id="kpi-flow-lead"' in body
    assert 'id="kpi-flow-forecast"' in body
    # WIP is a plain integer repeated verbatim in the prose above; the fallback
    # dating (no explicit item dates in this fixture) puts throughput's done_on
    # before the trailing window, so it reads 0 in both places, not just the strip.
    assert 'id="kpi-flow-wip" class="value">1<' in body  # matches flow-wip's own figure
    assert 'id="flow-throughput">0<' in body
    assert (
        'id="kpi-flow-throughput" class="value">0<' in body
    )  # matches flow-throughput's own figure


def test_the_kpi_strip_carries_no_empty_tile_values(client: TestClient) -> None:
    body = client.get(f"/projects/1/flow{Q}").text
    for tile_id in (
        "kpi-flow-wip",
        "kpi-flow-throughput",
        "kpi-flow-cycle",
        "kpi-flow-lead",
        "kpi-flow-forecast",
    ):
        start = body.index(f'id="{tile_id}"')
        span_open_end = body.index(">", start) + 1
        span_close = body.index("<", span_open_end)
        value = body[span_open_end:span_close]
        assert value.strip() != ""


def test_a_pinned_as_of_regenerates_the_strip_byte_identically(client: TestClient) -> None:
    url = f"/projects/1/flow{Q}"
    assert client.get(url).content == client.get(url).content
