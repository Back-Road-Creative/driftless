"""``map.css``'s ten knowledge-area tints (and the technique/artifact/process
neutrals) each clear two WCAG ratios, computed straight off the file rather
than eyeballed: >=3:1 against the white page (1.4.11, a graphical object) and
>=4.5:1 against the fixed #1a1a1a ink map.css draws every node label in. The
formula itself is ``tests/test_web_a11y.py``'s own (verified there against the
canonical WCAG figures); this file only re-applies it to a sheet that test
never reads."""

from __future__ import annotations

import re
from pathlib import Path

_STYLESHEET = (
    Path(__file__).resolve().parents[1] / "driftless" / "web" / "static" / "map.css"
).read_text()
_FILL = re.compile(r"fill:\s*(#[0-9a-fA-F]{6})\s*;")
INK = "#1a1a1a"
WHITE = "#ffffff"


def _luminance(colour: str) -> float:
    digits = colour.lstrip("#")
    channels = [int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _every_fill() -> set[str]:
    """Every ``fill: #rrggbb`` literal map.css declares — the whole tinted
    vocabulary, area, neutral and legend swatch alike, walked rather than
    hand-listed so a colour added later is caught the same way."""
    return set(_FILL.findall(_STYLESHEET))


def test_the_stylesheet_declares_at_least_the_ten_area_tints() -> None:
    areas = re.findall(r'data-area="(\w+)"\]\s*\{\s*fill:\s*#[0-9a-fA-F]{6}', _STYLESHEET)
    assert len(set(areas)) == 10, f"want 10 distinct knowledge-area tints, found {sorted(areas)}"


def test_every_fill_clears_wcag_aa_against_white_and_against_the_fixed_label_ink() -> None:
    failures = []
    for fill in sorted(_every_fill()):
        if fill in (INK, WHITE):
            continue
        white_ratio = _ratio(fill, WHITE)
        ink_ratio = _ratio(fill, INK)
        if white_ratio < 3.0:
            failures.append(f"{fill} vs white is {white_ratio:.2f}:1, want >=3:1")
        if ink_ratio < 4.5:
            failures.append(f"{fill} vs ink {INK} is {ink_ratio:.2f}:1, want >=4.5:1")
    assert not failures, "\n".join(failures)


#: MP19 -- decorations drawn on the PAGE background (never on a fixed tint,
#: which is the header comment's own carve-out) must follow the theme's own
#: `--ink` token so they survive the dark re-point, not a literal that measures
#: ~1.06:1 against `--background: #151515` and vanishes.
_PAGE_DECORATIONS = ("band", "tray", "map-pill", "map-pill:has(input:checked)")


def test_page_background_decorations_follow_the_theme_ink_token() -> None:
    failures = []
    for name in _PAGE_DECORATIONS:
        rule = re.search(rf"\.{re.escape(name)}\s*\{{([^}}]*)\}}", _STYLESHEET)
        assert rule, f"no .{name} rule found in map.css"
        declarations = rule.group(1)
        if INK in declarations:
            failures.append(f".{name} still hard-codes {INK}: {declarations!r}")
    assert not failures, "\n".join(failures)
