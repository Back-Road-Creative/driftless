"""The displays the five-page list left out, and the record each render leaves.

``test_renders`` renders five pages chosen to cover a tile, a wide table, a
chart, an inventory and a form. That list omits every page whose whole content
*is* a drawing -- the method map, the process map, flow, gantt, the heatmap --
and those are the ones a static gate can say least about: the template emits an
``<svg>``, the structural checks confirm the element is there, and whether it
came out full-width or thumbnail-sized, labelled or bare, is answered nowhere.
A thumbnail method map and an empty flow page both shipped green that way.

So this module renders the other eight routes beside the original five, and
writes an **audit record** while it does: viewport, the document's scroll width
against its client width, the box of the largest SVG on the page, how many SVG
text labels actually came out visible, and everything the page logged. The
record is evidence, not a gate -- the numbers in it are allowed to be small.
What is *asserted* is only what no page may do: overflow sideways, raise in the
browser, answer with something that is not a page, or come back blank.

Deliberately absent: any assertion about how much data a page drew. The seeded
fixture is thin, flow and gantt are sparse under it, and a "at least N bars"
check here would be a test of the fixture. The counts get recorded so a human
(or a later gate) can read the trend; they never fail the run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import ConsoleMessage, Page

from tests.browser.test_renders import DESKTOP, MOBILE, PAGES

# The eight routes the original list omitted. Five of them are drawings, two are
# catalogues rendered from a registry, and one is the PMBOK proof table.
DISPLAY_PAGES = [
    ("method map", "/map"),
    ("process map", "/process-map"),
    ("flow", "/projects/1/flow"),
    ("gantt", "/projects/1/gantt"),
    ("heatmap", "/org/heatmap"),
    ("assist cost", "/projects/1/assist/cost"),
    ("methods", "/methods"),
    ("pmbok proof", "/pmbok/proof"),
]
# The originals stay in the matrix: the audit record is only worth reading if it
# covers every page the tier renders, not just the ones added last.
AUDIT_PAGES = [*PAGES, *DISPLAY_PAGES]

# Defects this module finds, recorded rather than hidden: path -> what is wrong.
# The fix is a layout change under driftless/web/ and does not belong in a test
# file, so an entry here is a placeholder for one, never a substitute.
#
# strict=True is the whole point: the day the page stops overflowing, the run
# goes red on an unexpected pass and whoever fixed it must delete the entry. A
# non-strict xfail would sit here forever, quietly green either way -- and that
# is exactly how the register emptied. Its first and so far only entry was
# /process-map, which pushed the document 475px sideways at 1280 and 1357px at
# 390 even though _scroll.wide() WAS in the template: the .sr-only spans inside
# the grid are position:absolute with no positioned ancestor, so they laid out
# against the initial containing block, escaped the scroll box's clip and
# stretched the document to the widest one's right edge. driftless.css's
# .scroll-x is position:relative now and the entry went with the fix.
_KNOWN_BROKEN: dict[str, str] = {}

AUDIT_PARAMS = [
    pytest.param(
        name,
        path,
        id=name.replace(" ", "-"),
        marks=(
            [pytest.mark.xfail(strict=True, reason=_KNOWN_BROKEN[path])]
            if path in _KNOWN_BROKEN
            else []
        ),
    )
    for name, path in AUDIT_PAGES
]

# reports/ is already the repo's home for regenerable output and is already
# ignored by git, so the record lands there by default and never asks to be
# committed. The env var is for CI, which uploads the directory as an artifact.
AUDIT_DIR = Path(os.environ.get("DRIFTLESS_BROWSER_AUDIT_DIR", "reports/browser-audit"))

# One file per xdist worker. The record is written from a session fixture, and
# under `-n auto` every worker owns a session; a single fixed filename would have
# them overwrite each other and the surviving file would look like a short run.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "")

_PROBE = """() => {
  const doc = document.documentElement;
  const svgs = Array.from(document.querySelectorAll('svg'));
  const area = (r) => r.width * r.height;
  let largest = null;
  for (const svg of svgs) {
    const r = svg.getBoundingClientRect();
    if (largest === null || area(r) > area(largest)) largest = r;
  }
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    return el.checkVisibility
      ? el.checkVisibility({opacityProperty: true, visibilityProperty: true})
      : true;
  };
  const labels = Array.from(document.querySelectorAll('svg text')).filter(shown);
  return {
    scroll_width: doc.scrollWidth,
    client_width: doc.clientWidth,
    svg_count: svgs.length,
    largest_svg: largest && {
      width: Math.round(largest.width), height: Math.round(largest.height)
    },
    visible_svg_labels: labels.length,
    body_text_length: (document.body.innerText || '').trim().length,
  };
}"""


@pytest.fixture(scope="session")
def audit() -> Iterator[list[dict[str, Any]]]:
    """Collects one record per page x viewport and writes them out at teardown.

    Teardown, not per-test, so a run that fails halfway still leaves the rows it
    got -- the record of a broken render is the point of having one.
    """
    records: list[dict[str, Any]] = []
    yield records
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"display-audit{'-' + _WORKER if _WORKER else ''}.json"
    (AUDIT_DIR / name).write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def logged(page: Page) -> Iterator[list[str]]:
    seen: list[str] = []
    page.on("pageerror", lambda exc: seen.append(str(exc)))
    page.on("console", lambda msg: seen.append(msg.text) if _is_error(msg) else None)
    yield seen


def _is_error(message: ConsoleMessage) -> bool:
    return message.type == "error"


@pytest.mark.parametrize("size", [DESKTOP, MOBILE], ids=["desktop", "mobile"])
@pytest.mark.parametrize(("name", "path"), AUDIT_PARAMS)
def test_the_page_renders_and_is_recorded(
    page: Page,
    base_url: str,
    audit: list[dict[str, Any]],
    logged: list[str],
    name: str,
    path: str,
    size: dict[str, int],
) -> None:
    page.set_viewport_size(size)
    response = page.goto(f"{base_url}{path}")
    status = response.status if response is not None else 0
    content_type = (response.header_value("content-type") or "").lower() if response else ""
    measured: dict[str, Any] = {}
    if response is not None and response.ok and content_type.startswith("text/html"):
        measured = dict(page.evaluate(_PROBE))
    record = {
        "page": name,
        "path": path,
        "viewport": dict(size),
        "status": status,
        "content_type": content_type,
        "errors": list(logged),
        **measured,
    }
    audit.append(record)

    assert response is not None and response.ok, f"{name} answered {status}, not a page"
    # The API answers /projects/{id} with JSON on this same app, so a path typed
    # one segment short returns 200 with no layout at all and every check below
    # would pass against it.
    assert content_type.startswith("text/html"), (
        f"{path} answered {content_type!r}, not a page — this check would prove nothing"
    )
    assert logged == [], f"{name} raised in the browser: {logged}"
    # A template that renders to nothing, or a page whose only content failed to
    # build, is a blank rectangle that every check above still passes. This is
    # what makes a blank render red without anyone opening a screenshot.
    assert record["body_text_length"] > 0, f"{name} rendered a blank body at {size['width']}px"
    # Overflow last, because it is the one check a page in _KNOWN_BROKEN is
    # expected to fail: ordering it here keeps a blank or raising render red on
    # its own reason even under that page's xfail.
    overflow = record["scroll_width"] - record["client_width"]
    assert overflow <= 0, (
        f"{name} at {size['width']}px scrolls {overflow}px sideways — a wide child "
        f"escaped its container, and on a phone that hides the right edge"
    )
