"""The business map speaks one vocabulary per section, and says why a row is empty.

Two badge vocabularies render on ``/process-map``. A grid cell is washed by a
SHARE bucket ("under half"); a listed project's badge carries its own process
STATE word ("Produced"). Both draw the same ``.st-*`` washes, so the page's one
share-bucket legend taught ``st-ok`` as "half+" while the badges directly under
it said "Produced" — one wash, two meanings, one page. Each vocabulary now
carries its own legend inside the section that uses it, and the listing's is
derived from the very predicate that filters its rows, so it can neither list a
state a row cannot carry nor omit one it can.

The other half is the empty listing. ``No applicable projects.`` named no
reason, no command and no link, and a process can be empty for three causes a
reader could not tell apart. The three are exhaustive by construction: with the
process assessable and a project neither waived nor excluded, that project IS a
row — so an empty listing means the store tracks none of the process's outputs,
or every project waived it, or there are no projects at all. Every process id
therefore renders either rows or a designed empty state naming its own cause.
"""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, NarrativeArtifact, Portfolio, Project, Risk, SignOff
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import Process
from driftless.web.business_map import _LEGEND
from driftless.web.templating import TEMPLATES
from driftless.web.views import STATE_RANK
from test_web_business_map import humanized

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
IDENTIFY_RISKS = catalog.get("11.2")  # assessable: risk_register, risk_report, assumption_log
# Every catalog process is tracked now, so no untracked one is left to borrow: the
# ``untracked`` fixture CREATES the condition (10.2 stood here; Monitor Communications,
# 10.3, stood here before it).
MANAGE_COMMS = catalog.get("10.2")
# A legend chip and the word beside it, paired by the markup that binds them.
_CHIP = re.compile(r'<dt aria-hidden="true"><span class="badge st-(\w+)"[^>]*>.*?</dt><dd>([^<]+)')
_ROW_BADGE = re.compile(r'<span class="badge st-(\w+)">([^<]+)</span>')
_EMPTY = re.compile(r'<section class="empty-state"[^>]*>(.*?)</section>', re.S)
# The grid's share-bucket words, read off the legend the page renders rather than
# re-typed here: a fifth bucket, or a reworded one, reaches this test on its own.
_SHARE_WORDS = tuple(label for label, _rank in _LEGEND)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


@pytest.fixture
def untracked(monkeypatch: pytest.MonkeyPatch) -> Process:
    """A process the store tracks no output of: removing its outputs' resolvers
    reproduces the exact condition the untracked empty state reports."""
    for kind in MANAGE_COMMS.outputs:
        monkeypatch.delitem(mapping.RESOLVERS, kind, raising=False)
    assert not st.is_assessable(MANAGE_COMMS), "still assessable — the empty state is untested"
    return MANAGE_COMMS


def _project(db: Session, name: str) -> Project:
    project = Project(
        name=name, portfolio=Portfolio(name=f"{name} port", business=Business(name=f"{name} biz"))
    )
    db.add(project)
    db.commit()
    return project


def _produced(db: Session, project: Project) -> None:
    """Enough for 11.2 to read ``produced`` on ``project``."""
    db.add(Risk(project=project, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=project, kind="assumption_log", body="drone weather"))
    db.commit()


def _waive(db: Session, project: Project) -> None:
    db.add(
        SignOff(
            project=project,
            subject_kind="process",
            subject_ref=st.process_subject_ref(IDENTIFY_RISKS, project),
            decision="waived",
        )
    )
    db.commit()


def _listing(client: TestClient, process_id: str) -> str:
    """The ``?process=`` section alone — the grid's own legend sits above it, and
    the section nests one, so it is read to the end of the content block."""
    page = client.get(f"/process-map{Q}&process={process_id}")
    assert page.status_code == 200, page.text
    assert '<section class="process-listing" id="listing">' in page.text, process_id
    return page.text.split('<section class="process-listing" id="listing">')[1].split("</main>")[0]


def test_a_listed_projects_state_word_is_explained_by_a_legend_beside_it(
    client: TestClient, db: Session
) -> None:
    """The page taught ``st-ok`` as "half+" at the top and printed it as "Produced"
    below: the same wash carrying two meanings on one page. Every wash a listed row
    uses must be explained where it is read, by the word the badge itself prints."""
    _produced(db, _project(db, "Alpha"))
    listing = _listing(client, "11.2")

    chips = dict(_CHIP.findall(listing))
    badges = _ROW_BADGE.findall(listing)
    assert badges, "no project state badge rendered — the fixture proves nothing"
    for rank, word in badges:
        assert chips.get(rank) == word, (
            f"a listed project's st-{rank} badge prints {word!r}, and the legend beside it "
            f"says {chips.get(rank)!r} — one wash, two vocabularies, one page"
        )
    for bucket in _SHARE_WORDS:
        assert bucket not in chips.values(), f"the share-bucket word {bucket!r} reads as a state"


