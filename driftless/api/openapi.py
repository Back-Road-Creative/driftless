"""Filter the generated OpenAPI schema down to the API — no HTML page route.

FastAPI's default schema publishes every route ``app`` serves, page and API
alike -- a page router is exactly as much a member of ``app.routes`` as a
resource endpoint is, so a generated client saw the dashboard's own HTML
forms as though they answered JSON. Filtered structurally, by route TYPE
(:func:`page_route_paths` reads ``route_class=PageRoute``), rather than by a
hand-kept list of the ``include_router`` calls in ``driftless.api.app``'s
``mount_web``: a router mounted the same way later is excluded with no edit
here.

Wired the same way ``driftless.api.logging`` and ``driftless.api.metrics``
already are -- one call from ``app.py`` -- and imports nothing from
``driftless.api.app`` itself, so that one call is never circular. ONE import
below stays inside the function that needs it: ``driftless.api.secure`` sits on
the far side of ``driftless.api.app`` in the import graph, because it imports
the finished ``app`` itself, so hoisting that one to module scope here would
re-close the very cycle this module exists apart from. ``driftless.web.errors``
used to be in the same position and no longer is -- nothing under
``driftless/web`` imports ``driftless.api.app`` -- so it is a plain import.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.routing import BaseRoute

from driftless.web.errors import PageRoute


def _leaf_routes(route: BaseRoute) -> list[BaseRoute]:
    """``route`` itself, or the routes an ``include_router`` call nested under it.

    The same shape :func:`driftless.api.secure._leaves` walks for the credential
    gate, duplicated rather than imported: that module imports the finished
    ``app`` from :mod:`driftless.api.app`, so importing back from it here at
    module scope would be circular.
    """
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaf_routes(child)]
    return [route]


def page_route_paths(app: FastAPI) -> frozenset[str]:
    """Every HTML page route's own path, read off ``app``'s live route table."""
    return frozenset(
        leaf.path
        for route in app.routes
        for leaf in _leaf_routes(route)
        if isinstance(leaf, PageRoute)
    )


def install_api_only_openapi(app: FastAPI) -> None:
    """Attach the filtered OpenAPI generator to ``app`` -- the app module's
    single wiring line, in the same idiom as
    :func:`driftless.api.logging.install_request_log` and
    :func:`driftless.api.metrics.install_metrics`.
    """

    def _api_only_openapi() -> dict[str, Any]:
        """The generated schema, minus every HTML page route.

        The bearer declaration on ``app`` is global, so an open path would be
        published as needing a credential it has never needed. Un-declared
        again from the gate's OWN rule, :func:`driftless.api.secure.is_open_path`
        -- ``/health`` is open and ``/health/ready`` is deliberately not, and a
        second list here would get exactly that distinction wrong. Imported
        inside the function because :mod:`driftless.api.secure` imports the
        finished ``app`` from :mod:`driftless.api.app`, so importing it here at
        module scope would be circular. It is the last import in this package
        that still has that reason.

        Otherwise mirrors ``FastAPI.openapi`` field for field, caching on
        ``app.openapi_schema`` the same way, so a repeated call still costs one
        dict filter rather than one full regeneration. The cache lives on
        ``app`` itself, never on this module, so a fresh app in a test gets a
        fresh schema.
        """
        from driftless.api.secure import is_open_path

        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                openapi_version=app.openapi_version,
                summary=app.summary,
                description=app.description,
                terms_of_service=app.terms_of_service,
                contact=app.contact,
                license_info=app.license_info,
                routes=app.routes,
                webhooks=app.webhooks.routes,
                tags=app.openapi_tags,
                servers=app.servers,
                separate_input_output_schemas=app.separate_input_output_schemas,
                external_docs=app.openapi_external_docs,
            )
            pages = page_route_paths(app)
            schema["paths"] = {p: ops for p, ops in schema["paths"].items() if p not in pages}
            for path, operations in schema["paths"].items():
                if is_open_path(path):
                    for operation in operations.values():
                        if isinstance(operation, dict):
                            operation.pop("security", None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _api_only_openapi  # type: ignore[method-assign]
