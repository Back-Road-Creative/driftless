"""The one shared ``?as_of=`` resolution every page router used to redefine.

Each ``create_*_router(default_as_of)`` factory takes either a fixed ``date`` (a
pinned test render) or a per-request callable (``date.today``, the served app) --
that seam stays here, unchanged, per router instance. :func:`as_of_dependency`
builds the resolver ONCE per factory call and hands back a plain function of the
posted-or-queried value: a callable default is invoked only when the caller sent
none, and freshly per request, never once at mount time and reused for the life
of the process (``tests/test_web_home.py``'s
``test_the_default_as_of_is_resolved_once_per_request``).

The returned function's OWN parameter -- ``as_of: date | None = None`` -- is what
FastAPI reads to build the query parameter, so wiring it through ``Depends()``
reproduces the exact ``?as_of=`` name, type and OpenAPI presence every route
already had. A route that already parsed ``as_of`` off a POSTed form (the wizard
and status-edit flows) calls the same function directly instead: one fallback
rule, never copied for the two calling conventions that need it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date


def as_of_dependency(default_as_of: date | Callable[[], date]) -> Callable[[date | None], date]:
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    def resolve_as_of(as_of: date | None = None) -> date:
        return as_of or resolve()

    return resolve_as_of
