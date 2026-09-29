"""The technique library on the web: ``GET /techniques`` and ``GET /techniques/{slug}``.

Driftless has held a full explanation of every ``tt.TT_CATALOG`` technique —
summary, when to use, when to avoid, ordered steps, outputs, pitfalls, a worked
example and a PMBOK-6 clause — with no page rendering any of it. An action's
``reference_href`` sent a reader who followed the app's own recommendation to an
ITTO list item bearing the technique's *name* and nothing else. These pages are
where that content becomes readable.

Every walk below is derived from the live registry rather than written down: the
index is checked against ``TT_CATALOG``, the detail fields against each
``TechniqueDefinition``'s own strings, and every address is built by calling
``driftless.web.templating.technique_slug`` — the one function the ITTO template
also reaches through its ``technique_slug`` filter. There is no second slug
formula in this file to hand-check against the first; there is one function,
called from both sides, and :func:`test_the_slug_index_is_a_bijection_over_the_whole_catalog`
proves it loses no technique on the way.
"""

from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from sqlalchemy.orm import Session

from driftless.assess.model import ASSISTANT_ROUTES, Action
from driftless.pmbok import catalog
from driftless.pmbok.definitions import (
    EXTENSION_SOURCE,
    PMBOK_SOURCE,
    PMBOK_SOURCE_VERSION,
    TECHNIQUES,
    TechniqueDefinition,
    TechniqueFamily,
)
from driftless.pmbok.provenance import MethodContext
from driftless.pmbok.reasons import UNCITED_EXEMPTIONS
from driftless.pmbok.tt import EXTENSION_REASONS, TT_CATALOG
from driftless.naming import technique_slug
from driftless.services.technique_runs import record_run
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.web.artifacts import BY_SLUG as ARTIFACT_BY_SLUG
from driftless.web.techniques import BY_SLUG, slug_index
from driftless.web.templating import TEMPLATES, uncited_reason
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db
AS_OF = test_web_pages.AS_OF


_GLOSS_WRAPPER = re.compile(r'<dfn><a href="/glossary#[^"]*">|</a></dfn>')


def _ungloss(body: str) -> str:
    """``body`` with the ``gloss`` filter's ``<dfn><a href="/glossary#…">…</a></dfn>``
    wrapper removed around whichever word it first linked, and every other
    character untouched.

    A technique's ``summary``/``when_to_use``/``when_to_avoid`` is glossed on the
    detail page, so a paragraph naming a term of art no longer appears in the body
    as one contiguous run of the registry's own string — the wrapper interrupts it
    mid-word. Stripping only the wrapper tags (never their text) restores that
    contiguity without weakening what a check below still requires: the registry's
    exact prose, once the markup around a linked word is peeled back off it.
    """
    return _GLOSS_WRAPPER.sub("", body)


def _body(client: TestClient, path: str) -> str:
    """A page's HTML, entities decoded once, so prose carrying ``&`` or an
    apostrophe is matched as the registry wrote it rather than as Jinja escaped it."""
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


def test_the_slug_index_is_a_bijection_over_the_whole_catalog() -> None:
    """Key -> slug -> key, for every member of the closed catalog, and no two keys
    sharing a slug.

    A collision would leave one technique reachable and the other silently gone —
    a 404 on a row the library itself lists — and nothing else in the tree would
    notice. ``slug_index`` refuses to build such a map at all, so this pins both
    halves: the map covers the catalog exactly, and it round-trips.
    """
    assert set(BY_SLUG.values()) == set(TT_CATALOG), "the index and the catalog disagree"
    assert len(BY_SLUG) == len(TT_CATALOG), "two keys collapsed onto one slug"
    for key in sorted(TT_CATALOG):
        assert BY_SLUG[technique_slug(key)] == key, key


