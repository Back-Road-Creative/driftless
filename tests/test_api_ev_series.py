"""Per-period earned value over ``GET /projects/{id}/ev-series`` — a period series
shaped for IPMDAR-style cost reporting, never claimed compliant or certified. Each
period is a full :func:`driftless.calc.evm.earned_value_snapshot`, computed through
the same canonical loader every other EVM surface reads
(``driftless.assess.adapters.project_snapshot``), so this cannot disagree with the
assessment engine or the reports about what CPI was on a given date."""

from collections.abc import Iterator
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.api.secure import TokenGate
from driftless.assess import adapters
from tests.conftest import AS_OF

PERIODS_PATH = f"/projects/{{}}/ev-series?as_of={AS_OF.isoformat()}"


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """Wired to the SAME session ``project`` was seeded on -- the real API, no
    second write or read path."""
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def test_the_series_is_byte_identical_and_its_last_period_matches_the_snapshot(
    db: Session, project: m.Project, client: TestClient
) -> None:
    path = PERIODS_PATH.format(project.id)
    first = client.get(path)
    assert first.status_code == 200, first.text
    second = client.get(path)
    assert second.content == first.content, "same store, same as-of must render identically"

    rows = first.json()
    assert [row["period_end"] for row in rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert [list(row.keys()) for row in rows] == [sorted(row.keys()) for row in rows]

    expected = adapters.project_snapshot(db, project, AS_OF)
    last = rows[-1]
    assert (last["bac"], last["ev"], last["ac"], last["cpi"]) == (
        expected.bac,
        expected.ev,
        expected.ac,
        expected.cpi,
    )
    assert last["eac"] == expected.eac
    assert last["vac"] == expected.vac
    assert last["cv"] == expected.cv
    assert last["sv"] == expected.sv
    assert last["spi"] == expected.spi
    assert last["etc"] == expected.etc


def test_an_unknown_project_is_404(client: TestClient) -> None:
    assert client.get(PERIODS_PATH.format(999)).status_code == 404


def test_unauthenticated_is_refused_like_every_other_route(db: Session, project: m.Project) -> None:
    gate = TokenGate(real_app, "s3cr3t", session_scope=lambda: nullcontext(db))
    resp = TestClient(gate).get(PERIODS_PATH.format(project.id))
    assert resp.status_code == 401
