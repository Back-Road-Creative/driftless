"""The five representative pages, rendered.

Two properties per page, both of which the static gates cannot answer:

- **Nothing overflows the viewport horizontally.** ``test_web_responsive`` proves
  every wide table sits in a declared scroll container; it cannot prove the page
  around them fits. A body wider than the window is the failure a phone actually
  shows, and it only exists once something has been laid out.
- **No page script raised.** Every page works with JavaScript off
  (``driftless.js`` opens by saying so, and the no-JS floor is pinned elsewhere),
  so a script error breaks no feature -- but it does mean the count-up, the swap
  and the status region silently stopped, and nothing else in the suite notices.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import ConsoleMessage, Page

# Dashboard, project hub, scorecard, configuration, status workflow -- the five the
# plan names, which between them cover tiles, a wide table, a chart, an inventory
# and a form.
PAGES = [
    ("dashboard", "/"),
    ("project hub", "/projects/1/hub"),
    ("scorecard", "/scorecard"),
    ("configuration", "/org/configuration"),
    ("status", "/projects/1/status"),
]
DESKTOP = {"width": 1280, "height": 900}
MOBILE = {"width": 390, "height": 844}  # iPhone 14-class, the narrow end that matters


@pytest.fixture
def errors(page: Page) -> Iterator[list[str]]:
    seen: list[str] = []
    page.on("pageerror", lambda exc: seen.append(str(exc)))
    page.on(
        "console",
        lambda msg: seen.append(msg.text) if _is_error(msg) else None,
    )
    yield seen


def _is_error(message: ConsoleMessage) -> bool:
    return message.type == "error"


@pytest.mark.parametrize("size", [DESKTOP, MOBILE], ids=["desktop", "mobile"])
@pytest.mark.parametrize(("name", "path"), PAGES, ids=[name for name, _ in PAGES])
def test_the_page_fits_its_viewport(
    page: Page, base_url: str, errors: list[str], name: str, path: str, size: dict[str, int]
) -> None:
    page.set_viewport_size(size)
    response = page.goto(f"{base_url}{path}")
    assert response is not None and response.ok, f"{name} did not load: {response}"
    # The API answers /projects/{id} with JSON on the same app. Without this, a page
    # path typed one segment short still returns 200 and every check below passes
    # against a JSON body that has no layout at all -- which is exactly what the
    # first draft of this list did.
    content_type = (response.header_value("content-type") or "").lower()
    assert content_type.startswith("text/html"), (
        f"{path} answered {content_type!r}, not a page — this check would prove nothing"
    )
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, (
        f"{name} at {size['width']}px scrolls {overflow}px sideways — a wide child "
        f"escaped its container, and on a phone that hides the right edge of the page"
    )
    assert errors == [], f"{name} raised in the browser: {errors}"
