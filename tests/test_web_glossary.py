"""The glossary on the web: ``GET /glossary``, and the ``gloss`` filter that links
a term's first mention on a technique page to it.

The page itself is checked by walking ``GLOSSARY`` -- every entry gets its own
``id``, and every entry's prose is on the page. The filter is checked against
real registry text (``critical_chain_method``, ``reserve_analysis``, ...) reached
through the live app, never a hand-built string: a term is wrapped in
``<dfn><a href="/glossary#key">`` on its first mention in a text run and left
alone after that, escaping is never bypassed, and a term's letters inside an
``href`` or an existing ``<a>`` are never touched.
"""

from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient
from markupsafe import Markup

import test_web_pages
from driftless.naming import technique_slug
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.web import templating
from driftless.web.glossary import _page_label
from driftless.web.templating import TEMPLATES

client, db = test_web_pages.client, test_web_pages.db

gloss = TEMPLATES.env.filters["gloss"]


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


def test_the_glossary_page_defines_every_entry(client: TestClient) -> None:
    body = _body(client, "/glossary")
    checked = 0
    for key, entry in GLOSSARY.items():
        assert f'id="{key}"' in body, key
        assert entry.term in body, key
        assert entry.plain in body, key
        assert entry.longer in body, key
        checked += 1
    assert checked > 0, "vacuous walk: GLOSSARY is empty"


def test_a_see_also_link_resolves_to_a_real_entry_on_the_page(client: TestClient) -> None:
    body = _body(client, "/glossary")
    written = re.findall(r'href="/glossary#([^"]+)"', body)
    assert written, "vacuous: the page writes no see-also links at all"
    for key in written:
        assert f'id="{key}"' in body, f"/glossary#{key} names no id on the page"


def test_the_glossary_is_reachable_from_the_primary_nav(client: TestClient) -> None:
    assert 'href="/glossary"' in _body(client, "/")


def test_the_az_jump_offers_only_letters_that_have_entries(client: TestClient) -> None:
    """The jump strip must never link a letter section that does not exist --
    a jump to an empty section is a dead end."""
    body = _body(client, "/glossary")
    present_letters = {entry.term[0].upper() for entry in GLOSSARY.values()}
    absent_letters = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - present_letters
    assert absent_letters, "fixture drifted: GLOSSARY now covers every letter"

    nav_start = body.index('aria-label="Glossary index"')
    nav = body[nav_start : body.index("</nav>", nav_start)]
    jumped = set(re.findall(r'href="#letter-([A-Z])"', nav))

    assert jumped == present_letters, jumped
    for letter in absent_letters:
        assert f'href="#letter-{letter}"' not in nav, letter
    for letter in present_letters:
        assert f'id="letter-{letter}"' in body, f"jump link to {letter} has no target"


def test_the_page_offers_a_back_to_top_control(client: TestClient) -> None:
    body = _body(client, "/glossary")
    assert 'id="top"' in body
    assert 'href="#top"' in body


def test_the_search_control_has_a_real_associated_label(client: TestClient) -> None:
    body = _body(client, "/glossary")
    assert 'id="glossary-filter"' in body
    assert '<label for="glossary-filter">' in body


def test_every_term_still_renders_with_the_page_javascript_disabled(
    client: TestClient,
) -> None:
    """The search control is progressive enhancement only: every entry must be
    present and visible in the markup itself, with no dependence on the script
    running to reveal it."""
    body = _body(client, "/glossary")
    entries = re.findall(r'<div class="glossary-entry"[^>]*>', body)
    assert entries, "vacuous: no glossary entries were wrapped for filtering"
    for entry_tag in entries:
        assert " hidden" not in entry_tag, entry_tag
    for key, entry in GLOSSARY.items():
        assert f'id="{key}"' in body, key


