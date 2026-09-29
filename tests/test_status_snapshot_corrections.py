"""``StatusSnapshot`` is append-only; a wrong reading used to be uncorrectable
because ``uq_status_snapshot_project_date`` 409'd a same-date refile outright
(see ``docs/temporal-model.md``, ``driftless.models.records.StatusSnapshot``).
Decision under test: the second filing is now ACCEPTED, and the most recently
RECORDED row -- higher ``id``, never ``taken_on`` order, which two same-date
rows now share -- is what every "latest reading" read returns.

Both write paths are covered here because they are separate code paths that
happened to share one constraint: dropping it has to free BOTH, and a test of
only the JSON route would leave the weekly form's acceptance unproven.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Project, StatusSnapshot
from driftless.web import csrf
from driftless.web.views import trend_series

BACKDATED = date(2026, 1, 10)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with made() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    # https, as production serves: the CSRF cookie is ``Secure``, so an http jar
    # would drop the pair's cookie half and no form could ever post back.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _project_via_api(client: TestClient) -> int:
    business = client.post("/businesses", json={"name": "Back Road Creative"}).json()["id"]
    portfolio = client.post(
        "/portfolios", json={"name": "Content Brands", "business_id": business}
    ).json()["id"]
    response = client.post(
        "/projects",
        json={"name": "GMS", "portfolio_id": portfolio, "delivery_mode": "predictive"},
    )
    return int(response.json()["id"])


def test_a_second_snapshot_for_an_already_snapshotted_date_is_accepted(
    client: TestClient,
) -> None:
    """This is the whole point: a same-date refile used to 409 and no longer does."""
    project_id = _project_via_api(client)
    body = {"project_id": project_id, "taken_on": BACKDATED.isoformat(), "rag_status": "green"}
    first = client.post("/status-snapshots", json=body)
    assert first.status_code == 201, first.text

    second = client.post("/status-snapshots", json={**body, "rag_status": "red"})
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


def test_the_web_form_accepts_a_same_date_refile_too(client: TestClient) -> None:
    """The other write path (``status_submit``) shares the same acceptance."""
    project_id = _project_via_api(client)
    at = BACKDATED.isoformat()

    def form() -> dict[str, str]:
        client.get(f"/projects/{project_id}/status?as_of={at}")
        return {"as_of": at, "rag_status": "green", csrf.FIELD: client.cookies[csrf.COOKIE]}

    first = client.post(f"/projects/{project_id}/status", data=form(), follow_redirects=False)
    assert first.status_code == 303, first.text

    second = client.post(f"/projects/{project_id}/status", data=form(), follow_redirects=False)
    assert second.status_code == 303, second.text


def _series(db: Session, project: Project) -> list[dict[str, object]]:
    """The series as a page renders it: rows in recording order, then plotted."""
    rows = db.scalars(
        select(StatusSnapshot)
        .where(StatusSnapshot.project_id == project.id)
        .order_by(StatusSnapshot.id)
    ).all()
    return trend_series(rows)


def test_recording_order_wins_not_taken_on_order(db: Session, project: Project) -> None:
    """Row A is recorded first, for 2026-01-10. Row B is recorded second but for the
    EARLIER 2026-01-05 -- an ordinary backfill, no date collision, which the tiebreak
    must not mistake for a correction. Row C is recorded THIRD, for 2026-01-10 again --
    the actual correction -- and must beat A for that date because it was recorded
    later, not because its ``taken_on`` compares any particular way to A's."""
    for taken_on, percent in ((date(2026, 1, 10), 50), (date(2026, 1, 5), 80), (BACKDATED, 99)):
        db.add(StatusSnapshot(project=project, taken_on=taken_on, percent_complete=percent))
        db.commit()

    series = _series(db, project)

    assert [point["taken_on"] for point in series] == ["2026-01-05", "2026-01-10"]
    assert [point["percent"] for point in series] == [80, 99], (
        "2026-01-10 must read C's 99 (recorded last), never A's 50 -- and 2026-01-05 "
        "is untouched, a plain backfill rather than a correction"
    )


def test_trend_series_is_deterministic_with_two_same_date_snapshots(
    db: Session, project: Project
) -> None:
    for percent in (10, 90):
        db.add(StatusSnapshot(project=project, taken_on=BACKDATED, percent_complete=percent))
        db.commit()

    assert (
        _series(db, project)
        == _series(db, project)
        == [{"taken_on": BACKDATED.isoformat(), "percent": 90, "rag": "green", "at": 0.0}]
    ), "one row per date on the chart, the most recently recorded one, every time"


def test_an_ordinary_single_snapshot_per_date_is_unchanged(db: Session, project: Project) -> None:
    """The dedupe must be inert when no date repeats -- the overwhelmingly common case."""
    for taken_on, percent in ((date(2026, 1, 5), 20), (date(2026, 1, 15), 60)):
        db.add(StatusSnapshot(project=project, taken_on=taken_on, percent_complete=percent))
    db.commit()

    series = _series(db, project)

    assert [point["taken_on"] for point in series] == ["2026-01-05", "2026-01-15"]
    assert [point["percent"] for point in series] == [20, 60]
    assert (series[0]["at"], series[1]["at"]) == (0.0, 1.0)
