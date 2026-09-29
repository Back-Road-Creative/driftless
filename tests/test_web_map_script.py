"""``static/map.js``, the method map's interaction layer (M.4).

Modelled on ``test_web_swap_script.py``: no browser and no Node run in this
suite, so the contract is pinned from both ends instead — the shipped source
must carry no network call and stay under its size cap, every page that loads
it must load it (and nothing else) from ``/static``, and every ``data-*`` name
the script reads must be a name the template really emits, so the script's own
claim about the DOM is one the page keeps.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from driftless.pmbok.graph import GRAPH
import test_web_pages
from test_web_pages import AS_OF

client, db = test_web_pages.client, test_web_pages.db
Q = f"as_of={AS_OF.isoformat()}"

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = (_ROOT / "driftless/web/static/map.js").read_text()
_STYLESHEET = (_ROOT / "driftless/web/static/driftless.css").read_text()
_TEMPLATES = _ROOT / "driftless/web/templates"

# The line cap the plan pins (M.4): never restate the measured size, only the ceiling.
_MAX_MAP_JS_BYTES = 8000

_FORBIDDEN = ("fetch(", "XMLHttpRequest", "WebSocket", "eval(", "innerHTML")


def test_the_script_makes_no_network_call_and_stores_nothing() -> None:
    offences = [name for name in _FORBIDDEN if name in _SCRIPT]
    assert not offences, f"map.js names {offences} — it may only toggle what the page already has"


def test_the_script_stays_under_its_size_cap() -> None:
    size = len(_SCRIPT.encode())
    assert size < _MAX_MAP_JS_BYTES, f"map.js is {size} bytes, want under {_MAX_MAP_JS_BYTES}"


_SCRIPT_SRC = re.compile(r'<script[^>]*\bsrc="([^"]+)"')


def test_every_script_tag_loads_from_static_and_nowhere_else() -> None:
    for template in (_TEMPLATES / "base.html", _TEMPLATES / "method_map.html"):
        for src in _SCRIPT_SRC.findall(template.read_text()):
            assert src.startswith("/static/"), f"{template.name} loads a script from {src!r}"


_DATA_LITERAL = re.compile(r"\bdata-([a-z-]+)")
_DATASET_PROP = re.compile(r"\.dataset\.([a-zA-Z]+)")
_DIMS_ARRAY = re.compile(r"var dims = \[([^\]]+)\]")


def _kebab(name: str) -> str:
    return re.sub(r"([A-Z])", r"-\1", name).lower()


def test_every_data_attribute_the_script_reads_is_one_the_template_emits(
    client: TestClient,
) -> None:
    names = set(_DATA_LITERAL.findall(_SCRIPT)) | {
        _kebab(prop) for prop in _DATASET_PROP.findall(_SCRIPT)
    }
    dims_array = _DIMS_ARRAY.search(_SCRIPT)
    assert dims_array, "map.js names no dims array, but reads dataset[dim] off one"
    names |= set(re.findall(r'"([a-z]+)"', dims_array.group(1)))
    assert names, "vacuous: the script reads no data-* attribute at all"
    body = client.get(f"/map?{Q}").text
    missing = [name for name in sorted(names) if f'data-{name}="' not in body]
    assert not missing, f"map.js reads {missing}, which /map never renders"


#: The one name three files have to agree on. The drawing's legibility floor is a
#: per-render number (each drawing's own native width), so it cannot be a static class
#: — and a page may not declare a layout property in its own markup either
#: (tests/test_web_responsive.py). It travels as a custom property instead: the
#: template sets the number, map.css turns it into the real ``min-width``, and map.js
#: reads it back as the floor no zoom step may cross.
_FLOOR = "--map-floor"


def test_the_zoom_floor_is_one_custom_property_all_three_files_agree_on() -> None:
    """Rename it in one file alone and nothing breaks loudly: the CSS falls back to no
    floor at all and a zoom-out silently shrinks labels past legible, which is the exact
    defect the floor exists to prevent. So the name is pinned from all three ends."""
    template = (_TEMPLATES / "method_map.html").read_text()
    map_css = (_ROOT / "driftless/web/static/map.css").read_text()

    assert f'style="{_FLOOR}:' in template, (
        f"method_map.html no longer hands the drawing's own width over as {_FLOOR}"
    )
    assert f"min-width: var({_FLOOR}" in map_css, (
        f"map.css no longer turns {_FLOOR} into .map-svg's min-width, so there is no floor"
    )
    assert f'getPropertyValue("{_FLOOR}")' in _SCRIPT, (
        f"map.js no longer reads {_FLOOR}, so every zoom step floors at 0"
    )


def test_the_reduced_motion_query_turns_off_the_maps_transition_and_glow() -> None:
    match = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{([^}]*\})", _STYLESHEET)
    assert match, "driftless.css declares no prefers-reduced-motion block"
    assert "transition: none" in match.group(1)


def test_every_node_gets_exactly_one_hidden_panel(client: TestClient) -> None:
    """Panels are pared to the drawn slice (page weight); ``view=all`` is the
    one read that draws every node, so it is the one read checked here."""
    body = client.get(f"/map?view=all&{Q}").text
    for node in GRAPH.nodes:
        found = re.findall(rf'data-panel-for="{re.escape(node.id)}"', body)
        assert len(found) == 1, f"{node.id}: {len(found)} panels, want exactly one"


#: Every listener the script binds, in source order, so a ``preventDefault()`` can be
#: attributed to the event it cancels without running a browser.
_LISTENER = re.compile(r'addEventListener\("(\w+)"')


def _cancelled_events() -> list[str]:
    """The event type of the listener each ``preventDefault()`` call sits inside."""
    binds = [(m.start(), m.group(1)) for m in _LISTENER.finditer(_SCRIPT)]
    types = []
    for call in re.finditer(r"preventDefault\(", _SCRIPT):
        before = [kind for start, kind in binds if start < call.start()]
        types.append(before[-1] if before else "<none>")
    return types


def test_the_only_event_the_map_cancels_is_the_key_that_pins() -> None:
    """A shape IS a link -- the same ``<a href>`` the "Open X" line below the drawing
    carries -- so cancelling its click made the picture a dead end: no plain click ever
    reached a page, and Ctrl/Cmd/Shift/middle-click were swallowed with it, which is
    every gesture a reader has for "open this in a new tab". Nothing the drawing does
    may cancel a click again; the one event the map is allowed to take from the browser
    is the key that pins, which must stop the page scrolling under the reader."""
    cancelled = _cancelled_events()
    assert cancelled, "vacuous: the script cancels no event at all"
    assert set(cancelled) == {"keydown"}, (
        f"map.js cancels {sorted(set(cancelled))}; only the pin key may be cancelled"
    )


def _keydown_body() -> str:
    parts = _SCRIPT.split('document.addEventListener("keydown"', 1)
    assert len(parts) == 2, "map.js binds no keydown handler"
    return parts[1].split("\n  });", 1)[0]


def test_space_pins_the_shape_under_focus() -> None:
    """Pinning was the only thing a click did, and a click now belongs to the link, so
    pinning needs a key of its own or the per-node panel becomes unreachable."""
    body = _keydown_body()
    assert 'event.key === " "' in body, "Space must be the key that pins the focused shape"
    assert "preventDefault" in body, "and it must stop the page scrolling as it pins"
    assert "pin(" in body, "and it must actually pin"


def test_escape_still_backs_out_of_a_slice() -> None:
    """The key that clears a pin predates the one that sets it; adding Space must not
    quietly cost the map its way back to the overview."""
    body = _keydown_body()
    assert 'event.key === "Escape"' in body
    assert "window.location.assign(overviewHref)" in body


_NODE_GROUP = re.compile(r'<g class="node[^"]*"[^>]*>')
_NODE_ANCHOR = re.compile(r'<g class="node[^"]*"[^>]*>\s*<a href="[^"]+"')


def test_every_shape_the_map_draws_is_a_real_link(client: TestClient) -> None:
    """The other end of the same contract: letting a click navigate is only right while
    every shape really is wrapped in its own ``<a href>``."""
    body = client.get(f"/map?{Q}").text
    groups = _NODE_GROUP.findall(body)
    assert groups, "vacuous: /map drew no node at all"
    assert len(_NODE_ANCHOR.findall(body)) == len(groups), (
        f"{len(groups)} shapes drawn, {len(_NODE_ANCHOR.findall(body))} of them links"
    )


def _function_body(name: str) -> str:
    match = re.search(rf"\n  function {name}\([^)]*\) \{{\n(.*?)\n  \}}", _SCRIPT, re.S)
    assert match, f"map.js declares no {name}()"
    return match.group(1)


def test_hovering_or_focusing_a_shape_opens_its_panel() -> None:
    """``setPanel`` used to be reachable only from ``pin()``, Escape and Reset, and
    pinning is now a key. A reader with a mouse and no keyboard could therefore reach
    a node's panel by no route at all: hover lit the ties but opened nothing, and a
    click opens the page. The panel follows the hovered or focused shape for the same
    reason the lighting does, so both halves of it are mouse-reachable."""
    for name in ("hoverIn", "hoverOut"):
        body = _function_body(name)
        assert "setPanel(" in body, (
            f"{name}() lights the ties but never opens or closes the panel, "
            "so a mouse-only reader has no way to one"
        )


def test_a_hover_never_yanks_a_pinned_panel_away() -> None:
    """Transient and pinned share one panel, so the pin has to win: without the guard,
    moving the mouse across the drawing would swap the panel a reader deliberately
    pinned for whatever shape the pointer happened to cross."""
    for name in ("hoverIn", "hoverOut"):
        assert "pinned" in _function_body(name), f"{name}() no longer defers to a pin"


def test_the_script_restores_filter_state_from_the_url_before_the_first_render() -> None:
    """A filtered map is a shareable URL (MP15): the query string must be read back
    into the filter controls before applyFilters first runs, or a reload of a shared
    link would show the unfiltered map for one paint."""
    assert "URLSearchParams" in _SCRIPT, "map.js must read filter state from the URL"
    assert "restoreFromURL();\n  applyFilters();" in _SCRIPT, (
        "the URL must be read into the filter controls before applyFilters first runs"
    )


def test_a_filter_change_writes_its_state_back_into_the_url() -> None:
    """The other half of MP15: as a chip, the search box or flow-only changes, the
    URL must follow, or a reader who copies the address bar gets the wrong filter."""
    assert "history.replaceState" in _SCRIPT, (
        "a filter change must update the URL without a navigation"
    )
    body = _function_body("applyFilters")
    assert "syncURL()" in body, "applyFilters must push its own state into the URL"


def test_the_node_group_carries_its_own_label_beside_data_kind() -> None:
    """MP28: search must match the node's own name, not the ``<title>`` the ``<g>``
    also carries (``label — kind, classification``), which lights every node whose
    kind or wash word happens to match the search term. ``data-label`` sits on the
    same element as ``data-kind`` -- ``attrOf`` reads ``kind`` off the ``<g>``, not
    off the inner ``.node-shape``, and search must follow that same element."""
    template = (_TEMPLATES / "method_map.html").read_text()
    tag = re.search(r'<g class="node[^"]*"[^>]*>', template)
    assert tag, "method_map.html renders no node <g>"
    assert "data-label=" in tag.group(0), "data-label must sit on the node <g>, beside data-kind"


def test_search_matches_the_label_not_the_titles_kind_or_state_word() -> None:
    """The bug: ``node.textContent`` includes the ``<title>`` (``"{label} —
    {kind}{classification}"``), so searching "process" used to light every node
    of that kind."""
    body = _function_body("applyFilters")
    assert "node.dataset.label" in body, (
        "applyFilters must match against data-label, not the whole node's textContent"
    )
    assert "node.textContent" not in body, (
        "applyFilters must not fall back to node.textContent, which also matches the title"
    )


def test_a_filter_change_updates_the_visible_count_text() -> None:
    """MP16: applyFilters computes visibleCount and must not let the server-rendered
    count sentence go stale the moment a filter is touched."""
    assert ".map-count" in _SCRIPT, "map.js must locate the existing count element by its class"
    body = _function_body("applyFilters")
    assert "textContent" in body, "applyFilters must write the new count back into the DOM"
    assert "visibleCount" in body and "visibleEdges" in body, (
        "the count sentence must reflect both the visible nodes and their visible ties"
    )