def test_gloss_escapes_plain_text_rather_than_trusting_it() -> None:
    rendered = str(gloss("a <script>alert(1)</script> stakeholder"))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_gloss_is_a_noop_when_the_registry_has_no_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty registry (e.g. mid-boot) must not crash the substitution -- the text
    comes back exactly as it went in."""
    import driftless.web.templating as templating

    monkeypatch.setattr(templating, "_KEY_BY_TERM", {})
    assert templating._link_first("a stakeholder register", set()) == "a stakeholder register"


def test_gloss_wraps_only_the_first_mention_of_a_term_in_the_text_run() -> None:
    definition = TECHNIQUES["reserve_analysis"]
    assert definition.summary.lower().count("baseline") >= 2, (
        "fixture drifted: reserve_analysis.summary no longer names baseline twice"
    )
    rendered = str(gloss(definition.summary))
    assert rendered.count('href="/glossary#baseline"') == 1, rendered


def test_gloss_wraps_a_different_first_mention_for_each_term_it_finds() -> None:
    definition = TECHNIQUES["critical_chain_method"]
    rendered = str(gloss(definition.when_to_avoid))
    assert 'href="/glossary#critical-path"' in rendered, rendered
    assert 'href="/glossary#float"' in rendered, rendered


def test_gloss_never_touches_a_term_already_inside_an_anchor() -> None:
    already_linked = Markup('See <a href="/elsewhere">the stakeholder register</a> for detail.')
    rendered = str(gloss(already_linked))
    assert rendered == str(already_linked), (
        "gloss must leave text inside an existing <a> exactly as it found it"
    )


def test_gloss_never_alters_an_hrefs_own_text() -> None:
    passthrough = Markup('<p data-note="stakeholder">stakeholder</p>')
    rendered = str(gloss(passthrough))
    assert 'data-note="stakeholder"' in rendered, "an attribute value must never be rewritten"
    assert rendered.count('href="/glossary#stakeholder"') == 1, rendered


def test_a_technique_detail_page_links_a_terms_first_mention_to_the_glossary(
    client: TestClient,
) -> None:
    slug = technique_slug("reserve_analysis")
    body = _body(client, f"/techniques/{slug}")
    assert 'href="/glossary#baseline"' in body, body


def test_every_glossary_deep_link_a_technique_page_writes_is_a_real_entry(
    client: TestClient,
) -> None:
    """No page links into the glossary at an address ``GLOSSARY`` does not hold."""
    seen = 0
    for key in sorted(TECHNIQUES):
        slug = technique_slug(key)
        body = _body(client, f"/techniques/{slug}")
        for term_key in re.findall(r'href="/glossary#([^"]+)"', body):
            assert term_key in GLOSSARY, f"/techniques/{slug} links to #{term_key}, which 404s"
            seen += 1
    assert seen > 0, "vacuous walk: no technique page links into the glossary at all"


def test_gloss_never_matches_a_term_inside_a_longer_word() -> None:
    """ "feedback" must not link BAC, "expert" must not link PERT, and "every"
    must not link EV -- a term's pattern must be anchored on word boundaries,
    not free to match anywhere it appears as a substring."""
    rendered = str(gloss("feedback expert every"))
    assert "href=" not in rendered, rendered

    rendered = str(gloss("the BAC, the EV, and PERT are all standing alone"))
    assert 'href="/glossary#bac"' in rendered, rendered
    assert 'href="/glossary#ev"' in rendered, rendered
    assert 'href="/glossary#pert"' in rendered, rendered


def test_no_gloss_link_starts_or_ends_mid_word() -> None:
    """A sweep over every technique, artifact and process summary the ``gloss``
    filter is run against: whatever it links, the link boundary must sit at a
    real word boundary in the surrounding text, never inside a longer word."""
    from driftless.pmbok.artifact_definitions import ARTIFACTS
    from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS

    texts: list[str] = []
    for technique in TECHNIQUES.values():
        texts.extend([technique.summary, technique.when_to_use, technique.when_to_avoid])
    for artifact in ARTIFACTS.values():
        texts.extend(
            [
                artifact.plain_summary,
                artifact.why_it_matters,
                artifact.what_it_looks_like_here,
            ]
        )
    for process in PROCESS_DEFINITIONS.values():
        texts.append(process.plain_summary)

    link_re = re.compile(r'<dfn><a href="/glossary#[^"]+">([^<]+)</a></dfn>')
    checked = 0
    for text in texts:
        if not text:
            continue
        rendered = str(gloss(text))
        for match in link_re.finditer(rendered):
            start, end = match.span(1)
            if start > 0:
                assert re.match(r"\w", rendered[start - 1]) is None, (text, rendered)
            if end < len(rendered):
                assert re.match(r"\w", rendered[end]) is None, (text, rendered)
            checked += 1
    assert checked > 0, "vacuous walk: gloss linked nothing across every summary"


def test_an_entry_with_defined_on_shows_where_you_meet_it(client: TestClient) -> None:
    body = _body(client, "/glossary")
    key, entry = next((k, e) for k, e in GLOSSARY.items() if e.defined_on)
    section = body[body.index(f'id="{key}"') :]
    section = section[: section.index("</dd>")]
    assert "Where you meet it" in section, key
    for path in entry.defined_on:
        assert f'href="{path}"' in section, f"{key}: {path} not linked"


def test_an_entry_without_defined_on_shows_no_where_you_meet_it_line(
    client: TestClient,
) -> None:
    body = _body(client, "/glossary")
    key, _ = next((k, e) for k, e in GLOSSARY.items() if not e.defined_on)
    section = body[body.index(f'id="{key}"') :]
    section = section[: section.index("</dd>")]
    assert "Where you meet it" not in section, key


def test_gloss_leaves_text_untouched_when_the_glossary_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_link_first``'s own guard clause — the live ``GLOSSARY`` is never
    empty (``test_glossary_is_non_empty``), so this drives it the only way it
    can be reached: with ``_KEY_BY_TERM`` cleared, proving a run with no
    terms to find returns the text unchanged rather than raising on the
    lookup table it no longer has."""
    monkeypatch.setattr(templating, "_KEY_BY_TERM", {})
    text = "a baseline and a critical path, mentioned twice"
    assert str(gloss(text)) == text


def test_an_unlabelable_defined_on_path_fails_loudly_rather_than_rendering_blank() -> None:
    """``_page_label``'s own guard clause. Every live ``defined_on`` path is a
    real page with a name (``test_every_defined_on_path_is_a_real_page``), so
    this drives the clause the only way it can be reached: a path no registry
    and no nav entry can name. The contract is that such a path raises here,
    when the page is built, rather than reaching a reader as a link with an
    empty word in it."""
    with pytest.raises(KeyError, match="no label source"):
        _page_label("/techniques/not-a-technique")
