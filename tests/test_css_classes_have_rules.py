"""No class a template emits may carry no rule at all — the defect this closes shipped
twice: ``.breadcrumbs`` (``_breadcrumbs.html``) and ``.empty-state`` (``_empty.html``,
the ONE empty state every list-shaped surface is meant to share) both rendered as
unstyled text, because neither ``driftless.css`` nor ``map.css`` declared a rule for
either class. Walked over every template's literal ``class="…"`` tokens rather than
listed by hand, so a class added next year and never styled fails here the day it
ships rather than being caught by eye in review.

A second gate closes the other half of the same defect: ``scorecard.html`` and
``project_hub.html`` once hand-rolled their own ad-hoc "nothing here yet" markup
(an ``<section class="empty">`` and a bare ``<p><em>… — unknown.</em></p>``) instead
of importing ``_empty.html`` — exactly the drift ``_breadcrumbs.html`` and
``_alert.html`` already guard against for their own shapes, with nothing guarding
this one. Rendered against a store with nothing in it, both pages must show ONLY the
shared ``_empty.html`` markup, never either bypass.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES = _ROOT / "driftless/web/templates"
_STATIC = _ROOT / "driftless/web/static"

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"

# A class whose only appearances are inside a Jinja expression this walk cannot
# resolve statically (``class="{{ status }}"`` — a closed status vocabulary rated
# elsewhere) is dropped at the token-collapse step below, not listed here.
#
# A class no stylesheet names can still be a CONTRACT rather than debt: a test
# selects rows by it (``<tr class="dept-raci">``), ``map.js`` queries it
# (``.map-filter``), a test asserts its presence by name (``"delta-up" in page``).
# Those are read off the tests and the static JS below instead of being copied
# into a hand list — the ~46-entry list the first cut of this test shipped with
# was already stale the day it landed. A class NOTHING names — no rule, no test,
# no script — is deleted from the template, not excused.

_TESTS = _ROOT / "tests"
_THIS_TEST = Path(__file__).name
# A hyphenated token in a quoted string is a class name in this codebase (Python
# identifiers cannot hyphenate); a bare word in quotes is not — ``"actions"``,
# ``"department"`` and ``"muted"`` all appear in tests as attribute names, slugs
# and rank vocabularies, never as the class of the same name.
_QUOTED_HYPHENATED = re.compile(r"""["']([a-zA-Z][\w]*-[\w-]*)["']""")
_JS_CLASS_SELECTOR = re.compile(r"""["'][^"']*\.([a-zA-Z][\w-]*)[^"']*["']""")


def _hooks_named_by_tests_or_js() -> set[str]:
    """Every class a test or a static script names: inside a ``class="…"`` literal,
    as a quoted hyphenated token, or as a ``.class`` selector in JS. This file is
    skipped so its own residue never counts as a reference."""
    hooks: set[str] = set()
    sources = [f for f in _TESTS.glob("*.py") if f.name != _THIS_TEST]
    sources += list(_STATIC.glob("*.js"))
    for source in sources:
        text = source.read_text()
        for attr in _CLASS_ATTR_IN_SOURCE.findall(text):
            hooks |= set(attr.split())
        hooks |= set(_QUOTED_HYPHENATED.findall(text))
        if source.suffix == ".js":
            hooks |= set(_JS_CLASS_SELECTOR.findall(text))
    return hooks


_CLASS_ATTR = re.compile(r'\bclass="([^"]*)"')
# The same attribute inside a Python or JS string literal, where the quote may be escaped.
_CLASS_ATTR_IN_SOURCE = re.compile(r'\bclass=\\?"([^"\\]*)')
_JINJA_EXPR = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_SELECTOR_TEXT = re.compile(r"([^{}]+)\{", re.S)
_SELECTOR_CLASS = re.compile(r"\.([a-zA-Z][\w-]*)")
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _emitted_classes() -> dict[str, set[str]]:
    """Every literal class token each template writes, keyed by filename. Jinja
    expressions are collapsed FIRST, over the whole document — not inside an
    already-extracted ``class="…"`` capture — because an expression itself can
    carry a quote (``{{ "green" if item.ready else "amber" }}``, ``{% if slice !=
    "all" %}``) that would otherwise truncate the attribute match early. A token
    that still carries a collapsed expression (``sev-DYNAMIC``) is dropped — it
    names no single class the markup always writes, and the data-driven
    vocabularies that produce it (severity, status) are rated by their own tests."""
    found: dict[str, set[str]] = {}
    for template in sorted(_TEMPLATES.glob("*.html")):
        sanitised = _JINJA_EXPR.sub("DYNAMIC", template.read_text())
        classes = {
            token
            for attr in _CLASS_ATTR.findall(sanitised)
            for token in attr.split()
            if "DYNAMIC" not in token
        }
        if classes:
            found[template.name] = classes
    return found


def _declared_selectors() -> set[str]:
    """Every class named anywhere in a selector, across both stylesheets — a page
    styled only by ``map.css`` (``method_map.html``) is still covered."""
    declared: set[str] = set()
    for sheet in ("driftless.css", "map.css"):
        text = _COMMENT.sub("", (_STATIC / sheet).read_text())
        for selector in _SELECTOR_TEXT.findall(text):
            declared |= set(_SELECTOR_CLASS.findall(selector))
    return declared


def test_every_emitted_class_carries_a_rule_or_is_a_named_hook() -> None:
    declared = _declared_selectors() | _hooks_named_by_tests_or_js()
    offences = [
        f"{template} writes class={cls!r} — no selector in driftless.css or map.css "
        "styles it and no test or static script names it, so it is dead markup. "
        "Add a rule, or drop the class."
        for template, classes in _emitted_classes().items()
        for cls in sorted(classes - declared)
    ]
    assert not offences, "\n".join(offences)


def test_the_hook_scan_reads_real_references_not_bare_words() -> None:
    """The three forms the scan must see, and the one it must not: a bare quoted
    word is a slug or an attribute name, never a class."""
    hooks = _hooks_named_by_tests_or_js()
    assert {"dept-raci", "delta-up", "map-filter"} <= hooks  # attr, quoted, JS selector
    assert "actions" not in hooks and "department" not in hooks and "muted" not in hooks


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


_OLD_SCORECARD_EMPTY = re.compile(r'<section class="empty"')
_OLD_UNKNOWN_PARAGRAPH = re.compile(r"<p><em>[^<]*— unknown\.</em>")
_THE_ONE_EMPTY_STATE = 'class="empty-state"'


def test_the_empty_scorecard_renders_only_the_shared_empty_state(client: TestClient) -> None:
    page = client.get(f"/scorecard{Q}")
    assert page.status_code == 200, page.text
    assert _THE_ONE_EMPTY_STATE in page.text
    assert not _OLD_SCORECARD_EMPTY.search(page.text), (
        'scorecard.html still hand-rolls its own <section class="empty"> instead of '
        "importing _empty.html"
    )


def test_the_empty_project_hub_renders_only_the_shared_empty_state(
    client: TestClient, db: Session
) -> None:
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add(project)
    db.commit()

    page = client.get(f"/projects/{project.id}/hub{Q}")
    assert page.status_code == 200, page.text
    assert _THE_ONE_EMPTY_STATE in page.text
    assert not _OLD_UNKNOWN_PARAGRAPH.search(page.text), (
        "project_hub.html still hand-rolls a bare <p><em>… — unknown.</em></p> instead "
        "of importing _empty.html"
    )
    # The bare project still trips the assessment engine's own "no data" threats
    # (unmeasured quality, and so on), so its threats section is genuinely populated
    # — only its scorecard-lens slot has nothing to show, which is the branch that
    # once bypassed _empty.html.
    assert 'id="scorecard-lens-empty"' in page.text
    assert "No scorecard contribution linked yet" in page.text


def test_a_pinned_as_of_regenerates_the_empty_hub_byte_identically(
    client: TestClient, db: Session
) -> None:
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add(project)
    db.commit()
    first = client.get(f"/projects/{project.id}/hub{Q}").text
    second = client.get(f"/projects/{project.id}/hub{Q}").text
    assert first == second
