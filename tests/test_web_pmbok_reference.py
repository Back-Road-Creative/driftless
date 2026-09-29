"""The PMBOK reference pages are their own controller, not part of the ITTO page module.

``web/pages.py`` grew by accumulation: every page that needed the write path or the
as-of dependency was added to the one ``create_pages_router`` body, which reached 11
route definitions in a single function. The carve is incremental — one controller per
change — and this pins the first slice from both ends: the routes leave ``pages.py``,
and the live app still serves them at the same paths. A carve nobody can observe from
the outside is the only acceptable kind.

``/pmbok`` and ``/pmbok/{process_id}`` go first because they are the cleanest cut: the
grid is the frozen catalog (the index reads the store only for the projects it offers to
read that grid against), and the detail page reads through ``fetch`` and
``process_in_project`` — none of the write helpers, the CSRF pair rule, or the sign-off
redirect table the rest of ``pages.py`` is built around.
"""

from __future__ import annotations

import html
import re
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
import test_web_pages
from driftless.pmbok import catalog
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.model import KnowledgeArea
from driftless.pmbok.process_definitions import get as get_definition
from driftless.pmbok.support import ProcessCoverage, build_coverage, driftless_help
from driftless.web.pmbok_reference import (
    SUPPORT_LEGEND,
    create_pmbok_reference_router,
    support_word,
)

client, db = test_web_pages.client, test_web_pages.db

AS_OF = date(2026, 3, 1)
REFERENCE_PATHS = {"/pmbok", "/pmbok/{process_id}"}
#: A deepened process with a worked example and a "how driftless helps" fact.
DEEPENED = "4.1"
#: A process whose "how driftless helps" join finds nothing, so that section
#: must render its honest empty line rather than a bare heading.
BARE = "9.6"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_reference_pages_have_a_controller_of_their_own() -> None:
    assert _paths(create_pmbok_reference_router(AS_OF).routes) == REFERENCE_PATHS


def test_the_live_app_still_serves_both_paths() -> None:
    """What a reader sees is unchanged — the same two paths, on the same app.

    Read through ``page_route_paths`` rather than by walking ``app.routes``: a web
    router is *included*, so its routes are leaves under the holder rather than
    entries at the top level, and a bare walk finds none of them and passes
    vacuously. That accessor is the one place that descent is written down. It
    answers a frozenset, so double-mounting is not this test's question —
    ``tests/test_web_mount_once.py`` counts a list precisely to ask it.
    """
    assert REFERENCE_PATHS <= page_route_paths(app)


def test_every_process_cell_carries_its_own_support_word(client: TestClient) -> None:
    """The reference grid says, in the newcomer's own words, what the product can
    do with each process — walked over the whole catalog rather than one exemplar,
    and each word checked against the exact cell it names rather than anywhere on
    the page, so a mismatched or missing word cannot hide behind another cell's."""
    body = client.get("/pmbok").text
    coverage = {row.process_id: support_word(row) for row in build_coverage().processes}
    for process in catalog.PROCESSES:
        pattern = (
            rf">{re.escape(process.id)} {re.escape(process.name)}</a> "
            r"— <small>([^<]*)</small>"
        )
        match = re.search(pattern, body)
        assert match is not None, f"{process.id}: no support word rendered on its own cell"
        assert match.group(1) == coverage[process.id], process.id


def test_a_process_with_no_producible_output_and_no_assessable_reading_is_read_only() -> None:
    """The catalog today has no such process — every one is already assessable
    or already producible, which is why the walk above never reaches this
    line — so this drives ``support_word`` directly with a synthetic
    ``ProcessCoverage`` for the one combination the catalog does not carry."""
    read_only = ProcessCoverage(
        process_id="0.0",
        process_name="Synthetic",
        area=KnowledgeArea.INTEGRATION,
        assessable=False,
        producible_outputs=(),
        techniques=(),
    )
    assert support_word(read_only) == "Read-only for now"


