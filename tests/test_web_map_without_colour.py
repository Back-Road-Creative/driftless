"""Both process maps still say what they mean with the colour thrown away (audit F3).

A wash cannot be a state's only carrier. ``waived`` and ``not_started`` deliberately
share the one neutral ``muted`` wash and the five washes sit under 1.2:1 from each
other, so the map shipped a legend of five colour chips — two of them identical — for a
grid that drew no distinction at all: in greyscale, in print, or to a colour-blind
reader every cell was one colour, and a waived process (tailored out of every
completeness figure) looked exactly like an untouched one. The off-screen ``sr-only``
word does not answer that (it is visually hidden) and neither does ``title=`` (hover
only: not keyboard, not touch, not print).

So these tests read the SHIPPED markup with every tag, attribute and off-screen span
stripped out — literally the page with its colour thrown away — and assert the state
survives: a distinct mark per legend chip, the same mark in the cell the legend
explains, and each business-map cell printing its share as a figure.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.pmbok import catalog, state
import test_web_pages
from test_web_pages import AS_OF, Q, _pair

# The seeded https store, reused as is (assigned, not imported: a test's own parameter
# must not read as a redefined import) — the idiom test_web_a11y already uses.
client, db = test_web_pages.client, test_web_pages.db

_LEGEND = re.compile(r'class="legend".*?</dl>', re.S)
_CHIP = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
_CELL = re.compile(
    r'<a href="[^"]*"><span class="badge st-[a-z]+" title="([^"]*)">(.*?)</span></a>', re.S
)
_OFFSCREEN = re.compile(r'<span class="sr-only">.*?</span>', re.S)


def _visible(markup: str) -> str:
    """What is left of a fragment for a reader the colour never reached: no tags (so
    no class and no hover title), no off-screen span, whitespace collapsed."""
    return " ".join(
        re.sub(r"<[^>]+>", "", _OFFSCREEN.sub("", markup)).replace("&nbsp;", " ").split()
    )


def _legend_marks(body: str) -> dict[str, str]:
    """Each legend entry's label -> what its chip shows once the colour is gone."""
    region = _LEGEND.search(body)
    assert region, "the page carries no <dl class=legend> to read"
    return {_visible(label): _visible(chip) for chip, label in _CHIP.findall(region.group(0))}


def _cell(body: str, process_id: str) -> str:
    """One grid cell of the per-project map, as a sighted reader sees it."""
    found = [
        inner for _, inner in _CELL.findall(body) if _visible(inner).startswith(f"{process_id} ")
    ]
    assert len(found) == 1, f"want exactly one grid cell for {process_id}, found {len(found)}"
    return _visible(found[0])


def test_the_five_legend_chips_are_five_distinguishable_marks(client: TestClient) -> None:
    marks = _legend_marks(client.get(f"/projects/1/process-map{Q}").text)
    assert len(marks) == 5, f"the legend names {sorted(marks)}, want the five process states"
    assert len(set(marks.values())) == 5, (
        f"the legend ships {len(set(marks.values()))} distinguishable chips for five states "
        f"({marks}) — a chip that is nothing but a colour draws Waived and Not Started as the "
        "same swatch under two labels, and no reader of any kind can tell them apart"
    )


def test_waiving_a_process_changes_what_its_cell_says_without_colour(
    client: TestClient, db: Session
) -> None:
    process = catalog.PROCESSES[0]
    project = db.scalars(select(Project)).one()
    before = _cell(client.get(f"/projects/1/process-map{Q}").text, process.id)
    posted = client.post(
        "/sign-off",
        data={
            "subject_kind": "process",
            "subject_ref": state.process_subject_ref(process, project),
            "decision": "waived",
            "project_id": "1",
            "as_of": AS_OF.isoformat(),
            **_pair(client),
        },
        follow_redirects=True,
    )
    assert posted.status_code == 200, posted.text
    after = _cell(posted.text, process.id)
    assert after != before, (
        f"{process.id} reads {after!r} waived and {before!r} untouched — the same cell with the "
        "colour thrown away, though a waiver drops the process from every completeness figure "
        "and an untouched one counts against it"
    )
    assert after.endswith(_legend_marks(posted.text)["Waived"]), (
        f"the waived cell reads {after!r}; the legend explains its Waived chip as "
        f"{_legend_marks(posted.text)['Waived']!r} — a mark the legend does not name explains nothing"
    )


_TM_LINK = re.compile(
    r'<a href="/portfolios/\d+/rollup"[^>]*><title>([^<]+)</title>\s*<rect class="tm (\w+)"'
)


def test_the_treemap_rag_survives_with_the_colour_thrown_away(client: TestClient) -> None:
    """The home treemap's RAG lived solely in the rectangle's ``--rag-*`` fill; its
    ``<title>`` named the portfolio and budget but never the verdict, so with the
    colour thrown away every cell read "a portfolio worth N" with no health at all.
    The title now prints the RAG as a word — the rollup table's own vocabulary,
    "no data" for unknown — beside the name and figure."""
    pairs = _TM_LINK.findall(client.get(f"/{Q}").text)
    assert pairs, "the seeded store draws a treemap"
    for title, rag in pairs:
        word = "no data" if rag == "unknown" else rag
        assert title.endswith(f" — {word}"), (
            f"the rectangle washed {rag} reads {title!r}: the wash is the only carrier"
        )


def test_the_business_map_prints_each_cell_share_as_a_figure(client: TestClient) -> None:
    cells = _CELL.findall(client.get(f"/process-map{Q}").text)
    assert len(cells) == len(catalog.PROCESSES), "the business grid renders every catalog process"
    silent = [_visible(inner) for share, inner in cells if not _visible(inner).endswith(share)]
    assert not silent, (
        f"{len(silent)} business-map cells carry their share only as a wash and a hover title "
        f"(e.g. {silent[:1]}) — four washes under 1.2:1 apart are one colour in greyscale, so "
        "the figure the cell is washed by has to be printed in it"
    )
