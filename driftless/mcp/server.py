"""Registers :mod:`driftless.mcp.tools` onto a small MCP server this module implements
itself -- newline-delimited JSON-RPC 2.0 over stdio (``initialize``, ``tools/list``,
``tools/call``: https://modelcontextprotocol.io/specification), not a wrapper over the
third-party ``mcp`` SDK. That package was never installed by ``.[dev]`` (CI's install
line) or ``requirements.lock``, only ever imported behind a guard for the one caller
that needed it, so a checkout that ran the ordinary test suite exercised none of the
guarded code and the guard itself only ever proved its own existence. Owning the wire
format directly means every environment -- CI, the lock file, a fresh checkout -- agrees
by construction: there is nothing optional left to install.

Every tool is a thin wrapper: it converts MCP's JSON-shaped arguments (dates and
process groups arrive as strings) and calls straight into :mod:`driftless.mcp.tools`,
which is the layer ``tests/test_mcp.py`` drives directly.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, get_args, get_origin, get_type_hints

from fastapi.testclient import TestClient

from driftless.api.secure import create_secured_app
from driftless.mcp import tools

_PROTOCOL_VERSION = "2024-11-05"


def _wraps_result(func: Callable[..., Any]) -> bool:
    """Whether :meth:`MCPServer.call_tool` should wrap ``func``'s return value in
    ``{"result": ...}`` -- every declared return type except the literal
    ``dict[str, Any]`` (a plain JSON object needs no envelope; anything else, union,
    list or scalar, is not itself an object and so gets one)."""
    ret = get_type_hints(func).get("return")
    return not (get_origin(ret) is dict and get_args(ret) == (str, Any))


@dataclass(frozen=True)
class _Tool:
    name: str
    func: Callable[..., Any]
    description: str
    wraps: bool


@dataclass(frozen=True)
class ToolResult:
    """What :meth:`MCPServer.call_tool` returns -- the one field ``tests/test_mcp_server.py``
    and the stdio loop both read."""

    structured_content: dict[str, Any]


class MCPServer:
    """A tool registry plus the stdio transport for it -- the whole of what this
    service's read-only, single-client use of MCP needs. Not a general SDK: no
    resources, no prompts, no streaming, no capability negotiation beyond the one
    fixed answer :meth:`_handle` gives ``initialize``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._tools: dict[str, _Tool] = {}

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[func.__name__] = _Tool(
                name=func.__name__,
                func=func,
                description=(func.__doc__ or "").strip(),
                wraps=_wraps_result(func),
            )
            return func

        return register

    async def list_tools(self) -> list[_Tool]:
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        found = self._tools[name]
        result = found.func(**arguments)
        return ToolResult({"result": result} if found.wraps else result)

    def run(self, transport: str) -> None:
        if transport != "stdio":
            raise ValueError(f"unsupported transport: {transport!r}")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            response = asyncio.run(self._handle(json.loads(line)))
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    async def _handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": "1.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": {"type": "object"},
                    }
                    for t in await self.list_tools()
                ]
            }
        elif method == "tools/call":
            params = request.get("params") or {}
            try:
                outcome = await self.call_tool(params["name"], params.get("arguments") or {})
            except Exception as exc:  # a tool failure is a call result, not a transport fault
                result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
            else:
                result = {
                    "content": [{"type": "text", "text": json.dumps(outcome.structured_content)}],
                    "structuredContent": outcome.structured_content,
                }
        elif request_id is None:
            return None  # an unknown notification: nothing to answer
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method: {method!r}"},
            }
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def build_server() -> MCPServer:
    """The configured :class:`MCPServer`, its tools registered."""
    client = TestClient(create_secured_app())
    server = MCPServer("driftless")

    @server.tool()
    def wizard_next(
        token: str, project_id: int, as_of: str, groups: list[str] | None = None
    ) -> dict[str, Any] | None:
        """The next PMBOK process this project has not finished, and how to produce it."""
        return tools.wizard_next(token, project_id, date.fromisoformat(as_of), groups)

    @server.tool()
    def wizard_status(token: str, project_id: int, as_of: str) -> list[list[str]]:
        """Every catalog process and this project's state for it, at once."""
        return tools.wizard_status(token, project_id, date.fromisoformat(as_of))

    @server.tool()
    def wizard_apply(
        token: str, project_id: int, kind: str, as_of: str, fields: dict[str, Any]
    ) -> int:
        """Produce one wizard output; returns the row id it landed at."""
        return tools.wizard_apply(token, project_id, kind, date.fromisoformat(as_of), fields)

    @server.tool()
    def create_resource(token: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/v1{path}`` -- create one row of any resource the API serves."""
        return tools.create_resource(client, token, path, body)

    @server.tool()
    def list_resource(
        token: str, path: str, params: dict[str, Any] | None = None, format: str = "json"
    ) -> dict[str, Any]:
        """``GET /api/v1{path}`` -- windowed, filterable, ``?format=csv`` included."""
        return tools.list_resource(client, token, path, params, format)

    @server.tool()
    def get_resource(token: str, path: str, row_id: int) -> dict[str, Any]:
        """``GET /api/v1{path}/{row_id}`` -- one row."""
        return tools.get_resource(client, token, path, row_id)

    @server.tool()
    def update_resource(
        token: str, path: str, row_id: int, body: dict[str, Any], if_match: int | None = None
    ) -> dict[str, Any]:
        """``PATCH /api/v1{path}/{row_id}``."""
        return tools.update_resource(client, token, path, row_id, body, if_match)

    @server.tool()
    def delete_resource(
        token: str, path: str, row_id: int, if_match: int | None = None
    ) -> dict[str, Any]:
        """``DELETE /api/v1{path}/{row_id}``."""
        return tools.delete_resource(client, token, path, row_id, if_match)

    return server


def serve_stdio() -> None:
    """Run the server over stdio -- what ``driftless mcp serve`` invokes."""
    build_server().run("stdio")
