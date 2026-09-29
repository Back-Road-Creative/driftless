"""Serve the resource API under ``/api/v1`` as well as at its bare path.

Every route was registered bare (``/projects``, ``/tasks``), which leaves no way
to change a response shape without breaking whatever is already reading it.
``/api/v1`` becomes the canonical path and is what the generated schema
describes; the bare path keeps answering, unlisted, so existing clients and the
dashboard's own forms are not broken by the introduction of a version.

Both paths reach the SAME endpoint function, so a versioned and an unversioned
request cannot diverge in behaviour -- the alias is a second address for one
implementation, never a second copy of it.

**Infrastructure is deliberately not versioned.** ``/health``, ``/metrics``,
``/docs`` and friends are how you operate the service, not resources whose shape
a client codes against, so a version buys nothing there. That exclusion is also
load-bearing for the credential gate:
:func:`driftless.api.secure.is_open_path` matches ``/health`` EXACTLY -- on
purpose, so that ``/health/ready``, which discloses the store's schema revision,
stays gated. A ``/api/v1/health`` alias would not match that test and would land
behind the gate, so a probe pointed at the versioned path would start failing
while the bare path went on answering and every test stayed green. The fix is
NOT to teach ``is_open_path`` about prefixes: the set of open paths is a
security control, and widening it as a side effect of a routing change is how a
gate quietly stops gating. Nothing here touches it, and
``tests/test_api_versioning.py`` pins that the open set is unchanged.

Wired by one call from ``driftless.api.app``, the same idiom as
:func:`driftless.api.logging.install_request_log`,
:func:`driftless.api.metrics.install_metrics` and
:func:`driftless.api.openapi.install_api_only_openapi`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from driftless.api.openapi import page_route_paths

API_PREFIX = "/api/v1"

#: Operate-the-service paths, matched as prefixes. Not a copy of the gate's open-path
#: list -- ``/health/ready`` is gated and still belongs here, because the question this
#: answers is "is this a versioned resource?", not "is this public?".
_UNVERSIONED = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/static")


def is_versioned_path(path: str) -> bool:
    """Whether ``path`` is a resource endpoint that should also answer under the prefix."""
    return not path.startswith(_UNVERSIONED) and not path.startswith(API_PREFIX)


def install_versioned_api(app: FastAPI, prefix: str = API_PREFIX) -> None:
    """Add a ``prefix``-ed twin for every resource route already registered on ``app``.

    Call AFTER the resource routes are registered. Page routes are excluded by route
    CLASS, reusing :func:`driftless.api.openapi.page_route_paths` rather than a second
    rule here -- a page router mounted later is excluded with no edit, and two rules
    that could disagree about what an HTML route is would be worse than one.

    The bare route is left serving but dropped from the schema, so generated clients
    are written against the versioned path while nothing already deployed breaks.
    """
    pages = page_route_paths(app)
    for route in list(app.routes):
        if not isinstance(route, APIRoute) or route.path in pages:
            continue
        if not is_versioned_path(route.path):
            continue
        app.router.add_api_route(
            prefix + route.path,
            route.endpoint,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            methods=sorted(route.methods or ()),
            response_class=route.response_class,
            name=route.name,
        )
        # Served, but no longer advertised: the schema is the thing a client generator
        # reads, so listing both would document two names for one endpoint and leave the
        # reader to guess which one is going to outlive the other.
        route.include_in_schema = False
