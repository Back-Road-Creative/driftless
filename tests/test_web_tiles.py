"""The KPI strip is one macro, not a shape each page re-types.

``home.html`` and ``drill.html`` render the SAME eight rollup tiles -- the five
financial/risk figures plus the three flow figures (``n/a`` where a node rolled up
no agile evidence, off ``gather.flow_cell``) -- from the same ``gather.overview()``
tree, and drill.html's own header comment promises they are "literally the same
ones". They were not: the markup was hand-copied, and it had already drifted --
home's tiles carry the ``data-countup`` hook and drill's do not. That divergence is
preserved deliberately (the count-up is a dashboard flourish; see ``driftless.js``
"Count-up on the home dashboard's KPI tiles"), and it is now a macro ARGUMENT
rather than a difference two files can drift into silently.

What this pins: no template hand-writes a ``.tile`` div, and the eight shared tiles
name the same labels against the same ids in the same order on both pages.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "driftless" / "web" / "templates"

# A macro CALL, read in source order. The rendered attribute order (``id`` before
# ``class="value"``) is pinned elsewhere: the ``_tile`` helpers in test_web_home and
# test_web_drills match on it against real responses, and test_web_drills already
# asserts the two pages report equal FIGURES. What is left to pin -- and what a hand
# copy got wrong -- is that both name the same labels against the same ids, in order.
CALL = re.compile(r'tiles\.tile\(\s*"([^"]+)"\s*,[^)]*?id="kpi-([a-z-]+)"')


def _tile_calls(name: str) -> list[tuple[str, str]]:
    return CALL.findall((TEMPLATES / name).read_text(encoding="utf-8"))


def test_no_template_hand_writes_a_tile_div() -> None:
    """A ``.tile`` div may exist in exactly one place: the macro that defines it."""
    offenders = sorted(
        path.name
        for path in TEMPLATES.glob("*.html")
        if path.name != "_tiles.html" and '<div class="tile"' in path.read_text(encoding="utf-8")
    )
    assert offenders == [], f"these templates hand-write a tile div: {offenders}"


def test_home_and_the_drill_page_agree_on_the_shared_tiles() -> None:
    """The drill is a rollup of the same tree, so its strip is home's, prefix-wise."""
    shared = [
        ("Budget", "budget"),
        ("Actual", "actual"),
        ("Complete", "complete"),
        ("On track", "on-track"),
        ("Open high risks", "risks"),
        ("Work in progress", "wip"),
        ("Throughput / wk", "throughput"),
        ("Median cycle time (days)", "cycle"),
    ]
    assert _tile_calls("drill.html") == shared
    assert _tile_calls("home.html")[: len(shared)] == shared
