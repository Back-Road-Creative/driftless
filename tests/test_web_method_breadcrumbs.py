"""Every Method-cluster page carries exactly one breadcrumb trail, and every
crumb it prints actually goes somewhere. The cluster (PMBOK, techniques,
methods, artifacts, glossary, and the two maps) sat outside the ``trail()``/
``top()`` convention every project sub-page already followed; ``theory()``
in ``_breadcrumbs.html`` closes that gap.

Live mode (``?project=``) is walked too, for the two routes that take it,
so a live crumb resolving to nowhere is caught the same way a theory one is.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

import test_web_pages
from driftless.pmbok import catalog

client, db = test_web_pages.client, test_web_pages.db
AS_OF, Q = test_web_pages.AS_OF, test_web_pages.Q

# The tag's opening, not its whole spelling: the trail carries an ``aria-label`` now,
# and a literal pinned to the old spelling would stop seeing the trail at all.
_NAV = re.compile(r'<nav class="breadcrumbs"')
_HREF = re.compile(r'href="([^"]+)"')

# A stable process id, technique and artifact slug to drill into — the same
# ones the rest of the PMBOK suite reaches with.
_PROCESS_ID = catalog.PROCESSES[0].id


def _theory_routes() -> list[str]:
    from driftless.web.artifacts import BY_SLUG as ARTIFACT_SLUGS
    from driftless.web.techniques import BY_SLUG as TECHNIQUE_SLUGS

    technique_slug = next(iter(TECHNIQUE_SLUGS))
    artifact_slug = next(iter(ARTIFACT_SLUGS))
    return [
        "/pmbok",
        f"/pmbok/{_PROCESS_ID}",
        "/pmbok/proof",
        "/techniques",
        f"/techniques/{technique_slug}",
        "/methods",
        "/methods/scrum",
        "/artifacts",
        f"/artifacts/{artifact_slug}",
        "/glossary",
        "/process-map",
        "/map",
        "/map?focus=" + _PROCESS_ID,
    ]


def _live_routes() -> list[str]:
    from driftless.web.artifacts import BY_SLUG as ARTIFACT_SLUGS

    artifact_slug = next(iter(ARTIFACT_SLUGS))
    return [
        f"/pmbok/{_PROCESS_ID}?project=1&as_of={AS_OF.isoformat()}",
        f"/artifacts/{artifact_slug}?project=1&as_of={AS_OF.isoformat()}",
        f"/map?project=1&as_of={AS_OF.isoformat()}",
    ]


def _assert_one_breadcrumb_and_every_href_resolves(client: TestClient, path: str) -> None:
    page = client.get(path)
    assert page.status_code == 200, f"{path}: {page.text[:200]}"
    body = page.text
    navs = _NAV.findall(body)
    assert len(navs) == 1, f"{path}: expected exactly one breadcrumb nav, found {len(navs)}"
    nav_match = re.search(r'<nav class="breadcrumbs".*?</nav>', body)
    assert nav_match, f"{path}: no breadcrumb nav found"
    for href in _HREF.findall(nav_match.group(0)):
        crumb_page = client.get(href)
        assert crumb_page.status_code == 200, (
            f"{path}: crumb href {href!r} -> {crumb_page.status_code}"
        )


def test_every_theory_method_route_carries_one_breadcrumb_with_live_links(
    client: TestClient,
) -> None:
    for path in _theory_routes():
        _assert_one_breadcrumb_and_every_href_resolves(client, path)


def test_every_live_method_route_carries_one_breadcrumb_with_live_links(
    client: TestClient,
) -> None:
    for path in _live_routes():
        _assert_one_breadcrumb_and_every_href_resolves(client, path)


def test_the_trail_names_itself_and_marks_the_page_the_reader_is_on(
    client: TestClient,
) -> None:
    """Unnamed, the trail is a second anonymous "navigation" beside the primary nav;
    and its last crumb IS the current page with nothing saying so."""
    for path in ["/method", *_theory_routes()]:
        page = client.get(path)
        assert page.status_code == 200, f"{path}: {page.text[:200]}"
        nav = re.search(r'<nav class="breadcrumbs".*?</nav>', page.text)
        assert nav, f"{path}: no breadcrumb trail"
        assert 'aria-label="Breadcrumb"' in nav.group(0), (
            f"{path}: the trail is an unnamed <nav> — a reader meets two anonymous "
            "navigation landmarks and cannot tell which is which"
        )
        assert re.search(r'<span aria-current="page">[^<]+</span></nav>', nav.group(0)), (
            f"{path}: the last crumb does not say it is the page the reader is on"
        )
