"""A name typed by one user must not become an instruction to another user's program.

Two exports hand attacker-authorable text to something that reads it as more than
text: ``?format=csv`` to a spreadsheet, which runs a cell beginning ``= + - @``
(or whitespace hiding one) as a formula the moment the file opens, and
``/calendar.ics`` to a calendar client, which frames values by line, so a bare CR
inside a name ends ``SUMMARY`` early and lets the rest of the name become a
property of its own. Both are fixed in the renderer rather than at a route, so
every list route and both feed scopes heal at once — hence the tests seed through
the ordinary validated API and read the ordinary published surface.
"""

import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory

PAYLOAD = "=cmd|' /C calc'!A0"  # the classic: a cell that runs a command on open
LEADS = ("=", "+", "-", "@", "\t", "\r")  # every lead a spreadsheet may read as a formula
CR = "Locked\rSUMMARY:Pwned"  # a bare CR would end SUMMARY and inject a second property


@pytest.fixture
def store(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _post(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.fixture
def folio(store: TestClient) -> int:
    return _post(
        store, "/portfolios", name="Brands", business_id=_post(store, "/businesses", name="BRC")
    )


def _column(body: str, name: str) -> list[str]:
    return [row[name] for row in csv.DictReader(io.StringIO(body))]


def _summaries(body: str) -> list[str]:
    """Every ``SUMMARY`` value, folding undone exactly as a client undoes it."""
    lines = body.replace("\r\n ", "").split("\r\n")[:-1]
    return [line.split(":", 1)[1] for line in lines if line.startswith("SUMMARY:")]


def test_a_formula_lead_in_an_exported_name_is_neutralised(store: TestClient, folio: int) -> None:
    """The text still reads; the spreadsheet no longer runs it."""
    _post(store, "/projects", name=PAYLOAD, portfolio_id=folio)
    for lead in LEADS:
        _post(store, "/projects", name=f'{lead}HYPERLINK("http://x")', portfolio_id=folio)

    names = _column(store.get("/projects", params={"format": "csv"}).text, "name")

    assert names[0] == f"'{PAYLOAD}"  # marked literal, not truncated or stripped
    assert [name[1:] for name in names[1:]] == [f'{lead}HYPERLINK("http://x")' for lead in LEADS]
    assert not [name for name in names if name.startswith(LEADS)]


def test_a_negative_number_still_exports_as_a_number(store: TestClient, folio: int) -> None:
    """A minus sign leads a formula and a negative alike — a variance must stay usable."""
    project = _post(store, "/projects", name="GMS", portfolio_id=folio)
    _post(
        store,
        "/quality-measurements",
        project_id=project,
        metric="Cost variance",
        target_value=0.0,
        actual_value=-42.5,
        measured_on="2026-08-15",
    )

    body = store.get("/quality-measurements", params={"format": "csv"}).text

    assert _column(body, "actual_value") == ["-42.5"]
    assert _column(body, "target_value") == ["0.0"]
    assert _column(body, "measured_on") == ["2026-08-15"]


def test_a_bare_cr_in_a_name_cannot_break_the_ical_framing(store: TestClient, folio: int) -> None:
    """A CR the client would read as a line break becomes the one escape RFC 5545 has."""
    project = _post(store, "/projects", name="Alpha", portfolio_id=folio)
    for name, day in ((CR, "2026-08-15"), ("Windows\r\nsecond line", "2026-08-16")):
        _post(store, "/milestones", project_id=project, name=name, target_date=day)

    body = store.get("/calendar.ics").text

    assert "\r" not in body.replace("\r\n", "")  # every CR left in the feed frames a line
    # A CRLF collapses to ONE break, not two: the escapes are what a subscriber reads back.
    assert _summaries(body) == ["Locked\\nSUMMARY:Pwned", "Windows\\nsecond line"]
