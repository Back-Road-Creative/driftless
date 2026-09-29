"""Drives :mod:`driftless.mcp.server` (its own registration shim and JSON-RPC stdio
loop -- no third-party MCP SDK) through its own tool registry, rather than through
``driftless.mcp.tools`` directly (see ``tests/test_mcp.py``): every ``@server.tool()``
wrapper's argument conversion (ISO date strings, ``groups`` lists) and its call into
the dispatch layer, plus :func:`serve_stdio`'s wiring and the ``initialize`` /
``tools/list`` / ``tools/call`` request handling itself.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from driftless.auth import tokens
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import session as db_session
from driftless.db.changelog import register_changelog
from driftless.mcp import cli as mcp_cli
from driftless.mcp import server as mcp_server
from driftless.mcp.server import MCPServer
from driftless.models import User

SHARED = "shared-bootstrap-token"  # pragma: allowlist secret  (in-test gate token)
AS_OF = "2026-03-31"


@dataclass
class Env:
    server: MCPServer
    factory: sessionmaker[Session]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    engine = new_engine(f"sqlite:///{tmp_path / 'mcp_server.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(db_session, "_factory", factory)
    monkeypatch.setenv("DRIFTLESS_API_TOKEN", SHARED)
    yield Env(mcp_server.build_server(), factory)


def _mint(factory: sessionmaker[Session], username: str, role: str) -> str:
    with factory() as db:
        user = User(username=username, password_hash="x", role=role)
        db.add(user)
        db.commit()
        token = tokens.issue(db, user, label="test")
    return token


def _call(server: MCPServer, name: str, arguments: dict[str, Any]) -> Any:
    """Call a registered tool and unwrap the ``{"result": ...}`` envelope
    :meth:`MCPServer.call_tool` adds for any return type that is not itself a
    ``dict[str, Any]``
    (``wizard_next`` returns ``dict[str, Any] | None`` -- a union, so it is
    wrapped too, exactly like the ``int`` and ``list`` returns)."""
    payload = asyncio.run(server.call_tool(name, arguments)).structured_content
    if isinstance(payload, dict) and set(payload) == {"result"}:
        return payload["result"]
    return payload


def _project_id(server: MCPServer) -> int:
    biz = _call(
        server,
        "create_resource",
        {"token": SHARED, "path": "/businesses", "body": {"name": "BRC"}},
    )
    portfolio = _call(
        server,
        "create_resource",
        {
            "token": SHARED,
            "path": "/portfolios",
            "body": {"name": "Content Brands", "business_id": biz["body"]["id"]},
        },
    )
    project = _call(
        server,
        "create_resource",
        {
            "token": SHARED,
            "path": "/projects",
            "body": {
                "name": "Aurora",
                "portfolio_id": portfolio["body"]["id"],
                "delivery_mode": "predictive",
            },
        },
    )
    return int(project["body"]["id"])


def test_build_server_registers_every_tool(env: Env) -> None:
    names = {t.name for t in asyncio.run(env.server.list_tools())}
    assert names == {
        "wizard_next",
        "wizard_status",
        "wizard_apply",
        "create_resource",
        "list_resource",
        "get_resource",
        "update_resource",
        "delete_resource",
    }


def test_wizard_next_tool_converts_its_arguments(env: Env) -> None:
    project_id = _project_id(env.server)
    step = _call(
        env.server,
        "wizard_next",
        {"token": SHARED, "project_id": project_id, "as_of": AS_OF, "groups": ["initiating"]},
    )
    assert step["process_id"] == "4.1"


def test_wizard_next_tool_with_no_groups_filter(env: Env) -> None:
    project_id = _project_id(env.server)
    step = _call(
        env.server, "wizard_next", {"token": SHARED, "project_id": project_id, "as_of": AS_OF}
    )
    assert step["process_id"] == "4.1"


def test_wizard_status_tool(env: Env) -> None:
    project_id = _project_id(env.server)
    pairs = _call(
        env.server, "wizard_status", {"token": SHARED, "project_id": project_id, "as_of": AS_OF}
    )
    assert ["4.1", "not_started"] in pairs


def test_wizard_apply_tool(env: Env) -> None:
    project_id = _project_id(env.server)
    row_id = _call(
        env.server,
        "wizard_apply",
        {
            "token": SHARED,
            "project_id": project_id,
            "kind": "assumption_log",
            "as_of": AS_OF,
            "fields": {"body": "Vendor lead times hold."},
        },
    )
    assert row_id == 1


def test_list_get_update_delete_resource_tools(env: Env) -> None:
    project_id = _project_id(env.server)
    created = _call(
        env.server,
        "create_resource",
        {
            "token": SHARED,
            "path": "/stakeholders",
            "body": {"project_id": project_id, "name": "Ada Lovelace"},
        },
    )
    row_id = created["body"]["id"]

    listed = _call(
        env.server,
        "list_resource",
        {"token": SHARED, "path": "/stakeholders", "params": {}, "format": "json"},
    )
    assert listed["status"] == 200

    fetched = _call(
        env.server, "get_resource", {"token": SHARED, "path": "/stakeholders", "row_id": row_id}
    )
    assert fetched["body"]["name"] == "Ada Lovelace"

    updated = _call(
        env.server,
        "update_resource",
        {
            "token": SHARED,
            "path": "/stakeholders",
            "row_id": row_id,
            "body": {"name": "Ada"},
            "if_match": created["body"]["row_revision"],
        },
    )
    assert updated["body"]["name"] == "Ada"

    deleted = _call(
        env.server,
        "delete_resource",
        {
            "token": SHARED,
            "path": "/stakeholders",
            "row_id": row_id,
            "if_match": updated["body"]["row_revision"],
        },
    )
    assert deleted["status"] == 204


def _run_stdio(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, lines: list[str]
) -> list[dict[str, Any]]:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines) + "\n"))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    server.run("stdio")
    return [json.loads(line) for line in out.getvalue().splitlines() if line]


def test_run_rejects_a_non_stdio_transport(env: Env) -> None:
    with pytest.raises(ValueError, match="unsupported transport"):
        env.server.run("http")


def test_stdio_initialize_and_tools_list(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _run_stdio(
        env.server,
        monkeypatch,
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ],
    )
    assert responses[0]["result"]["protocolVersion"]
    names = {t["name"] for t in responses[1]["result"]["tools"]}
    assert "wizard_status" in names


def test_stdio_tools_call_success_error_and_notifications(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _project_id(env.server)
    responses = _run_stdio(
        env.server,
        monkeypatch,
        [
            "",  # a blank line between requests is skipped, not parsed
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "wizard_status",
                        "arguments": {"token": SHARED, "project_id": project_id, "as_of": AS_OF},
                    },
                }
            ),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "no_such_tool"},
                }
            ),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "not/a/method"}),
            json.dumps(
                {"jsonrpc": "2.0", "method": "not/a/method"}
            ),  # a notification: no id, no answer
            json.dumps({"jsonrpc": "2.0", "method": "tools/list"}),  # a known-method notification
        ],
    )
    assert ["4.1", "not_started"] in responses[0]["result"]["structuredContent"]["result"]
    assert responses[1]["result"]["isError"] is True
    assert responses[2]["error"]["code"] == -32601
    assert len(responses) == 3  # neither notification produced a fourth or fifth line


def test_serve_stdio_runs_the_built_server_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _FakeServer:
        def run(self, transport: str) -> None:
            calls.append(transport)

    monkeypatch.setattr(mcp_server, "build_server", lambda: _FakeServer())
    mcp_server.serve_stdio()
    assert calls == ["stdio"]


def test_run_serve_calls_serve_stdio_and_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(mcp_server, "serve_stdio", lambda: calls.append("served"))
    assert mcp_cli._run_serve(argparse.Namespace()) == 0
    assert calls == ["served"]


def test_add_mcp_subparser_registers_serve_with_run_serve_handler() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    mcp_cli.add_mcp_subparser(commands)
    args = parser.parse_args(["mcp", "serve"])
    assert args.handler is mcp_cli._run_serve