def test_two_keys_that_would_share_a_slug_are_refused_rather_than_one_being_lost() -> None:
    """The collision branch, forced.

    The slug lowercases and turns ``_`` into ``-``, so any key written with a hyphen
    where another uses an underscore lands on the same word — as does any pair
    differing only in case. Both are shapes a future ``tt.py`` edit could introduce
    without a second thought, and in a naive dict the later one would simply
    overwrite the earlier, leaving a listed technique 404ing.
    """
    definition = TECHNIQUES[sorted(TT_CATALOG)[0]]
    assert technique_slug("expert_judgment") == technique_slug("expert-judgment")
    colliding = {"expert_judgment": definition, "expert-judgment": definition}
    with pytest.raises(ValueError, match="unreachable"):
        slug_index(colliding)


def test_the_index_reaches_every_technique_in_the_closed_catalog(client: TestClient) -> None:
    """One row per ``TT_CATALOG`` member, each linking to its own detail page.

    The walk is the catalog itself, so a technique added to a family in ``tt.py``
    is required here without anyone editing this file, and no count is pinned.
    """
    body = _body(client, "/techniques")
    for key in sorted(TT_CATALOG):
        definition = TECHNIQUES[key]
        assert f'href="/techniques/{technique_slug(key)}"' in body, key
        assert definition.display_name in body, key
        assert definition.summary in body, f"{key}: the index row carries no summary"
    assert len(TT_CATALOG) > 0, "vacuous walk: the closed catalog is empty"


def test_every_library_address_the_pages_write_is_one_the_router_answers(
    client: TestClient,
) -> None:
    """No page links into the library at an address the slug index does not hold.

    This is the half of "the reader never meets a raw identifier" that lives in the
    markup — the ITTO pages' own rule is pinned by ``tests/test_web_pages`` and
    ``tests/test_web_pmbok_drill``, which keying the route on the slug is what keeps
    passing. The other half, the rendered prose, is
    :func:`test_no_library_page_prints_a_raw_technique_identifier_anywhere_a_reader_reads`:
    this file used to scope it out, and two content entries promptly cross-referenced
    each other by raw key.
    """
    written = re.compile(r'href="/techniques/([^"#]+)"')
    pages = ["/techniques"] + [f"/pmbok/{p.id}" for p in catalog.PROCESSES]
    seen = 0
    for path in pages:
        for slug in written.findall(_body(client, path)):
            assert slug in BY_SLUG, f"{path} links to /techniques/{slug}, which 404s"
            seen += 1
    assert seen > 0, "vacuous walk: no page links into the library at all"


def test_the_index_groups_the_library_by_family(client: TestClient) -> None:
    """Every family the registry can name has a heading; the reader never meets one
    undifferentiated list of the whole catalog."""
    humanize = TEMPLATES.env.filters["humanize"]
    body = _body(client, "/techniques")
    families = {definition.family for definition in TECHNIQUES.values()}
    assert families == set(TechniqueFamily), "a declared family holds no technique at all"
    for family in families:
        assert humanize(family.value) in body, family.value


def test_a_detail_page_prints_every_populated_field_of_every_technique(
    client: TestClient,
) -> None:
    """Not one hand-picked exemplar: all of them, field by field.

    A field left empty in the registry is skipped rather than asserted, so a
    technique whose content is still thin does not fail here — but nothing the
    registry *does* hold may go unrendered.
    """
    humanize = TEMPLATES.env.filters["humanize"]
    checked = 0
    for slug, key in sorted(BY_SLUG.items()):
        definition: TechniqueDefinition = TECHNIQUES[key]
        body = _body(client, f"/techniques/{slug}")
        assert definition.display_name in body, key
        assert humanize(definition.family.value) in body, key
        for field in ("summary", "when_to_use", "when_to_avoid", "worked_example"):
            if prose := getattr(definition, field):
                assert prose in _ungloss(body), f"{key}: {field} is not on the page"
                checked += 1
        for field in ("steps", "outputs", "pitfalls", "further_reading"):
            for item in getattr(definition, field):
                assert item in body, f"{key}: {field} entry missing — {item[:60]}"
                checked += 1
    assert checked > 0, "vacuous walk: the registry holds no populated field at all"


def test_the_citation_is_the_registrys_own_and_never_invented(client: TestClient) -> None:
    """A technique with no ``further_reading`` gets no citation block — the page
    never manufactures a clause number for one the registry left blank."""
    for slug, key in sorted(BY_SLUG.items()):
        if not TECHNIQUES[key].further_reading:
            assert "PMBOK-6 §" not in _body(client, f"/techniques/{slug}"), key
    assert any(TECHNIQUES[k].further_reading for k in TT_CATALOG), (
        "vacuous: no technique carries a citation at all"
    )


