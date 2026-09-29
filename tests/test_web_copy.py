"""Reader-facing copy across the whole web surface (D.5): the demo review found
"n/a" tiles, "0 item(s)" pluralisation hacks and prose that told a reader to type
a query string by hand -- ``?method=scrum``, ``?project={id}`` -- rather than
linking there. This pins the fix at the rendered-page level, not just at the
one template each defect was first seen in, and pins the four catalog pages'
one-sentence lede against the same plain-language gate the catalog's own
``plain_summary`` fields already have to pass.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from driftless.pmbok import plain_language as pl
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.methods import METHODS
from driftless.pmbok.proof import GAP_SHAPES, Proof
import test_web_pages
from test_web_pages import Q

client, db = test_web_pages.client, test_web_pages.db

#: Every reader-facing page the seeded project (id 1) reaches whose copy is
#: rendered entirely from ``driftless.web`` -- swept for the two literal
#: defects: a bare "n/a" and the "word(s)" shorthand for a plural nobody
#: computed. The dashboard ("/"), the threat board and the project hub carry
#: attention-feed rail text from ``driftless.report.gather`` and
#: ``driftless.assess.evaluators.schedule`` too, so they are swept as well.
_SWEPT_PATHS = (
    "/",
    f"/threats{Q}",
    f"/projects/1/hub{Q}",
    f"/projects/1/flow{Q}",
    f"/projects/1/gantt{Q}",
    f"/projects/1/status{Q}",
    f"/projects/1/wizard{Q}",
    f"/projects/1/process-map{Q}",
    f"/projects/1/assist/earned-value{Q}",
    f"/projects/1/assist/closeout{Q}",
    f"/projects/1/assist/procurement{Q}",
    f"/projects/1/assist/risk-responses{Q}",
    "/process-map",
    "/map",
    "/method",
    "/pmbok/proof",
    "/methods",
    "/artifacts",
)

_LEDE = re.compile(r'<p class="lede">(.*?)</p>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _bodies(client: TestClient) -> dict[str, str]:
    return {path: client.get(path).text for path in _SWEPT_PATHS}


def test_no_page_ever_prints_the_bare_na_shorthand(client: TestClient) -> None:
    for path, body in _bodies(client).items():
        assert "n/a" not in body, f"{path} still prints the bare n/a shorthand"


def test_no_page_ever_prints_the_word_s_pluralisation_hack(client: TestClient) -> None:
    hack = re.compile(r"\w\(s\)")
    for path, body in _bodies(client).items():
        found = hack.findall(body)
        assert not found, f"{path} still hard-codes {found} instead of a real plural"


def test_the_wizard_offers_real_method_links_never_told_to_type_the_query(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert "to the address" not in body
    assert 'href="/projects/1/wizard?as_of=2026-03-31&amp;method=scrum"' in body
    assert 'href="/projects/1/wizard?as_of=2026-03-31&amp;method=kanban"' in body


def test_the_map_offers_real_project_links_never_told_to_type_the_query(
    client: TestClient,
) -> None:
    body = client.get("/map").text
    assert "Shown as theory" not in body
    assert "?project={id}" not in body
    assert 'href="/map?project=1&amp;as_of=' in body


def test_the_dashboard_subtitle_names_no_internal_module(client: TestClient) -> None:
    for path in ("/", f"/portfolios/1/rollup{Q}"):
        body = client.get(path).text
        assert "driftless.calc" not in body
        assert "every figure is computed from the records, never typed" in body


def test_each_catalog_pages_lede_is_one_plain_sentence(client: TestClient) -> None:
    glossary_keys = frozenset(GLOSSARY)
    for path in ("/map", "/pmbok/proof", "/methods", "/artifacts"):
        body = client.get(path).text
        match = _LEDE.search(body)
        assert match, f'{path} carries no <p class="lede"> headline'
        sentence = _TAG.sub("", match.group(1)).strip()
        violations = pl.violations(sentence, glossary_keys=glossary_keys)
        assert not violations, f"{path}'s lede {sentence!r} fails plain language: {violations}"


def test_the_totality_proof_page_explains_every_gap_shape_it_counts(
    client: TestClient,
) -> None:
    """A reader meeting the proof table is told what each row checked and what a
    count above zero would mean -- for every shape the walk can report, not a
    hand-picked few."""
    body = client.get("/pmbok/proof").text
    for shape in GAP_SHAPES:
        assert shape.label in body, f"{shape.label} is missing from the proof page"
        assert shape.explanation in body, f"{shape.label} is counted with no explanation"


def test_the_totality_proof_page_links_gap_members_to_their_own_pages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every gap-shape member the page ever lists names a real catalog entry --
    a technique, an artifact, a process or a method practice -- and the page
    must send a reader there, not just print the bare key. Exercises every
    shape ``proof.gaps()`` can report, with one real member per shape (the live
    catalog holds no actual gaps to walk), and confirms the href each linked
    shape gets is one the test client can actually open."""
    import driftless.web.proof as proof_module

    technique_key = next(iter(TECHNIQUES))
    method = next(iter(METHODS.values()))
    practice_key = method.practices[0].key
    fake = Proof(
        orphan_techniques=(technique_key,),
        unexplained_techniques=(technique_key,),
        unlaunchable_techniques=(technique_key,),
        orphan_method_practices=(f"{method.key}:{practice_key}",),
        uncrosswalked_method_practices=(f"{method.key}:{practice_key}",),
        uncrosswalked_agile_models=("BacklogItem",),
        uncrosswalked_tailoring_gaps=("predictive:4.5",),
    )
    monkeypatch.setattr(proof_module, "build_proof", lambda: fake)
    body = client.get("/pmbok/proof").text

    for shape in GAP_SHAPES:
        members = getattr(fake, shape.field)
        for member in members:
            href = proof_module.member_href(shape.field, member)
            if href is None:
                assert f"<li>{member}</li>" in body, (
                    f"{shape.label} member {member!r} should render as plain text"
                )
            else:
                assert f'<li><a href="{href}">{member}</a></li>' in body, (
                    f"{shape.label} member {member!r} is not linked to {href}"
                )
                assert client.get(href).status_code == 200, (
                    f"{shape.label} member {member!r} links to {href}, which does not open"
                )
