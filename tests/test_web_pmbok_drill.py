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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.assess.model import Action
from driftless.assess import engine as assess
from driftless.models import Project
from driftless.pmbok import catalog, mapping
from driftless.pmbok import state as st
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.model import KnowledgeArea
from driftless.web.templating import TEMPLATES
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
    humanize = TEMPLATES.env.filters["humanize"]
    for kind in (*process.inputs, *process.outputs):
        # The DISPLAY is humanized; the artifact lookup itself stays keyed on the
        # raw kind (asserted separately below), so the badge still resolves.
        assert humanize(kind) in body, kind
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
    assert "Cost Forecasts" in body  # still the ITTO it always printed, now humanized


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


def test_the_drill_shows_a_reference_link_when_a_process_names_the_technique(
    client: TestClient, db: Session
) -> None:
    """A reference link for every technique this assessment recommends, each
    rendered at the address its own ``Action`` gives — the same outcome the CLI
    and the report give.

    One hand-written anchor for one technique used to stand for the whole set,
    which made this file the last thing pinning the model's slug against the
    page's; a walk over the live actions, taking each address off the ``Action``
    rather than restating it, is what that string was standing in for.
    """
    project = db.get(Project, 1)
    assert project is not None
    cost = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}["cost"]
    assert cost.actions, "the fixture must overspend, or this proves nothing"
    body = _body(client, DRILL.format(CONTROL_COSTS))
    for action in cost.actions:
        href = action.reference_href
        assert href is not None, f"{action.pmbok_tt}: Control Costs names it, yet it has no link"
        assert f'<a href="{href}">{action.technique.display_name}</a>' in body, action.pmbok_tt
        if "_" in action.pmbok_tt:
            assert action.pmbok_tt not in body, "humanized, never the raw key"
        # The cost workbench now routes every Cost technique
        # (driftless.assess.model.ASSISTANT_ROUTES), so "reference only" is checked
        # against each action's own launch state rather than assumed to appear
        # somewhere in the page — the CLI and report tests still pin an exemplar
        # (schedule_compression) outside the cost family for that phrase.
        if action.is_reference_only:
            assert "reference only" in body, action.pmbok_tt
        else:
            assert (
                f'<a href="{action.launch_href}">apply {action.technique.display_name}</a>' in body
            )


def test_the_drill_links_a_technique_no_process_names_the_same_way(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A technique no process names at all reads exactly like any other
    recommendation: its explanation, linked. It used to get the label "no linked
    process yet either" and no link — a page that was already being served. Injected
    (see ``test_web_pages._inject_unlinked_action``) because the real pipeline
    recommends no such technique on its own — that gap is what PR #273 closed."""
    if not test_web_pages._UNNAMED_UNROUTED:
        pytest.skip(test_web_pages._NO_UNROUTED_REASON)
    technique = test_web_pages._UNNAMED_UNROUTED[0]
    test_web_pages._inject_unlinked_action(monkeypatch, technique)
    action = Action("probe:unlinked", "label", technique, "why", "project:1")
    body = _body(client, DRILL.format(CONTROL_COSTS))
    name = TECHNIQUES[technique].display_name
    assert f'<a href="{action.reference_href}">{name}</a>' in body
    assert technique not in body  # humanized, never the raw key
    assert "no linked process yet either" not in body


def test_the_process_page_names_the_agile_equivalence_for_a_covered_output(
    client: TestClient,
) -> None:
    """4.3 owes ``issue_log``, which ``crosswalk.EQUIVALENCES`` covers — the page
    names how Scrum/Kanban projects satisfy it, verbatim from that dataclass,
    with no project on the URL at all (the equivalence is a product fact)."""
    from driftless.pmbok import crosswalk

    equivalence = crosswalk.EQUIVALENCES["issue_log"]
    body = _body(client, "/pmbok/4.3")
    assert "How Scrum/Kanban projects satisfy this" in body
    assert equivalence.native_source in body
    assert equivalence.rule_in_plain_words in body


def test_the_drill_lists_this_projects_runs_of_the_process(client: TestClient, db: Session) -> None:
    """A recorded ``TechniqueRun`` for this process shows up on the drill page,
    named plainly by date, actor and process."""
    from driftless.pmbok.provenance import MethodContext
    from driftless.services.technique_runs import record_run

    key = catalog.get(CONTROL_COSTS).tools_techniques[0]
    record_run(
        db,
        project_id=1,
        technique_key=key,
        process_id=CONTROL_COSTS,
        actor="jp",
        as_of=AS_OF,
        method=MethodContext.PREDICTIVE,
        source_version="PMBOK-6",
    )
    body = _body(client, DRILL.format(CONTROL_COSTS))
    assert f"Run on {AS_OF.isoformat()} by jp for" in body
