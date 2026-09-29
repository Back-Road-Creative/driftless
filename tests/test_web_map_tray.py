"""The method map says out loud what its bottom row is (F6 of the display audit).

Four graph members -- three artifacts and one technique -- have no ``reads``,
``produces`` or ``used_by`` tie at all. The layout used to hand them the LAST
lifecycle band as a fallback coordinate, so the map silently asserted they
belong to Closing when no edge and no catalog fact says so. They now sit in
their own tray below every band, and the tray carries a visible caption
explaining what it is rather than leaving a reader to guess.

The tray is drawn by the read that draws its members: ``?view=all``. The default
overview holds processes only, and a captioned strip below a row of members that
are not there would name nothing (:mod:`test_web_map_overview`).
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from driftless.pmbok.graph_layout import LAYOUT, unconnected_member_ids
import test_web_pages
from test_web_pages import Q

client, db = test_web_pages.client, test_web_pages.db

_TRAY_LABEL = re.compile(r'<text class="tray-label"[^>]*\sy="([^"]+)"[^>]*>([^<]*)</text>')


def test_the_tray_carries_a_visible_caption_in_plain_words(client: TestClient) -> None:
    body = client.get(f"/map{Q}&view=all").text
    found = _TRAY_LABEL.search(body)
    assert found, "the map draws no tray caption"
    caption = found.group(2)
    assert "accounted for elsewhere" in caption.lower()
    assert "no tie" in caption.lower()


def test_the_caption_sits_just_above_the_tray_row_it_names(client: TestClient) -> None:
    body = client.get(f"/map{Q}&view=all").text
    found = _TRAY_LABEL.search(body)
    assert found
    caption_y = float(found.group(1))
    tray_top = min(LAYOUT.label_boxes[node_id][1] for node_id in unconnected_member_ids())
    assert 0 < tray_top - caption_y <= 24, (
        f"caption at y={caption_y} is not sitting on the tray row at y={tray_top}"
    )


def test_the_tray_backing_reaches_the_foot_of_the_map(client: TestClient) -> None:
    body = client.get(f"/map{Q}&view=all").text
    found = re.search(r'<rect class="tray" x="0" y="([^"]+)" width="[^"]+" height="([^"]+)"', body)
    assert found, "the map draws no tray backing"
    top, height = float(found.group(1)), float(found.group(2))
    assert top + height == LAYOUT.viewbox[1]
