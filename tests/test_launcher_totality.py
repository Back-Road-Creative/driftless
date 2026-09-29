"""Launcher totality: every technique is either launchable or says why not,
and every artifact kind is either producible or says why not — walked as a
set-equality property over the whole catalog, not sampled.

``tests/test_technique_definitions.py`` already pins that a routed technique
must raise its ``assistance_mode`` above ``GUIDE``. This module pins the other
half: EVERY unrouted technique must carry a documented reason, and the two
groups partition ``TT_CATALOG`` exactly — so a technique cannot silently sit
in neither (an assistant nobody built and nobody explained why not) nor in
both (a route that never got promoted out of ``GUIDE_ONLY_REASONS``).

The same shape is asserted for artifacts: ``ARTIFACT_KINDS`` against
``wizard.cli.producible_kinds()`` and ``UNTRACKED_REASONS``.
"""

from __future__ import annotations

from driftless.api.app import app
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.reasons import (
    GUIDE_ONLY_REASONS,
    UNTRACKED_REASONS,
    GuideOnlyKind,
    Reason,
    UntrackedKind,
)
from driftless.pmbok.tt import TT_CATALOG
from driftless.pmbok.worksheets import WORKSHEETS
from driftless.wizard.cli import producible_kinds
from test_web_routes_not_shadowed import _included, _leaves, _shape


def test_every_technique_is_routed_or_has_a_guide_only_reason() -> None:
    routed = set(ASSISTANT_ROUTES)
    guide_only = set(GUIDE_ONLY_REASONS)
    assert routed.isdisjoint(guide_only), routed & guide_only
    assert routed | guide_only == TT_CATALOG, (
        f"missing: {sorted(TT_CATALOG - routed - guide_only)}, "
        f"extra: {sorted((routed | guide_only) - TT_CATALOG)}"
    )


def test_every_routed_technique_s_page_is_actually_mounted() -> None:
    """``ASSISTANT_ROUTES`` promises a launch address for a routed technique;
    this walks the LIVE app's route table (the same shape
    ``test_web_routes_not_shadowed`` and ``test_web_csrf`` already normalise
    every other page against) and asserts every promised address is really
    served — so a route named in the model but never wired into
    ``api.assembly.mount_web`` fails here, not on the page a reader clicks
    that route's launch link from."""
    mounted = {
        _shape(str(getattr(leaf, "path", "")))
        for route in app.routes
        for child in (_included(route) or ())
        for leaf in _leaves(child)
        if "GET" in (getattr(leaf, "methods", None) or ())
    }
    routed_shapes = {_shape(template) for template in ASSISTANT_ROUTES.values()}
    missing = routed_shapes - mounted
    assert not missing, (
        f"ASSISTANT_ROUTES promises {sorted(missing)}, but no mounted GET route matches — "
        "the router was never included in api.assembly.mount_web"
    )


def test_no_guide_only_reason_outlives_a_shipped_route() -> None:
    """The mirror check: a technique that later ships a route must be removed
    from ``GUIDE_ONLY_REASONS``, not left to explain a launcher that exists."""
    stale = set(GUIDE_ONLY_REASONS) & set(ASSISTANT_ROUTES)
    assert not stale, f"{sorted(stale)} have a route but are still in GUIDE_ONLY_REASONS"


def test_no_guide_only_reason_offers_a_worksheet_that_already_shipped() -> None:
    """The third mirror check, over ``WORKSHEETS`` instead of ``ASSISTANT_ROUTES``.

    ``NOT_YET_BUILT`` covers a worksheet OR a calculator (see its own docstring),
    so a worksheet shipping only falsifies the entries that offered a WORKSHEET.
    A technique whose reason offers a calculator keeps it honestly after its sheet
    ships -- the sheet is not the calculator, and flattening the two to silence
    this walk would assert nothing further is owed when something is. ``/techniques/{slug}``
    prints ``reason.why`` verbatim after "Guide only — " (``web.techniques.
    support_tier``), so a stale entry here is a page telling a reader a worksheet
    could be built for the one technique a worksheet WAS built for. Walked over
    the registry rather than asserted of one key, so the next worksheet to ship
    fails here until its reason is moved off ``NOT_YET_BUILT`` too.
    """
    with_sheets = sorted(set(WORKSHEETS) & set(GUIDE_ONLY_REASONS))
    assert with_sheets, "vacuous walk: no guide-only technique has a worksheet"
    stale = [
        key
        for key in with_sheets
        if GUIDE_ONLY_REASONS[key].kind is GuideOnlyKind.NOT_YET_BUILT
        and "worksheet" in GUIDE_ONLY_REASONS[key].why.lower()
    ]
    assert not stale, (
        f"{stale} have a worksheet in WORKSHEETS but their guide-only reason still "
        "offers one as unbuilt"
    )


def test_every_guide_only_reason_names_a_real_technique_kind_and_sentence() -> None:
    for key, reason in sorted(GUIDE_ONLY_REASONS.items()):
        assert key in TT_CATALOG, f"{key} has a guide-only reason but is not a technique"
        assert isinstance(reason, Reason)
        assert isinstance(reason.kind, GuideOnlyKind), key
        assert reason.why.strip(), f"{key} has a guide-only reason with no sentence"


def test_every_artifact_kind_is_producible_or_has_an_untracked_reason() -> None:
    """``producible_kinds()`` also names ``status_report`` — a wizard form with
    no ``ARTIFACT_KINDS`` member of its own (a pre-existing gap outside this
    unit's scope) — so the property checked here is containment, not the
    stronger set equality ``test_every_untracked_reason_names_a_real_artifact_
    kind_and_sentence`` already gives the other direction: every
    ``ARTIFACT_KINDS`` member is producible or explained, and the two never
    overlap."""
    producible = frozenset(producible_kinds())
    untracked = set(UNTRACKED_REASONS)
    assert producible.isdisjoint(untracked), producible & untracked
    missing = ARTIFACT_KINDS - producible - untracked
    assert not missing, f"no producer and no untracked reason: {sorted(missing)}"


def test_no_untracked_reason_outlives_a_shipped_producer() -> None:
    """The mirror check: an artifact kind that later gains a wizard producer
    must be removed from ``UNTRACKED_REASONS``, not left to explain a form
    that now exists."""
    stale = set(UNTRACKED_REASONS) & frozenset(producible_kinds())
    assert not stale, f"{sorted(stale)} are producible but are still in UNTRACKED_REASONS"


def test_every_untracked_reason_names_a_real_artifact_kind_and_sentence() -> None:
    for key, reason in sorted(UNTRACKED_REASONS.items()):
        assert key in ARTIFACT_KINDS, f"{key} has an untracked reason but is not an artifact kind"
        assert isinstance(reason, Reason)
        assert isinstance(reason.kind, UntrackedKind), key
        assert reason.why.strip(), f"{key} has an untracked reason with no sentence"
