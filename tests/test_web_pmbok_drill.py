"""A process-map cell reaches the assessment, instead of dying at the theory page.

The drill the map promises is: process -> its ITTO -> this project's live artifacts
(``mapping.resolve``) -> the knowledge area's assessment -> the threats and actions it
attached -> back to the map the reader came from. Every hop below is checked against
what the engines answer for the SAME store and the SAME as-of, never against a literal
sentence, so the page cannot pass by printing something plausible.

The cell that bites hardest gets its own test. Control Costs (7.4) reads ``produced``
for the seeded project — the work-performance information it owes is derived from that
project's plan and its dated spend — while the cost evaluator raises a red threat about
that very spend. No cell state can say that; the drill is where the two finally meet.
"""

from __future__ import annotations

import html

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.assess import engine as assess
from driftless.models import Project
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.model import KnowledgeArea
import test_web_pages

# The seeded https store, reused as is (assigned, not imported: a test's own
# parameter must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db
AS_OF, Q = test_web_pages.AS_OF, test_web_pages.Q
DRILL = "/pmbok/{}?project=1&as_of=" + AS_OF.isoformat()
#: Sits in the area the fixture makes red; what it owes is derived or untracked.
CONTROL_COSTS = "7.4"


def _body(client: TestClient, path: str) -> str:
    """A page's HTML with entities decoded once, so a finding carrying ``&`` or a
    quote is matched as the engine wrote it rather than as Jinja escaped it."""
    page = client.get(path)
    assert page.status_code == 200, page.text[:200]
    return html.unescape(page.text)


def test_the_map_cell_carries_the_project_and_the_as_of(client: TestClient) -> None:
    """Hop 1 keeps its context: the cell's href names the project and the pinned
    as-of, so neither is dropped at the first click."""
    body = _body(client, f"/projects/1/process-map{Q}")
    assert f'href="/pmbok/{CONTROL_COSTS}?project=1&as_of={AS_OF.isoformat()}"' in body


def test_the_drill_reads_this_projects_live_artifacts(client: TestClient, db: Session) -> None:
    """Hop 3: every ITTO artifact kind carries what ``mapping.resolve`` answers for
    this project as of this date — the resolver's own detail, not a restatement."""
    process = catalog.get(CONTROL_COSTS)
    project = db.get(Project, 1)
    assert project is not None
    body = _body(client, DRILL.format(CONTROL_COSTS))
    for kind in (*process.inputs, *process.outputs):
        assert kind in body, kind
        assert mapping.resolve(kind, project, db, AS_OF).detail in body, kind
    # None of this process's outputs is a kind the store holds, and the page says so
    # in those words rather than calling the project's work "not started".
    assert body.count("not tracked") >= len(process.outputs)


def test_the_drill_reaches_the_assessment_the_cell_can_never_show(
    client: TestClient, db: Session
) -> None:
    """Hops 4 and 5, on the process whose cell reads ``produced`` while its area is
    red: the knowledge area's assessment, its live threats, and the actions it
    attached — none of which any process state can carry."""
    project = db.get(Project, 1)
    assert project is not None
    cell = st.process_state(catalog.get(CONTROL_COSTS), project, db, AS_OF)
    assert cell is st.ProcessState.PRODUCED, "the gap this test bridges is not the one it names"
    cost = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}["cost"]
    assert cost.threats and cost.actions, "the fixture must overspend, or this proves nothing"

    body = _body(client, DRILL.format(CONTROL_COSTS))
    assert cost.status in body
    for threat in cost.threats:
        assert threat.description in body, threat.id
    for action in cost.actions:
        assert action.label in body and action.rationale in body, action.id


def test_the_back_link_returns_to_the_map_the_reader_came_from(client: TestClient) -> None:
    """Hop 6: back is the project's own map at the same as-of, not the theory grid."""
    body = _body(client, DRILL.format(CONTROL_COSTS))
    assert f'href="/projects/1/process-map?as_of={AS_OF.isoformat()}"' in body
    assert "PMBOK reference" not in body, "the project drill must not send the reader to theory"


def test_without_a_project_the_page_is_the_theory_it_always_was(client: TestClient) -> None:
    body = _body(client, f"/pmbok/{CONTROL_COSTS}")
    assert "PMBOK reference" in body  # the stateless back link
    assert "GMS" not in body, "no project state leaks into the reference view"
    assert "cost_forecasts" in body  # still the ITTO it always printed


def test_every_knowledge_area_reaches_an_assessment(client: TestClient, db: Session) -> None:
    """The join is by name — ``Assessment.kind`` IS the ``KnowledgeArea`` value — so it
    has to be total, or some area's drill would stop one hop short in silence."""
    project = db.get(Project, 1)
    assert project is not None
    kinds = {a.kind for a in assess.assess_project(db, project, AS_OF)}
    assert kinds == {area.value for area in KnowledgeArea}
    for area in KnowledgeArea:
        process = catalog.by_area(area)[0]
        body = _body(client, DRILL.format(process.id))
        assert f"{area.value.title()} assessment" in body, process.id


def test_the_drill_regenerates_byte_identically(client: TestClient) -> None:
    """A pinned as-of renders the same bytes twice — nothing here reads a clock."""
    first = client.get(DRILL.format(CONTROL_COSTS))
    assert first.content == client.get(DRILL.format(CONTROL_COSTS)).content
