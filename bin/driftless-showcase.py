#!/usr/bin/env python3
"""Export the deterministic demo pages as a portable, read-only static showcase."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import driftless
from driftless import __version__
from driftless.demo.data import ANCHOR
from driftless.web.method_map import WHOLE_GRAPH

#: Retired as a written file: the clobber guard now reads ``manifest.json``'s
#: ``kind`` instead. Kept as a name so a leftover marker from an older run is
#: still recognizable as this tool's own residue when a test builds one.
MARKER = ".driftless-static-showcase"
KIND = "driftless-static-showcase"
DROP_PAGES = frozenset({"login.html"})
#: Path templates the router mounts that the showcase must never publish, and why --
#: a reviewer reading this list should never have to open the router and ask "on
#: purpose?" Every GET page route NOT named here is exported (tests/test_showcase_
#: route_coverage.py asserts that split matches the live router on every run).
EXCLUDED_ROUTES: dict[str, str] = {
    "/login": "renders the sign-in form; the page is dropped from the bundle entirely "
    "(DROP_PAGES), so it is never a link target either",
}
#: Shares its ``{department_id}`` with the bare detail page below it, but narrates
#: only the one department the demo's story is told through -- same reason
#: ``project_id`` stays singular in :func:`render_showcase`.
SINGLE_DEPARTMENT_ASSIST = "/org/departments/{department_id}/assist"
#: The only ``{project_id}`` pages the dashboard itself links to (every rollup row's
#: hub, and the rail's "Fix this" on ``status``/``wizard``) -- so, unlike the deep
#: flow/RAID/assist walkthrough told through one chosen project, these three ship for
#: every project a dashboard reader can actually click to.
ALL_PROJECT_PAGES = frozenset(
    {"/projects/{project_id}/hub", "/projects/{project_id}/status", "/projects/{project_id}/wizard"}
)
SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
FORM = re.compile(r"<form\b[^>]*>.*?</form>", re.IGNORECASE | re.DOTALL)
# The method map's filter strip is driven by static/map.js alone; with every script
# stripped it would be a row of dead checkboxes and a Reset button that resets nothing.
MAP_FILTERS = re.compile(r'<div class="map-filters">.*?</div>', re.DOTALL)
# Same reasoning for the zoom group: four buttons whose only handler lives in the
# app's static/map.js, which this bundle does not ship. ``showcase-map.js`` -- the
# one script it does ship -- carries no ``data-zoom`` at all, so exported as-is
# the group is a Fit button that fits nothing. It sat in the bundle unnoticed
# because the committed export predated the zoom controls (PR 450) by several
# releases; the first regen after v0.6.0 surfaced all four against headlessmode's
# inertness contract. ``[^>]*`` because this opening tag carries role and
# aria-label, unlike the filter strip's bare class.
MAP_ZOOM = re.compile(r'<div class="map-zoom"[^>]*>.*?</div>', re.DOTALL)
#: The capacity heatmap exports one horizon (its default), so the other three ``?weeks=``
#: links on the picker would point at a file this bundle never writes. Stripped rather
#: than multiplied into four files: the read-only export tells one story at one anchor,
#: like the map's dropped view links above.
HEATMAP_PAGE = "org-heatmap.html"
# A data attribute, not a class: it marks the paragraph for this script and styles
# nothing, and the class walker (tests/test_css_classes_have_rules.py) rightly
# refuses a class no stylesheet names.
HEATMAP_HORIZON_PICKER = re.compile(r"<p data-heatmap-horizons>.*?</p>", re.DOTALL)
HEATMAP_HORIZON_COPY = (
    "<p data-heatmap-horizons>Shown at its default horizon. This export draws that "
    "one span; the other horizons a live reader can dial in from the address bar are a "
    "read of the live product, not a page in this bundle.</p>"
)
LOGIN_LINK = re.compile(
    r"<a\b[^>]*href=(?P<q>[\"'])/login(?:\?[^\"']*)?(?P=q)[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
#: The masthead's Print control is a progressive-enhancement reload -- live, driftless.js
#: would intercept the click and call ``window.print()``; the showcase ships no scripts
#: at all (SCRIPT strips every ``<script>``), so left in place it is a second link to the
#: page's own file, a dead reload the map-page convention test catches by name. Native
#: browser printing (Ctrl/Cmd-P) still works with no control on the page, so this one is
#: dropped rather than rewired, the same call as the map's filter/zoom controls above.
PRINT_LINK = re.compile(r'<a\b[^>]*\bid="print-link"[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)
#: Quote-agnostic: a single-quoted ``href='/x'`` is as real as a double-quoted one, and
#: the app's own templates are not pinned to one style. Group 1 is the quote character
#: itself, kept only so the closing quote must match the opening one; the URL is the
#: named group ``url``, so every caller reads ``match.group("url")``.
HREF = re.compile(r"href=([\"'])(?P<url>[^\"']*)\1")
ANCHOR_TAG = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
CSS_LINK = re.compile(r"<link\b[^>]*href=(?P<q>[\"'])/static/(?P<name>[\w.-]+\.css)(?P=q)[^>]*/?>")
#: The web app manifest makes the live site installable; a static export has no
#: server behind it to answer ``/static/manifest.webmanifest``, and nothing here
#: is worth installing anyway (a fixed demo, not an app to reopen), so the link
#: is dropped rather than shipped as a sibling asset the way CSS is.
MANIFEST_LINK = re.compile(r'<link\b[^>]*rel="manifest"[^>]*/?>')
SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)
# An <svg> carrying aria-label but no role -- assistive tech may ignore an
# aria-label with no role to hang it on. Matched on the opening tag only, so an
# <svg> already aria-hidden (an inner legend swatch) or already role="img" is
# untouched; a live-page defect this export otherwise carries through unfixed.
# The role depends on what the SVG holds: one with a link inside is not one
# image -- role="img" prunes its subtree, so the link becomes unreachable and
# axe reports "interactive controls must not be nested" (headlessmode #352,
# 2026-09-05) -- it is a named group. A chart with nothing to click is an image.
SVG_HAS_LINK = re.compile(r"<a\b", re.IGNORECASE)


def _name_svg(match: re.Match[str]) -> str:
    block = match.group(0)
    role = "group" if SVG_HAS_LINK.search(block) else "img"
    return SVG_NEEDS_ROLE.sub(rf'<svg\1 role="{role}">', block, count=1)


SVG_NEEDS_ROLE = re.compile(
    r'<svg\b(?![^>]*\brole=")(?![^>]*\baria-hidden="true")([^>]*\baria-label="[^>]*)>',
    re.IGNORECASE,
)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

#: The pages that carry an interaction layer, and the one script they carry: the process
#: overview ``/map`` opens on, and the whole graph ``?view=all`` draws. The second needs a
#: name of its own because ``snapshot_name`` keeps the path and drops the query -- both
#: reads are ``/map``, so both would otherwise be written to the same file.
MAP_PAGE = "map.html"
MAP_ALL_PAGE = "map-all.html"
MAP_PAGES = (MAP_PAGE, MAP_ALL_PAGE)
SHOWCASE_SCRIPT = Path(__file__).with_name("showcase-map.js")
MAP_SCRIPT_TAG = f'<script src="{SHOWCASE_SCRIPT.name}" defer></script>'
#: A ``/map?focus=`` address -- "See it on the map" on a process, technique or artifact
#: page, and the two per node on the map pages themselves. The query used to be dropped
#: with the rest, landing every one of them on the process overview, which draws no
#: technique and no artifact and pins nothing; they name :data:`MAP_ALL_PAGE` and the node
#: to open on instead. Read off the unescaped href, since a template writes ``&amp;``.
FOCUS_QUERY = re.compile(r"[?&]focus=(?P<node>[^&#]+)")
#: What a rewritten focus link points at: the node's own entry in the ``<details>`` lists
#: under the drawing -- markup that needs no script, so the link lands somewhere a reader
#: can see whether or not ``showcase-map.js`` runs (it pins the shape when it does).
NODE_ANCHOR = "node-"
#: One list entry per node, found by the ``?focus=`` link it carries; ``method_map.html``
#: emits each on its own line, so the match never has to cross one.
NODE_LIST_ITEM = re.compile(r"<li>(?P<rest>[^\n]*?focus=(?P<node>[^\"&\n]+)\")")
#: A collapsed list is not somewhere a ``#node-`` link can land, so the exhaustive read
#: exports its lists open -- being exhaustive is what that page is for.
NODE_LISTS = ("<details>", "<details open>")
#: A per-node panel's "Open <node>" line once ``_static_anchor`` has flattened it: the
#: node's own name is already the panel's heading, so an inert "Open" reads as a button
#: that does nothing rather than as prose. Dropped only where the link did not survive.
ELEMENT_ID = re.compile(r'\bid="([^"]+)"')
DEAD_OPEN_LINE = re.compile(r'<p><span class="showcase-unavailable">Open [^<]*</span></p>\n?')
#: ``(what the live page says, what the exported page can honestly say)``, applied to
#: both map pages. Copy the export cannot keep is a defect, not a cosmetic: the
#: promises below described the filter strip and the per-node pages the export strips.
#: tests/test_showcase_demo.py asserts each replacement actually lands, so a template
#: rewording reddens the suite rather than silently restoring the false claim.
MAP_COPY: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"Every shape links to its own page;.*?handful of nodes\.", re.DOTALL),
        "Every shape opens its own summary below the map, on click or on Enter, and its "
        "own name shows on hover and on keyboard focus while its ties light up with it. "
        "Every shape still links onward too: its own process, technique or artifact page "
        "is in this export as well.",
    ),
    (
        # Anchored on the opening clause alone, not on the sentence that follows it:
        # that second sentence now glosses "washing" (X04) and rewording it again must
        # not silently un-land this replacement and restore the false promise.
        re.compile(r"<p>Shown without any project's reading\..*?</p>", re.DOTALL),
        "<p>Shown without any project's reading: this export draws the method in theory. "
        "Washing these processes with one project's own progress is a read of the live "
        "product, not a page in this bundle.</p>",
    ),
)
#: The "other reads of this graph" line, written per page: each map page now names a file
#: the bundle really carries, where every ``/map?`` address the live page offers used to
#: flatten to the one the reader was already on.
MAP_VIEWS = re.compile(r'<p class="map-views">.*?</p>', re.DOTALL)
MAP_VIEWS_COPY = {
    MAP_PAGE: '<p class="map-views">The processes in lifecycle order. Open any one below '
    'to see what it touches, or <a href="map-all">show the whole graph</a>: every node '
    "and every tie at once, exported as its own page. Either way, every node and every "
    "tie is listed in full below.</p>",
    MAP_ALL_PAGE: '<p class="map-views">Every node and every tie at once, for exhaustive '
    'reading. <a href="map">Back to the process overview</a>. Every process, technique '
    "and artifact page in this export links here, opening this page on its own node: "
    "that shape and its ties light up, and the node's entry in the lists below, open and "
    "complete with no script running, is where the link lands.</p>",
}


#: The one flow page, so the id it carries is the story project's -- the deep
#: walkthrough (:data:`PROJECT_PAGES` in the test suite) is exported for that one
#: project alone, the same reasoning :data:`SINGLE_DEPARTMENT_ASSIST` and
#: :data:`ALL_PROJECT_PAGES` already carry above.
STORY_HUB = re.compile(r"projects-(\d+)-flow\.html")
#: Every project the dashboard could link a reader to (:data:`ALL_PROJECT_PAGES`
#: ships one hub file per project), so counting these files -- not a store query
#: this module has no session for -- is what "measured, never typed" means here.
PROJECT_HUB = re.compile(r"projects-(\d+)-hub\.html")
#: The hub page's own ``<h1>`` names its project (``project_hub.html``); read off
#: the rendered page instead of threading the name through as a second parameter
#: that could drift from what the export actually contains.
PROJECT_H1 = re.compile(r"<h1>(?P<name>[^<]*)</h1>")
#: Every ``/{slug}.html`` the Method nav cluster mounts (``base.html``'s
#: ``nav-group-method``), in that order -- the demo intro below links each one by
#: name rather than repeating the list a template already owns.
METHOD_PAGES: tuple[tuple[str, str], ...] = (
    ("pmbok", "PMBOK"),
    ("techniques", "Techniques"),
    ("methods", "Methods"),
    ("artifacts", "Artifacts"),
    ("glossary", "Glossary"),
    ("map", "Map"),
)


def _story_project(kept: dict[str, str]) -> tuple[str, str] | None:
    """The id and display name of the one project the demo's deep walkthrough
    tells, read off its own hub page heading -- ``None`` for a bundle that
    carries no project pages at all (a synthetic bundle a test builds)."""
    project_id = next(
        (found.group(1) for name in kept if (found := STORY_HUB.fullmatch(name))), None
    )
    if project_id is None:
        return None
    hub = kept.get(f"projects-{project_id}-hub.html")
    if hub is None:
        return None
    found = PROJECT_H1.search(hub)
    return (project_id, html.unescape(found.group("name"))) if found else None


def _project_count(kept: dict[str, str]) -> int:
    """How many seeded projects the bundle carries, measured off the hub files
    actually in it rather than typed."""
    return len({found.group(1) for name in kept if (found := PROJECT_HUB.fullmatch(name))})


def _demo_intro(project_id: str, project_name: str, project_count: int) -> str:
    """The bundle's front door: its own heading and orientation, before the
    dashboard sample below it -- a reader landing here must be told what a
    fixed demo is and where to go, not shown the product's Dashboard screen
    first and an explanatory box second."""
    plural = "" if project_count == 1 else "s"
    links = "".join(
        f'<a href="{slug}">{label}</a>{"" if slug == METHOD_PAGES[-1][0] else ", "}'
        for slug, label in METHOD_PAGES
    )
    return (
        '<section class="showcase-intro" aria-label="About this demo">'
        "<h1>About this demo</h1>"
        f"<p>This is a fixed demo: {project_count} seeded project{plural}, frozen at the "
        f'as-of date above and browsed read-only. One of them, <a href="projects-{project_id}-hub">'
        f"<strong>{html.escape(project_name)}</strong></a>, tells the full story -- its flow, "
        "RAID log, status history and every PMBOK assistant page are exported; the rest "
        "ship only the dashboard, hub, status and wizard pages every reader can already "
        "click to.</p>"
        f"<p>The method behind it is exported too: {links}.</p>"
        "<p>The screen below is a live sample from the export.</p>"
        "</section>"
    )


#: Marks a link the export could not carry (see :func:`_static_anchor`); the note
#: below explains, once per page, rather than leaving the greyed-out span to speak
#: for itself.
UNAVAILABLE_NOTE_CLASS = "showcase-unavailable"
UNAVAILABLE_NOTE = (
    '<p class="showcase-note">A greyed-out label above marks a link this fixed demo does '
    "not ship: only the story project's pages go this deep, and an action a live reader "
    "could take here (signing in, applying a technique) is disabled in a read-only "
    "export.</p>"
)


def _static_css(name: str = "driftless.css") -> str:
    """A ``web/static`` stylesheet's own bytes, so an exported page can carry it
    inline rather than a ``<link>`` the static bundle has no server to answer --
    every ``/static/*.css`` link a page carries, not only the shared sheet (the
    method map's ``map.css`` was left as a dead link, so the export lost its
    legend, its node colours and its controls).

    Comments are stripped: they never render, and a maintainer's prose in one is free
    to say "<button>" or "map.js" without tripping the bundle's own checks for a real
    interactive control or a real script reference.
    """
    css = Path(driftless.__file__).resolve().parent / "web" / "static" / name
    return CSS_COMMENT.sub("", css.read_text(encoding="utf-8"))


#: Every ``/static/*.css`` a template links, written once as a sibling file rather
#: than inlined per page (69 ``<style>`` blocks, 475,994 bytes in the shipped
#: bundle otherwise). Read by whoever writes the bundle the same way ``write_bundle``
#: already reads ``SHOWCASE_SCRIPT`` -- a module-level seam, not a parameter, so this
#: file stays the one place the sibling-css list is declared. ``print.css`` joined
#: base.html's ``<head>`` alongside the shared sheet, so it ships the same way --
#: CSS_LINK already rewrites its ``<link>`` generically; leaving it off this tuple
#: was the gap (the rewritten link pointed at a sibling file the bundle never wrote).
CSS_ASSET_NAMES = ("driftless.css", "map.css", "print.css")


def css_assets() -> dict[str, str]:
    """Every stylesheet an exported page may link, keyed by the sibling file name
    it is written under."""
    return {name: _static_css(name) for name in CSS_ASSET_NAMES}


def _rewrite_css_link(match: re.Match[str]) -> str:
    """Point a ``<link>`` at its sibling stylesheet file instead of embedding it;
    the site's CSP allows ``'self'`` stylesheets, so a sibling file is servable
    where the app's own ``/static/*.css`` route is not."""
    return f'<link rel="stylesheet" href="{match.group("name")}">'


def _snapshot_module() -> ModuleType:
    path = Path(__file__).with_name("driftless-snapshot-pages.py")
    spec = importlib.util.spec_from_file_location("driftless_snapshot_pages", path)
    if spec is None or spec.loader is None:  # pragma: no cover - interpreter failure
        raise SystemExit(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _param_name(template: str) -> str | None:
    """The one ``{name}`` a route's path template carries, or ``None`` for none."""
    if "{" not in template:
        return None
    return template[template.index("{") + 1 : template.index("}")]


def _static_anchor(
    match: re.Match[str],
    files: dict[str, frozenset[str]],
    snapshot: ModuleType,
    in_svg: bool = False,
) -> str:
    """Rewrite a captured-page link; render unavailable app routes as plain text.

    ``files`` maps each exported page to the ids it carries. A link whose query the
    export collapses (``/process-map?process=4.1#listing`` becomes the one
    ``process-map.html``) keeps its fragment only where the page has that id -- the
    per-process listing it pointed at is not in the bundle, so the page itself is
    the nearest thing that is.

    Inside an ``<svg>`` an unavailable link keeps an SVG element -- a ``<g>`` --
    because an HTML ``<span>`` is not an SVG child and the browser stops painting
    the subtree around it (the dashboard treemap vanished this way)."""
    attrs, body = match.group("attrs"), match.group("body")
    found = HREF.search(attrs)
    if found is None:
        return match.group(0)
    value = found.group("url")
    if value == "/driftless/" or not value.startswith("/") or value.startswith("//"):
        return match.group(0)
    path, _, fragment = value.partition("#")
    candidate = str(snapshot.snapshot_name(path))
    focus = FOCUS_QUERY.search(html.unescape(path))
    if candidate == MAP_PAGE and focus is not None and MAP_ALL_PAGE in files:
        anchor = NODE_ANCHOR + focus.group("node")
        if anchor in files[MAP_ALL_PAGE]:
            candidate, fragment = MAP_ALL_PAGE, anchor
    if candidate not in files:
        if in_svg:
            return f'<g class="showcase-unavailable">{body}</g>'
        return f'<span class="showcase-unavailable">{body}</span>'
    keep = fragment and fragment in files[candidate]
    href = _page_href(candidate) + (f"#{fragment}" if keep else "")
    attrs = HREF.sub(f'href="{href}"', attrs, count=1)
    return f"<a{attrs}>{body}</a>"


def _page_href(candidate: str) -> str:
    """The clickable form of a sibling page file name: on Cloudflare Pages a
    ``.html`` request 308s to its extensionless path, so the link is emitted
    extensionless too (``./`` for the index) even though the file on disk keeps
    its ``.html`` name."""
    return "./" if candidate == "index.html" else candidate.removesuffix(".html")


def _anchor_nodes(body: str) -> str:
    """Give every node's own list entry an id to be landed on, and open the lists that
    hold them. This runs before the ids are read off the page, so the generic fragment
    rewrite in :func:`_static_anchor` sees them as ids the target page really carries."""
    anchored = NODE_LIST_ITEM.sub(
        lambda found: f'<li id="{NODE_ANCHOR}{found.group("node")}">{found.group("rest")}', body
    )
    return anchored.replace(*NODE_LISTS)


def _rewrite_anchors(body: str, files: dict[str, frozenset[str]], snapshot: ModuleType) -> str:
    """Every ``<a>`` rewritten, SVG ones in SVG vocabulary."""
    out: list[str] = []
    pos = 0
    for svg in SVG_BLOCK.finditer(body):
        out.append(
            ANCHOR_TAG.sub(lambda m: _static_anchor(m, files, snapshot), body[pos : svg.start()])
        )
        out.append(
            ANCHOR_TAG.sub(lambda m: _static_anchor(m, files, snapshot, in_svg=True), svg.group(0))
        )
        pos = svg.end()
    out.append(ANCHOR_TAG.sub(lambda m: _static_anchor(m, files, snapshot), body[pos:]))
    return "".join(out)


#: The one way back to the live site; the exporter takes this as ``--site-url``
#: so the URL is not hard-coded twice between the CLI default and the notice.
DEFAULT_SITE_URL = "https://headlessmode.com/driftless/"


def transform_bundle(
    pages: dict[str, str], anchor: str, source: str, site_url: str = DEFAULT_SITE_URL
) -> dict[str, str]:
    """Remove active behavior, label the fixture, and make page links portable."""
    snapshot = _snapshot_module()
    kept = {name: body for name, body in pages.items() if name not in DROP_PAGES}
    if MAP_ALL_PAGE in kept:
        kept[MAP_ALL_PAGE] = _anchor_nodes(kept[MAP_ALL_PAGE])
    files = {name: frozenset(ELEMENT_ID.findall(body)) for name, body in kept.items()}
    label = (
        '<aside class="showcase-notice" role="note">'
        f'<a href="{html.escape(site_url)}">&larr; Back to headlessmode.com/driftless</a> '
        f"&middot; <strong>Fixed fictional demo</strong> &middot; as of "
        f"{html.escape(anchor)}</aside>"
    )
    style = (
        "<style>.showcase-notice{border:2px solid var(--focus);padding:.65rem .8rem;"
        "margin:0 0 1rem;background:var(--muted-bg);font-size:.85rem}"
        ".showcase-unavailable{color:var(--muted-ink)}"
        ".showcase-intro{border:1px solid var(--rule);border-radius:.4rem;"
        "padding:.65rem .8rem;margin:0 0 1rem;background:var(--muted-bg)}"
        ".showcase-intro p{margin:0 0 .4rem}"
        ".showcase-intro p:last-child{margin-bottom:0}"
        ".showcase-sample-heading{border-top:1px dashed var(--rule);padding-top:.8rem}"
        ".showcase-note{font-size:.85rem;color:var(--muted-ink);margin:0 0 1rem}"
        # The export strips the <a> each map shape carried, so showcase-map.js makes the
        # shape itself the focusable thing; map.css only rings a focused <a>.
        ".node[tabindex]:focus-visible .node-shape{stroke-width:3.5}"
        ".node[tabindex]:focus-visible text{opacity:1}</style>"
    )
    meta = '<meta name="robots" content="noindex, nofollow">'
    story = _story_project(kept)
    intro = _demo_intro(story[0], story[1], _project_count(kept)) if story is not None else ""
    transformed: dict[str, str] = {}
    for name, body in kept.items():
        body = SCRIPT.sub("", body)
        body = CSS_LINK.sub(_rewrite_css_link, body)
        body = MANIFEST_LINK.sub("", body)
        body = PRINT_LINK.sub("", body)
        body = FORM.sub("", body)
        body = MAP_FILTERS.sub("", body)
        body = MAP_ZOOM.sub("", body)
        body = LOGIN_LINK.sub("", body)
        if name == HEATMAP_PAGE:
            body = HEATMAP_HORIZON_PICKER.sub(HEATMAP_HORIZON_COPY, body, count=1)
        script = ""
        if name in MAP_PAGES:
            for pattern, replacement in MAP_COPY:
                body = pattern.sub(replacement, body, count=1)
            body = MAP_VIEWS.sub(MAP_VIEWS_COPY[name], body, count=1)
            script = MAP_SCRIPT_TAG
        body = SVG_BLOCK.sub(_name_svg, body)
        body = _rewrite_anchors(body, files, snapshot)
        if name in MAP_PAGES:
            body = DEAD_OPEN_LINE.sub("", body)
        if name == "index.html" and intro:
            # The landing intro's own <h1> leads the page now, so the dashboard's
            # heading below it is demoted -- one page must not carry two <h1>s
            # disagreeing about what it is.
            body = PROJECT_H1.sub(
                lambda m: f'<h2 class="showcase-sample-heading">{m.group("name")}</h2>',
                body,
                count=1,
            )
        main_extra = intro if name == "index.html" else ""
        if UNAVAILABLE_NOTE_CLASS in body:
            main_extra += UNAVAILABLE_NOTE
        if main_extra:
            body = body.replace('<main id="main">', f'<main id="main">{main_extra}', 1)
        body = body.replace("</head>", f"{meta}{style}{script}</head>", 1)
        body = body.replace("<body>", f"<body>{label}", 1)
        body = "\n".join(line.rstrip() for line in body.splitlines()) + "\n"
        transformed[name] = body
    return transformed


def _owns_bundle(out: Path) -> bool:
    """True only when ``out`` already carries this tool's own ``manifest.json`` --
    the clobber guard below is keyed on that, not on a marker file, so a bundle
    written before the marker was retired is still recognized as owned."""
    manifest_path = out / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("kind") == KIND


def write_bundle(out: Path, pages: dict[str, str], anchor: str, source: str) -> int:
    """Replace one owned showcase bundle and write deterministic provenance."""
    if out.exists() and any(out.iterdir()) and not _owns_bundle(out):
        raise SystemExit(f"{out}: not a showcase bundle; refusing to replace its files")
    out.mkdir(parents=True, exist_ok=True)
    # Every regular file this run does not own is cleared before writing, not only
    # ``*.html``: a prior run's renamed or dropped asset (a stylesheet, a script, a
    # stray legacy marker) would otherwise leak forward as an orphan the manifest
    # never lists.
    for stale in sorted(out.iterdir()):
        if stale.is_file():
            stale.unlink()
    digests: dict[str, str] = {}
    for name, body in sorted(pages.items()):
        (out / name).write_text(body, encoding="utf-8")
        digests[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    # The interaction layer travels as its own relative file, never inline: the
    # deployment's CSP is `default-src 'self'` with `unsafe-inline` for styles ONLY,
    # so an inline <script> would be blocked where a sibling file is served.
    asset = SHOWCASE_SCRIPT.name
    script_body = SHOWCASE_SCRIPT.read_text(encoding="utf-8")
    (out / asset).write_text(script_body, encoding="utf-8")
    digests[asset] = hashlib.sha256(script_body.encode("utf-8")).hexdigest()
    # Every stylesheet a rewritten <link> now points at travels the same way: a
    # sibling file, written once, named in the manifest beside the script.
    stylesheets = css_assets()
    for name, body in sorted(stylesheets.items()):
        (out / name).write_text(body, encoding="utf-8")
        digests[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest = {
        "anchor": anchor,
        "files": sorted([*pages, asset, *stylesheets]),
        "kind": KIND,
        "pages": len(pages),
        "scripts": [asset],
        "sha256": digests,
        "source": source,
        "stylesheets": sorted(stylesheets),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return len(pages)


def render_showcase(snapshot: ModuleType, anchor: date, project_name: str) -> dict[str, str]:
    """Seed once and render every read-only page that tells the product's causal story:
    the dashboard/execution surfaces plus the method map, PMBOK/technique/artifact
    catalogs, org capacity view, and the per-project flow/RAID/status/assist pages."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = snapshot.new_engine(f"sqlite:///{Path(tmp) / 'showcase.db'}")
        snapshot.Base.metadata.create_all(engine)
        factory = snapshot.new_session_factory(engine)

        def session() -> Iterator[Any]:
            with factory() as db:
                yield db

        snapshot.app.dependency_overrides[snapshot.get_session] = session
        try:
            # The lifespan checks the app's own factory, so point it at this throwaway
            # store before entering TestClient rather than probing the deployment DB.
            with (
                snapshot.temporary_factory(factory),
                snapshot.TestClient(snapshot.app, base_url="https://testserver") as client,
            ):

                def post(path: str, body: dict[str, Any]) -> int:
                    response = client.post(path, json=body)
                    if response.status_code >= 400:
                        raise SystemExit(f"seed POST {path} -> {response.status_code}")
                    return int(response.json()["id"])

                def patch(path: str, body: dict[str, Any]) -> None:
                    response = client.patch(path, json=body)
                    if response.status_code >= 400:
                        raise SystemExit(f"seed PATCH {path} -> {response.status_code}")

                snapshot.seed(post, snapshot.demo_payload(anchor), patch)
                projects = client.get("/projects").json()
                project = next((row for row in projects if row["name"] == project_name), None)
                if project is None:
                    raise SystemExit(f"the demo store has no project named {project_name!r}")
                departments = client.get("/departments").json()
                department = next((row for row in departments if row["name"] == "Production"), None)
                if department is None:
                    raise SystemExit("the demo store has no department named 'Production'")

                query = f"?as_of={anchor.isoformat()}"
                #: One id per store-backed collection, EXCEPT the ones the dashboard or
                #: the demo's single-project story pins to a chosen row or every row --
                #: see :data:`ALL_PROJECT_PAGES` and :data:`SINGLE_DEPARTMENT_ASSIST`.
                #: Every other collection -- and the whole frozen PMBOK/technique/
                #: artifact/method catalog -- exports every row a reader could reach by
                #: following a real link, so a list page this export ships never links
                #: forward into a page it did not also ship.
                id_sources: dict[str, list[str]] = {
                    "project_id": [str(project["id"])],
                    "business_id": [str(row["id"]) for row in client.get("/businesses").json()],
                    "portfolio_id": [str(row["id"]) for row in client.get("/portfolios").json()],
                    "program_id": [str(row["id"]) for row in client.get("/programs").json()],
                    "department_id": [str(row["id"]) for row in departments],
                    "process_id": [process.id for process in snapshot.catalog.PROCESSES],
                    "slug": sorted(snapshot.BY_SLUG),
                    "key": sorted(snapshot.METHODS),
                    "kind_slug": sorted(snapshot.ARTIFACT_BY_SLUG),
                }
                all_project_ids = [str(row["id"]) for row in projects]
                urls: list[str] = []
                for template in snapshot.page_templates(snapshot.app.routes):
                    if template in EXCLUDED_ROUTES:
                        continue
                    param = _param_name(template)
                    if param is None:
                        urls.append(f"{template}{query}")
                        continue
                    if template == SINGLE_DEPARTMENT_ASSIST:
                        ids = [str(department["id"])]
                    elif template in ALL_PROJECT_PAGES:
                        ids = all_project_ids
                    else:
                        ids = id_sources[param]
                    urls.extend(
                        f"{template.replace('{' + param + '}', value)}{query}" for value in ids
                    )

                def fetch(url: str) -> tuple[int, str]:
                    response = client.get(url)
                    return response.status_code, response.text

                pages = cast(dict[str, str], snapshot.capture(fetch, urls))
                # The whole graph is the same route under a query, so it is captured on
                # its own and renamed: one read of /map per file, and the one page every
                # "See it on the map" link in the bundle can land on with its node drawn.
                whole = cast(
                    dict[str, str], snapshot.capture(fetch, [f"/map{query}&view={WHOLE_GRAPH}"])
                )
                pages[MAP_ALL_PAGE] = whole[MAP_PAGE]
                return pages
        finally:
            snapshot.app.dependency_overrides.pop(snapshot.get_session, None)


def _tag_matches_version(repo_root: Path) -> bool:
    """True only when HEAD carries the exact tag this checkout's version names --
    ``v{__version__}`` is honest as a --source default there, and nowhere else."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == f"v{__version__}"


def _short_sha(repo_root: Path) -> str:
    """The commit this checkout actually is, for every checkout that is not sitting
    on its version's own release tag."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def _default_source(repo_root: Path) -> str:
    if _tag_matches_version(repo_root):
        return f"v{__version__}"
    return _short_sha(repo_root)


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--anchor", type=date.fromisoformat, default=ANCHOR, metavar="YYYY-MM-DD")
    parser.add_argument("--source", default=None)
    parser.add_argument("--project", default="Season 4 Rollout")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    args = parser.parse_args(argv)
    if args.source is None:
        args.source = _default_source(repo_root)
        print(f"--source not given; defaulting to {args.source!r} (checkout at {repo_root})")
    snapshot = _snapshot_module()
    pages = render_showcase(snapshot, args.anchor, args.project)
    transformed = transform_bundle(pages, args.anchor.isoformat(), args.source, args.site_url)
    count = write_bundle(args.out, transformed, args.anchor.isoformat(), args.source)
    print(f"Showcase: {count} read-only pages at {args.anchor} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
