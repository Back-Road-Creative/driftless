"""The rendered web surface is usable by keyboard and screen reader (§5 C5).

Two gates, both walked rather than listed by hand. *Contrast* parses the colour
tokens out of ``driftless.css`` — light ``:root`` set and dark re-point — and COMPUTES
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
import test_web_pages
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_web_csrf import SAMPLE, _web_paths

from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    AcceptanceRecord,
    Acquisition,
    ArtifactLink,
    Baseline,
    BaselineLine,
    BudgetLine,
    ChangeRequest,
    ConflictAction,
    ConflictRecord,
    CostEntry,
    Deliverable,
    Department,
    DepartmentService,
    EstimateScenario,
    Gate,
    Improvement,
    Incident,
    Issue,
    Milestone,
    NarrativeArtifact,
    Note,
    OperatingControl,
    Person,
    ProcurementAgreement,
    Program,
    Project,
    ProjectRole,
    QualityMeasurement,
    RecurringWork,
    Requirement,
    RequirementTrace,
    ResourceBreakdown,
    ResourceType,
    ResponsibilityAssignment,
    Risk,
    RiskResponse,
    ScorecardContribution,
    ServiceLevel,
    Sprint,
    Stakeholder,
    StatusSnapshot,
    StrategicObjective,
    Task,
    TeamAssessment,
    TechniqueRun,
    TrainingRecord,
    WorkRequest,
)

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
_STATIC = Path(__file__).resolve().parents[1] / "driftless/web/static"
_STYLESHEET = (_STATIC / "driftless.css").read_text()
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
# Every RAG fill --badge-ink is ever laid on: the severity badge (driftless.css) and
# the treemap label (home.html, drawn INSIDE its rectangle). Declared over the whole RAG
# vocabulary rather than the two severities that happen to reach a badge today, so
# widening either surface cannot outrun the rating.
PAIRS += [("--badge-ink", f"--rag-{rag}", 4.5) for rag in ("red", "amber", "green", "unknown")]
PAIRS += [("--gridline", "--background", 3.0)]  # chart rules + the dashed budget reference
# .btn-primary's fill (driftless.css): --badge-ink text on an --ink background rather than
# --focus, which the focus ring already claims — stacking that ring's own outline on a
# --focus fill would land at 2.56:1 light / 1.70:1 dark against the button beneath it.
# --ink and --badge-ink are both already rated above (against --background and every
# --rag-* fill); this is the one pairing neither of those covers, the two laid directly
# on each other.
PAIRS += [("--badge-ink", "--ink", 4.5)]

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
    blocks = _ROOT_BLOCK.findall(_STYLESHEET)
    assert len(blocks) == 2, f"driftless.css declares {len(blocks)} :root blocks, want light + dark"
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
            assert name in tokens, f"driftless.css declares no {name} for the {scheme} set"
        ratio = _ratio(tokens[foreground], tokens[background])
        if ratio < floor:
            failures.append(
                f"{scheme}: {foreground} {tokens[foreground]} on {background} "
                f"{tokens[background]} is {ratio:.2f}:1, want {floor}:1"
            )
    assert not failures, "\n".join(failures)


def test_no_template_outside_base_writes_a_colour_literal() -> None:
    """What makes the ratio gate above *total*. It can only see hexes declared in
    driftless.css's two :root blocks, so a page-local ``fill="#888"`` was invisible to
    it — and two such colours shipped under the floor. Forbidding the literal
    everywhere else means a colour cannot exist without a token, and a token cannot
    exist without a computed ratio (the pairing test below)."""
    offences = [
        f"driftless.css writes the colour literal {found.group(0)!r} outside its :root "
        "blocks — the palette lives there; nothing else may declare one"
        for found in _COLOUR_LITERAL.finditer(_ROOT_BLOCK.sub("", _STYLESHEET))
    ]
    for template in sorted(_TEMPLATES.glob("*.html")):
        body = template.read_text()
        offences += [
            f"{template.name} writes the colour literal {found.group(0)!r} — declare it "
            "as a --token in driftless.css's light AND dark :root blocks and use var(--token)"
            for found in _COLOUR_LITERAL.finditer(body)
        ]
    assert not offences, "\n".join(offences)


# The tag's OPENING, not its full spelling: a literal pinned attribute-for-attribute
# would stop refusing a hand-copy that carried the same extra attribute.
_BREADCRUMB_LITERAL = re.compile(r'<nav class="breadcrumbs"')


def test_no_template_hand_writes_a_breadcrumb_nav_instead_of_the_macro() -> None:
    """Five templates once hand-copied the identical three-crumb ``<nav>`` — nothing
    stopped a sixth copy from drifting the moment one of the five changed.
    ``_breadcrumbs.html`` is now the ONE place that markup is written; every project
    sub-page imports it and calls ``breadcrumbs.trail(...)``, the two-crumb pages call
    ``breadcrumbs.top(...)``, and the Method cluster calls ``breadcrumbs.theory(...)``,
    so a second hand-copy is refused here rather than merely caught by eye in review."""
    offences = [
        f'{template.name} writes <nav class="breadcrumbs"> directly — import '
        "_breadcrumbs.html and call breadcrumbs.trail(project, page, as_of) instead"
        for template in sorted(_TEMPLATES.glob("*.html"))
        if template.name != "_breadcrumbs.html" and _BREADCRUMB_LITERAL.search(template.read_text())
    ]
    assert not offences, "\n".join(offences)


_OPEN_TAG = re.compile(r"<\w+[^>]*>")


def _is_an_error_alert(tag: str) -> bool:
    """Any element carrying BOTH the refusal styling and the alert role, whatever its tag.

    Matching the macro's exact current markup is what a gate against hand-copying must
    NOT do: this element has already changed shape once (a ``<p>`` became a ``<div>`` when
    the macro grew its field-linked list), and a literal pinned to the new spelling stops
    refusing the old one — which still renders an identical red card, minus every field
    link. The pair of attributes is the thing that makes it an error alert; the tag name
    and the attribute order are not, so neither is matched.
    """
    return "sev-red" in tag and 'role="alert"' in tag


def test_no_template_hand_writes_an_error_alert_instead_of_the_macro() -> None:
    """The same idiom as the breadcrumb gate above, for the same reason: login.html and
    wizard.html once hand-copied the identical error alert byte-for-byte (a ``<p>``, before
    the macro grew a field-linked ``<ul>`` and became a ``<div>``), and nothing stopped a
    third copy from drifting the moment one of the two changed — a missing ``role="alert"``
    on a later copy would fail silently, since a sighted reviewer sees the red card either
    way. ``_alert.html`` is now the ONE place that markup is written; every page that
    renders a refusal imports it and calls ``alert.error(error, field_errors)``, so a
    second hand-copy is refused here rather than merely caught by eye in review."""
    offences = [
        f"{template.name} writes an error alert ({tag}) directly — import _alert.html "
        "and call alert.error(error, field_errors) instead"
        for template in sorted(_TEMPLATES.glob("*.html"))
        if template.name != "_alert.html"
        for tag in _OPEN_TAG.findall(template.read_text())
        if _is_an_error_alert(tag)
    ]
    assert not offences, "\n".join(offences)


_BUTTON = re.compile(r"<button\b[^>]*>")
_RANKED = re.compile(r'class="btn (btn-primary|btn-secondary)"')


def test_every_button_declares_where_it_sits_in_the_hierarchy() -> None:
    """A hierarchy nothing enforces is a hierarchy that lasts until the next button.

    Eight buttons shipped bare and identical, which is how the primary submit of a form
    came to read exactly like an auxiliary sign-off beside it. Classing those eight fixes
    the pages that exist; it does nothing about the ninth, and a bare ``<button>`` added
    later inherits only the shared control surface — visually the *lesser* of the pair,
    so a new page's main action would render quieter than the sign-off next to it and
    no test would say a word. Every button names its rank, or this is red.
    """
    offences = [
        f"{template.name} has a button with no rank: {tag}"
        for template in sorted(_TEMPLATES.rglob("*.html"))
        for tag in _BUTTON.findall(template.read_text())
        if not _RANKED.search(tag)
    ]
    assert not offences, "\n".join(offences)


def test_every_declared_token_is_rated_or_declared_decorative() -> None:
    """No token may be added without a floor or an explicit decorative exemption —
    otherwise tokenising a colour would quietly move it out of the gate's reach."""
    rated = {name for pair in PAIRS for name in pair[:2]} | set(DECORATIVE)
    unrated = sorted(set(_token_sets()["light"]) - rated)
    assert not unrated, (
        f"driftless.css declares {unrated} with no contrast floor — add each to PAIRS, or to "
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
    """Severity is a CLOSED vocabulary — ``calc.rollup.RagStatus`` — so driftless.css is
    read against that list, not against the classes it happens to declare. Two rules
    shipped (``.sev-red``, ``.sev-amber``): a ``green`` or ``unknown`` severity drew no
    stripe at all, so "no severity shown" read exactly like "not a severity we style",
    and its ``.sev-badge`` inherited no background — ``--badge-ink`` #ffffff on the page
    at 1.00:1, the word invisible. Driving the walk off ``RAG_SEVERITY`` means a new
    member of the vocabulary cannot reach a card without a stripe and a rated badge."""
    tokens = _token_sets()[scheme]
    stripes = dict(_SEV_STRIPE.findall(_STYLESHEET))
    badges = dict(_SEV_BADGE.findall(_STYLESHEET))
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


_DESCRIBEDBY = re.compile(r'aria-describedby="([^"]+)"')


def test_a_refused_field_s_control_is_described_by_its_own_error(
    client: TestClient, db: Session
) -> None:
    """The error macro's ``<li>`` links to the control (``#body``), which moves a
    keyboard user's FOCUS there — but a screen reader landing on the textarea in
    isolation, tabbing rather than following the link, hears nothing that ties it to
    the refusal. ``aria-describedby`` is the other half: the control names the id of
    the text describing why it was refused. Asserted as a LINKAGE — the id the
    attribute names actually exists on the page — rather than a pinned string, since
    a test pinned to one exact id stops catching the case it exists for."""
    client.get(f"/projects/1/wizard{Q}")  # mints the pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": "   "}
        | test_web_pages._pair(client),
    )
    assert resp.status_code == 422
    described = _DESCRIBEDBY.search(resp.text)
    assert described, "the refused body control carries no aria-describedby"
    assert f'id="{described.group(1)}"' in resp.text, (
        f"aria-describedby points at {described.group(1)!r}, which no element in the "
        "response declares as its id — a screen reader would be sent nowhere"
    )


