"""The resource routes register onto an app they are HANDED, not onto a global.

``reads``, ``writes`` and ``creates`` (now in :mod:`driftless.api.crud`) closed over
the module-level ``app``, and their
seventy-four calls ran at module scope against it. That is what makes a second app
impossible: importing the module is the registration, so there is no way to build a
fresh one and no way to test a variation of it.

They take the app as a parameter now, and the calls live inside
``register_resources(app)`` in :mod:`driftless.api.resources`, which the factory calls
once. This file pins the
property that makes the coming factory possible at all — the same registration run
against a fresh :class:`fastapi.FastAPI` produces the same routes there, and produces
nothing on the singleton.
"""

from __future__ import annotations

from collections import Counter

from fastapi import FastAPI
from fastapi.routing import APIRoute

from driftless.api.app import app
from driftless.api.resources import register_resources


def _keys(routes: object) -> Counter[tuple[str, tuple[str, ...]]]:
    """(path, methods) for every ``APIRoute``, as a multiset — a duplicate stays visible."""
    return Counter(
        (route.path, tuple(sorted(route.methods or ())))
        for route in routes  # type: ignore[attr-defined]
        if isinstance(route, APIRoute)
    )


def test_the_same_registration_runs_against_a_fresh_app() -> None:
    """What the singleton got at import is exactly what a second app gets on demand."""
    fresh = FastAPI()
    register_resources(fresh)
    made = _keys(fresh.routes)

    assert made, "the walk registered nothing at all -- vacuous-pass guard tripped"
    assert made - _keys(app.routes) == Counter(), "a resource route the singleton lacks"


def test_registering_elsewhere_leaves_the_singleton_alone() -> None:
    """The whole point of the parameter: no helper reaches for the module global."""
    before = _keys(app.routes)
    register_resources(FastAPI())

    assert _keys(app.routes) == before, "a registration landed on the global app"
