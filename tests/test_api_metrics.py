"""``GET /metrics``: gated like every other route, Prometheus text, HTTP shape only.

Two properties matter more than the format. **Gated**: a scraper endpoint is
conventionally left open, which is wrong for a service that would disclose
portfolio scale the moment a row count answers uncredentialed -- so this
asserts an anonymous caller is refused exactly as any other route would refuse
one, never that ``/metrics`` is reachable. **HTTP shape only**:
:func:`test_the_module_imports_no_way_to_reach_a_row_count` (whitebox: this
module cannot import a session or a model) and
:func:`test_the_exposition_names_only_http_shape_metrics` (blackbox: the
families it actually declares) are two angles on one guarantee -- a future
edit would have to defeat both to smuggle a business figure onto this route.
"""

from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api import metrics, secure
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business

TOKEN = "metrics-test-token"  # pragma: allowlist secret  (throwaway in-test gate token)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    # A file, not in-memory: TestClient serves the request on another thread.
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        app.dependency_overrides[get_session] = lambda: session
        yield session
        app.dependency_overrides.clear()


@pytest.fixture
def client(db: Session) -> TestClient:
    # The real gate wrapping the real app (tests/test_secure.py's own pattern):
    # the property under test is what TokenGate decides, not a mock of it.
    return TestClient(secure.TokenGate(app, TOKEN), follow_redirects=False)


def _authed(client: TestClient) -> str:
    response = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    return response.text


def test_an_unauthenticated_caller_is_refused(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 401


def test_an_authenticated_caller_gets_a_valid_exposition(client: TestClient) -> None:
    body = _authed(client)
    assert "# TYPE driftless_http_requests_total counter" in body
    assert "# TYPE driftless_http_request_duration_seconds_sum counter" in body
    assert re.search(r"^driftless_process_uptime_seconds \d+\.\d{3}$", body, re.MULTILINE)


def test_counters_increment_across_requests(client: TestClient) -> None:
    """``/health`` is the target, not ``/metrics`` itself -- whose own count would
    otherwise reflect every *previous* scrape, never the request in flight."""

    def count(body: str) -> int:
        match = re.search(
            r'driftless_http_requests_total\{method="GET",status="200",route="/health"\} (\d+)',
            body,
        )
        return int(match.group(1)) if match else 0

    before = count(_authed(client))
    for _ in range(3):
        assert client.get("/health").status_code == 200
    assert count(_authed(client)) - before == 3


def test_an_unmatched_path_is_labelled_once_not_per_garbage_url(client: TestClient) -> None:
    """A 404 carries no route template, so every miss shares one label instead of
    minting a fresh one per attacker-chosen path."""
    client.get("/no-such-route-at-all", headers={"Authorization": f"Bearer {TOKEN}"})
    body = _authed(client)
    assert 'route="unmatched"' in body
    assert "/no-such-route-at-all" not in body


def test_the_module_imports_no_way_to_reach_a_row_count() -> None:
    """Structural: adding a business figure to ``/metrics`` would need a new
    import here first, and this pins that the module currently has none."""
    tree = ast.parse(inspect.getsource(metrics))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    forbidden = {n for n in names if n.split(".")[0] == "sqlalchemy" or n.startswith("driftless.")}
    assert not forbidden, f"metrics.py now imports {forbidden} -- a row count could reach /metrics"


def test_the_exposition_names_only_http_shape_metrics(client: TestClient, db: Session) -> None:
    """Whitelist, not blacklist: a patch adding ``driftless_projects_total`` would
    grow this set, not shrink it -- unlike a check for the word "project", which
    the ``route="/projects"`` label already contains legitimately."""
    for name in ("Acme", "Beta Co", "Gamma LLC"):
        db.add(Business(name=name))
    db.commit()
    families = set(re.findall(r"# TYPE (\S+)", _authed(client)))
    assert families == {
        "driftless_http_requests_total",
        "driftless_http_request_duration_seconds_sum",
        "driftless_process_uptime_seconds",
    }
