"""A process page reads as an explanation, not a reference table.

``ProcessContent`` has carried four explanation fields per process since it was
built, and the page rendered exactly one of them: the summary. ``why_bother``,
``done_when`` and ``first_time_tip`` were filled for all 49 processes and shown
for none, so the page opened straight into three ITTO lists and left a newcomer
to infer why the step exists at all.

These walk the whole catalog rather than one exemplar -- every process must
explain itself, in the registry's own words -- and pin the three navigation
facts that make the page a hub rather than a dead end: the summary's terms link
to the glossary, the shared "Related" block is actually on the page, and a page
opened from a project's map carries that project and the pinned as-of onward
instead of dropping the reader into theory.
"""

from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

import test_web_pages
from driftless.naming import technique_slug
from driftless.pmbok import catalog
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.web import related
from driftless.web.templating import TEMPLATES, artifact_slug

client, db = test_web_pages.client, test_web_pages.db
AS_OF = test_web_pages.AS_OF
LIVE = "/pmbok/{}?project=1&as_of=" + AS_OF.isoformat()
#: The process the drill tests already lean on: it sits in the area the seeded
#: fixture makes red, so its live page is a real drill rather than an empty one.
DRILLED = "7.4"

gloss = TEMPLATES.env.filters["gloss"]

#: The three fields the page never rendered, and the heading each is shown under.
EXPLANATIONS = (
    ("why_bother", "Why it matters"),
    ("done_when", "What done looks like"),
    ("first_time_tip", "First time tip"),
)


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


def test_every_process_page_explains_itself_in_the_registrys_own_words(
    client: TestClient,
) -> None:
    """Walked over the whole catalog: each of the three fields is on its own
    process's page, under its own heading, verbatim -- so a field filled in the
    registry and dropped by the template fails here naming the process."""
    checked = 0
    for process in catalog.PROCESSES:
        definition = PROCESS_DEFINITIONS[process.id]
        body = _body(client, f"/pmbok/{process.id}")
        for field, heading in EXPLANATIONS:
            prose = getattr(definition, field)
            assert prose, f"{process.id}: the registry holds no {field} to render"
            assert f"<h2>{heading}</h2>" in body, f"{process.id}: no {heading!r} section"
            assert prose in body, f"{process.id}: {field} is not on the page"
            checked += 1
    assert checked > 0, "vacuous walk: the catalog holds no process at all"


def test_a_process_summary_links_its_terms_to_the_glossary(client: TestClient) -> None:
    """The summary is glossed, so a reader meeting "baseline" on a process page
    reaches its definition the same way a technique page already lets them."""
    glossed = [
        process.id
        for process in catalog.PROCESSES
        if "/glossary#" in str(gloss(PROCESS_DEFINITIONS[process.id].plain_summary))
    ]
    assert glossed, "vacuous: no process summary names a glossary term at all"
    for process_id in glossed:
        body = _body(client, f"/pmbok/{process_id}")
        assert 'href="/glossary#' in body, f"{process_id}: its summary is not glossed"


def test_every_glossary_link_a_process_page_writes_is_a_real_entry(client: TestClient) -> None:
    """No process page links into the glossary at an address ``GLOSSARY`` lacks."""
    seen = 0
    for process in catalog.PROCESSES:
        body = _body(client, f"/pmbok/{process.id}")
        for key in re.findall(r'href="/glossary#([^"]+)"', body):
            assert key in GLOSSARY, f"/pmbok/{process.id} links #{key}, which 404s"
            seen += 1
    assert seen > 0, "vacuous walk: no process page links into the glossary"


def test_every_process_page_carries_the_shared_related_block(client: TestClient) -> None:
    """``driftless.web.related.for_process`` is on the page, not just in the tree:
    every group it builds, and every link in it, is rendered."""
    checked = 0
    for process in catalog.PROCESSES:
        body = _body(client, f"/pmbok/{process.id}")
        assert '<section class="related"' in body, f"{process.id}: no Related block"
        for group in related.for_process(process.id).groups:
            assert group.title in body, f"{process.id}: no {group.title!r} group"
            for link in group.links:
                assert f'href="{link.href}"' in body, f"{process.id}: {link.href}"
                checked += 1
    assert checked > 0, "vacuous walk: the Related block holds no link at all"


def test_a_live_process_page_carries_the_project_and_as_of_onward(client: TestClient) -> None:
    """Opened from a project's map, the ITTO and map links keep the project and
    the pinned as-of, so the drill does not dead-end in theory one hop later."""
    process = catalog.get(DRILLED)
    body = _body(client, LIVE.format(process.id))
    carried = f"?project=1&as_of={AS_OF.isoformat()}"
    seen = 0
    for key in (*process.inputs, *process.outputs):
        assert f'href="/artifacts/{artifact_slug(key)}{carried}"' in body, key
        seen += 1
    for key in process.tools_techniques:
        assert f'href="/techniques/{technique_slug(key)}{carried}"' in body, key
        seen += 1
    assert seen > 0, f"vacuous: {DRILLED} names no input, output or technique"
    assert f'href="/map?focus=process:{process.id}&project=1&as_of=' in body


def test_the_theory_page_keeps_its_bare_links(client: TestClient) -> None:
    """The other reading mode is unchanged: with no project there is no project to
    carry, and the ITTO and map links stay the bare hrefs they have always been."""
    process = catalog.get(DRILLED)
    body = _body(client, f"/pmbok/{process.id}")
    assert f'href="/map?focus=process:{process.id}"' in body
    assert "?project=" not in body, "no project was asked for, so none may be carried"
