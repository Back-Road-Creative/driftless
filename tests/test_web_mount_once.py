"""Every web route path appears exactly once in the live route table.

``driftless.api.assembly.mount_web`` used to carry a module-global ``_web_mounted``
flag, because ``driftless.api.app`` called it from TWO places — module import, and a
lifespan backstop for the one import order that could not mount at import. Both the
second call site and the flag are gone (the import cycle that forced them is gone), so
nothing absorbs a double mount any more: a second ``mount_web`` call, or one page router
included twice inside it, now duplicates every one of that router's routes onto ``app``.

No other test would catch that: both ``tests/test_web_routes_not_shadowed.py`` and
``tests/test_api_import_order.py`` compare ``sorted({...})`` — a set, so a duplicated
path collapses back down to one entry and the assertion passes regardless. This one
counts a LIST, so a duplicate stays visible. ``tests/test_api_import_order.py`` holds
the other half: that the single call site stays single, and unconditional.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from starlette.routing import BaseRoute

from driftless.api.app import app


def _included(route: BaseRoute) -> list[BaseRoute] | None:
    """The routes an ``include_router`` call contributed, or ``None`` when the
    route was registered directly on the app.

    Duplicated from ``tests/test_web_routes_not_shadowed.py`` rather than
    imported: it is a private test helper, and a shared import buys nothing a
    six-line duplicate does not already give this module on its own.
    """
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return list(children)
    return None


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    children = _included(route)
    if children is None:
        return [route]
    return [leaf for child in children for leaf in _leaves(child)]


def _web_route_keys(routes: Iterable[BaseRoute]) -> list[tuple[str, tuple[str, ...]]]:
    """(path, methods) for every leaf an included (web) router contributes — as a
    LIST, duplicates and all, so a route mounted twice appears twice.

    Keyed on path AND methods, not path alone: ``/login`` legitimately carries
    both a ``GET`` and a distinct ``POST`` route object (the form's own page and
    its submit handler), and counting bare paths would flag that as a false
    duplicate before it ever saw a real double mount.
    """
    keys: list[tuple[str, tuple[str, ...]]] = []
    for route in routes:
        children = _included(route)
        if children is None:
            continue
        for leaf in _leaves(route):
            path = str(getattr(leaf, "path", ""))
            methods = tuple(sorted(getattr(leaf, "methods", None) or ()))
            keys.append((path, methods))
    return keys


def test_each_web_route_path_appears_exactly_once() -> None:
    keys = _web_route_keys(app.routes)
    assert keys, "the walk found no web routes at all -- vacuous-pass guard tripped"
    counts = Counter(keys)
    duplicated = sorted(key for key, n in counts.items() if n > 1)
    assert not duplicated, f"web route(s) mounted more than once: {duplicated}"