def test_an_unknown_technique_slug_404s_rather_than_500s(client: TestClient) -> None:
    """Including the raw registry key, which is deliberately NOT an address here."""
    for missing in ("not-a-technique", "earned_value_analysis", "Earned-Value-Analysis"):
        assert client.get(f"/techniques/{missing}").status_code == 404, missing


def test_every_technique_a_process_names_links_from_its_itto_to_a_real_page(
    client: TestClient,
) -> None:
    """The gap this unit closes, checked from the surface a reader actually starts on:
    every Tools & Techniques entry on every process page is a link, and every one of
    those links resolves."""
    seen = 0
    for process in catalog.PROCESSES:
        body = _body(client, f"/pmbok/{process.id}")
        for key in process.tools_techniques:
            slug = technique_slug(key)
            assert f'href="/techniques/{slug}"' in body, f"{process.id}: {key}"
            assert client.get(f"/techniques/{slug}").status_code == 200, key
            seen += 1
    assert seen > 0, "vacuous walk: no process names a technique"


def test_every_reference_href_an_action_produces_answers_with_the_explanation(
    client: TestClient,
) -> None:
    """A real ``Action`` is built for every member of the closed catalog, and the
    address its ``reference_href`` gives is fetched from the running app — the exact
    hop a reader who follows a recommendation takes.

    The whole catalog rather than the techniques some process names, because that
    difference is the defect: an extension is tied to no PMBOK process by definition,
    so ``reference_href`` came back ``None`` for it and four surfaces said there was
    nothing to read, while ``/techniques/critical-chain-method`` answered 200 with the
    full page. Walking ``TT_CATALOG`` covers every such technique by construction
    rather than by anybody remembering to name one, and the closing assertion is that
    the walk really did reach all of them.

    Nothing here restates a slug: the address comes off the model, and what proves it
    is the right page is the registry's own display name and summary in the response.
    """
    walked = set()
    for key in sorted(TT_CATALOG):
        definition = TECHNIQUES[key]
        href = Action(f"probe:{key}", "label", key, "rationale", "project:1").reference_href
        body = _body(client, href)
        assert definition.display_name in body, f"{href} is not {key}'s page"
        assert definition.summary in _ungloss(body), f"{href} answers without {key}'s explanation"
        walked.add(key)
    assert walked == set(TT_CATALOG) and walked, "the walk must reach every catalog member"


def test_the_itto_deep_link_anchor_survives_the_recommendation_moving_off_it(
    client: TestClient,
) -> None:
    """``pmbok_detail.html`` still writes ``id="tt-{slug}"`` on every Tools &
    Techniques row, and this is what guards it now.

    Until this change the anchor's only guard was the one an ``Action`` addressed:
    the reference walk fetched ``/pmbok/{id}#tt-{slug}`` and looked the fragment up in
    the page. Recommendations land on ``/techniques/{slug}`` now, so nothing in the
    product links to the anchor and that guard would have gone with the href — leaving
    an id no test reads, which is how a template loses an attribute in a later tidy-up
    without anything noticing.

    The anchor is kept rather than deleted because it is a reader's address, not the
    app's: a process page lists up to a dozen techniques, and ``#tt-earned-value-analysis``
    is how a link in a note, a bookmark or a search result lands on the row rather than
    at the top of the list. It costs one attribute. What it may not do is drift from the
    slug the library is keyed by, so the walk asserts both on the same row.
    """
    seen = 0
    for process in catalog.PROCESSES:
        body = _body(client, f"/pmbok/{process.id}")
        for key in process.tools_techniques:
            slug = technique_slug(key)
            assert f'id="tt-{slug}"' in body, f"{process.id}: {key} has no deep-link anchor"
            assert f'href="/techniques/{slug}"' in body, f"{process.id}: {key}"
            seen += 1
    assert seen > 0, "vacuous walk: no process names a technique"