# The bare HTML attribute, never a substring of another one: a plain ``"required" in tag``
# also matches ``aria-required="false"``, which declares the exact opposite and would have
# been read as compliance.
_REQUIRED = re.compile(r"(?<![-\w])required(?![-\w=])")

_MANDATORY_SELECTS = {
    "wizard.html": 'id="kind-select"',
    "process_map.html": 'id="process-subject"',
    "_signoff.html": 'name="decision"',
}


def test_every_server_mandatory_select_declares_required() -> None:
    """``kind`` (wizard.html), ``subject_ref`` (process_map.html) and ``decision``
    (_signoff.html, shared by home.html/threats.html/process_map.html) are all
    FastAPI ``Form()`` parameters with no default — server-mandatory. Each select is
    always pre-populated with no blank option, so an empty submit is not reachable
    through the UI today; the gap is that nothing tells assistive tech the field is
    mandatory, not that a bad submit gets through. Matched by a distinguishing
    attribute rather than the whole opening tag, so adding ``required`` is exactly
    what turns this red."""
    offences = []
    for filename, marker in _MANDATORY_SELECTS.items():
        body = (_TEMPLATES / filename).read_text()
        found = [
            tag for tag in _OPEN_TAG.findall(body) if tag.startswith("<select") and marker in tag
        ]
        assert found, f"{filename}: no <select> carries {marker!r}, test needs updating"
        offences += [
            f"{filename}: {tag} has no required attribute"
            for tag in found
            if not _REQUIRED.search(tag)
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
    # The cost workbench's stored-estimate section and the department workspace's
    # budget/run-rate section (both W4.3b): one filed cost estimate, one budget line
    # held by the department and one cost entry on its project, so neither renders
    # an empty state under this fixture.
    store.add(
        EstimateScenario(
            project=project,
            target="cost",
            kind="parametric",
            value=1200.0,
            basis="12 per hour over 100 hours",
            actor="jp",
            as_of=JAN,
        )
    )
    store.add(
        BudgetLine(
            department=project.responsible_department, category="labour", planned_amount=4000.0
        )
    )
    store.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=300.0))
    # The scope worksheet's actors table and its product-analysis/prototype prompts,
    # so /projects/{id}/assist/scope renders content rather than its empty state.
    store.add(Stakeholder(project=project, name="Ada Lovelace", interest="high"))
    store.add(
        NarrativeArtifact(
            project=project, kind="project_scope_statement", body="Ship the new fleet tracker."
        )
    )
    store.add(
        NarrativeArtifact(
            project=project,
            kind="requirements_documentation",
            body="Track every vehicle in real time.",
        )
    )
    # The flow page's charts render only for a sprint whose window contains AS_OF —
    # otherwise it renders its (legitimate) empty state, which this walk's non-empty
    # assertion would then trip on the flow page's behalf.
    store.add(
        Sprint(
            project=project,
            name="Flow Sprint",
            start_date=JAN,
            end_date=AS_OF,
            committed_points=10,
            completed_points=6,
        )
    )
    # Two DATED readings a quarter apart, so the weekly-status trend draws its line, its
    # two axis ends and the table twin. It is the one slot on that page the rest of this
    # seed leaves blank, and until it held rows every rule below passed over markup the
    # walk had never once seen — the chart shipped unwalked from the day it was written.
    store.add_all(
        StatusSnapshot(project=project, taken_on=taken_on, percent_complete=percent, rag_status=rag)
        for taken_on, percent, rag in ((JAN, 10, "amber"), (AS_OF, 60, "green"))
    )
    store.add(
        risk := Risk(
            project=project,
            description="Data loss",
            probability=0.5,
            impact=100.0,
            response="mitigate",
            status="open",
            kind="threat",
        )
    )
    store.flush()
    store.add(
        RiskResponse(
            project=project,
            risk=risk,
            strategy="mitigate",
            owner=dana,
            trigger="Backup job fails twice in a row",
            planned_action="Add a second offsite backup target",
            residual_probability=0.2,
            residual_impact=20.0,
            cost_of_response=500.0,
            schedule_days=2,
            status="planned",
            actor="qa",
            as_of=AS_OF,
        )
    )
    store.add(
        Stakeholder(
            project=project,
            name="Sponsor",
            interest="high",
            influence="high",
            comms_cadence="weekly",
        )
    )
    store.add(
        Stakeholder(
            project=project,
            name="Neighbour",
            interest="low",
            influence="low",
            comms_cadence="on_request",
        )
    )
    store.add(Issue(project=project, description="Delay", raised_on=AS_OF, status="open"))
    # Two dated readings of the same legacy (unlinked) metric, one over target, so
    # /projects/{id}/assist/quality draws a control chart and the Pareto has a
    # failure to rank, rather than either section's own empty state.
    store.add_all(
        QualityMeasurement(
            project=project,
            metric="Defect rate",
            target_value=2.0,
            actual_value=actual,
            unit="%",
            measured_on=taken_on,
        )
        for taken_on, actual in ((JAN, 1.5), (AS_OF, 3.0))
    )
    store.add(
        NarrativeArtifact(
            project=project,
            kind="quality_management_plan",
            body="Inspect every reel before delivery. Log a defect the moment it is found.",
        )
    )
    store.add(
        ChangeRequest(
            project=project, description="Scope change", raised_on=AS_OF, status="proposed"
        )
    )
    # Two budget lines (one of them the "contingency" category) so the cost
    # workbench's aggregation and reserve-analysis tables render real rows, and a
    # second project with its own spend so the workbench's historical-information
    # section has a real reference figure rather than its empty state.
    store.add(BudgetLine(project=project, category="labour", planned_amount=900.0))
    store.add(BudgetLine(project=project, category="contingency", planned_amount=100.0))
    other = Project(name="Watchtower", portfolio=project.portfolio, delivery_mode="predictive")
    store.add(other)
    store.add(CostEntry(project=other, category="labour", incurred_on=JAN, amount=450.0))
    # One row of each department operations table, so /org/departments/{id} renders
    # real content in every section rather than seven empty states beside the two
    # populated ones (module docstring: every page is walked on markup that HOLDS
    # something).
    dept = project.responsible_department
    service = DepartmentService(department=dept, name="Colour grading", owner="Ada")
    store.add(service)
    store.add(
        WorkRequest(
            department=dept, service=service, requester="Grace", raised_on=AS_OF, status="queued"
        )
    )
    store.add(RecurringWork(department=dept, name="License audit", cadence="weekly", owner="Sam"))
    store.add(ServiceLevel(department=dept, service=service, measure="turnaround_hours", target=48))
    control = OperatingControl(department=dept, name="Dual approval", owner="Sam")
    store.add(control)
    store.add(
        Incident(department=dept, control=control, description="Late render", raised_on=AS_OF)
    )
    store.add(
        Improvement(
            department=dept, what="Automate the license check", why="Missed once", owner="Sam"
        )
    )
    # One artifact link on the department, so its "Linked artifacts" section draws a row.
    store.flush()
    store.add(
        ArtifactLink(
            record_kind="department",
            record_id=str(dept.id),
            uri="https://example.com/grading-sop.pdf",
            title="Grading SOP",
            actor="Sam",
            as_of=AS_OF,
        )
    )
    # And one note, so its "Notes" section draws a row rather than its empty state.
    store.add(
        Note(
            record_kind="department",
            record_id=str(dept.id),
            body="Grading SOP revised after the March audit",
            actor="Sam",
            as_of=AS_OF,
        )
    )
    # The requirements/WBS worksheet: a filed requirement, a two-node WBS, a trace
    # between them and one ledger entry, so that page renders content rather than
    # four empty states under this fixture.
    requirement = Requirement(project=project, code="REQ-2", statement="Must ship", actor="qa")
    store.add(requirement)
    deliverable = Deliverable(project=project, name="Grade", wbs_code="2")
    store.add(deliverable)
    store.flush()
    store.add(RequirementTrace(requirement=requirement, deliverable=deliverable))
    store.add(AcceptanceRecord(deliverable=deliverable, verified_on=AS_OF, actor="qa"))
    # The team assist page: a resource type and an RBS node over it, a RACI line
    # against the deliverable above, an acquisition, a training record, a team
    # assessment and a conflict with its one action — so that page renders
    # content rather than five empty states under this fixture.
    resource_type = ResourceType(project=project, name="Colourist", kind="people", unit="hours")
    store.add(resource_type)
    store.flush()
    store.add(ResourceBreakdown(project=project, resource_type=resource_type, quantity=1.0))
    store.add(
        ResponsibilityAssignment(
            project=project, deliverable=deliverable, person=dana, role="accountable"
        )
    )
    store.add(
        Acquisition(
            project=project,
            resource_type=resource_type,
            source="external",
            requested_on=JAN,
            status="requested",
        )
    )
    store.add(TrainingRecord(person=dana, topic="Colour grading", completed_on=JAN))
    store.add(
        TeamAssessment(
            project=project, assessed_on=AS_OF, dimension="Performing", score=70.0, actor="qa"
        )
    )
    store.add(
        conflict := ConflictRecord(
            project=project,
            raised_on=AS_OF,
            parties="Ada, Dana",
            approach="collaborate",
            actor="qa",
        )
    )
    store.flush()
    store.add(ConflictAction(conflict=conflict, owner=dana, due_on=AS_OF))
    # The department workspace (/org/departments/{id}/assist) adds three sections the drill
    # page above has none of — an objective this project actively contributes to, a
    # stakeholder-proxy role (RACI's "consulted" column), a vendor agreement and a project
    # stakeholder — so it renders real content rather than three more empty states.
    objective = StrategicObjective(
        business=project.portfolio.business, perspective="financial", name="Grow revenue"
    )
    store.add(
        ScorecardContribution(
            project=project, objective=objective, contribution_type="direct", status="active"
        )
    )
    store.add(ProjectRole(project=project, role="stakeholder_proxy", holder="Robin"))
    store.add(ProcurementAgreement(project=project, vendor="Acme Studio", start_date=AS_OF))
    store.add(
        Stakeholder(
            project=project, name="Priya", interest="high", influence="high", comms_cadence="weekly"
        )
    )
    # A meeting run, so /projects/{id}/assist/decisions's evidence table draws a row
    # rather than only its empty state.
    store.add(
        TechniqueRun(
            project=project,
            technique_key="meetings",
            process_id="4.3",
            actor="Dana",
            as_of=AS_OF,
            method="predictive",
        )
    )
    # A second approved baseline, and the change request that produced it, so
    # /projects/{id}/baselines/diff has a default pair to compare rather than its
    # empty state (the seed above carries only v1).
    store.add(v2 := Baseline(project=project, version=2, status="approved", approved_at=AS_OF))
    store.add(
        BaselineLine(
            baseline=v2, task=task, planned_cost=1200.0, planned_start=JAN, planned_finish=AS_OF
        )
    )
    store.add(
        ChangeRequest(
            project=project,
            description="Extend grading schedule",
            raised_on=JAN,
            status="approved",
            resulting_baseline=v2,
        )
    )
    # A gate, so /projects/{id}/gates draws its section rather than its empty state.
    store.add(Gate(project=project, name="Kickoff", position=1, required_processes=""))
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
    assert ":focus-visible" in _STYLESHEET and "outline: none" not in _STYLESHEET, "no focus ring"


