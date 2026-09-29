"""Contract tests for response planning: ``Risk.kind`` and ``RiskResponse``.

The generic create/read/update/delete machinery (``api.crud``) is already proved by
``tests/test_api_records.py``; these tests exercise this family's own registration
(project scoping, the delete guard, the vocabulary CHECKs) and its bespoke cross-row
rule — a response's ``strategy`` must belong to its risk's ``kind`` family.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _project(client: TestClient, name: str = "Aurora") -> int:
    business = _create(client, "/businesses", name=f"BRC {name}")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(client, "/projects", name=name, portfolio_id=portfolio)


def _risk(client: TestClient, project: int, kind: str = "threat", **extra: Any) -> int:
    return _create(
        client,
        "/risks",
        project_id=project,
        description=f"a {kind}",
        probability=0.5,
        impact=1000.0,
        kind=kind,
        **extra,
    )


def _owner(client: TestClient, name: str = "Priya") -> int:
    return _create(client, "/people", name=name)


_RESPONSE_FIELDS = {
    "trigger": "Vendor outage exceeds one day",
    "planned_action": "Fail over to the secondary vendor",
    "residual_probability": 0.1,
    "residual_impact": 200.0,
    "cost_of_response": 500.0,
    "schedule_days": 3,
    "status": "planned",
    "actor": "pm",
    "as_of": "2026-02-20",
}


def test_a_risk_response_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    risk = _risk(client, project, kind="threat")
    owner = _owner(client)

    response = _create(
        client,
        "/risk-responses",
        project_id=project,
        risk_id=risk,
        owner_id=owner,
        strategy="mitigate",
        **_RESPONSE_FIELDS,
    )

    read = client.get(f"/risk-responses/{response}").json()
    assert read["strategy"] == "mitigate" and read["owner_id"] == owner
    assert read["residual_probability"] == pytest.approx(0.1)


def test_an_unknown_strategy_is_refused_by_the_vocabulary(client: TestClient) -> None:
    project = _project(client)
    risk = _risk(client, project, kind="threat")
    owner = _owner(client)

    refused = client.post(
        "/risk-responses",
        json={
            "project_id": project,
            "risk_id": risk,
            "owner_id": owner,
            "strategy": "bogus",
            **_RESPONSE_FIELDS,
        },
    )
    assert refused.status_code == 422, refused.text


def test_an_opportunity_strategy_is_refused_against_a_threat(client: TestClient) -> None:
    project = _project(client)
    risk = _risk(client, project, kind="threat")
    owner = _owner(client)

    refused = client.post(
        "/risk-responses",
        json={
            "project_id": project,
            "risk_id": risk,
            "owner_id": owner,
            "strategy": "exploit",  # an opportunity-only strategy
            **_RESPONSE_FIELDS,
        },
    )
    assert refused.status_code == 422, refused.text
    assert "does not apply to a threat risk" in refused.json()["detail"]


def test_a_threat_strategy_is_refused_against_an_opportunity(client: TestClient) -> None:
    project = _project(client)
    risk = _risk(client, project, kind="opportunity")
    owner = _owner(client)

    refused = client.post(
        "/risk-responses",
        json={
            "project_id": project,
            "risk_id": risk,
            "owner_id": owner,
            "strategy": "avoid",  # a threat-only strategy
            **_RESPONSE_FIELDS,
        },
    )
    assert refused.status_code == 422, refused.text
    assert "does not apply to a opportunity risk" in refused.json()["detail"]


def test_accept_and_escalate_apply_to_either_kind(client: TestClient) -> None:
    project = _project(client)
    owner = _owner(client)
    threat = _risk(client, project, kind="threat")
    opportunity = _risk(client, project, kind="opportunity")

    for risk, strategy in ((threat, "escalate"), (opportunity, "accept")):
        created = client.post(
            "/risk-responses",
            json={
                "project_id": project,
                "risk_id": risk,
                "owner_id": owner,
                "strategy": strategy,
                **_RESPONSE_FIELDS,
            },
        )
        assert created.status_code == 201, created.text


def test_a_response_crossing_projects_is_refused(client: TestClient) -> None:
    left, right = _project(client, "Left"), _project(client, "Right")
    risk = _risk(client, left)
    owner = _owner(client)

    refused = client.post(
        "/risk-responses",
        json={
            "project_id": right,
            "risk_id": risk,
            "owner_id": owner,
            "strategy": "mitigate",
            **_RESPONSE_FIELDS,
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_risk_with_a_filed_response_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    risk = _risk(client, project)
    owner = _owner(client)
    _create(
        client,
        "/risk-responses",
        project_id=project,
        risk_id=risk,
        owner_id=owner,
        strategy="mitigate",
        **_RESPONSE_FIELDS,
    )

    refused = client.delete(f"/risks/{risk}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Risk {risk} still has responses", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_risk_response_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the one this change adds."""
    project = _project(client)
    risk = _risk(client, project)
    owner = _owner(client)
    _create(
        client,
        "/risk-responses",
        project_id=project,
        risk_id=risk,
        owner_id=owner,
        strategy="mitigate",
        **_RESPONSE_FIELDS,
    )

    as_json = client.get("/risk-responses").json()
    as_csv = client.get("/risk-responses", params={"format": "csv"}).text

    assert as_json[0]["strategy"] == "mitigate"
    assert "mitigate" in as_csv
