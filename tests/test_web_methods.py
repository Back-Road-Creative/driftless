"""The method-profile pages: ``GET /methods`` and ``GET /methods/{key}``.

Mirrors :mod:`tests.test_web_techniques`'s shape over the much smaller
:data:`driftless.pmbok.methods.METHODS` registry: no as-of (the registry is
frozen), every profile reachable from the index, every practice of every
profile rendered on its detail page, and an unknown key 404s rather than 500s.
"""

from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

from driftless.pmbok.method_content import CONTENT as METHOD_CONTENT
from driftless.pmbok.methods import METHODS
from driftless.pmbok.practice_content import CONTENT as PRACTICE_CONTENT
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


_GLOSS_WRAPPER = re.compile(r'<dfn><a href="/glossary#[^"]*">|</a></dfn>')


def _ungloss(body: str) -> str:
    """``body`` with the ``gloss`` filter's wrapper removed around whichever word it
    first linked — the same restoration ``test_web_artifacts._ungloss`` applies, so a
    prose field's exact registry string is matched contiguously rather than split
    around a term the filter wrapped."""
    return _GLOSS_WRAPPER.sub("", body)


def test_a_summary_containing_a_glossary_term_is_glossed(client: TestClient) -> None:
    """``method.plain_summary`` and ``practice.plain_summary`` go through the same
    ``gloss`` filter every other detail page pipes its prose through — a reader who
    does not already know "backlog" gets the same link here as on ``/pmbok/{id}``."""
    body = _body(client, "/methods/scrum")
    assert '<dfn><a href="/glossary#backlog">backlog</a></dfn>' in body


def test_a_detail_page_names_every_practice_of_its_method(client: TestClient) -> None:
    checked = 0
    for method in METHODS.values():
        body = _ungloss(_body(client, f"/methods/{method.key}"))
        assert method.display_name in body, method.key
        assert method.source_version in body, method.key
        for practice in method.practices:
            assert practice.display_name in body, f"{method.key}.{practice.key}"
            assert practice.plain_summary in body, f"{method.key}.{practice.key}"
            checked += 1
    assert checked > 0, "vacuous walk: no method carries a practice at all"


def test_a_detail_page_gives_working_material_for_its_method(client: TestClient) -> None:
    """Each method's page shows the working material ``method_content.CONTENT``
    records for it — a sprint-planning agenda and a Definition of Done checklist
    for Scrum, a board-policy template for Kanban — never a bare crosswalk table."""
    checked = 0
    for key, blocks in METHOD_CONTENT.items():
        body = _body(client, f"/methods/{key}")
        assert blocks, f"vacuous walk: {key} carries no working material"
        for block in blocks:
            assert block.heading in body, f"{key}: {block.heading}"
            for item in block.items:
                assert item in body, f"{key}: {block.heading}: {item}"
                checked += 1
    assert checked > 0, "vacuous walk: no method carries a working-material item"
    assert METHOD_CONTENT, "vacuous walk: the content registry is empty"


def test_every_practice_content_key_names_a_real_practice(client: TestClient) -> None:
    """A typo'd key in ``practice_content.CONTENT`` would silently never render;
    catch it against the registry rather than the page."""
    all_keys = {practice.key for method in METHODS.values() for practice in method.practices}
    for key in PRACTICE_CONTENT:
        assert key in all_keys, f"practice_content.CONTENT has an unknown key: {key}"


def test_a_practice_with_deeper_content_shows_how_it_is_run(client: TestClient) -> None:
    """A practice named in ``practice_content.CONTENT`` gets its "running it well"
    and "going wrong" material on the method's own page, not just its one-sentence
    summary."""
    checked = 0
    for key, detail in PRACTICE_CONTENT.items():
        method = next(m for m in METHODS.values() if any(p.key == key for p in m.practices))
        body = _ungloss(_body(client, f"/methods/{method.key}"))
        assert detail.running_it, f"vacuous walk: {key} carries no running_it material"
        assert detail.going_wrong, f"vacuous walk: {key} carries no going_wrong material"
        for item in detail.running_it:
            assert item in body, f"{key}: running_it: {item}"
            checked += 1
        for item in detail.going_wrong:
            assert item in body, f"{key}: going_wrong: {item}"
            checked += 1
    assert checked > 0, "vacuous walk: no practice carries deeper content"
    assert PRACTICE_CONTENT, "vacuous walk: the practice content registry is empty"


def test_a_practice_without_deeper_content_renders_no_running_it_section(
    client: TestClient,
) -> None:
    """A practice absent from ``practice_content.CONTENT`` must not leave behind an
    empty "how it's run" section — the template renders cleanly with nothing there."""
    key_with_no_entry = next(
        p.key for m in METHODS.values() for p in m.practices if p.key not in PRACTICE_CONTENT
    )
    method = next(
        m for m in METHODS.values() if any(p.key == key_with_no_entry for p in m.practices)
    )
    body = _body(client, f"/methods/{method.key}")
    assert f'id="{key_with_no_entry}-running-it"' not in body


def test_the_kanban_page_links_its_board_only_with_a_project_in_scope(
    client: TestClient,
) -> None:
    body = _body(client, "/methods/kanban?project=1")
    assert 'href="/projects/1/board"' in body


def test_the_kanban_page_has_no_board_link_without_a_project(client: TestClient) -> None:
    body = _body(client, "/methods/kanban")
    assert "/projects/1/board" not in body


def test_scrum_has_no_project_link_even_with_a_project_in_scope(client: TestClient) -> None:
    """No sprint or flow route exists for Scrum today, so the page must not
    fabricate one — the same rule the technique page follows for assist links."""
    body = _body(client, "/methods/scrum?project=1")
    assert "/projects/1/" not in body


def test_the_index_lists_every_method_and_links_to_its_page(client: TestClient) -> None:
    body = _body(client, "/methods")
    for method in METHODS.values():
        assert f'href="/methods/{method.key}"' in body, method.key
        assert method.display_name in body, method.key
        assert method.plain_summary in body, method.key
    assert METHODS, "vacuous walk: the registry is empty"


def test_an_unknown_method_key_404s_rather_than_500s(client: TestClient) -> None:
    assert client.get("/methods/safe").status_code == 404
    assert client.get("/methods/xp").status_code == 404


def test_the_library_is_reachable_from_the_primary_nav(client: TestClient) -> None:
    assert 'href="/methods"' in _body(client, "/")


def test_the_index_carries_a_coverage_count_that_sums_to_the_dt_count(
    client: TestClient,
) -> None:
    body = _body(client, "/methods")
    dt_count = body.count("<dt>")
    assert dt_count == len(METHODS), "the count line must describe the rendered rows"

    fully_crosswalked = sum(
        1 for method in METHODS.values() if all(practice.crosswalk for practice in method.practices)
    )
    with_guide_only = len(METHODS) - fully_crosswalked
    assert with_guide_only, "vacuous walk: no method has a guide-only practice"
    assert fully_crosswalked, "vacuous walk: no method is fully crosswalked"

    expected = (
        f"{len(METHODS)} methods · {fully_crosswalked} fully crosswalked · "
        f"{with_guide_only} with a guide-only practice"
    )
    assert expected in body


def test_the_index_explains_crosswalked_and_guide_only_and_links_the_glossary(
    client: TestClient,
) -> None:
    body = " ".join(_body(client, "/methods").split())
    assert 'href="/glossary#crosswalk"' in body, "crosswalk is never linked to its definition"
    assert "PMBOK-6 process or technique" in body, "the explanation never says what a crosswalk is"
    assert "no PMBOK-6 equivalent" in body, "the explanation never says what guide-only means"