_ANY_TOKEN = re.compile(r"(--[a-z0-9-]+)\s*:", re.I)


def test_the_dark_block_re_points_colours_and_nothing_else() -> None:
    """The dark ``:root`` exists to say what CHANGES under a dark scheme. A type step, a
    spacing step and a radius do not — they cascade from the light block untouched.
    Declaring one in the re-point anyway makes a second copy of a value with no reason
    to differ, which is the shape that drifts apart.

    :func:`_token_sets`'s own parity check cannot see this: its pattern requires a hex
    value, so a non-colour token is invisible to it in both blocks.
    """
    _, dark = _ROOT_BLOCK.findall(_STYLESHEET)
    declared, colours = set(_ANY_TOKEN.findall(dark)), {name for name, _ in _TOKEN.findall(dark)}
    assert colours, "vacuous walk: the dark block re-points no colour at all"
    assert declared == colours, (
        f"the dark re-point declares {sorted(declared - colours)}, which carry no colour — "
        "declare them once in the light :root and let them cascade"
    )


_MEASURE = re.compile(r"(--[a-z-]+)\s*:\s*([0-9.]+(?:rem|px))\s*;", re.I)
# The type scale and the 8-pt spacing scale the shell is built from: every step a
# multiple of 8px (0.5rem at the default 16px root), so a card's padding and a
# tile's gap are always the same family of number rather than two designers'
# guesses. Pinned to exact values, not merely "declared", because a scale one step
# off in only one direction is not a scale at all.
TYPE_SCALE = {
    "--fs-sm": "0.875rem",
    "--fs-base": "1rem",
    "--fs-lg": "1.25rem",
    "--fs-xl": "1.75rem",
}
SPACE_SCALE = {
    "--space-sm": "0.5rem",
    "--space-md": "1rem",
    "--space-lg": "1.5rem",
    "--space-xl": "2rem",
}