def test_the_listing_legend_covers_exactly_the_states_a_row_there_can_carry(
    client: TestClient, db: Session
) -> None:
    """Derived, not hand-kept: the legend is read off the SAME predicate that filters
    the rows, so a sixth process state cannot reach a row unexplained, and a state
    that can never be listed (waived is excluded from every completeness figure)
    cannot be legended as though it could."""
    _produced(db, _project(db, "Alpha"))
    expected = [
        (STATE_RANK[state.value], humanized(state.value))
        for state in st.ProcessState
        if not st.excluded_from_completeness(IDENTIFY_RISKS, state)
    ]
    assert _CHIP.findall(_listing(client, "11.2")) == expected


def test_every_process_listing_either_lists_projects_or_says_why_it_cannot(
    client: TestClient, db: Session, untracked: Process
) -> None:
    """The mechanical half: a walk over the whole catalog, so no process id can grow
    an empty state that names neither a reason nor a next step. One process is made
    untracked, so the walk still crosses both branches at total coverage."""
    _produced(db, _project(db, "Alpha"))
    listed, empty = 0, 0
    for process in catalog.PROCESSES:
        section = _listing(client, process.id)
        if "<li>" in section:
            listed += 1
            continue
        empty += 1
        bodies = _EMPTY.findall(section)
        assert bodies, f"{process.id} lists nothing and renders no designed empty state"
        for body in bodies:
            assert "<code" in body or "<a " in body, f"{process.id}'s empty state names no step"
    assert listed and empty, f"the walk saw {listed} listed and {empty} empty — not both"


def test_an_empty_listing_names_its_own_cause_of_the_three_it_can_have(
    client: TestClient, db: Session, untracked: Process
) -> None:
    """ "No applicable projects." was true of all three and explained none of them."""
    bare = _listing(client, "11.2")
    assert 'href="/docs"' in bare, "an empty store names no way to make a project"
    assert "POST /projects" not in bare, "the store's own verb, not a reader-facing sentence"

    alpha, beta = _project(db, "Alpha"), _project(db, "Beta")
    unheld = _listing(client, untracked.id)
    assert "no output of this process is a kind the store tracks" in unheld
    assert f'href="/pmbok/{untracked.id}"' in unheld

    _waive(db, alpha)
    _waive(db, beta)
    waived = _listing(client, "11.2")
    assert "waived" in waived.lower()
    for project in (alpha, beta):
        assert f'href="/projects/{project.id}/process-map?as_of={AS_OF.isoformat()}"' in waived
    assert len({bare, unheld, waived}) == 3, "two causes render the same words"


def test_an_empty_listing_is_byte_identical_at_a_pinned_as_of(
    client: TestClient, db: Session
) -> None:
    _waive(db, _project(db, "Alpha"))
    assert _listing(client, "11.2") == _listing(client, "11.2")


def test_the_listing_vocabulary_moves_when_the_word_rule_itself_is_substituted(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mechanical half of the legend test above. Two spellings that agree today
    keep agreeing whether or not either one is the rule the page renders through, so
    the rule is REPLACED — by a marker shape that restates none of its arithmetic —
    and every legend chip and every row badge in the section is required to be
    spelled the new way, with the old spelling gone from the section entirely. A
    legend expectation rebuilt from the rule's own arithmetic fails here.
    """
    _produced(db, _project(db, "Alpha"))
    before = _listing(client, "11.2")
    was = sorted(
        {word for _rank, word in _CHIP.findall(before)}
        | {w for _r, w in _ROW_BADGE.findall(before)}
    )
    assert was, "neither a chip nor a badge rendered — the substitution would prove nothing"

    monkeypatch.setitem(TEMPLATES.env.filters, "humanize", lambda text: f"({text})")
    after = _listing(client, "11.2")
    expected = [
        (STATE_RANK[state.value], humanized(state.value))
        for state in st.ProcessState
        if not st.excluded_from_completeness(IDENTIFY_RISKS, state)
    ]
    assert _CHIP.findall(after) == expected, "the legend did not follow the substituted rule"
    words = {word for _rank, word in expected}
    badges = _ROW_BADGE.findall(after)
    assert badges, "no row badge rendered after the substitution"
    for _rank, word in badges:
        assert word in words, (
            f"a row badge printed {word!r}, which the substituted rule cannot spell"
        )
    for word in was:
        assert word not in after, f"{word!r} kept its old spelling after the word rule was replaced"