def test_the_library_is_reachable_from_the_primary_nav(client: TestClient) -> None:
    assert 'href="/techniques"' in _body(client, "/")


def _visible(body: str) -> str:
    """The page with the two places a raw technique word legitimately appears removed:
    the library address a link is written to, and the ITTO anchor a reference lands on.
    Both are slugs the router owns rather than prose, and neither is something a reader
    reads — what is left is what the page actually says."""
    body = re.sub(r'href="[^"]*"', "", body)
    body = re.sub(r'id="tt-[^"]*"', "", body)
    return body


#: The catalog keys a reader could not decode: an identifier is only distinguishable
#: from ordinary English by the underscore, because both the display name and the slug
#: spell it without one. A single-word key (``training``, ``negotiation``) is the same
#: string as the word for it, so no walk can tell prose from identifier there and this
#: one does not pretend to. Derived from ``TT_CATALOG`` and ``ARTIFACT_KINDS``, never
#: written down — the two closed vocabularies an ITTO table can name.
_IDENTIFIER_KEYS = sorted(key for key in TT_CATALOG if "_" in key)
_ARTIFACT_IDENTIFIER_KEYS = sorted(key for key in ARTIFACT_KINDS if "_" in key)


def test_no_library_page_prints_a_raw_technique_identifier_anywhere_a_reader_reads(
    client: TestClient,
) -> None:
    """The whole library, page by page and key by key — not one hand-named exemplar.

    ``tests/test_web_pmbok_drill`` asserts one chosen key is absent, which is a sample
    rather than a property; and this module used to put prose out of scope entirely, on
    the argument that an explanation may name another technique's key on purpose. It may
    not: a reader who meets ``knowledge_management`` in a sentence has to decode it,
    which is the thing the slug-keyed route exists to prevent. A cross-reference is
    written the way a reader would say it, so the whole rendered body is in scope here —
    every technique's content, on every page it reaches.
    """
    pages = ["/techniques"] + [f"/techniques/{slug}" for slug in sorted(BY_SLUG)]
    for path in pages:
        visible = _visible(_body(client, path))
        leaked = [key for key in _IDENTIFIER_KEYS if key in visible]
        assert not leaked, f"{path} prints raw identifiers a reader must decode: {leaked}"
    assert _IDENTIFIER_KEYS, "vacuous walk: no catalog key is an identifier at all"


def test_no_page_prints_a_raw_artifact_identifier_anywhere_a_reader_reads(
    client: TestClient,
) -> None:
    """The artifact vocabulary's counterpart, over every surface an ITTO table can name
    one on: the technique library (a technique's worked example or pitfalls could
    mention one), the PMBOK reference grid's own process detail pages, and the artifact
    catalog itself. ``test_web_pages`` used to pin one process (``4.1``) and one key
    (``business_case``) each way — a sample, not a property, and this walk is what
    replaces it: every process, every artifact kind, on every page any of them reaches.
    """
    pages = (
        ["/techniques"]
        + [f"/techniques/{slug}" for slug in sorted(BY_SLUG)]
        + ["/pmbok"]
        + [f"/pmbok/{p.id}" for p in catalog.PROCESSES]
        + ["/artifacts"]
        + [f"/artifacts/{slug}" for slug in sorted(ARTIFACT_BY_SLUG)]
    )
    for path in pages:
        visible = _visible(_body(client, path))
        leaked = [key for key in _ARTIFACT_IDENTIFIER_KEYS if key in visible]
        assert not leaked, f"{path} prints raw identifiers a reader must decode: {leaked}"
    assert _ARTIFACT_IDENTIFIER_KEYS, "vacuous walk: no artifact key is an identifier at all"


