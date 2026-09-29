"""What the pages do once the reader states a preference.

Three settings a rendering engine honours and a text gate cannot see at all:
a dark colour scheme, a keyboard with no pointer, and a request for less motion.
Each is already implemented -- these check the implementation reaches the page,
which is the half no static parse can reach.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from tests.browser.test_renders import MOBILE, PAGES


@pytest.fixture
def dark(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(color_scheme="dark")
    yield context.new_page()
    context.close()


@pytest.fixture
def still(browser: Browser) -> Iterator[Page]:
    """A reader who asked for less motion, via the OS setting the JS reads."""
    context = browser.new_context(reduced_motion="reduce")
    yield context.new_page()
    context.close()


def _body_background(page: Page) -> str:
    return str(page.evaluate("() => getComputedStyle(document.body).backgroundColor"))


@pytest.mark.parametrize(("name", "path"), PAGES, ids=[name for name, _ in PAGES])
def test_the_dark_scheme_repaints_the_page(
    dark: Page, page: Page, base_url: str, name: str, path: str
) -> None:
    """One media query re-points every token, so the proof is that the surface
    itself moved -- not that some rule somewhere mentions a dark colour."""
    dark.goto(f"{base_url}{path}")
    page.goto(f"{base_url}{path}")
    assert _body_background(dark) != _body_background(page), (
        f"{name} paints {_body_background(dark)} under prefers-color-scheme: dark, "
        f"the same as it does in light — the dark tokens did not reach this page"
    )


@pytest.mark.parametrize(("name", "path"), PAGES, ids=[name for name, _ in PAGES])
def test_the_first_tab_stop_is_the_skip_link_and_it_becomes_visible(
    page: Page, base_url: str, name: str, path: str
) -> None:
    """``.skip`` sits at left: -9999px until focus moves it back on-screen. Whether
    that actually happens is a layout fact: the rule could be overridden, the link
    could be preceded by another tab stop, and the source would read the same."""
    page.set_viewport_size(MOBILE)
    page.goto(f"{base_url}{path}")
    page.keyboard.press("Tab")
    focused = page.evaluate("() => document.activeElement.className")
    assert focused == "skip", f"{name}: the first Tab lands on {focused!r}, not the skip link"
    box = page.locator("a.skip").bounding_box()
    assert box is not None and box["x"] >= 0, (
        f"{name}: the skip link is focused but still off-screen at x={box and box['x']} — "
        f"a keyboard reader is on a control they cannot see"
    )


def test_less_motion_means_the_dashboard_figure_is_final_at_first_paint(
    still: Page, base_url: str
) -> None:
    """The count-up animates 0 -> the server's figure. Asked for less motion, the
    script returns before touching a tile, so the first painted value IS the final
    one. Read immediately: waiting would let the animation finish and pass either way."""
    still.goto(f"{base_url}/", wait_until="commit")
    budget = still.locator("#kpi-budget")
    budget.wait_for(state="attached")
    assert budget.inner_text().strip() == "1,000", (
        "the dashboard animated its KPI tile for a reader who asked for less motion"
    )
