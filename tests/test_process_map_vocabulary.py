"""The map says "not tracked" about the store, never "Not Started" about the project.

``process_state`` answers ``NOT_STARTED`` for a process none of whose outputs the store
holds a resolver for — there is nothing to look for, so nothing is ever found. All 49
are tracked now, so none is. Printed as "Not Started", that reads as a
verdict on the project: work it owes and has not begun. It is a fact about this product's
coverage, settled and deliberate, so no reader is owed anything by those cells.

That retires this file's census half, not its rendering rule: coverage can regress, so
the census is pinned alone and the cells below are read against a process the store is
MADE to stop tracking. Each cell is read as SHIPPED — hover title, visible mark and
off-screen word together — because the old cell told a reader "Not Started" in all three
at once, and reading only the visible half would prove nothing.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.pmbok import catalog, mapping, state
from driftless.pmbok.model import Process
import test_web_pages
from test_web_pages import AS_OF, Q, _pair

# The seeded https store, reused as is (assigned, not imported: a test's own parameter
# must not read as a redefined import) — the idiom test_web_a11y already uses.
client, db = test_web_pages.client, test_web_pages.db

MAP = f"/projects/1/process-map{Q}"
_CELL = re.compile(r'<a href="/pmbok/([\w.]+)\?[^"]*">(.*?)</a>', re.S)
_OPTION = re.compile(r'<option value="process:([\w.]+):project:\d+">(.*?)</option>', re.S)


def _cells(body: str) -> dict[str, str]:
    """Every grid cell of the per-project map: process id -> the cell exactly as shipped."""
    found = dict(_CELL.findall(body))
    assert len(found) == len(catalog.PROCESSES), (
        f"read {len(found)} grid cells for {len(catalog.PROCESSES)} processes — the extractor "
        "no longer sees the grid, so anything it asserts below is vacuous"
    )
    return found


#: The exact remainder after the plan-and-communications wave: nothing. Still an exact set
#: rather than a floor — the direction left to fire is coverage REGRESSING, the one event
#: that would put "Not Tracked" back on a real cell.
UNTRACKED_IDS: frozenset[str] = frozenset()

#: The process the rendering tests read an untracked cell off. Coverage being total, the
#: condition is created rather than found: the store stops resolving this process's outputs.
UNTRACKABLE = "10.2"


def test_the_store_tracks_an_output_of_every_process() -> None:
    """The census alone, so the made-untracked fixture cannot stand in for it."""
    live = {p.id for p in catalog.PROCESSES if not state.is_assessable(p)}
    assert live == UNTRACKED_IDS, f"the coverage boundary moved: {sorted(live)} untracked now"


@pytest.fixture
def untracked(monkeypatch: pytest.MonkeyPatch) -> list[Process]:
    """One real process the store is made to stop tracking, and the census that follows."""
    process = catalog.get(UNTRACKABLE)
    for kind in process.outputs:
        monkeypatch.delitem(mapping.RESOLVERS, kind, raising=False)
    processes = [p for p in catalog.PROCESSES if not state.is_assessable(p)]
    assert process in processes, f"{UNTRACKABLE} stayed assessable — the cells below prove nothing"
    return processes


def test_no_cell_calls_an_untracked_process_not_started(
    client: TestClient, untracked: list[Process]
) -> None:
    cells = _cells(client.get(MAP).text)
    said = ("Not Started", "not_started")  # the off-screen word and the hover title
    blamed = [p.id for p in untracked if any(word in cells[p.id] for word in said)]
    assert not blamed, (
        f"{len(blamed)} cells call the project's work Not Started for a process the catalog "
        f"tracks no output of (e.g. {blamed[0]}: {cells[blamed[0]]!r}) — nothing is owed on any "
        "of them, and the grid is telling a reader the project is behind on all of them"
    )


def test_an_untracked_cell_says_whose_fact_it_is(
    client: TestClient, untracked: list[Process]
) -> None:
    cells = _cells(client.get(MAP).text)
    silent = [p.id for p in untracked if "Not Tracked" not in cells[p.id]]
    assert not silent, (
        f"{len(silent)} untracked cells print no word of their own (e.g. {silent[0]}: "
        f"{cells[silent[0]]!r}) — a cell that merely withholds the state says nothing at all"
    )


def test_a_tracked_process_nobody_has_begun_still_says_not_started(
    client: TestClient, db: Session
) -> None:
    """The word is not deleted, only moved off the cells it never described."""
    project = db.scalars(select(Project)).one()
    cells = _cells(client.get(MAP).text)
    untouched = [
        p
        for p in catalog.PROCESSES
        if state.is_assessable(p)
        and state.process_state(p, project, db, AS_OF) is state.ProcessState.NOT_STARTED
    ]
    assert untouched, "the seed must leave a tracked process untouched, or this proves nothing"
    missing = [p.id for p in untouched if "Not Started" not in cells[p.id]]
    assert not missing, f"{missing} are tracked and unbegun, and the grid no longer says so"


def test_waiving_an_untracked_process_shows_the_decision(
    client: TestClient, db: Session, untracked: list[Process]
) -> None:
    """A recorded decision outranks the coverage fact — a waiver is what a reader acted on."""
    project = db.scalars(select(Project)).one()
    process = untracked[0]
    client.get(MAP)  # the render that hands this browser its half of the CSRF pair
    posted = client.post(
        "/sign-off",
        data={
            "subject_kind": "process",
            "subject_ref": state.process_subject_ref(process, project),
            "decision": "waived",
            "project_id": str(project.id),
            "as_of": AS_OF.isoformat(),
            **_pair(client),
        },
        follow_redirects=True,
    )
    assert posted.status_code == 200, posted.text[:200]
    cell = _cells(posted.text)[process.id]
    assert "Waived" in cell and "Not Tracked" not in cell, (
        f"{process.id} was waived and its cell reads {cell!r} — the ledger entry someone signed "
        "is the whole state of that process now, and the grid has to show it"
    )


def test_the_signoff_picker_says_what_the_cell_says(
    client: TestClient, untracked: list[Process]
) -> None:
    """One page, one vocabulary: the picker under the grid names the same states."""
    body = client.get(MAP).text
    options = dict(_OPTION.findall(body))
    assert len(options) == len(catalog.PROCESSES), f"the picker offers {len(options)} processes"
    blamed = [p.id for p in untracked if "Not Started" in options[p.id]]
    assert not blamed, (
        f"the picker calls {len(blamed)} untracked processes Not Started (e.g. "
        f"{options[blamed[0]]!r}) while the cell above it does not — the same process, the same "
        "page, two words for it"
    )
