"""A change request records which PMBOK process raised it.

The wizard step and the CLI's ``--process`` flag are the surfaces that know the
acting process, so they pass it through; the API accepts it from any caller but
refuses an id the live catalog does not name — no write path can invent a
process. Nullable because history and plain API callers may not know.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import cli
from driftless import models as m
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.demo.data import ANCHOR, demo_payload
from driftless.pmbok import catalog
from driftless.web import csrf

JAN, AS_OF = "2026-01-31", "2026-03-31"
WHY = "The drone crew is weather-bound; the March shoot moves to April."  # posted, not invented
Q = f"?as_of={AS_OF}"


@pytest.fixture
def factory(tmp_path: Path) -> Any:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)
    register_changelog(made)
    return made


@pytest.fixture
def client(factory: Any) -> Iterator[TestClient]:
    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    # https, as production serves: the CSRF cookie is ``Secure``.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _project(client: TestClient) -> int:
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(
        client, "/projects", name="GMS", portfolio_id=portfolio, delivery_mode="predictive"
    )


def _pair(client: TestClient) -> dict[str, str]:
    return {csrf.FIELD: client.cookies[csrf.COOKIE]}


def test_change_request_provenance_round_trips(client: TestClient) -> None:
    """POST persists the origin, GET returns it, a PATCH carries it along — and an
    omitted origin stays null rather than invented."""
    project = _project(client)
    body = {"project_id": project, "description": "Two pickup days", "raised_on": JAN}
    made = client.post("/change-requests", json=body | {"origin_process_id": "5.6"})
    assert made.status_code == 201, made.text
    assert made.json()["origin_process_id"] == "5.6"
    row_id = made.json()["id"]

    assert client.get(f"/change-requests/{row_id}").json()["origin_process_id"] == "5.6"
    patched = client.patch(f"/change-requests/{row_id}", json={"description": "Three days"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["origin_process_id"] == "5.6"
    moved = client.patch(f"/change-requests/{row_id}", json={"origin_process_id": "5.5"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["origin_process_id"] == "5.5"

    plain = client.post("/change-requests", json=body)
    assert plain.status_code == 201, plain.text
    assert plain.json()["origin_process_id"] is None


@pytest.mark.parametrize("bad", ["99.9", "not-a-clause"])
def test_change_request_origin_must_name_a_catalog_process(client: TestClient, bad: str) -> None:
    """A non-catalog id is refused at the boundary — on create AND on patch."""
    project = _project(client)
    body = {"project_id": project, "description": "Invented", "raised_on": JAN}
    refused = client.post("/change-requests", json=body | {"origin_process_id": bad})
    assert refused.status_code == 422, refused.text

    row_id = _create(client, "/change-requests", origin_process_id="5.6", **body)
    walked = client.patch(f"/change-requests/{row_id}", json={"origin_process_id": bad})
    assert walked.status_code == 422, "a patch must not launder a non-catalog process id in"


def test_the_wizard_form_carries_the_steps_process_id(client: TestClient, factory: Any) -> None:
    """The hidden field equals the process the page says is acting, and the row
    the form writes carries it — provenance captured where it is known."""
    project = _project(client)
    page = client.get(f"/projects/{project}/wizard{Q}").text
    hidden = re.search(r'name="origin_process_id" value="([^"]+)"', page)
    assert hidden, "the wizard form does not carry the acting process"
    shown = re.search(r"Next: ([\d.]+)", page)
    assert shown and hidden.group(1) == shown.group(1), page

    pid = hidden.group(1)
    resp = client.post(
        f"/projects/{project}/wizard/apply{Q}",
        data={"kind": "change_log", "as_of": AS_OF, "description": WHY, "origin_process_id": pid}
        | _pair(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200, resp.text
    with factory() as db:
        row = db.scalars(select(m.ChangeRequest)).one()
        assert (row.origin_process_id, row.description) == (pid, WHY)


def test_the_wizard_form_refuses_a_forged_process_id(client: TestClient, factory: Any) -> None:
    """The hidden field is client-controlled bytes like any other, so a forged id
    answers 422 from the same schema the API refuses it with — and writes nothing."""
    project = _project(client)
    client.get(f"/projects/{project}/wizard{Q}")  # mints the pair
    resp = client.post(
        f"/projects/{project}/wizard/apply{Q}",
        data={"kind": "change_log", "as_of": AS_OF, "description": WHY, "origin_process_id": "99.9"}
        | _pair(client),
    )
    assert resp.status_code == 422, resp.text
    with factory() as db:
        assert not db.scalars(select(m.ChangeRequest)).all(), "a refused origin wrote a row"


def test_wizard_cli_apply_records_the_acting_process(tmp_path: Path) -> None:
    """``wizard apply --kind change_log --process 5.6`` writes the attributed row."""
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        db.add(
            m.Project(name="GMS", portfolio=m.Portfolio(name="C", business=m.Business(name="BRC")))
        )
        db.commit()

    argv = ["wizard", "apply", "--project", "GMS", "--kind", "change_log", "--field",
            f"description={WHY}", "--process", "5.6", "--as-of", AS_OF, "--db-url", url]  # fmt: skip
    assert cli.main(argv) == 0
    with new_session_factory(engine)() as db:
        assert db.scalars(select(m.ChangeRequest)).one().origin_process_id == "5.6"


def test_demo_change_requests_are_attributed() -> None:
    """Both seeded change requests name a live catalog process, and the payload rows
    post as built — so the attribution flows through the real API untouched."""
    ids = {p.id for p in catalog.PROCESSES}
    requests = [
        change
        for business in demo_payload(ANCHOR)["businesses"]
        for portfolio in business["portfolios"]
        for project in portfolio["projects"]
        for change in project.get("change_requests", ())
    ]
    assert requests, "the demo payload lost its change requests"
    assert all(change["origin_process_id"] in ids for change in requests)
