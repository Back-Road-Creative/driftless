"""The wizard's form collects the fields its outputs are made of (F-G1, browser half).

The producers refuse a field nobody supplied, and the select offered a browser eleven
kinds it had no input for — so every one of those clicks was a 422 a person could not
answer. The form now renders an input per field the step's kinds need, and the values
posted are the values stored.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.wizard import cli as wizard_cli
import test_web_pages
from test_web_pages import AS_OF

# The seeded https store, reused as is (assigned, not imported: a test's own
# ``client``/``db`` parameter must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db

Q = f"?as_of={AS_OF.isoformat()}"
NAMED = re.compile(r'<(input|select)[^>]*\bname="([^"]+)"')


def _pair(browser: TestClient) -> dict[str, str]:
    from driftless.web import csrf

    return {csrf.FIELD: browser.cookies[csrf.COOKIE]}


def test_the_form_offers_an_input_for_every_field_its_kinds_need(client: TestClient) -> None:
    """Read off ``required_fields`` for the kinds the step itself offers, so a kind given
    a producer is asked for by the form on the same commit — no template edit to forget.
    The charter step is produced first because its one output is prose; the step after it
    (13.1) wants a stakeholder's name, which is what this form could never collect."""
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": "Six-week leads."}
        | _pair(client),
        follow_redirects=True,
    )
    page = client.get(f"/projects/1/wizard{Q}").text
    offered = re.findall(r'<option value="([^"]+)"', page)
    needed = {field for kind in offered for field in wizard_cli.required_fields(kind)}
    assert needed, f"no offered kind on this step needs a field: {offered}"
    rendered = {name for _tag, name in NAMED.findall(page)}
    assert needed <= rendered, f"the form cannot collect {sorted(needed - rendered)}"


@pytest.mark.parametrize(
    ("kind", "posted", "model", "column", "expected"),
    [
        ("stakeholder_register", {"name": "Ada Lovelace"}, m.Stakeholder, "name", "Ada Lovelace"),
        ("risk_register", {"description": "Weather", "probability": "0.4", "impact": "2500"},
         m.Risk, "impact", 2500.0),
        ("cost_baseline", {"category": "materials", "planned_amount": "2500"},
         m.BudgetLine, "planned_amount", 2500.0),
        ("quality_report", {"metric": "colour_delta", "target_value": "2", "actual_value": "1.5"},
         m.QualityMeasurement, "metric", "colour_delta"),
        ("agreements", {"vendor": "Skyward Drones"}, m.ProcurementAgreement, "vendor",
         "Skyward Drones"),
        ("milestone_list", {"name": "Rig delivered", "target_date": "2026-04-30"},
         m.Milestone, "name", "Rig delivered"),
    ],
)  # fmt: skip
def test_the_row_carries_what_the_browser_typed(
    client: TestClient,
    db: Session,
    kind: str,
    posted: dict[str, str],
    model: type[object],
    column: str,
    expected: object,
) -> None:
    """Quote-for-quote: a form that renders an input and then drops what it collected is
    the same bug as the placeholder it replaced."""
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": kind, "as_of": AS_OF.isoformat(), **posted} | _pair(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200, resp.text
    # The shared ``db`` fixture seeds one Risk of its own (test_web_pages._seed, for the
    # risk-response planner's own coverage) -- the wizard's row is the LATEST one, never
    # "the only one", so this reads what the browser just posted, not whichever row a
    # sibling fixture happened to add first.
    row = db.scalars(select(model).order_by(model.id.desc())).first()  # type: ignore[attr-defined]
    assert row is not None
    assert getattr(row, column) == expected


def test_process_query_param_404s_on_an_unknown_id(client: TestClient) -> None:
    """``?process=`` is client-controlled bytes like any other address segment: an
    id the live catalog does not name 404s — same as ``/pmbok/{process_id}`` —
    never a 500 from ``catalog.get``'s own ``KeyError``."""
    assert client.get(f"/projects/1/wizard{Q}&process=99.9").status_code == 404


def test_a_refusal_hands_the_typed_fields_back(client: TestClient, db: Session) -> None:
    """A refused post re-renders the FORM carrying what was typed — the POST replaced the
    page, so nothing else holds those words. Same contract the prose textarea has. The
    refusal here is an oversize name, refused by the same schema the API refuses it with."""
    client.get(f"/projects/1/wizard{Q}")  # mints the CSRF pair
    client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": "Six-week leads."}
        | _pair(client),
        follow_redirects=True,
    )
    oversize = "Ada Lovelace " * 20  # past the schema's 200-character ceiling
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "stakeholder_register", "name": oversize, "as_of": AS_OF.isoformat()}
        | _pair(client),
    )
    assert resp.status_code == 422
    assert f'value="{oversize}"' in resp.text, "the refusal destroyed the typed name"
    assert not db.scalars(select(m.Stakeholder)).all(), "a refused apply wrote a row"
