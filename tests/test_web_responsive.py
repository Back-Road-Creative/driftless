"""The rendered surface holds together down to a tablet (§5 C5's second clause).

What is asserted is *structure*, on the HTML that shipped — never appearance. CSS
cannot be unit-tested and a grep for ``@media`` would be theatre. Three properties,
each a way the layout can silently fail:

*Viewport* — every page the app registers carries ``<meta name="viewport">``, walked
over the real routes. Without it a tablet browser reports a lied-about ~980px width
and every breakpoint below is inert, so this is the load-bearing tag.

*Containment* — every ``<table>`` (RAG rollup, person × week capacity, the PMBOK and
process grids, the Gantt's text twin) sits in a container that SCROLLS rather than
clipping, and that container is focusable and named, so the scroll is reachable by
keyboard and announced rather than mouse-only. Nothing is hidden at a narrow width: a
manager on a tablet must not lose the column the decision turned on.

*Ownership* — no page-local ``<style>`` or ``style=`` declares a layout property
base.html owns (``display:flex/grid``, ``flex``, ``overflow``, ``min-``/``max-width``),
so a surface cannot lay itself out one way on the dashboard and another on the drill
page; and exactly ONE width breakpoint is declared, so it cannot drift into three. That
gate reaches containment only, which is why the rollup table's alignment and indents are
now base.html's ``.rollup`` rather than a copy in each of the two pages that render it.

WHAT THIS DOES NOT PROVE: that it *looks* right at 768px. No test here renders a
viewport, so column widths, where the flex rows choose to wrap, whether a scrolled
table reads well under a thumb, and whether the Gantt's bars stay legible once the SVG
scales are all eye checks. Every wrapped table IS rendered, though: the capacity grid
and the search results used to come back empty under this fixture, so their wrappers
were covered by the static gates alone — ``test_web_a11y._html`` now refuses to hand
back a page holding nothing, which closes that hole for this walk and the a11y one at
once. What is proved: nothing is clipped or hidden, the scroll containers are reachable
and named, and the rules live in one place.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import test_web_pages
from test_web_a11y import _html
from test_web_csrf import _web_paths

# The seeded https store, reused as is (assigned, not imported: a test's own
# parameter must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless/web/templates"
_BASE_HTML = (_TEMPLATES / "base.html").read_text()
VIEWPORT = "width=device-width, initial-scale=1"
BREAKPOINT = "max-width: 60rem"

_STYLE_BLOCK = re.compile(r"<style>(.*?)</style>", re.S)
_STYLE_ATTR = re.compile(r'\bstyle="([^"]*)"')
_WIDTH_QUERY = re.compile(r"@media\s*\(([^)]*width[^)]*)\)")
# The properties that decide whether a wide surface fits, as opposed to how it is
# painted: a page may still set its own colour, padding or text alignment.
_LAYOUT = re.compile(
    r"\b(?:overflow(?:-[xy])?|flex(?:-wrap|-basis|-grow|-shrink|-flow)?"
    r"|min-width|max-width|grid-template-columns)\s*:"
    r"|\bdisplay\s*:\s*(?:inline-)?(?:flex|grid)\b",
    re.I,
)


class _Layout(HTMLParser):
    """Every ``<table>`` on one rendered page, paired with the scroll container it
    sits in (``None`` when it sits in none), plus the page's viewport tags.

    Only ``<div>`` nesting is counted, so an unclosed void tag (``<br>``, ``<input>``)
    cannot desynchronise the depth the way a full element stack would."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, str] | None] = []
        self.viewports: list[str] = []
        self._region: dict[str, str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "meta" and attr.get("name") == "viewport":
            self.viewports.append(attr.get("content", ""))
        elif tag == "div":
            if self._region is not None:
                self._depth += 1
            elif "scroll-x" in attr.get("class", "").split():
                self._region, self._depth = attr, 1
        elif tag == "table":
            self.tables.append(self._region)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._region is not None:
            self._depth -= 1
            if not self._depth:
                self._region = None


def _layout(browser: TestClient, store: Session, shape: str) -> _Layout:
    page = _Layout()
    page.feed(_html(browser, store, shape))
    return page


@pytest.mark.parametrize("shape", sorted(_web_paths("GET")))
def test_every_page_declares_the_viewport(client: TestClient, db: Session, shape: str) -> None:
    assert _layout(client, db, shape).viewports == [VIEWPORT], (
        f"{shape} must carry exactly one <meta name=viewport content='{VIEWPORT}'>; without "
        "it a tablet renders at a lied-about ~980px and every breakpoint is inert"
    )


@pytest.mark.parametrize("shape", sorted(_web_paths("GET")))
def test_every_wide_table_scrolls_rather_than_clipping_and_the_scroll_is_reachable(
    client: TestClient, db: Session, shape: str
) -> None:
    for index, region in enumerate(_layout(client, db, shape).tables, start=1):
        assert region is not None, (
            f"{shape}: table {index} sits in no .scroll-x container, so below the breakpoint "
            'it overflows the page. Wrap it: {% call scroll.wide("…") %}…{% endcall %}'
        )
        assert region.get("tabindex") == "0", (
            f"{shape}: table {index}'s scroll box takes no focus — a keyboard cannot scroll it"
        )
        assert region.get("role") == "region" and region.get("aria-label"), (
            f"{shape}: table {index}'s scroll box is an unnamed div — a reader announces "
            "neither that it scrolls nor which surface it holds"
        )


def test_no_page_local_style_declares_a_layout_property_base_owns() -> None:
    """Layout lives in base.html so behaviour cannot diverge per page. A page may
    still paint (colour, padding, alignment) — only containment is centralised."""
    offences = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        if template.name == "base.html":  # the stylesheet lives here; nothing else may
            continue
        body = template.read_text()
        for css in _STYLE_BLOCK.findall(body) + _STYLE_ATTR.findall(body):
            offences += [
                f"{template.name} declares {found.group(0)!r} in its own CSS — move it to a "
                "class in base.html and apply that class here"
                for found in _LAYOUT.finditer(css)
            ]
    assert not offences, "\n".join(offences)


def test_the_stylesheet_declares_exactly_one_width_breakpoint() -> None:
    """One well-chosen breakpoint beats three arbitrary ones; pinning it here is what
    stops the second and third from arriving unargued (base.html says why 60rem)."""
    assert [q.strip() for q in _WIDTH_QUERY.findall(_BASE_HTML)] == [BREAKPOINT], (
        f"base.html must declare exactly one width media query, ({BREAKPOINT}) — the width "
        "at which the dashboard's 36rem heatmap + 18rem rail + 1.5rem gap stops fitting"
    )
