"""The decisions and meetings page: ``GET/POST /projects/{id}/assist/decisions``.

Voting, weighted scoring, the autocratic preview and facilitation planning are all
no-write what-ifs off GET params; meeting evidence is the one write the page makes,
through the same ``TechniqueRun`` ledger ``tests/test_technique_runs.py`` covers.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import Business, Portfolio, Project, TechniqueRun

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_page_renders_with_no_query_params(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/decisions{Q}")
    assert resp.status_code == 200
    assert "Decisions and meetings" in resp.text


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/decisions{Q}").status_code == 404


def test_a_vote_what_if_computes_without_writing(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}"
        "&vote_options=red,blue&vote_ballots=red,red,blue&vote_rule=majority"
    )
    assert resp.status_code == 200
    assert "red won 2 of 3 ballots, more than half" in resp.text


def test_an_unlisted_ballot_422s(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/decisions{Q}&vote_options=red,blue&vote_ballots=purple")
    assert resp.status_code == 422


def test_a_multicriteria_what_if_ranks_and_names_the_deciding_criterion(
    client: TestClient,
) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}"
        "&mc_options=vendor-a,vendor-b&mc_weights=cost:0.6,quality:0.4"
        "&mc_scores=vendor-a:cost=10,quality=5;vendor-b:cost=4,quality=6"
    )
    assert resp.status_code == 200
    assert "vendor-a pulled ahead of vendor-b most on cost" in resp.text


def test_a_facilitation_plan_shows_the_fixed_agenda(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}"
        "&facil_purpose=Prioritise+backlog&facil_participants=jp,ada&facil_technique=workshop"
    )
    assert resp.status_code == 200
    assert "State the purpose and the decision or artifact the workshop must produce." in resp.text


def test_an_autocratic_preview_shows_the_decider_and_rationale(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}&autocratic_decider=PM&autocratic_rationale=Deadline+forced+it"
    )
    assert resp.status_code == 200
    assert "PM" in resp.text and "Deadline forced it" in resp.text


def test_recording_a_meeting_writes_a_technique_run_and_redirects(
    client: TestClient, db: Session
) -> None:
    before = db.query(TechniqueRun).count()
    page = client.get(f"/projects/1/assist/decisions{Q}")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    resp = client.post(
        "/projects/1/assist/decisions",
        data={
            "csrf_token": token,
            "as_of": AS_OF.isoformat(),
            "actor": "jp",
            "purpose": "Kickoff",
            "attendees": "jp\nada",
            "decisions": "Scope confirmed",
            "actions": "Send charter | jp | 2026-04-01",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/projects/1/assist/decisions{Q}"
    assert db.query(TechniqueRun).count() == before + 1
    run = db.query(TechniqueRun).order_by(TechniqueRun.id.desc()).first()
    assert run is not None
    assert run.technique_key == "meetings"
    assert run.actor == "jp"
    assert '"attendees"' in run.inputs_snapshot


def test_the_meeting_evidence_list_shows_a_recorded_run(client: TestClient) -> None:
    page = client.get(f"/projects/1/assist/decisions{Q}")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    client.post(
        "/projects/1/assist/decisions",
        data={
            "csrf_token": token,
            "as_of": AS_OF.isoformat(),
            "actor": "jp",
            "purpose": "Kickoff",
            "attendees": "jp",
            "decisions": "",
            "actions": "",
        },
        follow_redirects=False,
    )
    resp = client.get(f"/projects/1/assist/decisions{Q}")
    assert "jp" in resp.text
    assert "No meetings recorded yet" not in resp.text


def test_the_five_routed_techniques_all_point_here(client: TestClient) -> None:
    for key in (
        "voting",
        "multicriteria_decision_analysis",
        "autocratic_decision_making",
        "focus_groups",
        "meetings",
    ):
        assert ASSISTANT_ROUTES[key] == "/projects/{project_id}/assist/decisions"


def _token(client: TestClient) -> str:
    page = client.get(f"/projects/1/assist/decisions{Q}")
    token: str = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    return token


def test_parse_csv_reads_blank_as_no_entries() -> None:
    from driftless.web.assist_decisions import _parse_csv

    assert _parse_csv(None) == ()
    assert _parse_csv("") == ()
    assert _parse_csv("red, blue ,, green") == ("red", "blue", "green")


def test_parse_weights_skips_a_pair_with_no_colon_or_no_key() -> None:
    from driftless.web.assist_decisions import _parse_weights

    assert _parse_weights("cost:0.6,badpair,:0.4,quality:0.4") == {
        "cost": 0.6,
        "quality": 0.4,
    }


def test_parse_scores_reads_blank_as_no_entries_and_skips_a_malformed_block() -> None:
    from driftless.web.assist_decisions import _parse_scores

    assert _parse_scores(None) == {}
    assert _parse_scores("") == {}
    assert _parse_scores("badblock;a:cost=8,quality=5;:cost=1") == {
        "a": {"cost": 8.0, "quality": 5.0}
    }


def test_parse_actions_drops_an_unparseable_date_rather_than_the_whole_line() -> None:
    from driftless.web.assist_decisions import _parse_actions

    actions = _parse_actions("Send charter | jp | not-a-date")
    assert actions[0].description == "Send charter"
    assert actions[0].owner == "jp"
    assert actions[0].due is None


def test_an_unknown_voting_rule_422s(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}&vote_options=red,blue&vote_ballots=red&vote_rule=bogus"
    )
    assert resp.status_code == 422


def test_multicriteria_options_that_parse_to_nothing_422s(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/decisions{Q}&mc_options=,,&mc_weights=cost:0.6")
    assert resp.status_code == 422


def test_an_unknown_facilitation_technique_422s(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}"
        "&facil_purpose=Prioritise&facil_participants=jp&facil_technique=bogus"
    )
    assert resp.status_code == 422


def test_facilitation_participants_that_parse_to_nothing_422s(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}&facil_purpose=Prioritise&facil_participants=,,"
    )
    assert resp.status_code == 422


def test_an_autocratic_preview_with_a_blank_rationale_422s(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decisions{Q}&autocratic_decider=PM&autocratic_rationale=+"
    )
    assert resp.status_code == 422


def test_recording_a_meeting_with_no_attendees_422s(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/projects/1/assist/decisions",
        data={
            "csrf_token": token,
            "as_of": AS_OF.isoformat(),
            "actor": "jp",
            "purpose": "Kickoff",
            "attendees": "",
            "decisions": "",
            "actions": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 422


def test_recording_a_meeting_with_no_actor_422s(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/projects/1/assist/decisions",
        data={
            "csrf_token": token,
            "as_of": AS_OF.isoformat(),
            "actor": "",
            "purpose": "Kickoff",
            "attendees": "jp",
            "decisions": "",
            "actions": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 422