def test_the_type_scale_and_spacing_scale_sit_on_an_8pt_grid() -> None:
    light, _ = _ROOT_BLOCK.findall(_STYLESHEET)
    declared = dict(_MEASURE.findall(light))
    for name, want in {**TYPE_SCALE, **SPACE_SCALE}.items():
        assert declared.get(name) == want, (
            f"driftless.css declares {name}={declared.get(name)!r}, want {want!r}"
        )


def test_prose_is_bounded_to_72ch_but_tables_and_figures_are_not() -> None:
    """A paragraph or a list item at full container width runs an unreadable line
    length; a table or a figure needs every pixel it can get to stay legible."""
    assert re.search(r"(?<![.\w-])p,\s*li\s*\{[^}]*max-width:\s*72ch", _STYLESHEET), (
        "driftless.css declares no `p, li { max-width: 72ch; }` rule"
    )
    assert not re.search(r"\btable\s*\{[^}]*max-width:\s*72ch", _STYLESHEET), (
        "a table must not be capped to a prose measure"
    )


def test_the_page_container_is_centred_and_bounded() -> None:
    assert re.search(r"body\s*\{[^}]*max-width:\s*1280px[^}]*\}", _STYLESHEET), (
        "body must declare the page container (max-width: 1280px)"
    )
    assert re.search(r"body\s*\{[^}]*margin:\s*[^;]*auto[^}]*\}", _STYLESHEET), (
        "body must centre the page container with an auto margin"
    )


