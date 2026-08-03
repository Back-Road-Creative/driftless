"""The schedule and weekly-status templates tell the truth in their small print
(audit F-D5, F-G8, F-G9).

Static reads of the shipped templates, the way test_web_a11y walks them: the empty
states must name the plan calls in the order the API accepts, the threat board's
trend glyphs must not be the only carrier of their meaning, and its second nav
landmark must be named.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless/web/templates"
_HIDDEN_GLYPH = '<span aria-hidden="true">'


def test_the_plan_empty_states_name_the_order_that_actually_works() -> None:
    """Both said "Baseline the plan and approve it (``POST /baselines``,
    ``POST /baseline-lines``)" — followed literally, approve-then-add-lines hits the
    API's own 409: an approved baseline refuses new lines, by design. The next step
    must be draft → lines → approve, and must name the approve call, which no empty
    state did."""
    for name in ("gantt.html", "status_form.html"):
        source = (_TEMPLATES / name).read_text()
        approve = source.find("PATCH /baselines")
        assert approve != -1, f"{name} never names the approve call at all"
        assert source.index("POST /baselines<") < source.index("POST /baseline-lines") < approve, (
            f"{name} names the plan calls out of working order"
        )


def test_the_threat_trend_glyphs_are_hidden_and_their_words_are_reachable() -> None:
    """▲/▼ were bare (announced as "black up-pointing triangle", or not at all) and
    "vs last week" lived only in ``title=`` — hover-only: no keyboard, no touch, no
    print. Each glyph hides from the tree and its words ride in an ``sr-only`` span,
    the treatment delta-flat already has. Jinja comments are stripped first — a glyph
    mentioned in one reaches no reader at all."""
    source = re.sub(r"\{#.*?#\}", "", (_TEMPLATES / "threats.html").read_text(), flags=re.S)
    for found in re.finditer(r"[▲▼]", source):
        lead = source[found.start() - len(_HIDDEN_GLYPH) : found.start()]
        assert lead == _HIDDEN_GLYPH, f"a bare {found.group(0)} is its badge's only carrier"
    assert '<span class="sr-only"> worse vs last week</span>' in source
    assert '<span class="sr-only"> better vs last week</span>' in source
    assert 'new<span class="sr-only"> since last week</span>' in source


def test_the_threat_pager_landmark_is_named() -> None:
    """Two nav landmarks and only base.html's carried a name: an unnamed second one
    is announced as bare "navigation", indistinguishable from Primary."""
    assert '<nav class="pager" aria-label="' in (_TEMPLATES / "threats.html").read_text()
