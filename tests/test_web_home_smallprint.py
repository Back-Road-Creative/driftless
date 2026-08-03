"""The dashboard and department templates tell the truth in their small print
(audit F-D5, F-G8, F-G9).

Static reads of the shipped templates, the way test_web_a11y walks them: the home
chart empty states must name the plan calls in the order the API accepts, the rail's
trend glyphs must not be their badges' only carrier, the business jump nav must be a
named landmark, and one department page must never render the same empty-state id
twice.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless/web/templates"
_HIDDEN_GLYPH = '<span aria-hidden="true">'


def _home() -> str:
    return (_TEMPLATES / "home.html").read_text()


def test_the_home_empty_states_name_the_order_that_actually_works() -> None:
    """Both chart empty states said "Baseline each project's plan and approve it
    (``POST /baselines``, ``POST /baseline-lines``)" — followed literally, that
    order hits the API's own 409: an approved baseline refuses new lines, by
    design. Each must walk draft → lines → approve and name the approve call,
    which neither did."""
    bodies = re.findall(r"\{% call empty\.state\(.*?\) %\}(.*?)\{% endcall %\}", _home(), re.S)
    plan = [body for body in bodies if "POST /baselines<" in body]
    assert len(plan) == 2, "both chart empty states name the plan calls"
    for body in plan:
        approve = body.find("PATCH /baselines")
        assert approve != -1, "an empty state never names the approve call at all"
        assert body.index("POST /baselines<") < body.index("POST /baseline-lines") < approve, (
            "the plan calls are named out of working order"
        )


def test_the_rail_trend_glyphs_are_hidden_and_their_words_are_reachable() -> None:
    """Same finding as the threat board's badges, which share the idiom: ▲/▼ were
    bare glyphs (announced as "black up-pointing triangle", or not at all) and
    "vs last week" lived only in ``title=`` — hover-only: no keyboard, no touch,
    no print. Jinja comments are stripped first — a glyph mentioned in one
    reaches no reader at all."""
    source = re.sub(r"\{#.*?#\}", "", _home(), flags=re.S)
    for found in re.finditer(r"[▲▼]", source):
        lead = source[found.start() - len(_HIDDEN_GLYPH) : found.start()]
        assert lead == _HIDDEN_GLYPH, f"a bare {found.group(0)} is its badge's only carrier"
    assert '<span class="sr-only"> worse vs last week</span>' in source
    assert '<span class="sr-only"> better vs last week</span>' in source
    assert 'new<span class="sr-only"> since last week</span>' in source


def test_the_business_jump_nav_is_a_named_landmark() -> None:
    """Two nav landmarks on a multi-business dashboard and only base.html's carried
    a name: the second is announced as bare "navigation", indistinguishable from
    Primary."""
    assert '<nav class="businesses" aria-label="' in _home()


def test_the_two_department_empty_states_carry_distinct_ids() -> None:
    """Both calls took _empty.html's default ``id="empty-state"``: a department
    with no projects and no people rendered the same id twice — invalid HTML, and
    an anchor only ever reaching the first."""
    source = (_TEMPLATES / "department_detail.html").read_text()
    ids = re.findall(r'empty\.state\([^)]*id="([\w-]+)"', source)
    assert len(ids) == 2 and len(set(ids)) == 2, f"want two distinct ids, got {ids}"