def test_a_link_reads_ink_with_an_underline_that_strengthens_on_hover_and_focus() -> None:
    assert re.search(r"\ba\s*\{[^}]*color:\s*var\(--ink\)", _STYLESHEET), (
        "a link must read --ink, not the browser default blue"
    )
    assert re.search(r"\ba\s*\{[^}]*text-decoration[a-z-]*:\s*underline", _STYLESHEET), (
        "a link must carry a rest-state underline"
    )
    assert re.search(
        r"a:hover[^{]*,\s*a:focus-visible|a:focus-visible[^{]*,\s*a:hover", _STYLESHEET
    ), "a link's underline must strengthen on hover AND on focus, not one alone"


def test_the_showcase_notice_overrides_the_exporters_inline_blue_box() -> None:
    """``bin/driftless-showcase.py`` (not ours to edit) carries its own inline
    fallback style for a bundle exported with no server behind it — a shouted 2px
    ``--focus`` border. Its selector is a bare class; ``aside.showcase-notice``
    here outranks it (0,0,1,1 beats 0,0,1,0) regardless of cascade order, so every
    export — which always inlines this stylesheet — renders a slim muted bar."""
    assert re.search(
        r"aside\.showcase-notice\s*\{[^}]*background:\s*var\(--muted-bg\)", _STYLESHEET
    ), "driftless.css declares no aside.showcase-notice override"
    assert not re.search(r"aside\.showcase-notice\s*\{[^}]*border:\s*2px", _STYLESHEET), (
        "the override must not itself be the shouted 2px box"
    )


