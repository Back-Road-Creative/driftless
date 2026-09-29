"""The method map fits the screen (M.1/F1): the SVG scales to the column with a
legibility floor, and three real ``<button>``s (Fit / 100% / +/-) let a reader with
JS running change how much of it shows at once. With JS off the page is the Fit
view — the buttons sit inert, exactly like the filters and search box already do.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

import test_web_pages
from test_web_pages import AS_OF

client, db = test_web_pages.client, test_web_pages.db
Q = f"as_of={AS_OF.isoformat()}"

_BUTTON = re.compile(r'<button[^>]*data-zoom="([^"]+)"[^>]*>')


def test_the_zoom_controls_are_real_buttons_with_visible_labels(client: TestClient) -> None:
    body = client.get(f"/map?{Q}").text
    zooms = _BUTTON.findall(body)
    assert set(zooms) == {"fit", "100", "in", "out"}, zooms


def test_every_zoom_button_is_inside_the_zoom_group(client: TestClient) -> None:
    body = client.get(f"/map?{Q}").text
    group = re.search(r'<div class="map-zoom"[^>]*role="group"[^>]*>.*?</div>', body, re.S)
    assert group, body
    for zoom in ("fit", "100", "in", "out"):
        assert f'data-zoom="{zoom}"' in group.group(0), zoom
