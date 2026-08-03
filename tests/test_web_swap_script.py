"""The data-swap script and the forms that opt into it (audit F-G5, F-G17).

``static/driftless.js`` promised a fragment swap keyed on ``data-target`` while no
template set one, so every background submit fell back to ``document.open()`` /
``document.write()``: focus destroyed, nothing announced, no history entry — and a
fetch that failed outright (offline, DNS) rejected with no ``.catch``, leaving the
page byte-identical with no word to anyone. The suite runs no browser and no Node,
so the contract is pinned from both ends instead: the shipped source must carry the
fragment-extraction, focus, announce and failure paths, and every rendered form
that names a target must name a fragment really on its own page — so the claim in
the script is one the templates use.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

import test_web_pages
from test_web_pages import Q

# The seeded https store, reused as is (assigned, not imported: a test's own parameter
# must not read as a redefined import) — the idiom test_web_map_without_colour uses.
client, db = test_web_pages.client, test_web_pages.db

_SCRIPT = (Path(__file__).resolve().parents[1] / "driftless/web/static/driftless.js").read_text()


def test_the_script_lifts_the_named_fragment_out_of_the_full_response() -> None:
    """The server answers a swap POST with the FULL re-rendered page (the same 303 a
    no-JS submit follows), so dumping ``response.text()`` into the target nests one
    document inside another. The fresh copy of the target must be parsed out."""
    assert "DOMParser" in _SCRIPT, "the response must be parsed, never injected wholesale"
    assert "parseFromString" in _SCRIPT


def test_a_swap_moves_focus_and_announces_politely() -> None:
    """The Save button the reader pressed is destroyed by the swap; without a focus
    move and a live region, a keyboard or screen-reader user is stranded on a control
    that no longer exists and hears nothing happen."""
    assert ".focus()" in _SCRIPT, "focus must move to the swapped region"
    assert 'setAttribute("tabindex", "-1")' in _SCRIPT, "a region takes focus only with tabindex"
    assert '"status"' in _SCRIPT, "a role=status live region announces the outcome"


def test_a_failed_fetch_is_surfaced_not_swallowed() -> None:
    """Offline, the promise rejected unseen and the sign-off looked saved."""
    assert re.search(r"\.catch\(\s*function", _SCRIPT), "a fetch rejection must be handled"
    assert "NOT saved" in _SCRIPT, "and the failure must be stated, not merely caught"


def test_every_threat_board_swap_form_names_the_board_it_swaps(client: TestClient) -> None:
    """F-G17: the sign-off forms swap the board itself, and that id is on the page."""
    page = client.get(f"/threats{Q}").text
    forms = re.findall(r"<form[^>]*data-swap[^>]*>", page)
    assert forms, "the threat board renders data-swap sign-off forms"
    for form in forms:
        assert 'data-target="#threat-board"' in form, form
    assert 'id="threat-board"' in page


def test_the_weekly_status_swap_form_names_its_fragment(client: TestClient) -> None:
    """Saving a snapshot changes the percent line, the trend and both charts — the
    whole of ``#main`` — so that is the fragment the form names."""
    page = client.get(f"/projects/1/status{Q}").text
    found = re.search(r"<form[^>]*data-swap[^>]*>", page)
    assert found is not None, "the weekly-status page renders its data-swap form"
    assert 'data-target="#main"' in found.group(0), found.group(0)
    assert 'id="main"' in page
