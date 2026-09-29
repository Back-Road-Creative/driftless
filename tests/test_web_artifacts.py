"""The artifact catalog on the web: ``GET /artifacts`` and ``GET /artifacts/{slug}``.

``driftless.pmbok.artifact_definitions.ARTIFACTS`` held a full plain-language
explanation of every ``ARTIFACT_KINDS`` member — what it is, why it matters, what
it looks like on this product, which processes produce and read it, and whether
this product's store can track it — with no page rendering any of it. An ITTO
table showed only the humanized word for an artifact, with nowhere to click
through to. These pages are where that content becomes readable, addressed by
the same collision-refusing slug pattern ``web/techniques.py`` already proved.
"""

from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.models import Stakeholder
from driftless.pmbok import catalog, mapping
from driftless.pmbok.artifact_definitions import ARTIFACTS, ArtifactFamily
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.web.artifacts import BY_SLUG, artifact_slug, slug_index, spell_out_identifiers
from driftless.web.templating import TEMPLATES
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db
AS_OF = test_web_pages.AS_OF


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


_GLOSS_WRAPPER = re.compile(r'<dfn><a href="/glossary#[^"]*">|</a></dfn>')


def _ungloss(body: str) -> str:
    """``body`` with the ``gloss`` filter's wrapper removed around whichever word it
    first linked — the same restoration ``test_web_techniques._ungloss`` applies, so a
    prose field's exact registry string is matched contiguously rather than split
    around a term the filter wrapped."""
    return _GLOSS_WRAPPER.sub("", body)


def test_the_slug_index_is_a_bijection_over_the_whole_catalog() -> None:
    assert set(BY_SLUG.values()) == ARTIFACT_KINDS, "the index and the catalog disagree"
    assert len(BY_SLUG) == len(ARTIFACT_KINDS), "two keys collapsed onto one slug"
    for key in sorted(ARTIFACT_KINDS):
        assert BY_SLUG[artifact_slug(key)] == key, key


def test_two_keys_that_would_share_a_slug_are_refused_rather_than_one_being_lost() -> None:
    definition = ARTIFACTS[sorted(ARTIFACT_KINDS)[0]]
    assert artifact_slug("project_charter") == artifact_slug("project-charter")
    colliding = {"project_charter": definition, "project-charter": definition}
    with pytest.raises(ValueError, match="unreachable"):
        slug_index(colliding)


def test_the_index_reaches_every_artifact_in_the_closed_catalog(client: TestClient) -> None:
    body = _body(client, "/artifacts")
    for key in sorted(ARTIFACT_KINDS):
        definition = ARTIFACTS[key]
        assert f'href="/artifacts/{artifact_slug(key)}"' in body, key
        assert definition.display_name in body, key
    assert len(ARTIFACT_KINDS) > 0, "vacuous walk: the closed catalog is empty"


def test_the_index_groups_the_catalog_by_family(client: TestClient) -> None:
    humanize = TEMPLATES.env.filters["humanize"]
    body = _body(client, "/artifacts")
    families = {definition.family for definition in ARTIFACTS.values()}
    assert families == set(ArtifactFamily), "a declared family holds no artifact at all"
    for family in families:
        assert humanize(family.value) in body, family.value


def _index_row(body: str, slug: str) -> str:
    """The one ``<dt>``/``<dd>`` pair the index renders for ``slug`` — everything
    from its link's ``<dt>`` up to the next ``</dd>``, so a per-row assertion
    cannot accidentally match a neighboring artifact's row."""
    start = body.index(f'href="/artifacts/{slug}"')
    end = body.index("</dd>", start)
    return body[start:end]


def test_the_index_marks_each_kind_tracked_or_not_from_the_resolver(
    client: TestClient,
) -> None:
    """AR02: a reader must be able to tell, from the index alone, which kinds
    this product's store can actually resolve. The marker is driven off
    ``mapping.is_tracked`` / ``mapping.UNTRACKED_DISPOSITIONS`` — the same
    resolver partition the detail page already reads through ``tracked_by`` —
    never a second, hand-typed list."""
    body = _ungloss(_body(client, "/artifacts"))
    tracked = untracked = 0
    for key in sorted(ARTIFACT_KINDS):
        row = _index_row(body, artifact_slug(key))
        if mapping.is_tracked(key):
            tracked += 1
            assert "Not tracked" not in row, key
        else:
            untracked += 1
            assert "Not tracked" in row, key
            assert spell_out_identifiers(mapping.UNTRACKED_DISPOSITIONS[key]) in row, (
                f"{key}: disposition sentence is not on the index row"
            )
    assert tracked and untracked, "vacuous: every artifact reads the same tracking answer"


