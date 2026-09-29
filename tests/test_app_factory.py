"""``create_app()`` builds a whole app, and two calls do not share one.

Every route used to be registered at module scope against a global ``app``: the twelve
decorated handlers, the exception handler, the seventy-four resource registrations (B1
moved those into a function), the page mount and the versioned twins. Importing the
module WAS the construction, so there was exactly one app per process and no way to
build a second — which is what makes any variation untestable and any per-app
configuration impossible.

The construction moves into ``create_app()``. ``app = create_app()`` stays at module
scope on purpose and is not an implementation detail to be tidied away later: the
production entrypoint is ``uvicorn driftless.api.secure:secured`` and
``driftless.api.secure`` imports that module-scope name, so losing it fails at deploy
rather than here. ``test_the_module_level_app_is_still_there`` is the guard for that.
"""

from __future__ import annotations

from collections import Counter

from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError

from driftless.api.app import app, create_app


def _keys(built: FastAPI) -> Counter[tuple[str, tuple[str, ...]]]:
    """(path, methods) for every ``APIRoute`` a built app answers, descending into the
    ``include_router`` wrappers the page mount hangs off it — as a multiset, so a route
    registered twice stays visible instead of collapsing into a set."""

    def leaves(route: object) -> list[object]:
        for holder in (route, getattr(route, "original_router", None)):
            children = getattr(holder, "routes", None)
            if children:
                return [leaf for child in children for leaf in leaves(child)]
        return [route]

    return Counter(
        (leaf.path, tuple(sorted(leaf.methods or ())))
        for route in built.routes
        for leaf in leaves(route)
        if isinstance(leaf, APIRoute)
    )


def test_two_apps_are_independent_and_serve_the_same_table() -> None:
    """The property the factory exists for: build twice, get two equal-but-separate apps."""
    first, second = create_app(), create_app()

    assert first is not second
    assert _keys(first), "the factory registered nothing at all -- vacuous-pass guard"
    assert _keys(first) == _keys(second)


def test_a_fresh_app_serves_what_the_module_level_one_does() -> None:
    """A build on demand is not a reduced build: same routes as the singleton's."""
    assert _keys(create_app()) == _keys(app)


def test_the_module_level_app_is_still_there() -> None:
    """``driftless.api.secure`` imports this name and the Dockerfile serves through it.

    Asserted rather than assumed: losing it is a container that will not start, and
    nothing else in the suite would notice, because every test builds its own client.
    """
    assert isinstance(app, FastAPI)


def test_the_page_mount_and_the_versioned_twins_are_inside_the_factory() -> None:
    """Both run last and both read the finished table, so a factory that skipped either
    would still look correct until something asked for a page or a ``/api/v1`` path."""
    paths = {path for path, _ in _keys(create_app())}

    assert "/" in paths, "the page mount did not run inside the factory"
    assert "/static" not in paths, "sanity: the static mount is not an APIRoute"
    assert any(path.startswith("/api/v1/") for path in paths), "no versioned twins"


def test_the_integrity_handler_is_registered_by_the_factory() -> None:
    """It is not a route, so no route-table check above can see it."""
    assert IntegrityError in create_app().exception_handlers