def test_every_family_fragment_a_page_writes_names_a_heading_on_the_index(
    client: TestClient,
) -> None:
    """The detail page's "back to the library" link lands on its family's heading.

    **This walk is the only thing holding the two halves together — do not delete it on
    the belief that a shared macro makes it redundant.** There is no such macro, and
    ``techniques.html`` says so in its own comment: the family's anchor word is written
    twice, once as ``id="family-{{ family }}"`` on the index and once as the
    ``href="/techniques#family-…"`` fragment on every detail page, because a macro
    cannot be shared across the two files (both extend ``base.html``, and importing a
    macro out of an extending template evaluates that template's own blocks).

    So the two copies are held together mechanically, here, over every family rather
    than a sampled one. Nothing else in the tree looks at fragments —
    :func:`test_every_library_address_the_pages_write_is_one_the_router_answers`
    excludes them by construction — so a fragment naming no id fails nowhere else, and
    the reader is dumped at the top of the whole catalog index instead of at the family
    they came from.
    """
    ids = set(re.findall(r'id="(family-[^"]+)"', _body(client, "/techniques")))
    reached = set()
    for slug in sorted(BY_SLUG):
        fragments = re.findall(r'href="/techniques#([^"]+)"', _body(client, f"/techniques/{slug}"))
        assert fragments, f"/techniques/{slug} writes no way back to its family"
        for fragment in fragments:
            assert fragment in ids, f"/techniques/{slug} links to #{fragment}, which no id names"
            reached.add(fragment)
    assert reached == ids, f"a family heading no detail page links to: {sorted(ids - reached)}"


def test_an_extension_is_exactly_a_technique_carrying_no_edition_string() -> None:
    """The equivalence the detail template's provenance branch rests on, walked over
    the whole registry rather than argued.

    ``definitions._source`` gives an extension an empty ``source_version`` and every
    PMBOK technique the one edition string, so the template can branch on "is there an
    edition to name?" without restating ``EXTENSION_SOURCE`` as a second copy of a
    constant. If that ever stops holding, this fails here rather than the page quietly
    telling a reader Driftless invented a technique out of the standard.
    """
    for key, definition in sorted(TECHNIQUES.items()):
        assert (definition.source == EXTENSION_SOURCE) == (not definition.source_version), key
        if definition.source_version:
            assert definition.source_version == PMBOK_SOURCE_VERSION, key
    sources = {definition.source for definition in TECHNIQUES.values()}
    assert sources == {PMBOK_SOURCE, EXTENSION_SOURCE}, sources


def test_every_technique_page_shows_exactly_one_support_tier_sentence(
    client: TestClient,
) -> None:
    """Every technique's detail page names its support tier in the newcomer's own
    words: "Runnable here" once ``ASSISTANT_ROUTES`` names it, else "Guide only —"
    followed by the exact ``GUIDE_ONLY_REASONS`` sentence — never both, never
    neither, and never a sentence the module itself did not produce."""
    from driftless.assess.model import ASSISTANT_ROUTES
    from driftless.web.techniques import support_tier

    for slug, key in sorted(BY_SLUG.items()):
        body = _body(client, f"/techniques/{slug}")
        expected = support_tier(key)
        assert expected in body, key
        runnable = "Runnable here" in body
        guide_only = "Guide only —" in body
        assert runnable != guide_only, f"{key}: exactly one tier sentence must render"
        assert runnable == (key in ASSISTANT_ROUTES), key


def test_every_detail_page_says_where_the_technique_came_from(client: TestClient) -> None:
    """Provenance rendered for all three shapes the registry can produce, each walked:
    a PMBOK technique with a clause, a PMBOK technique the registry left uncited, and a
    Driftless extension.

    ``source`` and ``source_version`` existed as fields with no template reading them,
    which left the one non-PMBOK technique in the catalog reading exactly like the
    standard's own. The machine half of the contract is the ``data-source`` /
    ``data-clause`` pair, taken from the registry entry rather than written here; the
    reader-facing half is that an extension never shows the edition string and an
    uncited technique never grows a clause number (the latter is
    :func:`test_the_citation_is_the_registrys_own_and_never_invented`'s job).
    """
    shapes: dict[tuple[str, str], int] = {}
    for slug, key in sorted(BY_SLUG.items()):
        definition = TECHNIQUES[key]
        body = _body(client, f"/techniques/{slug}")
        cited = "cited" if definition.further_reading else "none"
        assert f'data-source="{definition.source}"' in body, f"{key}: no provenance rendered"
        assert f'data-clause="{cited}"' in body, f"{key}: provenance misstates the citation"
        if definition.source_version:
            assert definition.source_version in body, f"{key}: the edition it comes from is unsaid"
        else:
            assert PMBOK_SOURCE_VERSION not in body, f"{key}: an extension claims an edition"
            assert "Driftless" in body, f"{key}: the page never says Driftless added it"
        shapes[definition.source, cited] = shapes.get((definition.source, cited), 0) + 1
    assert {(PMBOK_SOURCE, "cited"), (PMBOK_SOURCE, "none")} <= shapes.keys(), (
        f"vacuous: the registry holds no uncited PMBOK technique to read honestly, {shapes}"
    )
    assert EXTENSION_SOURCE in {source for source, _ in shapes}, (
        f"vacuous: no extension in the catalog, so its branch went unrendered, {shapes}"
    )