def test_a_deepened_process_renders_its_worked_example_pitfalls_and_help() -> None:
    definition = get_definition(DEEPENED)
    facts = driftless_help(catalog.get(DEEPENED))
    assert facts, "pick a DEEPENED id the join actually finds something for"
    body = TestClient(app).get(f"/pmbok/{DEEPENED}").text
    assert "<h2>Worked example</h2>" in body and definition.worked_example in body
    assert "<h2>Common pitfalls</h2>" in body
    for pitfall in definition.pitfalls:
        assert pitfall in body
    assert "<h2>How driftless helps</h2>" in body
    assert "does not yet help run this process" not in body


def test_a_process_driftless_cannot_help_with_says_so() -> None:
    assert driftless_help(catalog.get(BARE)) == (), "pick a BARE id the join finds nothing for"

    body = TestClient(app).get(f"/pmbok/{BARE}").text
    assert "<h2>How driftless helps</h2>" in body
    assert "does not yet help run this process" in body


def test_a_definition_with_no_depth_hides_both_of_its_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hiding rule, driven with a blanked definition rather than a catalog
    process: every area written so far carries a worked example and pitfalls, so
    no real process demonstrates it any more. Same shape as the read-only test
    above, which drives a combination the catalog does not carry either."""
    blanked = replace(get_definition(BARE), worked_example="", pitfalls=())
    monkeypatch.setattr(
        "driftless.web.pmbok_reference.get_process_definition", lambda process_id: blanked
    )

    body = TestClient(app).get(f"/pmbok/{BARE}").text
    assert "<h2>Worked example</h2>" not in body
    assert "<h2>Common pitfalls</h2>" not in body


def test_the_grid_legends_every_support_word_it_prints(client: TestClient) -> None:
    """The three support words are explained under the grid that prints them.

    Walked from ``build_coverage`` — the very rows the cells are rendered from —
    rather than from a list typed here, so a fourth word added to ``support_word``
    fails this the day it ships instead of printing unexplained on 49 cells.
    """
    body = html.unescape(client.get("/pmbok").text)
    legend = re.search(r'<dl class="legend">(.*?)</dl>', body, re.S)
    assert legend is not None, "the grid prints support words with no legend explaining them"
    explained = dict(SUPPORT_LEGEND)
    for row in build_coverage().processes:
        word = support_word(row)
        assert word in legend.group(1), f"{row.process_id}'s cell prints {word!r}, unlegended"
        assert explained[word] in legend.group(1), f"{word!r} is legended with no meaning"


def test_the_page_defines_itto_predictive_and_both_grid_headings(client: TestClient) -> None:
    """The h1 and the opening line use four terms a newcomer does not have. Two are
    glossary entries, so their definition is READ from the registry rather than
    retyped here; the two that are not are spelled out in the same block."""
    body = client.get("/pmbok").text
    block = re.search(r'<details class="how-to-read">(.*?)</details>', body, re.S)
    assert block is not None, "the PMBOK index carries no 'How to read this page' block"
    how = block.group(1)
    assert "inputs, tools &amp; techniques and outputs" in how, "ITTO is never expanded"
    assert "predictive" in how.lower(), "'predictive' is used in the lede and never explained"
    for key in ("knowledge-area", "process-group"):
        assert f'href="/glossary#{key}"' in how, f"{key} is not linked to its glossary entry"
        assert GLOSSARY[key].plain in how, f"{key}'s definition is retyped, not read from GLOSSARY"


def test_the_index_offers_a_real_link_per_project_never_told_to_type_the_query(
    client: TestClient,
) -> None:
    """PM07: the theory grid says how to see it with a project's own reading, as real
    links built from the store — the same courtesy ``/map`` already extends."""
    body = client.get("/pmbok").text
    assert "?project={id}" not in body, "the page tells a reader to type a query string"
    projects = [int(row["id"]) for row in client.get("/projects").json()]
    assert projects, "vacuous: the seeded store holds no project to offer a reading of"
    for project in projects:
        assert f'href="/projects/{project}/process-map?as_of=' in body, project


def test_the_index_links_every_other_method_hub(client: TestClient) -> None:
    """NV16: the index linked only its own cells and the proof."""
    body = client.get("/pmbok").text
    strip = re.search(r'<section class="related".*?</section>', body, re.S)
    assert strip is not None, "the PMBOK index carries no Related hub strip"
    for href in ("/techniques", "/artifacts", "/methods", "/map", "/process-map"):
        assert f'href="{href}"' in strip.group(0), f"{href} is not reachable from the index"
