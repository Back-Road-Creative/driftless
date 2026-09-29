"""``driftless.web.related``: one shared "Related" block for a Method page.

``for_artifact`` is adopted on the artifact page, ``for_technique`` on the
technique page and ``for_theory_index`` on ``/pmbok``; ``for_process`` is not on a
page yet (that is a later PR's work). What this pins is the module's own contract
— totality over the closed registry, determinism, and that every href it produces
resolves through the running app — plus, for each page that adopted it, that the
block a reader opens is the one built for that technique, artifact or index.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from driftless.naming import technique_slug
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.catalog import PROCESSES
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.methods import METHODS
from driftless.web import related
from driftless.web.templating import TEMPLATES
import test_web_pages

client = test_web_pages.client
db = test_web_pages.db


def _hrefs(r: related.Related) -> list[str]:
    return [link.href for group in r.groups for link in group.links]


def test_every_process_has_a_related_block() -> None:
    for process in PROCESSES:
        assert related.for_process(process.id).groups, f"process {process.id}: no groups"


def test_calls_are_deterministic() -> None:
    assert related.for_process("4.1") == related.for_process("4.1")


def test_every_href_resolves(client: TestClient) -> None:
    seen: set[str] = set()
    for process in PROCESSES:
        seen.update(_hrefs(related.for_process(process.id)))

    assert seen, "nothing to check"
    for href in sorted(seen):
        page = client.get(href)
        assert page.status_code == 200, f"{href} -> {page.status_code}"


def test_macro_renders_a_labelled_section_and_lists() -> None:
    macro = TEMPLATES.env.get_template("_related.html").module.related  # type: ignore[attr-defined]
    r = related.for_process("4.1")
    html = str(macro(r, id_prefix="t"))

    assert '<section class="related" aria-labelledby="t-heading">' in html
    assert '<h2 id="t-heading">Related</h2>' in html
    for index in range(len(r.groups)):
        assert f'id="t-{index}"' in html
        assert f'aria-labelledby="t-{index}"' in html
    for group in r.groups:
        for link in group.links:
            assert f'href="{link.href}"' in html


def test_macro_renders_nothing_for_an_empty_related() -> None:
    macro = TEMPLATES.env.get_template("_related.html").module.related  # type: ignore[attr-defined]
    html = str(macro(related.Related(groups=())))
    assert "<section" not in html


def test_every_practice_has_a_related_block() -> None:
    for method in METHODS.values():
        for practice in method.practices:
            assert related.for_practice(practice.key).groups, f"practice {practice.key}: no groups"


def test_every_term_has_a_related_block() -> None:
    for key in GLOSSARY:
        assert related.for_term(key).groups, f"term {key}: no groups"


def test_a_practice_links_what_its_crosswalk_names_and_its_siblings_but_not_itself() -> None:
    hrefs = _hrefs(related.for_practice("sprint"))

    assert "/pmbok/6.5" in hrefs, "the crosswalked process is missing"
    assert "/techniques/rolling-wave-planning" in hrefs, "the crosswalked technique is missing"
    assert "/methods/scrum#sprint_review" in hrefs, "a sibling event is missing"
    assert "/methods/scrum#sprint" not in hrefs, "a practice lists itself as its own sibling"


def test_a_practice_with_no_crosswalk_still_reaches_the_map() -> None:
    """Two Kanban practices are deliberately guide-only, so nothing on the graph is
    theirs to focus — the block falls back to the whole map rather than vanishing."""
    assert "/map" in _hrefs(related.for_practice("start_with_what_you_do_now"))


def test_a_terms_index_reads_whole_words_only() -> None:
    """ "Encourage Leadership at Every Level" says "Every", not the term "EV" — the
    reverse index and the glossary group both match on word boundaries."""
    assert "/glossary#ev" not in _hrefs(related.for_practice("encourage_leadership_at_every_level"))
    assert "/methods/kanban#encourage_leadership_at_every_level" not in _hrefs(
        related.for_term("ev")
    )


def test_a_term_names_every_kind_of_page_that_mentions_it() -> None:
    hrefs = _hrefs(related.for_term("backlog"))
    assert "/methods/scrum#product_owner" in hrefs, "a practice mentioning the term is missing"
    assert "/glossary#backlog" not in hrefs, "a term lists itself"


def test_practice_and_term_calls_are_deterministic() -> None:
    assert related.for_practice("sprint") == related.for_practice("sprint")
    assert related.for_term("baseline") == related.for_term("baseline")


def test_every_practice_and_term_href_resolves(client: TestClient) -> None:
    seen: set[str] = set()
    for method in METHODS.values():
        for practice in method.practices:
            seen.update(_hrefs(related.for_practice(practice.key)))
    for key in GLOSSARY:
        seen.update(_hrefs(related.for_term(key)))

    assert seen, "nothing to check"
    for href in sorted(seen):
        page = client.get(href)
        assert page.status_code == 200, f"{href} -> {page.status_code}"


def test_for_map_reaches_the_catalogs_it_draws_from() -> None:
    hrefs = _hrefs(related.for_map())
    assert "/pmbok" in hrefs
    assert "/techniques" in hrefs
    assert "/artifacts" in hrefs
    assert "/process-map" in hrefs


def test_for_map_reaches_the_washed_projects_own_process_map() -> None:
    hrefs = _hrefs(related.for_map(project_id=1, project_name="Acme"))
    assert "/projects/1/process-map" in hrefs
    assert related.for_map() != related.for_map(project_id=1, project_name="Acme")


def test_for_map_is_deterministic() -> None:
    assert related.for_map() == related.for_map()
    assert related.for_map(project_id=1, project_name="Acme") == related.for_map(
        project_id=1, project_name="Acme"
    )


def test_every_technique_has_a_related_block_carrying_at_least_its_place_on_the_map() -> None:
    """Totality over the closed registry, and the floor that makes it hold.

    A technique no PMBOK process names — an extension, ``critical_chain_method``
    today — has no graph neighbour at all, so every "who uses this" group comes back
    empty for it. The map link is what keeps its block from being the one page the
    shared section silently skips, and it is asserted here per technique rather than
    once for a sampled one.
    """
    for key in TECHNIQUES:
        built = related.for_technique(key)
        assert built.groups, f"technique {key}: no groups"
        assert f"/map?focus=technique:{key}" in _hrefs(built), f"technique {key}: no map link"


def test_technique_calls_are_deterministic() -> None:
    key = sorted(TECHNIQUES)[0]
    assert related.for_technique(key) == related.for_technique(key)


def test_every_technique_href_resolves(client: TestClient) -> None:
    """Every address the technique blocks write, fetched from the running app — the
    walk ``tests/test_web_click_path_bound`` does over the whole surface, narrowed to
    the links this module is the author of."""
    seen: set[str] = set()
    for key in TECHNIQUES:
        seen.update(_hrefs(related.for_technique(key)))

    assert seen, "nothing to check"
    for href in sorted(seen):
        page = client.get(href)
        assert page.status_code == 200, f"{href} -> {page.status_code}"


def test_every_artifact_has_a_related_block_that_reaches_the_map() -> None:
    for key in sorted(ARTIFACT_KINDS):
        block = related.for_artifact(key)
        assert block.groups, f"artifact {key}: no groups"
        assert f"/map?focus=artifact:{key}" in _hrefs(block), f"artifact {key}: no map focus"


def test_an_artifact_block_names_its_processes_parts_family_and_techniques() -> None:
    block = related.for_artifact("scope_baseline")
    assert {"Made by", "Used by", "Parts", "Same family", "Techniques"} <= {
        group.title for group in block.groups
    }
    hrefs = _hrefs(block)
    assert "/pmbok/5.4" in hrefs, "5.4 Create WBS is what makes the scope baseline"
    assert "/artifacts/work-breakdown-structure" in hrefs, "the WBS is part of the scope baseline"
    assert "/techniques/decomposition" in hrefs, "a technique 5.4 uses is not reachable"


def test_a_component_kind_links_the_whole_it_belongs_to() -> None:
    block = related.for_artifact("work_breakdown_structure")
    assert "Part of" in {group.title for group in block.groups}
    assert "/artifacts/scope-baseline" in _hrefs(block)


def test_an_artifact_agile_evidence_covers_links_the_method_profiles() -> None:
    """``issue_log`` is a ``crosswalk.EQUIVALENCES`` key and ``project_charter`` is not,
    so the group is present for one and absent for the other rather than always shown."""
    assert "Agile equivalence" in {g.title for g in related.for_artifact("issue_log").groups}
    assert "Agile equivalence" not in {
        g.title for g in related.for_artifact("project_charter").groups
    }


def test_artifact_calls_are_deterministic() -> None:
    assert related.for_artifact("scope_baseline") == related.for_artifact("scope_baseline")


def test_every_artifact_href_resolves(client: TestClient) -> None:
    seen: set[str] = set()
    for key in sorted(ARTIFACT_KINDS):
        seen.update(_hrefs(related.for_artifact(key)))

    assert seen, "nothing to check"
    for href in sorted(seen):
        page = client.get(href)
        assert page.status_code == 200, f"{href} -> {page.status_code}"


def test_the_method_page_renders_one_block_per_practice(client: TestClient) -> None:
    body = client.get("/methods/scrum").text
    for practice in METHODS["scrum"].practices:
        assert f'id="{practice.key}"' in body, f"{practice.key} has no anchor to link to"
        assert f'aria-labelledby="related-{practice.key}-heading"' in body, practice.key


def test_the_glossary_page_renders_one_block_per_term(client: TestClient) -> None:
    body = client.get("/glossary").text
    for key in GLOSSARY:
        assert f'aria-labelledby="related-{key}-heading"' in body, key


def test_every_technique_page_renders_its_own_related_block(client: TestClient) -> None:
    """The adoption half: not that the module can build a block, but that the page a
    reader opens shows the one built for that technique.

    Walked over the whole registry rather than a chosen technique, so the extension
    with nothing but a map link is rendered here too — the case a page that only
    printed a non-empty group would drop.
    """
    for key in sorted(TECHNIQUES):
        body = client.get(f"/techniques/{technique_slug(key)}").text
        assert '<section class="related"' in body, f"{key}: the page renders no Related block"
        for group in related.for_technique(key).groups:
            assert f">{group.title}</h3>" in body, f"{key}: {group.title} is not on the page"
            for link in group.links:
                assert f'href="{link.href}"' in body, f"{key}: {link.href} is not on the page"


def test_the_artifact_page_renders_its_related_block(client: TestClient) -> None:
    body = client.get("/artifacts/scope-baseline").text
    assert '<section class="related"' in body
    for group in related.for_artifact("scope_baseline").groups:
        assert f">{group.title}</h3>" in body, group.title
        for link in group.links:
            assert f'href="{link.href}"' in body, link.href


def test_the_theory_index_strip_offers_every_other_method_hub() -> None:
    """A Method index's Related strip is the rest of the method reference, and never
    a link back to the page the reader is already on."""
    strip = related.for_theory_index("/pmbok")
    assert strip.groups, "no hub strip at all"
    assert "/pmbok" not in _hrefs(strip), "the strip links the page it is rendered on"
    assert set(_hrefs(strip)) == {"/techniques", "/artifacts", "/methods", "/map", "/process-map"}


def test_every_theory_index_strip_href_resolves(client: TestClient) -> None:
    for href in sorted(_hrefs(related.for_theory_index("/pmbok"))):
        page = client.get(href)
        assert page.status_code == 200, f"{href} -> {page.status_code}"
