"""A process sign-off must carry the as-of it was judged at (R2 residual of F-C3).

The ledger is bounded by ``SignOff.as_of`` — a decision recorded against a later
assessment date cannot rewrite an earlier page. That column is nullable, and
``state.current_sign_off`` treats a row with no recorded date as applying at every
as-of, so a process sign-off posted as raw JSON without ``as_of`` escaped the bound
entirely and silently rewrote history back to the store's first day. The browser
form always stamps the date, so only the JSON route could open the hole; it is now
shut at the write boundary, where no row can land without one.

Threat sign-offs keep the optional field on purpose: a threat decision suppresses
only while its stamped ``signal`` holds (``engine.is_suppressed``), and
``app.stamped_signal`` records ``None`` when there is no as-of to score at — so a
dateless threat sign-off never suppresses anything and needs no date to be safe.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Portfolio, Project
from driftless.pmbok import catalog
from driftless.pmbok import state as st

JAN, DECIDED, LATER = "2026-01-01", "2026-03-01", "2026-03-31"
IDENTIFY_RISKS = catalog.get("11.2")


@pytest.fixture
def factory(tmp_path: Path) -> Any:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    return new_session_factory(engine)


@pytest.fixture
def project(factory: Any) -> int:
    with factory() as db:
        row = Project(
            name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
        )
        db.add(row)
        db.commit()
        return int(row.id)


@pytest.fixture
def client(factory: Any) -> Iterator[TestClient]:
    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _body(project: int, **extra: Any) -> dict[str, Any]:
    return {
        "project_id": project,
        "subject_kind": "process",
        "subject_ref": f"process:{IDENTIFY_RISKS.id}:project:{project}",
        "decision": "accepted",
        "signed_by": "jp",
        **extra,
    }


def test_a_process_sign_off_without_an_as_of_is_refused(client: TestClient, project: int) -> None:
    """The escape hatch: this row applied at EVERY as-of, 2020 included."""
    refused = client.post("/sign-offs", json=_body(project))

    assert refused.status_code == 422, (
        f"a dateless process sign-off landed ({refused.status_code}) — nothing bounds it, "
        "so one JSON post rewrites every process map the store can render"
    )
    assert "as_of" in refused.text, f"the refusal must name the missing field: {refused.text}"


def test_a_process_sign_off_carrying_its_as_of_is_recorded(
    client: TestClient, project: int
) -> None:
    created = client.post("/sign-offs", json=_body(project, as_of=DECIDED))

    assert created.status_code == 201, created.text
    assert created.json()["as_of"] == DECIDED


def test_a_threat_sign_off_still_needs_no_as_of(client: TestClient, project: int) -> None:
    """Its suppression is gated by the stamped signal, which is ``None`` without a date."""
    created = client.post(
        "/sign-offs",
        json=_body(project, subject_kind="threat", subject_ref=f"cost:project:{project}"),
    )

    assert created.status_code == 201, created.text
    assert created.json()["signal"] is None, "a dateless threat sign-off suppresses nothing"


def test_every_process_sign_off_the_api_accepts_is_bounded_by_its_as_of(
    client: TestClient, factory: Any, project: int
) -> None:
    """The point of the field: what the write boundary lets through cannot rewrite
    an earlier as-of, and the only rows it lets through carry a date."""
    created = client.post("/sign-offs", json=_body(project, as_of=DECIDED))
    assert created.status_code == 201, created.text

    with factory() as db:
        proj = db.get(Project, project)
        assert proj is not None
        states = tuple(
            st.process_state(IDENTIFY_RISKS, proj, db, at)
            for at in (date.fromisoformat(JAN), date.fromisoformat(LATER))
        )

    assert states == (st.ProcessState.NOT_STARTED, st.ProcessState.SIGNED_OFF), (
        f"a March decision reads {states} across January and March — the recorded "
        "assessment date is what bounds it, so every row has to carry one"
    )
