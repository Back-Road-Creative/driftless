"""Every sign-off vocabulary member is reachable from a rendered form (audit F1).

``SIGNOFF_SUBJECTS`` and ``SIGNOFF_DECISIONS`` are closed vocabularies the model, the
process-state engine and the process-map legend all treat as first-class — yet the
browser could post only one of the two subject kinds and four of the five decisions, so
*waiving a process* (the sanctioned way to tailor a process out of every completeness
figure) existed only for a hand-written HTTP call, and the map drew a legend for a state
no page could produce.

The gate is structural, not a spot check: it walks every GET page the app registers,
reads the sign-off forms that SHIPPED, and asserts the offered values EQUAL the
vocabularies. A member added to the model therefore fails here until some form offers
it — the same shape ``test_web_board`` applies to ``TASK_STATUSES`` — rather than
existing in the store and silently missing the UI.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import (
    Baseline,
    BaselineLine,
    Department,
    Gate,
    Program,
    Project,
    SignOff,
    Task,
)
from driftless.models.governance import SIGNOFF_DECISIONS, SIGNOFF_SUBJECTS
from driftless.pmbok import catalog, state
from test_web_csrf import SAMPLE, _forms, _web_paths
import test_web_pages
from test_web_pages import AS_OF, Q

# The seeded https store, reused as is (assigned, not imported: a test's own parameter
# must not read as a redefined import) — the same idiom test_web_a11y uses.
client, db = test_web_pages.client, test_web_pages.db

_SIGN_OFF_FORM = re.compile(r'<form[^>]*action="/sign-off"[^>]*>(.*?)</form>', re.S)
_SUBJECT_KIND = re.compile(r'name="subject_kind"[^>]*value="([^"]*)"')
_DECISION = re.compile(r'<select[^>]*name="decision".*?</select>', re.S)
_OPTION = re.compile(r'<option value="([^"]*)"')


def _sign_off_forms(browser: TestClient, store: Session) -> list[str]:
    """Every sign-off form on every GET page the app registers, as rendered HTML.

    The two rows the seed lacks go in first — the same pair ``test_web_csrf``'s page
    walk adds — so no route shape answers 404 and the walk reads real markup.
    """
    project = store.scalars(select(Project)).one()
    project.program = Program(name="Reels", portfolio=project.portfolio)
    store.add(Department(name="Post", business=project.portfolio.business))
    # A second approved baseline, so /projects/{}/baselines/diff's default pair (the
    # two most recent approved) has one to draw, and its "sign off v2" form ships —
    # the same addition test_web_csrf makes for the sign-out-form walk.
    task = store.scalars(select(Task)).first()
    if task is not None:
        store.add(v2 := Baseline(project=project, version=2, status="approved"))
        store.add(
            BaselineLine(
                baseline=v2, task=task, planned_cost=1.0, planned_start=AS_OF, planned_finish=AS_OF
            )
        )
    # A gate, so /projects/{}/gates renders a sign-off form and its "gate" subject
    # kind ships too — the same addition made above for "baseline".
    store.add(Gate(project=project, name="Kickoff", position=1, required_processes=""))
    store.commit()
    forms: list[str] = []
    for shape in sorted(_web_paths("GET")):
        page = browser.get(shape.replace("{}", SAMPLE.get(shape, "")) + Q)
        assert page.status_code == 200, f"{shape} -> {page.status_code}"
        forms += _SIGN_OFF_FORM.findall(page.text)
    return forms


def test_every_signoff_vocabulary_member_is_offered_by_a_rendered_form(
    client: TestClient, db: Session
) -> None:
    forms = _sign_off_forms(client, db)
    assert forms, "no page renders a sign-off form, so this test proves nothing"
    kinds = {kind for form in forms for kind in _SUBJECT_KIND.findall(form)}
    assert kinds == set(SIGNOFF_SUBJECTS), (
        f"the rendered forms can post {sorted(kinds)}; the model accepts "
        f"{sorted(SIGNOFF_SUBJECTS)} — a subject kind no form posts is reachable only by "
        "hand-writing an HTTP call"
    )
    for form in forms:
        offered = _DECISION.search(form)
        assert offered, "a sign-off form renders no decision select"
        values = set(_OPTION.findall(offered.group(0)))
        assert values == set(SIGNOFF_DECISIONS), (
            f"a sign-off form offers {sorted(values)}; the model accepts "
            f"{sorted(SIGNOFF_DECISIONS)} — build the options FROM the vocabulary so a new "
            "decision cannot appear in the model and miss the UI"
        )


def test_the_process_map_waives_a_process_and_reads_the_waiver_back(
    client: TestClient, db: Session
) -> None:
    """The round trip the legend has always promised: choose a process, waive it, and
    the cell that explains ``waived`` now says so — through the same validated boundary
    the JSON route uses, redirected back to the map by the subject, not by a posted
    target."""
    page = client.get(f"/projects/1/process-map{Q}")
    assert page.status_code == 200, page.text
    action, body = next((a, b) for a, b in _forms(page.text) if a == "/sign-off")
    first = catalog.PROCESSES[0]
    project = db.scalars(select(Project)).one()
    assert body["subject_kind"] == "process"
    assert body["subject_ref"] == state.process_subject_ref(first, project)

    posted = client.post(action, data=body | {"decision": "waived"}, follow_redirects=False)

    assert posted.status_code == 303, posted.text
    assert posted.headers["location"] == f"/projects/1/process-map?as_of={AS_OF.isoformat()}"
    row = db.scalars(select(SignOff)).one()
    assert (row.subject_kind, row.decision) == ("process", "waived")
    assert row.subject_ref == state.process_subject_ref(first, project)
    refreshed = client.get(f"/projects/1/process-map{Q}").text
    assert f'title="waived">{first.id} {first.name}' in refreshed