def test_the_masthead_names_the_product_and_shows_the_as_of_when_the_page_carries_one(
    client: TestClient, db: Session
) -> None:
    home = client.get("/" + Q).text
    assert '<a class="wordmark" href="/">driftless</a>' in home, "no wordmark on the dashboard"
    assert f"As of {AS_OF.isoformat()}" in home and "as-of-chip" in home, (
        "the as-of chip is missing from a page that carries an as_of"
    )

    login = client.get("/login").text
    assert 'class="wordmark"' in login, "every page must render the masthead, including /login"
    assert "as-of-chip" not in login, (
        "/login carries no as_of — the chip must not render on a page with none"
    )


def test_the_masthead_names_the_open_project_and_only_on_a_project_page(
    client: TestClient, db: Session
) -> None:
    hub = client.get(f"/projects/1/hub{Q}").text
    assert "masthead-project" in hub, "a project page must name its project in the masthead"
    marker = hub.index("masthead-project")
    assert "GMS" in hub[marker : marker + 120], "the masthead names the wrong (or no) project"

    home = client.get("/" + Q).text
    assert "masthead-project" not in home, (
        "the dashboard has no open project — the masthead must not claim one"
    )


_NAV_GROUPS = {
    "nav-group-work": ["/", "/scorecard", "/threats", "/org/heatmap"],
    "nav-group-method": [
        "/pmbok",
        "/techniques",
        "/methods",
        "/artifacts",
        "/glossary",
        "/process-map",
        "/map",
    ],
    "nav-group-org": ["/org/configuration", "/org/departments"],
}


