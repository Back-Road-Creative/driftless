"""``driftless.mcp.tools`` -- the dispatch layer an MCP tool call reaches, with no stdio
transport in between (that layer is exercised end to end by
``tests/test_docs_agent_guide.py``'s §6 blocks; this file pins its contract directly):
a wizard write lands on the ``ChangeLog`` credited to the bearer token's own user, and a
viewer's token is refused a write exactly as the API gate refuses it over HTTP.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.auth import tokens
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import session as db_session
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.mcp import tools
from driftless.models import User

SHARED = "shared-bootstrap-token"  # pragma: allowlist secret  (in-test gate token)
AS_OF = date(2026, 3, 31)


@dataclass
class Env:
    client: TestClient
    factory: sessionmaker[Session]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    engine = new_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(db_session, "_factory", factory)
    monkeypatch.setenv("DRIFTLESS_API_TOKEN", SHARED)
    client = TestClient(TokenGate(app, SHARED))
    yield Env(client, factory)


def _mint(factory: sessionmaker[Session], username: str, role: str) -> str:
    with factory() as db:
        user = User(username=username, password_hash="x", role=role)
        db.add(user)
        db.commit()
        token = tokens.issue(db, user, label="test")
    return token


def _project_id(env: Env) -> int:
    biz = tools.create_resource(env.client, SHARED, "/businesses", {"name": "Back Road Creative"})
    portfolio = tools.create_resource(
        env.client,
        SHARED,
        "/portfolios",
        {"name": "Content Brands", "business_id": biz["body"]["id"]},
    )
    project = tools.create_resource(
        env.client,
        SHARED,
        "/projects",
        {"name": "Aurora", "portfolio_id": portfolio["body"]["id"], "delivery_mode": "predictive"},
    )
    return int(project["body"]["id"])


def test_wizard_loop_writes_land_credited_to_the_tokens_own_user(env: Env) -> None:
    project_id = _project_id(env)
    contributor = _mint(env.factory, "agent", "contributor")

    step = tools.wizard_next(contributor, project_id, AS_OF)
    assert step is not None and step["process_id"] == "4.1"
    assert "assumption_log" in step["producible"]

    row_id = tools.wizard_apply(
        contributor, project_id, "assumption_log", AS_OF, {"body": "Vendor lead times hold."}
    )
    assert row_id == 1

    with env.factory() as db:
        rows = db.scalars(
            select(ChangeLog).where(ChangeLog.table_name == "narrative_artifact")
        ).all()
    assert [row.actor for row in rows] == ["agent"]

    status = dict(tools.wizard_status(contributor, project_id, AS_OF))
    assert status["4.1"] == "produced"


def test_bootstrap_bearer_credits_writes_to_system(env: Env) -> None:
    project_id = _project_id(env)
    tools.wizard_apply(SHARED, project_id, "assumption_log", AS_OF, {"body": "Seeded."})
    with env.factory() as db:
        row = db.scalars(
            select(ChangeLog).where(ChangeLog.table_name == "narrative_artifact")
        ).one()
    assert row.actor == "system"


def test_viewer_role_is_refused_a_wizard_write(env: Env) -> None:
    project_id = _project_id(env)
    viewer = _mint(env.factory, "reader", "viewer")
    with pytest.raises(tools.McpAuthError):
        tools.wizard_apply(viewer, project_id, "assumption_log", AS_OF, {"body": "nope"})


def test_viewer_role_is_refused_a_resource_write_over_the_same_gated_app(env: Env) -> None:
    project_id = _project_id(env)
    viewer = _mint(env.factory, "reader", "viewer")
    answer = tools.create_resource(
        env.client, viewer, "/stakeholders", {"project_id": project_id, "name": "Ada"}
    )
    assert answer["status"] == 403


def test_an_unresolvable_token_is_refused(env: Env) -> None:
    with pytest.raises(tools.McpAuthError):
        tools.authenticate("dfl_not_a_real_token")


def test_the_shared_bootstrap_bearer_authenticates_with_no_principal(env: Env) -> None:
    assert tools.authenticate(SHARED) is None


def test_list_and_get_resource_round_trip(env: Env) -> None:
    project_id = _project_id(env)
    contributor = _mint(env.factory, "agent", "contributor")
    tools.wizard_apply(contributor, project_id, "assumption_log", AS_OF, {"body": "x"})

    listed = tools.list_resource(env.client, contributor, "/narrative-artifacts")
    assert listed["status"] == 200
    assert listed["body"][0]["project_id"] == project_id

    fetched = tools.get_resource(env.client, contributor, "/narrative-artifacts", 1)
    assert fetched["status"] == 200
    assert fetched["body"]["body"] == "x"


def test_a_non_dfl_token_is_refused_before_any_store_lookup(env: Env) -> None:
    with pytest.raises(tools.McpAuthError):
        tools.authenticate("not-a-recognised-shape")


def test_wizard_next_rejects_an_unknown_project(env: Env) -> None:
    with pytest.raises(ValueError, match="no project"):
        tools.wizard_next(SHARED, 999, AS_OF)


def test_wizard_status_rejects_an_unknown_project(env: Env) -> None:
    with pytest.raises(ValueError, match="no project"):
        tools.wizard_status(SHARED, 999, AS_OF)


def test_wizard_apply_rejects_an_unknown_project(env: Env) -> None:
    with pytest.raises(ValueError, match="no project"):
        tools.wizard_apply(SHARED, 999, "assumption_log", AS_OF, {"body": "x"})


def test_list_resource_falls_back_to_text_for_a_non_json_body(env: Env) -> None:
    project_id = _project_id(env)
    tools.wizard_apply(SHARED, project_id, "assumption_log", AS_OF, {"body": "x"})
    listed = tools.list_resource(env.client, SHARED, "/narrative-artifacts", format="csv")
    assert listed["status"] == 200
    assert isinstance(listed["body"], str)


def test_update_and_delete_resource_round_trip(env: Env) -> None:
    project_id = _project_id(env)
    created = tools.create_resource(
        env.client, SHARED, "/stakeholders", {"project_id": project_id, "name": "Ada Lovelace"}
    )
    row_id = created["body"]["id"]

    updated = tools.update_resource(
        env.client,
        SHARED,
        "/stakeholders",
        row_id,
        {"name": "Ada"},
        if_match=created["body"]["row_revision"],
    )
    assert updated["status"] == 200
    assert updated["body"]["name"] == "Ada"

    deleted = tools.delete_resource(
        env.client, SHARED, "/stakeholders", row_id, if_match=updated["body"]["row_revision"]
    )
    assert deleted["status"] == 204
