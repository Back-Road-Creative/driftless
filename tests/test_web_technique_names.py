"""One visible name per technique, wherever a page prints one.

``definitions._DISPLAY_NAME_OVERRIDES`` exists because ``str.title()`` mishandles a
couple of PMBOK terms of art, and ``TechniqueDefinition.display_name`` is the corrected
result. The ITTO list on ``/pmbok/{process_id}`` used to derive the name a second time —
piping the raw registry key through the ``humanize`` filter, which is exactly the
``.title()`` behaviour the overrides correct — so the two keys the table exists to fix
were spelled one way on the process page and another on the technique page they linked
to.

These walks are mechanical rather than a pair of pinned strings: every technique the
registry holds is checked against the name a *rendered* page actually shows for it —
the real ITTO lists of the real catalog processes for the ones a process names, and the
technique's own page for all of them. A future override that corrected a third key
would be caught the same way, with no test to remember to extend.
"""

from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

from driftless.pmbok import catalog
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.tt import EXTENSION_REASONS
from driftless.web.techniques import BY_SLUG
from driftless.web.templating import technique_slug
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db

#: The library link the ITTO macro writes: ``<a href="/techniques/{slug}">{name}</a>``.
_LIBRARY_LINK = re.compile(r'<a href="/techniques/([a-z0-9-]+)">(.*?)</a>')

#: Which techniques a process actually names, computed off the live catalog so this
#: guard's reach is measured rather than written down.
_NAMED_BY_A_PROCESS = {tt for process in catalog.PROCESSES for tt in process.tools_techniques}


def _itto_names(client: TestClient) -> dict[str, set[str]]:
    """``{technique key: every name an ITTO list rendered for it}``, gathered by
    fetching every catalog process page and reading its real library links."""
    rendered: dict[str, set[str]] = {}
    for process in catalog.PROCESSES:
        page = client.get(f"/pmbok/{process.id}")
        assert page.status_code == 200, f"{process.id} -> {page.status_code}"
        for slug, name in _LIBRARY_LINK.findall(page.text):
            assert slug in BY_SLUG, (
                f"{process.id} links /techniques/{slug}, which resolves to no technique"
            )
            rendered.setdefault(BY_SLUG[slug], set()).add(html.unescape(name))
    return rendered


def test_every_itto_list_names_a_technique_the_way_the_registry_does(client: TestClient) -> None:
    """The name on a process page is character-for-character the registry's."""
    rendered = _itto_names(client)
    wrong = {
        key: sorted(names)
        for key, names in rendered.items()
        if names != {TECHNIQUES[key].display_name}
    }
    assert not wrong, "ITTO lists disagree with the registry: " + "; ".join(
        f"{key}: page {names} vs registry {TECHNIQUES[key].display_name!r}"
        for key, names in sorted(wrong.items())
    )


def test_the_itto_walk_reaches_every_technique_a_process_names(client: TestClient) -> None:
    """The guard above is only worth its assertion if it saw the whole catalog: it
    must reach exactly the techniques the catalog's processes name, no more and no
    fewer, so a technique cannot drop out of the walk unnoticed."""
    assert set(_itto_names(client)) == _NAMED_BY_A_PROCESS


def test_every_technique_page_titles_itself_from_the_registry(client: TestClient) -> None:
    """And the other half of the pair, for all of the registry — including any
    technique no process names, which no ITTO list can cover.

    ``<title>`` carries the registry's ``display_name`` qualified with the
    ``— driftless`` suffix every Driftless detail page uses (see
    ``test_web_techniques.test_the_page_title_is_qualified_the_way_other_detail_pages_are``,
    which pins that suffix for a single technique); this is the registry-wide walk
    that reaches every technique, including one no process names."""
    for key, technique in TECHNIQUES.items():
        page = client.get(f"/techniques/{technique_slug(key)}")
        assert page.status_code == 200, f"{key} -> {page.status_code}"
        body = html.unescape(page.text)
        assert f"<h1>{technique.display_name}</h1>" in body
        assert f"<title>{technique.display_name} — driftless</title>" in body


def test_an_extension_page_gives_the_recorded_reason_it_is_one(client: TestClient) -> None:
    """``tt.EXTENSION_REASONS`` records, per extension, why the edition's own
    processes do not name it. The page said only that Driftless added the technique;
    the recorded reason is rendered as written rather than restated here."""
    for key, reason in EXTENSION_REASONS.items():
        body = html.unescape(client.get(f"/techniques/{technique_slug(key)}").text)
        assert reason in body, f"{key} page omits its recorded extension reason"


def test_a_pmbok_technique_page_carries_no_extension_reason(client: TestClient) -> None:
    """The reason block belongs to extensions alone — a PMBOK technique cites the
    edition and must not gain a paragraph explaining why it is not in it."""
    key = next(key for key in TECHNIQUES if key not in EXTENSION_REASONS)
    body = html.unescape(client.get(f"/techniques/{technique_slug(key)}").text)
    assert "why-extension" not in body