def test_the_primary_nav_is_grouped_into_work_method_and_organization(
    client: TestClient, db: Session
) -> None:
    body = client.get("/" + Q).text
    nav = body[body.index('<nav aria-label="Primary"') : body.index("</nav>")]
    for group_id, hrefs in _NAV_GROUPS.items():
        assert f'id="{group_id}"' in nav, f"{group_id} is missing from the primary nav"
        start = nav.index(f'id="{group_id}"')
        end = nav.index("</ul>", start)
        group_html = nav[start:end]
        for href in hrefs:
            assert f'href="{href}"' in group_html, f"{href} is missing from {group_id}"
    assert 'href="/search"' not in nav, (
        "Search is a masthead utility link now, not a fourth item inside <nav>"
    )
    masthead = body[body.index('<header class="masthead"') : body.index("</header>")]
    assert 'href="/search"' in masthead, "Search must be a right-aligned masthead utility link"


def test_the_primary_nav_collapses_behind_a_disclosure_on_mobile(
    client: TestClient, db: Session
) -> None:
    """Reducing mobile navigation cost without hiding routes (F6 Wave 4 item 7): every
    route from ``_NAV_GROUPS`` stays reachable and marked, but the three clusters now
    sit behind a checkbox-driven disclosure that starts unchecked, so a narrow
    viewport is not forced to render all 13 links before a reader chooses one."""
    body = client.get("/" + Q).text
    nav = body[body.index('<nav aria-label="Primary"') : body.index("</nav>")]
    assert '<input type="checkbox" id="nav-toggle" class="nav-toggle-checkbox">' in nav, (
        "the nav clusters must sit behind a checkbox-driven disclosure"
    )
    assert '<label class="nav-toggle-label" for="nav-toggle">Menu</label>' in nav, (
        "the disclosure needs a labelled trigger bound to its checkbox"
    )
    for hrefs in _NAV_GROUPS.values():
        for href in hrefs:
            assert f'href="{href}"' in nav, f"{href} must still be reachable, not hidden"
    assert re.search(r"\.nav-toggle-label\s*\{[^}]*display:\s*none", _STYLESHEET), (
        "the disclosure trigger stays out of the way above the mobile breakpoint"
    )
    assert re.search(
        r"@media \(max-width: 60rem\)\s*\{.*?\.nav-toggle-label\s*\{[^}]*display:",
        _STYLESHEET,
        re.S,
    ), "the trigger must only appear at the mobile breakpoint"
    assert re.search(
        r"@media \(max-width: 60rem\)\s*\{.*?\.primary-nav\s*\{[^}]*display:\s*none",
        _STYLESHEET,
        re.S,
    ), "below the breakpoint the clusters must start hidden"
    assert re.search(
        r"\.nav-toggle-checkbox:checked\s*~\s*\.primary-nav\s*\{[^}]*display:\s*flex", _STYLESHEET
    ), "checking the box must reveal the clusters"
    # The checkbox has to LEAVE above the breakpoint, not merely become invisible.
    # `position: absolute; width: 1px; opacity: 0` hides it from eyes but keeps it in
    # the accessibility tree, so a reader on a desktop viewport met an unlabelled
    # checkbox that toggles nothing there -- its <label> is display:none at that width,
    # and axe counts a hidden label as no label ("Form elements must have labels",
    # #nav-toggle). base.html already says this control "render[s] only" at the mobile
    # breakpoint; the stylesheet said that of the label and not of the box it drives.
    assert re.search(r"\.nav-toggle-checkbox\s*\{[^}]*display:\s*none", _STYLESHEET), (
        "the checkbox must not exist above the mobile breakpoint, where it does nothing"
    )
    assert re.search(
        r"@media \(max-width: 60rem\)\s*\{.*?\.nav-toggle-checkbox\s*\{[^}]*display:\s*block",
        _STYLESHEET,
        re.S,
    ), "below the breakpoint the checkbox must come back, or the label toggles nothing"


