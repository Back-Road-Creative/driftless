"""The rendered web surface is usable by keyboard and screen reader (§5 C5).

Two gates, both walked rather than listed by hand. *Contrast* parses the colour
tokens out of ``base.html`` — light ``:root`` set and dark re-point — and COMPUTES
the WCAG ratio of every pair carrying text, so a failure names the token and its
number instead of an eyeballed "looks fine". *Structure* walks every GET page the
app registers (the recursion ``test_web_routes_not_shadowed`` uses, over the ids
``test_web_csrf`` keeps) and asserts on the HTML that shipped: every control
programmatically named — a placeholder is not a name — every table scoped and
captioned, one ``<h1>``, a language. A page added next year is walked the day it is
mounted — and walked on markup that HOLDS something: ``_html`` asserts each page is
populated, against an exact set of the pages empty by design, so no rule can pass
because the page under it was blank. The walk also reads every ``aria-label`` back:
a figure announced there is spelled the way the page prints it, never a raw float.
Neither gate carries a per-file exemption — ``home.html`` was once named as owed on
the trend badge, and the named file is precisely the one that went on failing while
this suite stayed green."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    Department,
    Milestone,
    Person,
    Program,
    Project,
    StatusSnapshot,
    Task,
)
import test_web_pages
from test_web_csrf import SAMPLE, _web_paths

# The seeded https store, reused as is (assigned, not imported: a test's own
# parameter must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db
AS_OF, JAN, Q = test_web_pages.AS_OF, test_web_pages.JAN, test_web_pages.Q
# The seeded project's name, so /search has something to find. Carried by EVERY page
# the walk requests rather than tacked onto that one route: a page that ignores ``q``
# renders identically with it, and the walk stays free of per-route branches.
TERM = "GMS"
WALK = f"{Q}&q={TERM}"
HOURS = 20.0  # against Dana's default 40/wk capacity, so the heatmap grid has a row

_TEMPLATES = Path(__file__).resolve().parents[1] / "driftless/web/templates"
_BASE_HTML = (_TEMPLATES / "base.html").read_text()
_ROOT_BLOCK = re.compile(r":root\s*\{([^}]*)\}", re.S)
_TOKEN = re.compile(r"(--[a-z-]+)\s*:\s*(#[0-9a-f]{3,6})\s*;", re.I)
_COLOUR_LITERAL = re.compile(r"#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?)\(", re.I)

# Every pair that carries text, foreground first: 4.5:1 is WCAG AA for body text,
# 3:1 for large text, for a UI boundary such as the focus ring, and for a chart
# line the legend names (WCAG 1.4.11 — a series is a meaningful graphical object).
_INKS = "--ink --muted-ink --rag-green --rag-amber --rag-red --rag-unknown".split()
PAIRS = [(ink, "--background", 4.5) for ink in _INKS] + [("--focus", "--background", 3.0)]
PAIRS += [("--ink", wash, 4.5) for wash in ("--ok-bg", "--warn-bg", "--bad-bg")]
PAIRS += [("--signed-ink", "--signed-bg", 4.5), ("--muted-ink", "--muted-bg", 4.5)]
# Every RAG fill --badge-ink is ever laid on: the severity badge (base.html) and the
# treemap label (home.html, drawn INSIDE its rectangle). Declared over the whole RAG
# vocabulary rather than the two severities that happen to reach a badge today, so
# widening either surface cannot outrun the rating.
PAIRS += [("--badge-ink", f"--rag-{rag}", 4.5) for rag in ("red", "amber", "green", "unknown")]
PAIRS += [("--gridline", "--background", 3.0)]  # chart rules + the dashed budget reference

# The one exemption, spelled out rather than left silent: a box edge is decorative
# (WCAG 1.4.11 exempts it — the structure is in the markup, not the line), so it
# carries no floor. Nothing else may sit outside PAIRS.
DECORATIVE = ("--rule",)
_SVG = re.compile(r"<svg\b.*?</svg>", re.S)

# ``_empty.html``'s own class, and the only place it is written — a whole page standing
# in for content it has none of. Not ``data-empty``: board.html's per-column
# ``data-empty-column`` starts with it, and a board WITH tasks would read as blank.
EMPTY = 'class="empty-state"'
# Which walked pages are empty BY DESIGN, exactly. ``_html`` asserts membership both
# ways, so a page that quietly goes empty is not in this set and fails, and a page
# that stops being empty must leave it. Currently nothing: the fixture populates
# every page the walks touch.
EMPTY_BY_DESIGN: frozenset[str] = frozenset()


def _token_sets() -> dict[str, dict[str, str]]:
    """The light token map and the dark one (light, re-pointed by the media query)."""
    blocks = _ROOT_BLOCK.findall(_BASE_HTML)
    assert len(blocks) == 2, f"base.html declares {len(blocks)} :root blocks, want light + dark"
    light, repointed = dict(_TOKEN.findall(blocks[0])), dict(_TOKEN.findall(blocks[1]))
    assert set(repointed) == set(light), (
        f"dark re-points {sorted(repointed)}, light declares {sorted(light)} — a token with "
        "no dark value keeps its light hex on a dark background"
    )
    return {"light": light, "dark": {**light, **repointed}}


def _luminance(colour: str) -> float:  # WCAG relative luminance of #rgb / #rrggbb
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    channels = [int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_contrast_formula_matches_the_wcag_reference_figures() -> None:
    """Guard the guard: black on white is 21:1, #777 on white the canonical AA near-miss."""
    assert round(_ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(_ratio("#777777", "#fff"), 2) == 4.48
    assert _ratio("#1a7a3c", "#1a7a3c") == 1.0


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_text_token_pair_clears_wcag_aa(scheme: str) -> None:
    tokens, failures = _token_sets()[scheme], []
    for foreground, background, floor in PAIRS:
        for name in (foreground, background):
            assert name in tokens, f"base.html declares no {name} for the {scheme} set"
        ratio = _ratio(tokens[foreground], tokens[background])
        if ratio < floor:
            failures.append(
                f"{scheme}: {foreground} {tokens[foreground]} on {background} "
                f"{tokens[background]} is {ratio:.2f}:1, want {floor}:1"
            )
    assert not failures, "\n".join(failures)


def test_no_template_outside_base_writes_a_colour_literal() -> None:
    """What makes the ratio gate above *total*. It can only see hexes declared in
    base.html's two :root blocks, so a page-local ``fill="#888"`` was invisible to
    it — and two such colours shipped under the floor. Forbidding the literal
    everywhere else means a colour cannot exist without a token, and a token cannot
    exist without a computed ratio (the pairing test below)."""
    offences = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        body = template.read_text()
        if template.name == "base.html":  # the palette lives here; nothing else may
            body = _ROOT_BLOCK.sub("", body)
        offences += [
            f"{template.name} writes the colour literal {found.group(0)!r} — declare it "
            "as a --token in base.html's light AND dark :root blocks and use var(--token)"
            for found in _COLOUR_LITERAL.finditer(body)
        ]
    assert not offences, "\n".join(offences)


def test_every_declared_token_is_rated_or_declared_decorative() -> None:
    """No token may be added without a floor or an explicit decorative exemption —
    otherwise tokenising a colour would quietly move it out of the gate's reach."""
    rated = {name for pair in PAIRS for name in pair[:2]} | set(DECORATIVE)
    unrated = sorted(set(_token_sets()["light"]) - rated)
    assert not unrated, (
        f"base.html declares {unrated} with no contrast floor — add each to PAIRS, or to "
        "DECORATIVE if it is a purely decorative edge (and say why)"
    )


def test_no_chart_draws_with_a_token_exempted_as_decorative() -> None:
    """What keeps the exemption above honest — it is scoped to the domain its own
    comment claims. In a table cell or a card the structure really is in the markup,
    so the edge carries no meaning; inside an ``<svg>`` the geometry IS the content,
    and nothing in the markup carries a bar's extent. ``--rule`` at 1.45:1 drew the
    Gantt's planned window, so a task at 0% complete was a ghost the reader could
    barely see, under a rule that had quietly stopped applying."""
    offences = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        for chart in _SVG.finditer(template.read_text()):
            offences += [
                f"{template.name} draws {token} inside an <svg> — it is exempt from every "
                "contrast floor as a decorative box edge, which a chart's geometry is not. "
                "Use a rated token (--gridline clears the 3:1 WCAG 1.4.11 floor)."
                for token in DECORATIVE
                if f"var({token})" in chart.group(0)
            ]
    assert not offences, "\n".join(offences)


_SEV_STRIPE = re.compile(r"\.sev-([a-z]+)\s*\{[^}]*border-left:[^}]*var\((--[a-z-]+)\)")
_SEV_BADGE = re.compile(r"\.sev-([a-z]+)\s+\.sev-badge\s*\{[^}]*background:\s*var\((--[a-z-]+)\)")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_severity_in_the_vocabulary_is_styled_and_its_badge_is_legible(scheme: str) -> None:
    """Severity is a CLOSED vocabulary — ``calc.rollup.RagStatus`` — so base.html is
    read against that list, not against the classes it happens to declare. Two rules
    shipped (``.sev-red``, ``.sev-amber``): a ``green`` or ``unknown`` severity drew no
    stripe at all, so "no severity shown" read exactly like "not a severity we style",
    and its ``.sev-badge`` inherited no background — ``--badge-ink`` #ffffff on the page
    at 1.00:1, the word invisible. Driving the walk off ``RAG_SEVERITY`` means a new
    member of the vocabulary cannot reach a card without a stripe and a rated badge."""
    tokens = _token_sets()[scheme]
    stripes, badges = dict(_SEV_STRIPE.findall(_BASE_HTML)), dict(_SEV_BADGE.findall(_BASE_HTML))
    failures = []
    for severity in sorted(RAG_SEVERITY):
        if severity not in stripes:
            failures.append(f".sev-{severity} declares no border-left — that card gets no stripe")
        if severity not in badges:
            failures.append(
                f".sev-{severity} .sev-badge declares no background, so --badge-ink "
                f"{tokens['--badge-ink']} falls onto the page at "
                f"{_ratio(tokens['--badge-ink'], tokens['--background']):.2f}:1"
            )
            continue
        ratio = _ratio(tokens["--badge-ink"], tokens[badges[severity]])
        if ratio < 4.5:
            failures.append(f"{scheme}: .sev-{severity} badge is {ratio:.2f}:1, want 4.5:1")
    assert not failures, "\n".join(failures)


_RING = re.compile(r'<svg class="ring".*?</svg>', re.S)
_RAG_TOKEN = re.compile(r"var\(--rag-[a-z]+\)")


def test_no_completion_ring_draws_its_arc_in_a_status_colour() -> None:
    """The RAG tokens' reserved job is status (home.html:33-35). A completion arc is a
    quantity — 5% complete is not "all clear" — and both rings drew every level in
    ``--rag-green``, borrowing an all-clear for a figure that is not a status. Drawn in
    ``currentColor`` instead: the same ink the ring's own percentage prints in, over the
    15%-opacity track it fills, so the arc still reads and the token stays reserved."""
    offences = [
        f'{template.name} draws {found.group(0)} inside <svg class="ring"> — a completion '
        "arc is a quantity, not a status; the RAG tokens are reserved for status"
        for template in sorted(_TEMPLATES.glob("*.html"))
        for ring in _RING.finditer(template.read_text())
        for found in _RAG_TOKEN.finditer(ring.group(0))
    ]
    assert not offences, "\n".join(offences)


_DELTA_FLAT = re.compile(r'<span class="badge delta delta-flat"[^>]*>')


def _element(markup: str, start: int, tag: str) -> str:
    """The ``<tag>`` opening at ``start``, closing tag included — nesting COUNTED, so an
    element that wraps its words in one of its own name is read whole rather than
    truncated at the first close (which reads as carrying no words at all)."""
    depth, end = 0, len(markup)
    for found in re.finditer(rf"<(/?){tag}\b[^>]*>", markup[start:]):
        depth += -1 if found.group(1) else 1
        if depth == 0:
            end = start + found.end()
            break
    return markup[start:end]


def test_the_unchanged_trend_badge_says_unchanged_somewhere_a_reader_can_reach() -> None:
    """``title=`` is hover-only: not keyboard, not touch, not print, and most readers do
    not announce it on a non-interactive ``<span>``. The ``up``/``down``/``new`` badges
    all carry their meaning in content; ``flat`` shipped a bare en dash with the whole
    word in the tooltip. Fixed the way ``process_map.html:62`` already does it — the
    glyph ``aria-hidden``, the words in an ``sr-only`` span beside it. No template is
    exempt: the rule shipped with ``home.html`` named as owed, and the named file is
    exactly the one that went on failing while this test stayed green."""
    offences = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        body = template.read_text()
        offences += [
            f"{template.name}'s delta-flat badge is {badge!r} — its meaning is only in "
            "title=. Add the sr-only span the process map already uses."
            for badge in (_element(body, f.start(), "span") for f in _DELTA_FLAT.finditer(body))
            if "sr-only" not in badge
        ]
    assert not offences, "\n".join(offences)


_SVG_AS_ONE_IMAGE = re.compile(r'<svg\b[^>]*role="img"[^>]*>.*?</svg>', re.S)


def test_no_svg_presented_as_one_image_hides_a_link_inside_itself() -> None:
    """``role="img"`` tells a reader "this is a single graphic" and PRUNES the subtree,
    so a link inside one is not merely unlabelled — it is unreachable. The treemap's
    rectangles each link their portfolio's rollup, and neither the links nor the
    ``<title>`` naming them survived the prune. An SVG holding genuinely interactive
    children is not one image, so it does not claim to be one; a chart with nothing to
    click still may, and keeps its ``aria-label`` either way."""
    offences = [
        f'{template.name} marks an <svg> role="img" — which prunes its subtree — and '
        "puts a link inside it, so that link is unreachable. Drop the role (the "
        "aria-label still names the graphic) or move the link outside the SVG."
        for template in sorted(_TEMPLATES.glob("*.html"))
        for svg in _SVG_AS_ONE_IMAGE.finditer(template.read_text())
        if re.search(r"<a\b", svg.group(0))
    ]
    assert not offences, "\n".join(offences)


_DATA_SEVERITY_CARD = re.compile(r'<(\w+)[^>]*\bclass="card sev-\{\{')


def test_a_card_that_takes_its_severity_from_the_data_prints_that_severity() -> None:
    """Otherwise the 6px stripe is the severity's only carrier, and the RAG tokens sit
    **1.01–1.44:1 apart from each other** — red beside amber, green beside unknown: the
    stripe says "a severity" and never which one. The dashboard rail shipped exactly
    that while ``threats.html`` printed the word. Scoped to a card whose class comes
    from the DATA (``sev-{{ … }}``), so ``login.html``'s literal ``sev-red`` — an error
    alert whose own text IS the message, not a reading of an assessment — falls outside
    the rule by construction rather than by an exemption a fix could be added to."""
    offences = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        body = template.read_text()
        offences += [
            f"{template.name}'s severity card prints no sev-badge, so its severity is "
            "carried by a stripe alone and the RAG stripes are 1.01–1.44:1 apart. "
            "Print the word, the way threats.html does."
            for found in _DATA_SEVERITY_CARD.finditer(body)
            if "sev-badge" not in _element(body, found.start(), found.group(1))
        ]
    assert not offences, "\n".join(offences)


_NAMELESS_BY_KIND = {"hidden", "submit", "button", "reset", "image"}  # carry their own text
# A figure the page spells one way and its own aria-label another. Everything a reader
# can SEE goes through ``{:,.0f}``, so an unseparated run of four digits or a trailing
# ``.0`` is a raw float that reached the ear as "one thousand point zero" beside a row
# printing "1,000" — the same number, two spellings, and no way to tell they are one.
# ISO dates (``2026-03-31``) and already-grouped figures (``-3,000``) fall outside the
# pattern by construction, so the rule needs no list of things it does not mean.
_RAW_FIGURE = re.compile(r"(?<![\d,.\-])(?:\d{4,}|\d+\.0)(?![\d,\-])")


class _Surface(HTMLParser):
    """What the structural rules need to know about one rendered page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang, self.h1s = "", 0
        self.raw_figures: list[str] = []
        self.tables: list[dict[str, bool]] = []
        self.controls: list[tuple[str, str, bool, str]] = []
        self._labelled: set[str] = set()
        self._label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        self.raw_figures += _RAW_FIGURE.findall(attr.get("aria-label", ""))
        named = bool(attr.get("aria-label") or attr.get("aria-labelledby"))
        if tag == "html":
            self.lang = attr.get("lang", "")
        elif tag == "h1":
            self.h1s += 1
        elif tag == "label":
            self._label_depth += 1
            self._labelled |= {attr["for"]} if attr.get("for") else set()
        elif tag == "table":
            self.tables.append({"named": named, "scoped": False})
        elif tag == "caption" and self.tables:
            self.tables[-1]["named"] = True
        elif tag == "th" and self.tables and attr.get("scope"):
            self.tables[-1]["scoped"] = True
        elif tag in ("input", "select", "textarea"):
            if attr.get("type", "text") not in _NAMELESS_BY_KIND:
                named = named or self._label_depth > 0
                self.controls.append((tag, attr.get("name", ""), named, attr.get("id", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_depth:
            self._label_depth -= 1

    @property
    def unnamed(self) -> list[str]:  # what a reader announces with no idea what it sets
        return [
            f"<{tag} name={name!r}>"
            for tag, name, named, element_id in self.controls
            if not named and element_id not in self._labelled
        ]


def _html(browser: TestClient, store: Session, shape: str) -> str:
    """The page at ``shape``, rendered. The rows the seed lacks go in first — program,
    owning department, person, milestone, and the seed task ASSIGNED to that person with
    an estimate in hours — so no page answers with a 404 or an empty state and every
    table it has is really rendered. The assertion below is what makes that sentence
    true rather than aspirational: /org/heatmap and /search rendered their empty states
    here, and every rule both walks apply was passing on markup that held nothing.
    ``test_web_responsive`` walks the same pages off this."""
    assert "{}" not in shape or shape in SAMPLE, f"{shape} needs a reachable id in SAMPLE"
    project = store.scalars(select(Project)).one()
    project.program = Program(name="Reels", portfolio=project.portfolio)
    project.responsible_department = Department(name="Post", business=project.portfolio.business)
    store.add(dana := Person(name="Dana", department=project.responsible_department))
    # The heatmap counts a task only when it is assigned, open and estimated in HOURS
    # (assess.evaluators.resource._OPEN_HOUR_TASK); the seed's task is the first two, so
    # this is the hour estimate and the assignee that give the grid a row to draw.
    task = store.scalars(select(Task)).one()
    task.assignee, task.estimate = dana, HOURS
    store.add(Milestone(project=project, name="Gate", target_date=AS_OF))
    # Two DATED readings a quarter apart, so the weekly-status trend draws its line, its
    # two axis ends and the table twin. It is the one slot on that page the rest of this
    # seed leaves blank, and until it held rows every rule below passed over markup the
    # walk had never once seen — the chart shipped unwalked from the day it was written.
    store.add_all(
        StatusSnapshot(project=project, taken_on=taken_on, percent_complete=percent, rag_status=rag)
        for taken_on, percent, rag in ((JAN, 10, "amber"), (AS_OF, 60, "green"))
    )
    store.commit()
    page = browser.get(shape.replace("{}", SAMPLE.get(shape, "")) + WALK)
    assert page.status_code == 200, f"{shape} -> {page.status_code}"
    blank = EMPTY in page.text
    assert blank == (shape in EMPTY_BY_DESIGN), (
        f"{shape} renders {'only its empty state' if blank else 'content'} under this fixture, "
        f"{'so' if blank else 'but'} EMPTY_BY_DESIGN "
        f"{'does not name it' if blank else 'names it'}. Every rule the walks apply would pass "
        "on markup that holds nothing: seed the rows this page needs in _html, or name it "
        "in EMPTY_BY_DESIGN with the reason it is genuinely empty."
    )
    return page.text


def _render(browser: TestClient, store: Session, shape: str) -> _Surface:
    surface = _Surface()
    surface.feed(_html(browser, store, shape))
    return surface


@pytest.mark.parametrize("shape", sorted(_web_paths("GET")))
def test_every_page_names_its_controls_and_its_tables_and_spells_its_figures_once(
    client: TestClient, db: Session, shape: str
) -> None:
    surface = _render(client, db, shape)
    assert surface.lang, f"{shape}: <html> carries no lang, so a reader guesses the language"
    assert surface.h1s == 1, f"{shape}: {surface.h1s} <h1> elements, want exactly one"
    assert not surface.unnamed, f"{shape}: {surface.unnamed} lack a label; a placeholder is not one"
    assert not surface.raw_figures, (
        f"{shape}: an aria-label announces {surface.raw_figures} — a raw float or an "
        'unseparated thousand, where the page prints the same figure through "{:,.0f}". '
        "Format both sides identically so a reader hears the number the page shows."
    )
    for index, table in enumerate(surface.tables, start=1):
        assert table["scoped"], f"{shape}: table {index} has no <th scope=…>; columns read flat"
        assert table["named"], f"{shape}: table {index} has no <caption> and no aria-label"


def test_the_layout_serves_the_keyboard_a_skip_link_a_focus_ring_and_aria_current(
    client: TestClient, db: Session
) -> None:
    body = client.get("/" + Q).text
    assert body.index('href="#main"') < body.index("<nav") and 'id="main"' in body, (
        "the skip-to-content link must precede the nav and point at the main landmark"
    )
    assert 'aria-current="page"' in body, "the active nav link is unmarked for a screen reader"
    assert ":focus-visible" in _BASE_HTML and "outline: none" not in _BASE_HTML, "no focus ring"
