"""The Method hub: ``GET /method``. Cards are walked off the page's OWN section list,
so one added later is checked without anyone remembering to; every count is rebuilt
here from the registry, so a typed or stale figure fails rather than reading as fact.
"""

from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

import test_web_pages
from driftless.pmbok import catalog
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.methods import METHODS
from driftless.web.method_hub import SECTIONS

client, db = test_web_pages.client, test_web_pages.db

_CARD = re.compile(r'<section class="method-hub-card">(.*?)</section>', re.S)

#: Each count, from the live registry — the same measurement the page makes.
_NODES, _TIES = GRAPH.size()
MEASURED = {
    "/pmbok": f"{len(catalog.PROCESSES)} processes",
    "/techniques": f"{len(TECHNIQUES)} techniques",
    "/methods": f"{len(METHODS)} method profiles",
    "/artifacts": f"{len(ARTIFACTS)} artifact kinds",
    "/glossary": f"{len(GLOSSARY)} terms",
    "/process-map": f"{len(catalog.PROCESSES)} processes, rolled up across every project",
    "/map": f"{_NODES} nodes and {_TIES:,} ties",
}


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}: {page.text[:200]}"
    return html.unescape(page.text)


def test_every_section_card_links_its_page_and_explains_it(client: TestClient) -> None:
    assert len(SECTIONS) == len(MEASURED), f"the hub lists {len(SECTIONS)} sections — walk is thin"
    cards = _CARD.findall(_body(client, "/method"))
    assert len(cards) == len(SECTIONS), f"{len(cards)} cards rendered for {len(SECTIONS)} sections"
    for section, card in zip(SECTIONS, cards, strict=True):
        assert f'href="{section.href}"' in card, f"{section.title}: card links nowhere"
        assert section.title in card, f"{section.title}: card carries no title"
        assert section.what in card, f"{section.title}: card says nothing about what it is for"
        assert section.count in card, f"{section.title}: card prints no count"
        assert client.get(section.href).status_code == 200, f"{section.href}: card links a 404"


def test_every_count_a_card_prints_is_the_registry_s_own(client: TestClient) -> None:
    printed = {section.href: section.count for section in SECTIONS}
    assert printed == MEASURED, (
        "a hub card states a count the registry does not hold — every figure here is "
        f"measured, never typed: {printed} vs {MEASURED}"
    )
    body = _body(client, "/method")
    for count in MEASURED.values():
        assert count in body, f"the page never prints the measured count {count!r}"


def test_the_nav_and_the_dashboard_both_reach_the_hub(client: TestClient) -> None:
    """The label lights on its own page, and the dashboard offers hub and map together."""
    front = _body(client, "/")
    assert 'href="/method"' in front and 'href="/map"' in front, (
        "the Method nav label and the dashboard's Method strip must both reach the hub"
    )
    assert '<a href="/method" aria-current="page">' in _body(client, "/method"), (
        "the Method nav label must light when the reader is on the hub"
    )
