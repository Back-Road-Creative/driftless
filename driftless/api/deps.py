"""Request-scoped dependencies, below both ``driftless.api.app`` and ``driftless.web``.

These four names are what the page routers need from the API layer: the session that
credits its writes, the identity behind a request, and the alias every route annotates
with. They lived in :mod:`driftless.api.app` until the module that imports the web
routers was also the module the web routers imported from — a cycle the mount-once
flag and the lifespan backstop existed to sequence around.

A leaf module removes the reason for the edge. ``api.app`` imports these names back,
so ``driftless.api.app.get_session`` is still the object every
``dependency_overrides`` key names — identity is the contract there, not the path.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.requests import Request

from driftless.auth.principal import Principal
from driftless.db.changelog import set_actor, set_via
from driftless.db.session import session_scope


def _actor(request: Request) -> str | None:
    """The username the gate resolved for this request, or ``None`` for no identity.

    Read off the ASGI scope where :class:`driftless.api.secure.TokenGate` stamped it,
    so the identity is looked up once per request and never a second time here.
    """
    who = (request.scope.get("state") or {}).get("principal")
    return who.username if isinstance(who, Principal) else None


def is_agent_actor(request: Request) -> bool:
    """Whether the gate resolved an agent Person's bound token for this request.

    Read off the same ASGI scope ``_actor`` reads, so this costs nothing beyond
    the gate's own lookup. ``False`` for every unauthenticated request and for
    the shared bootstrap bearer, which resolves no principal at all — an agent
    is a *bound* credential, never the absence of one.
    """
    who = (request.scope.get("state") or {}).get("principal")
    return who.is_agent if isinstance(who, Principal) else False


def signer(request: Request, claimed: str) -> str:
    """Who the sign-off ledger records — the resolved principal, never the caller's claim.

    The same rule as the ChangeLog actor above, applied to the one column whose whole
    value is that it names a person: when the gate resolved an identity, that identity
    is what is written and the request's own ``signed_by`` is discarded, exactly as a
    ``StatusSnapshot``'s percent is stamped from calc rather than accepted from the
    request. Otherwise any contributor could append a permanent, un-deletable approval
    in a colleague's name.

    Discarded, not refused: both browser forms post the field on every sign-off, so a
    4xx would break the UI's own write while adding nothing — the 201 body carries the
    name actually stored, so a caller is never told a claim it did not get.

    The claim survives on exactly one path, and deliberately: the shared
    ``DRIFTLESS_API_TOKEN`` bearer resolves no principal (it is the bootstrap credential
    — see :func:`driftless.api.secure._refuses_write`), so an importer or an agent
    recording a decision a named human made offline supplies the name itself. Inventing
    one there would put a name on a row nobody signed; refusing it would delete the only
    honest on-behalf-of write the service has.
    """
    return _actor(request) or claimed


def resolved_actor(request: Request) -> str:
    """The identity :func:`get_session` already credits to this request, handed to
    a service that requires a non-optional ``actor`` rather than re-derived.
    ``_actor`` answers ``None`` for an unauthenticated request or the bootstrap
    bearer token; this is where that gap closes, to the literal ``"system"``.
    """
    return _actor(request) or "system"


def get_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session that credits its writes to the signed-in user.

    The credit is stamped here rather than at each write site, for the same reason
    the ChangeLog listener exists at all: a per-endpoint convention is something a
    future writer forgets, and this is the one dependency every route already takes.

    What is deliberately NOT attributed: a request authorized by the shared
    ``DRIFTLESS_API_TOKEN`` bearer resolves no principal, so its writes stay
    ``actor=None`` — the same as a CLI or migration write. That token is the
    bootstrap credential, and per-user API tokens are a separate, planned unit;
    inventing an actor for it would put a name on a row nobody signed.
    """
    with session_scope() as db:
        set_actor(db, _actor(request))
        # Web pages import this same dependency (see the module docstring) rather than
        # wiring a session provider of their own, so "api" credits both surfaces — there
        # is no distinct web channel to stamp until one exists.
        set_via(db, "api")
        yield db


Db = Annotated[Session, Depends(get_session)]