def test_the_index_explains_what_each_family_is(client: TestClient) -> None:
    """AR07: a family heading with nothing saying what a family IS leaves a
    reader guessing why these kinds are grouped together. Every family gets a
    short plain-words explanation, and no two families share the same one."""
    body = _body(client, "/artifacts")
    notes = set()
    for family in ArtifactFamily:
        heading = f'<h2 id="family-{family.value}">'
        assert heading in body, family.value
        start = body.index(heading)
        end = body.index("<dl", start)
        section = body[start:end]
        match = re.search(r'<p class="family-note">(.*?)</p>', section, re.S)
        assert match, f"{family.value}: no family-note prose after its heading"
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        assert len(text) > 20, f"{family.value}: family note is too thin to explain anything"
        notes.add(text)
    assert len(notes) == len(list(ArtifactFamily)), "two families share the same explanation"


def test_a_detail_page_shows_what_it_is_why_it_matters_and_what_it_looks_like_here(
    client: TestClient,
) -> None:
    checked = 0
    for slug, key in sorted(BY_SLUG.items()):
        definition = ARTIFACTS[key]
        body = _body(client, f"/artifacts/{slug}")
        assert definition.display_name in body, key
        assert "What it is" in body
        assert "Why it matters" in body
        assert "What it looks like here" in body
        for field in ("plain_summary", "why_it_matters", "what_it_looks_like_here"):
            if prose := getattr(definition, field):
                assert prose in _ungloss(body), f"{key}: {field} is not on the page"
                checked += 1
    assert checked > 0, "vacuous walk: the registry holds no populated field at all"


def test_a_detail_page_links_every_process_that_produces_or_reads_it(
    client: TestClient,
) -> None:
    seen = 0
    for slug, key in sorted(BY_SLUG.items()):
        definition = ARTIFACTS[key]
        body = _body(client, f"/artifacts/{slug}")
        for process_id in definition.produced_by:
            assert f'href="/pmbok/{process_id}"' in body, f"{key}: not made by {process_id}"
            seen += 1
        for process_id in definition.read_by:
            assert f'href="/pmbok/{process_id}"' in body, f"{key}: not used by {process_id}"
            seen += 1
    assert seen > 0, "vacuous walk: no artifact names a producing or reading process"


def test_a_detail_page_says_whether_this_product_tracks_the_artifact(
    client: TestClient,
) -> None:
    tracked = untracked = 0
    for slug, key in sorted(BY_SLUG.items()):
        body = _body(client, f"/artifacts/{slug}")
        if ARTIFACTS[key].tracked_by:
            tracked += 1
            assert "does not track" not in body
        else:
            untracked += 1
            assert "does not track" in body
    assert tracked and untracked, "vacuous: every artifact reads the same tracking answer"


def test_an_unknown_artifact_slug_404s_rather_than_500s(client: TestClient) -> None:
    for missing in ("not-an-artifact", "project_charter", "Project-Charter"):
        assert client.get(f"/artifacts/{missing}").status_code == 404, missing


def test_every_itto_row_on_a_process_page_links_to_a_real_artifact_page(
    client: TestClient,
) -> None:
    seen = 0
    for process in catalog.PROCESSES:
        body = _body(client, f"/pmbok/{process.id}")
        for key in (*process.inputs, *process.outputs):
            slug = artifact_slug(key)
            assert f'href="/artifacts/{slug}"' in body, f"{process.id}: {key}"
            assert client.get(f"/artifacts/{slug}").status_code == 200, key
            seen += 1
    assert seen > 0, "vacuous walk: no process names an artifact"


def test_the_catalog_is_reachable_from_the_primary_nav(client: TestClient) -> None:
    assert 'href="/artifacts"' in _body(client, "/")


