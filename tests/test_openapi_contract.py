"""The generated OpenAPI schema describes the real API, not a fiction of it.

Three properties, each pinned structurally against the live route table rather
than a hand-typed list -- in the idiom ``test_governance_contract.py`` and
``tests/test_secure.py``'s exact-set checks already use in this repo:

1. No HTML page route -- built with ``route_class=PageRoute``
   (:mod:`driftless.web.errors`) -- is published as an API endpoint. The walk
   below is a fresh one, not a call into :mod:`driftless.api.app`'s own
   exclusion: reusing that here would let a broken exclusion agree with itself
   and pass.
2. The schema declares a bearer credential, describing the real gate
   (:class:`driftless.api.secure.TokenGate`) rather than a second one that
   could disagree with it.
3. Every route ``reads``/``writes``/``creates`` register (the ~30 resources
   sharing those three functions) carries a tag derived from its own path --
   never a hand-typed name that a 31st resource could be left out of.
"""

from __future__ import annotations

from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from driftless.api import secure
from driftless.api.app import app
from driftless.api.versioning import API_PREFIX
from driftless.web.errors import PageRoute

_GENERIC_ENDPOINTS = frozenset({"list_rows", "get_row", "update_row", "delete_row", "create_row"})


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    """``route`` itself, or the routes an ``include_router`` call nested under it --
    the same shape :func:`driftless.api.secure._leaves` walks for the credential
    gate, re-derived here (not imported) so this test's page set is independent
    of anything the code under test could get wrong."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def _live_page_paths() -> frozenset[str]:
    pages = frozenset(
        leaf.path for route in app.routes for leaf in _leaves(route) if isinstance(leaf, PageRoute)
    )
    assert pages, "the walk found no page route at all -- vacuous, not passing"
    return pages


def test_no_html_page_route_is_published_in_the_generated_schema() -> None:
    leaked = set(app.openapi()["paths"]) & _live_page_paths()
    assert not leaked, f"page routes published as API endpoints: {sorted(leaked)}"


def test_the_schema_declares_a_bearer_credential() -> None:
    """Metadata only: :class:`driftless.api.secure.TokenGate` is what actually
    enforces this, as ASGI middleware outside this app -- this just says so."""
    schemes = app.openapi()["components"]["securitySchemes"]
    bearer = [
        s for s in schemes.values() if s.get("type") == "http" and s.get("scheme") == "bearer"
    ]
    assert bearer, f"no HTTP bearer scheme declared: {schemes}"
    op = app.openapi()["paths"][f"{API_PREFIX}/businesses"]["post"]
    assert op.get("security"), "a real write route carries no security requirement"


def test_every_generic_crud_route_is_tagged_with_its_own_resource() -> None:
    generic = [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and not isinstance(r, PageRoute)
        and getattr(r.endpoint, "__name__", None) in _GENERIC_ENDPOINTS
    ]
    assert generic, "vacuous walk: found none of reads/writes/creates' own routes"
    for route in generic:
        # The prefix is an ADDRESS, not a resource: a versioned route is still tagged
        # with the thing it serves, so strip it before deriving what the tag should be.
        # Reading the tag off the first path segment would call every versioned route
        # "api" and quietly stop checking anything.
        resource = route.path.removeprefix(API_PREFIX).strip("/").split("/")[0]
        assert route.tags == [resource], (route.path, route.tags)


def test_limit_and_offset_document_their_own_clamp() -> None:
    published = app.openapi()["paths"][f"{API_PREFIX}/businesses"]["get"]["parameters"]
    by_name = {p["name"]: p for p in published}
    assert "2000" in by_name["limit"]["description"]
    assert by_name["offset"]["description"]


def test_an_open_path_is_not_published_as_needing_a_credential() -> None:
    """Claiming a credential where none is required describes a gate that is not
    there — the same untruth as publishing a page route, pointing the other way.
    Read off the gate's own rule, so ``/health/ready`` — deliberately NOT open,
    because it discloses the store's revision — must keep its requirement."""
    schema = app.openapi()
    opened = {path for path in schema["paths"] if secure.is_open_path(path)}
    assert opened, "vacuous walk: the schema published no open path at all"
    for path in opened:
        for method, operation in schema["paths"][path].items():
            assert "security" not in operation, f"{method.upper()} {path} claims a credential"
    scheme = next(iter(schema["components"]["securitySchemes"]))
    gated = schema["paths"]["/health/ready"]["get"]
    assert gated["security"] == [{scheme: []}], "readiness sits INSIDE the gate on purpose"