#: The one sentence every uncited technique page has always carried, whatever the
#: reason for the gap. It stays — it is true of all of them — and the recorded reason
#: now follows it where the page may print one.
GENERAL_CITATION_SENTENCE = "No clause number is recorded for it here"


def test_every_uncited_technique_page_gives_the_recorded_reason_there_is_no_clause(
    client: TestClient,
) -> None:
    """``reasons.UNCITED_EXEMPTIONS`` records, one by one, WHY PMBOK-6 gives a technique
    no clause number — narrative rather than a numbered clause, an umbrella group whose
    members carry the numbers, a tool of nearly every process, a clause ruled out. None
    of it reached a page: every uncited technique got the same general sentence, so a
    reader was told a clause was missing while the registry held the specific reason.

    Walked over the registry rather than a list written here, so a technique that gains
    or loses an exemption is covered without editing this file. Two shapes are not the
    general case and are asserted as themselves: an extension's page already prints the
    recorded reason it is one, and where the recorded sentence quotes the very clause
    that was ruled out and blanked, the page keeps the general sentence rather than
    putting a clause number on a technique that has none —
    :func:`test_the_citation_is_the_registrys_own_and_never_invented` outranks it.
    """
    shown = 0
    for slug, key in sorted(BY_SLUG.items()):
        definition = TECHNIQUES[key]
        body = _body(client, f"/techniques/{slug}")
        if definition.further_reading:
            assert GENERAL_CITATION_SENTENCE not in body, f"{key} is cited, yet the page hedges"
            continue
        assert key in UNCITED_EXEMPTIONS, f"{key} is uncited with no recorded reason"
        if not definition.source_version:
            assert EXTENSION_REASONS[key] in body, f"{key}: the extension reason is unsaid"
            continue
        assert GENERAL_CITATION_SENTENCE in body, f"{key}: the page does not own the gap"
        recorded = UNCITED_EXEMPTIONS[key].why
        if uncited_reason(key):
            assert recorded in body, f"{key}: the page omits the reason recorded for it"
            shown += 1
        else:
            assert "PMBOK-6 §" not in body, f"{key}: a withheld clause reached the page"
    assert shown, "vacuous: not one recorded reason reached a page"