def test_the_masthead_is_a_full_width_bar_with_a_bottom_rule() -> None:
    assert re.search(
        r"\.masthead\s*\{[^}]*border-bottom:\s*1px solid var\(--rule\)", _STYLESHEET
    ), "the masthead must carry its 1px bottom rule"
    assert re.search(r"\.masthead\s*\{[^}]*padding:\s*\.75rem 0", _STYLESHEET), (
        "the masthead must carry its 12px (.75rem) vertical padding"
    )
    assert re.search(r"\.masthead\s*\{[^}]*justify-content:\s*space-between", _STYLESHEET), (
        "the masthead must lay its brand and utility groups out on the SAME row, opposite ends"
    )


def test_the_wordmark_is_a_link_that_is_never_underlined() -> None:
    assert re.search(r"\.wordmark\s*\{[^}]*text-decoration:\s*none", _STYLESHEET), (
        "the wordmark is a logotype, not prose — it must not carry the default link underline"
    )


def test_nav_clusters_stack_their_caption_above_their_links_and_sit_32px_apart() -> None:
    assert re.search(r"\.primary-nav\s*\{[^}]*gap:\s*2rem\b", _STYLESHEET), (
        "clusters must sit 32px (2rem) apart"
    )
    assert re.search(r"\.nav-cluster\s*\{[^}]*flex-direction:\s*column", _STYLESHEET), (
        "a cluster's caption must sit ABOVE its links (a column), not inline beside them"
    )
    assert re.search(r"\.nav-cluster ul\s*\{[^}]*gap:[^;]*1rem\b", _STYLESHEET), (
        "links within a cluster must sit 16px (1rem) apart"
    )
    assert re.search(r"\.nav-cluster ul\s*\{[^}]*font-size:\s*\.95rem", _STYLESHEET), (
        "nav links must read at .95rem"
    )


def test_h1_gets_room_to_breathe_below_the_masthead_and_nav() -> None:
    assert re.search(r"\bh1\s*\{[^}]*margin-top:\s*2rem", _STYLESHEET), (
        "h1 must carry a 32px (2rem) top margin"
    )