def test_a_project_scoped_detail_page_shows_what_the_store_answers_for_it(
    client: TestClient,
) -> None:
    """``?project=`` carries the pinned as-of through the hop, the same convention
    ``/pmbok/{id}?project=`` already reads — and answers with the store's own
    resolved status for this one kind rather than dropping the reader at a dead
    end (the theory page they came from already told them)."""
    slug = artifact_slug("project_charter")
    resp = client.get(f"/artifacts/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert resp.status_code == 200
    assert 'class="badge st-' in resp.text, "no artifact status badge rendered at all"


def test_a_present_and_healthy_artifact_reads_healthy(client: TestClient, db: Session) -> None:
    """``project_charter`` above is UNTRACKED, so that test can only ever reach
    ``_cell``'s "not tracked" branch. ``stakeholder_register`` is both tracked
    and, once a stakeholder is on record, always healthy the moment it is
    present — the one other ``_cell`` branch."""
    db.add(Stakeholder(project_id=1, name="Ada", interest="high", influence="high"))
    db.commit()
    slug = artifact_slug("stakeholder_register")
    resp = client.get(f"/artifacts/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert resp.status_code == 200
    assert "healthy" in resp.text


def test_a_live_detail_page_carries_project_and_as_of_onto_its_process_links(
    client: TestClient,
) -> None:
    """AR05/NV22: a reader who arrived with a project in scope must not lose it on
    the first hop off the page — ``/pmbok/{id}`` carries the same ``?project=`` and
    ``&as_of=`` pair ``/pmbok/{id}`` itself already carries onward for a live ITTO
    row, and the page gains a way back to this project's own process map."""
    key = "project_charter"
    definition = ARTIFACTS[key]
    slug = artifact_slug(key)
    query = f"?project=1&as_of={AS_OF.isoformat()}"
    body = _body(client, f"/artifacts/{slug}{query}")
    for process_id in (*definition.produced_by, *definition.read_by):
        assert f'href="/pmbok/{process_id}{query}"' in body, process_id
    assert f"/projects/1/process-map?as_of={AS_OF.isoformat()}" in body


def test_a_theory_mode_detail_page_links_pmbok_pages_bare(client: TestClient) -> None:
    key = "project_charter"
    definition = ARTIFACTS[key]
    slug = artifact_slug(key)
    body = _body(client, f"/artifacts/{slug}")
    for process_id in (*definition.produced_by, *definition.read_by):
        assert f'href="/pmbok/{process_id}"' in body, process_id
        assert f'href="/pmbok/{process_id}?' not in body, process_id


def test_an_untracked_artifact_s_own_page_says_why(client: TestClient) -> None:
    """Q23: the disposition sentence already exists in
    ``mapping.UNTRACKED_DISPOSITIONS`` and already reaches the index page — this is
    the artifact's own detail page saying the same thing, glossed through the same
    ``spell_out_identifiers`` helper rather than a second one."""
    key = "project_charter"
    slug = artifact_slug(key)
    body = _ungloss(_body(client, f"/artifacts/{slug}"))
    assert spell_out_identifiers(mapping.UNTRACKED_DISPOSITIONS[key]) in body


def test_a_theory_mode_detail_page_says_a_project_s_process_map_can_narrow_it(
    client: TestClient,
) -> None:
    """AR06: ``artifact_detail`` accepts ``?project=`` (``artifacts.py`` docstring),
    but nothing on the page told a theory-mode reader that link exists or how to
    reach it. A reader arrives at this scoping the same way every other live
    reading is reached — off a project's own process map — so the page says so."""
    slug = artifact_slug("project_charter")
    body = _body(client, f"/artifacts/{slug}")
    assert "project's own process map" in body


def test_a_tracked_but_absent_artifact_reads_absent(client: TestClient) -> None:
    """``issue_log`` is tracked (the store CAN answer for it) but this project
    has no issues on record — present is false, tracked is true — ``_cell``'s
    middle branch, between "healthy/at risk" and "not tracked". (It used to be
    ``risk_register``, until the shared seed grew an open risk for the
    risk-response planner's filing form.)"""
    slug = artifact_slug("issue_log")
    resp = client.get(f"/artifacts/{slug}?project=1&as_of={AS_OF.isoformat()}")
    assert resp.status_code == 200
    assert "absent" in resp.text
