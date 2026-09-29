"""``OPERATIONS.md``'s public-path list stays honest against the gate that actually decides.

The same rot has already bitten this repo twice for two different lists: the
``/health`` prose stayed green through a behaviour change until
``tests/test_docs_health_truthfulness.py`` pinned it, and the request-log field
list "was stale by one field the moment ``request_id`` was added, and nothing
said so" (``tests/test_api_logging.py``). Nothing did the same job for the
*public-path* list — a hand-maintained bulleted list an operator reads to learn
what answers without a credential, sitting next to a predicate
(:func:`driftless.api.secure.is_open_path`) that alone decides it. The two can
drift apart silently in either direction: the doc could grow a path the gate
never admits (an operator would wrongly believe something is reachable
uncredentialed), or the gate could start admitting a path the doc never named
(an operator reading the doc would not know to expect it, or to worry about it).
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.routing import BaseRoute

from driftless.api.app import app
from driftless.api.secure import is_open_path

SERVICE = Path(__file__).resolve().parents[1]


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    """``route`` itself, or the routes an ``include_router``/``mount`` call nested
    under it — the same shape :mod:`tests.test_openapi_contract` and
    :func:`driftless.api.secure._leaves` already walk, re-derived here (not
    imported) so this walk is independent of anything either could get wrong."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def _live_open_paths() -> frozenset[str]:
    live = frozenset(
        leaf.path for route in app.routes for leaf in _leaves(route) if hasattr(leaf, "path")
    )
    assert live, "the route walk found no route at all -- vacuous, not passing"
    opened = frozenset(path for path in live if is_open_path(path))
    assert opened, "vacuous walk: the live route table admits no open path at all"
    return opened


def _documented_public_paths() -> frozenset[str]:
    """Every path-shaped token named in an actual bullet of the *Public paths*
    list, never off the surrounding prose. That prose deliberately names paths
    the gate does NOT admit as counter-examples — ``/health/ready``,
    ``/login-admin``, ``/static-export`` — so pulling from the whole section
    would poison this set with paths that are supposed to stay gated. Scoped to
    ``- ``-prefixed lines only, so a reword of the explanatory prose around the
    list cannot flip this test either way; only the list itself can.
    """
    text = (SERVICE / "OPERATIONS.md").read_text(encoding="utf-8")
    heading, _, rest = text.partition("\n### Public paths")
    # Named rather than indexed: a renamed heading is the likeliest way this section
    # moves out from under the test, and an IndexError on [1] would report that as a
    # crash rather than as what it is -- the list this test exists to read is gone.
    assert rest, "OPERATIONS.md has no '### Public paths' heading -- the list moved or was renamed"
    section = rest.split("\n### ")[0]
    bullets = "\n".join(line for line in section.splitlines() if line.startswith("- "))
    paths = frozenset(re.findall(r"/[\w][\w/-]*", bullets))
    assert paths, "the Public paths bullet list named no path at all -- vacuous, not passing"
    return paths


def test_every_open_path_is_named_in_operations_md() -> None:
    documented = _documented_public_paths()
    for path in _live_open_paths():
        assert path in documented, (
            f"{path!r} answers without a credential (driftless.api.secure.is_open_path) "
            "but OPERATIONS.md's Public paths list never names it -- an operator reading "
            "that list would not know to expect it"
        )


def test_no_documented_public_path_is_actually_gated() -> None:
    for path in _documented_public_paths():
        assert is_open_path(path), (
            f"OPERATIONS.md's Public paths list names {path!r} as public, but "
            "driftless.api.secure.is_open_path refuses it without a credential -- "
            "the doc is claiming an allowance the gate does not grant"
        )
