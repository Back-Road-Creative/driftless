"""The tool-dispatch layer an MCP client actually calls -- importable with no ``mcp``
package on the path, so it is unit-tested directly (see ``tests/test_mcp.py``) and the
real server (:mod:`driftless.mcp.server`) is a thin registration shim over it.

Two families, both "no second write path":

* The generic resource verbs (``create_resource``, ``list_resource``, ``get_resource``,
  ``update_resource``, ``delete_resource``) go through the SAME gated ASGI app the
  container serves -- a caller-supplied :class:`~fastapi.testclient.TestClient` wrapping
  :class:`driftless.api.secure.TokenGate` -- so auth, role gating, ``ChangeLog`` actor
  attribution and every validation rule are the app's own, never reimplemented here.
* The wizard verbs (``wizard_next``, ``wizard_status``, ``wizard_apply``) have no HTTP
  JSON endpoint to proxy (:mod:`driftless.wizard.engine` and
  :func:`driftless.services.wizard_writes.produce` back the CLI and the web wizard page
  instead), so they call those same service functions directly and authenticate the
  bearer token themselves via :func:`driftless.auth.tokens.resolve` -- exactly the
  lookup :class:`~driftless.api.secure.TokenGate` already makes for a ``dfl_...`` token.
"""

from __future__ import annotations

import dataclasses
import hmac
import os
from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient

from driftless.auth import tokens
from driftless.auth.principal import Principal
from driftless.db.session import session_scope
from driftless.models import Project
from driftless.pmbok.model import ProcessGroup
from driftless.services.wizard_writes import Fields, produce
from driftless.wizard import engine

#: The same floor ``driftless.api.secure`` enforces before any write route runs
#: (``_WRITE_ROLES`` there) -- restated here because that name is private to its module
#: and a write made through this layer needs the identical gate.
WRITE_ROLES = frozenset({"admin", "contributor"})

#: The env vars ``driftless.api.secure.create_secured_app`` reads for the bootstrap
#: bearer -- checked here too, so a shared-token caller authenticates the same way
#: whether it reaches the app over HTTP or through a wizard tool.
_TOKEN_ENV = "DRIFTLESS_API_TOKEN"
_LEGACY_TOKEN_ENV = "PMHUB_API_TOKEN"


class McpAuthError(PermissionError):
    """A bearer token this layer refused -- unknown, revoked, or the wrong role."""


def _shared_token() -> str | None:
    return os.environ.get(_TOKEN_ENV) or os.environ.get(_LEGACY_TOKEN_ENV) or None


def authenticate(token: str) -> Principal | None:
    """The identity behind ``token``, or ``None`` for the un-role-gated bootstrap bearer.

    Raises :class:`McpAuthError` for anything else the store does not vouch for --
    a token with no ``dfl_...`` prefix, or one :func:`~driftless.auth.tokens.resolve`
    could not resolve (revoked, expired, or a deactivated owner).
    """
    shared = _shared_token()
    if shared is not None and hmac.compare_digest(token, shared):
        return None
    if not token.startswith(tokens.PREFIX):
        raise McpAuthError("not a recognised credential")
    with session_scope() as db:
        principal = tokens.resolve(db, token, datetime.now(UTC))
    if principal is None:
        raise McpAuthError("not a recognised credential")
    return principal


def _actor(principal: Principal | None) -> str:
    """Who a wizard write is credited to -- the same fallback
    :func:`driftless.api.deps.resolved_actor` uses for a request the gate resolved no
    principal for (the bootstrap bearer): the literal ``"system"``."""
    return principal.username if principal is not None else "system"


def wizard_next(
    token: str, project_id: int, as_of: date, groups: list[str] | None = None
) -> dict[str, Any] | None:
    """The next incomplete process this project can work, as a plain dict -- a read,
    open to every role a token resolves."""
    authenticate(token)
    with session_scope() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError(f"no project {project_id}")
        wanted = [ProcessGroup(g) for g in groups] if groups else None
        step = engine.next_step(db, project, as_of, wanted)
        return None if step is None else dataclasses.asdict(step)


def wizard_status(token: str, project_id: int, as_of: date) -> list[list[str]]:
    """Every catalog process and its state, as ``[process_id, state]`` pairs."""
    authenticate(token)
    with session_scope() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError(f"no project {project_id}")
        return [[process_id, state] for process_id, state in engine.status(db, project, as_of)]


def wizard_apply(token: str, project_id: int, kind: str, as_of: date, fields: Fields) -> int:
    """Produce one wizard output through :func:`~driftless.services.wizard_writes.produce`
    -- a write, refused with :class:`McpAuthError` for a role outside
    :data:`WRITE_ROLES`, exactly as the API gate would refuse the same request over HTTP.
    """
    principal = authenticate(token)
    if principal is not None and principal.role not in WRITE_ROLES:
        raise McpAuthError("writes need the contributor or admin role")
    with session_scope() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError(f"no project {project_id}")
        return produce(db, project, kind, fields, as_of, _actor(principal))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_resource(
    client: TestClient, token: str, path: str, body: dict[str, Any]
) -> dict[str, Any]:
    """``POST /api/v1{path}`` through the same gated app the container serves."""
    answer = client.post(f"/api/v1{path}", json=body, headers=_headers(token))
    return {"status": answer.status_code, "body": _body(answer)}


def list_resource(
    client: TestClient,
    token: str,
    path: str,
    params: dict[str, Any] | None = None,
    format: str = "json",
) -> dict[str, Any]:
    """``GET /api/v1{path}`` -- every filter and ``?format=csv`` documented in
    ``docs/agent-guide.md`` §4 is just a query parameter here, unchanged."""
    query = {**(params or {}), "format": format}
    answer = client.get(f"/api/v1{path}", params=query, headers=_headers(token))
    return {"status": answer.status_code, "body": _body(answer)}


def get_resource(client: TestClient, token: str, path: str, row_id: int) -> dict[str, Any]:
    """``GET /api/v1{path}/{row_id}``."""
    answer = client.get(f"/api/v1{path}/{row_id}", headers=_headers(token))
    return {"status": answer.status_code, "body": _body(answer)}


def update_resource(
    client: TestClient,
    token: str,
    path: str,
    row_id: int,
    body: dict[str, Any],
    if_match: int | None = None,
) -> dict[str, Any]:
    """``PATCH /api/v1{path}/{row_id}``, carrying ``If-Match`` when given."""
    headers = _headers(token)
    if if_match is not None:
        headers["If-Match"] = str(if_match)
    answer = client.patch(f"/api/v1{path}/{row_id}", json=body, headers=headers)
    return {"status": answer.status_code, "body": _body(answer)}


def delete_resource(
    client: TestClient, token: str, path: str, row_id: int, if_match: int | None = None
) -> dict[str, Any]:
    """``DELETE /api/v1{path}/{row_id}``, carrying ``If-Match`` when given."""
    headers = _headers(token)
    if if_match is not None:
        headers["If-Match"] = str(if_match)
    answer = client.delete(f"/api/v1{path}/{row_id}", headers=headers)
    return {
        "status": answer.status_code,
        "body": None if answer.status_code == 204 else _body(answer),
    }


def _body(answer: Any) -> Any:
    try:
        return answer.json()
    except ValueError:
        return answer.text
