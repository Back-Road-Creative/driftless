from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _project(client: TestClient) -> int:
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(client, "/projects", name="GMS", portfolio_id=portfolio)


def test_quality_metric_definition_sets_direction_and_thresholds(tmp_path: Path) -> None:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    try:
        with TestClient(app) as client:
            project = _project(client)
            metric = _create(
                client,
                "/quality-metrics",
                project_id=project,
                name="availability",
                direction="higher_is_better",
                lower_bound=99.9,
                unit="percent",
            )
            _create(
                client,
                "/quality-measurements",
                project_id=project,
                metric="availability",
                target_value=99.9,
                actual_value=99.95,
                measured_on="2026-08-12",
                quality_metric_id=metric,
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_quality_metric_definition_rejects_an_invalid_directional_threshold(tmp_path: Path) -> None:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    try:
        with TestClient(app) as client:
            project = _project(client)
            refused = client.post(
                "/quality-metrics",
                json={
                    "project_id": project,
                    "name": "availability",
                    "direction": "higher_is_better",
                    "upper_bound": 99.9,
                },
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert refused.status_code == 422, refused.text