def test_project_runs_are_listed_on_the_technique_page(client: TestClient, db: Session) -> None:
    """``?project=`` lists this project's recorded runs of the technique; without it
    the page carries no such block at all."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    assert "Runs on this project" not in _body(client, f"/techniques/{slug}")
    record_run(
        db,
        project_id=1,
        technique_key=key,
        process_id=catalog.PROCESSES[0].id,
        actor="jp",
        as_of=AS_OF,
        method=MethodContext.PREDICTIVE,
        source_version="PMBOK-6",
    )
    body = _body(client, f"/techniques/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert "Runs on this project" in body
    assert (
        f"Run on {AS_OF.isoformat()} by jp for "
        f'<a href="/pmbok/{catalog.PROCESSES[0].id}">{catalog.PROCESSES[0].id}</a>' in body
    )


def test_a_run_links_its_process_id_to_the_processs_own_page(
    client: TestClient, db: Session
) -> None:
    """A run's ``process_id`` used to sit on the page as bare text; it now links to
    the process page that address actually answers."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    process_id = catalog.PROCESSES[0].id
    record_run(
        db,
        project_id=1,
        technique_key=key,
        process_id=process_id,
        actor="jp",
        as_of=AS_OF,
        method=MethodContext.PREDICTIVE,
        source_version="PMBOK-6",
    )
    body = _body(client, f"/techniques/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert f'href="/pmbok/{process_id}"' in body, "the run's process_id is not linked"


def test_the_page_title_is_qualified_the_way_other_detail_pages_are(
    client: TestClient,
) -> None:
    """A bare display name in ``<title>`` cannot be told apart, in a browser tab or a
    search result, from any other page carrying the same words. Every other Driftless
    detail page (business, department, drill, error, project hub) qualifies its title
    with ``— driftless``; the technique page did not."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    body = _body(client, f"/techniques/{slug}")
    assert f"<title>{TECHNIQUES[key].display_name} — driftless</title>" in body


def test_a_runnable_technique_links_its_tier_sentence_to_the_assist_page(
    client: TestClient,
) -> None:
    """Once ``ASSISTANT_ROUTES`` names a launch route for a technique and a project
    is in scope (``?project=``), the "Runnable here" sentence is a link to it —
    never left as words pointing nowhere."""
    key, route = next(iter(ASSISTANT_ROUTES.items()))
    slug = technique_slug(key)
    href = route.format(project_id=1)
    body = _body(client, f"/techniques/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert f'<a href="{href}">Runnable here</a>' in body


def test_a_technique_with_no_assist_route_renders_plain_text_with_no_link(
    client: TestClient,
) -> None:
    """The negative case that catches a fabricated route: a technique
    ``ASSISTANT_ROUTES`` does not name must render its "Guide only —" sentence as
    plain text, never wrapped in a link to an address that does not exist."""
    key = next(k for k in TT_CATALOG if k not in ASSISTANT_ROUTES)
    slug = technique_slug(key)
    body = _body(client, f"/techniques/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert "Guide only —" in body
    tier_line = next(line for line in body.splitlines() if "Guide only —" in line)
    assert "<a href=" not in tier_line, tier_line


def test_an_unknown_project_404s_rather_than_rendering_an_empty_run_list(
    client: TestClient,
) -> None:
    """``?project=`` names a project the same way ``/pmbok/{process_id}`` does — a
    ``project_id`` an assist link is filled with and a run list is scoped to — so an
    id no ``Project`` row answers to must 404 the same way, not render as if the
    project had simply logged no runs yet."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    page = client.get(f"/techniques/{slug}?project=999999")
    assert page.status_code == 404


def test_a_real_projects_id_still_renders(client: TestClient) -> None:
    """The positive case beside the 404 above: a project the store actually holds
    keeps rendering exactly as it always has."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    page = client.get(f"/techniques/{slug}?project=1")
    assert page.status_code == 200


def test_a_technique_with_steps_renders_them_as_a_checklist(client: TestClient) -> None:
    """Steps are a checkable list, not plain numbered prose (TQ08): a reader can
    actually work from the page rather than merely read it. Every step gets its
    own checkbox, walked over a technique the registry actually gives steps to."""
    key = next(k for k in TT_CATALOG if TECHNIQUES[k].steps)
    slug = technique_slug(key)
    body = _body(client, f"/techniques/{slug}")
    assert body.count('class="steps-checklist"') == 1
    assert body.count('<li><label><input type="checkbox"') == len(TECHNIQUES[key].steps)


def test_arriving_with_a_project_gets_a_live_header_and_a_way_back(
    client: TestClient,
) -> None:
    """``?project=`` (NV23) gives the page a project breadcrumb trail and a back
    link to the project hub, the same live header ``pmbok_detail.html`` and
    ``artifact_detail.html`` already carry — so a reader who arrived from a
    project page is not stranded in theory with no way back."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    body = _body(client, f"/techniques/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert f'href="/projects/1/hub?as_of={AS_OF.isoformat()}"' in body
    assert "GMS" in body


def test_without_a_project_the_page_keeps_its_theory_breadcrumb(
    client: TestClient,
) -> None:
    """The plain, project-less page keeps linking back to the library, not a
    project hub it has no project for."""
    key = sorted(TT_CATALOG)[0]
    slug = technique_slug(key)
    body = _body(client, f"/techniques/{slug}")
    assert "/projects/" not in body


#: One rendered index row: the technique its name links to, and the tier cell that row
#: prints. Read off the table so a tier is tied to the technique it sits beside — a
#: substring check over the whole page would pass with every tier on the wrong row.
_INDEX_ROW = re.compile(
    r'<th scope="row"><a href="/techniques/([^"]+)">.*?</a></th>\s*<td>.*?</td>\s*<td>([^<]*)</td>',
    re.S,
)


def _index_tiers(client: TestClient) -> dict[str, str]:
    """``{technique key: the tier cell the index prints for it}``."""
    rows = _INDEX_ROW.findall(_body(client, "/techniques"))
    assert rows, "the index renders no technique row at all"
    return {BY_SLUG[slug]: tier.strip() for slug, tier in rows}


def test_the_index_gives_every_technique_a_support_tier_derived_from_the_registries(
    client: TestClient,
) -> None:
    """A reader can tell which techniques are runnable BEFORE opening one (TQ02).

    Every cell is derived from the three registries that decide it — ``ASSISTANT_ROUTES``,
    the worksheet registry, ``GUIDE_ONLY_REASONS`` — rather than typed per row, so a
    technique that gains an assistant or a worksheet changes its own row with no edit
    here. The guide-only cell is the registry's recorded sentence verbatim: a tier that
    paraphrased it would be a second copy to keep honest.
    """
    from driftless.assess.model import ASSISTANT_ROUTES
    from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
    from driftless.pmbok.worksheets import WORKSHEETS
    from driftless.web.techniques import RUNNABLE_TIER, WORKSHEET_TIER, index_support_tier

    tiers = _index_tiers(client)
    assert set(tiers) == set(TT_CATALOG), "the tier column misses a technique the index lists"
    for key in sorted(TT_CATALOG):
        assert tiers[key] == index_support_tier(key), key
        if key in ASSISTANT_ROUTES:
            assert tiers[key] == RUNNABLE_TIER, key
        elif key in WORKSHEETS:
            assert tiers[key] == WORKSHEET_TIER, key
        else:
            assert tiers[key] == GUIDE_ONLY_REASONS[key].why, key
    assert {RUNNABLE_TIER, WORKSHEET_TIER} <= set(tiers.values()), (
        "vacuous walk: the index met neither a runnable nor a worksheet technique"
    )


def test_the_index_says_what_every_family_it_groups_by_actually_is(client: TestClient) -> None:
    """A family heading names a grouping; it does not explain one (TQ01). The
    explanation is required for every member of the closed enum and for no other key,
    so a family added to the vocabulary cannot reach the page unexplained."""
    from driftless.pmbok.definitions import FAMILY_EXPLANATIONS

    assert set(FAMILY_EXPLANATIONS) == set(TechniqueFamily), (
        "a family with no explanation, or an explanation for a family that does not exist"
    )
    body = _body(client, "/techniques")
    for family in sorted(TechniqueFamily, key=lambda member: member.value):
        assert FAMILY_EXPLANATIONS[family], family.value
        assert FAMILY_EXPLANATIONS[family] in body, (
            f"{family.value}: the index never says what the family is for"
        )


def test_the_index_carries_a_tier_key_and_a_how_to_read_block_with_measured_counts(
    client: TestClient,
) -> None:
    """The legend names all three tiers and states how many techniques sit in each,
    counted off the registries rather than typed into the template (TQ01)."""
    from driftless.web.techniques import RUNNABLE_TIER, WORKSHEET_TIER, tier_counts

    body = _body(client, "/techniques")
    counts = tier_counts()
    assert sum(counts.values()) == len(TT_CATALOG), counts
    assert set(counts) == {"runnable", "worksheet", "guide"}, counts
    for tier in (RUNNABLE_TIER, WORKSHEET_TIER):
        assert tier in body, f"the key never names the {tier!r} tier"
    for label, count in sorted(counts.items()):
        assert f"{count} of {len(TT_CATALOG)}" in body, (
            f"the key never states, as a measured count, how many techniques are {label}"
        )
    assert '<details class="how-to-read">' in body, "the index carries no how-to-read block"
