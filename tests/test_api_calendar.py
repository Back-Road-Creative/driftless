"""The calendar feed: the store's dates, subscribable from Outlook, Google or Apple.

Every assertion goes through the HTTP surface and unfolds the feed the way a client does,
so what is pinned is the CONTRACT a subscriber is handed. ``driftless/api/calendar.py``
holds the decisions and their reasons."""

from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.api.secure import TokenGate
from driftless.auth import tokens
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import User

ALPHA, BETA = 1, 2  # a fresh store numbers the two seeded projects in creation order
EVENTS = 4  # three milestones and one sprint; the seeded task is deliberately not one
# Every character RFC 5545 §3.3.11 escapes, in one name: a single unescaped comma splits
# SUMMARY into two values and corrupts the feed for every subscriber.
SPECIAL = "Cut, locked; take 2\\final\nand a second line"
LONG = "é" * 100  # 200 octets, so every fold lands inside a two-octet character
MAX_OCTETS = 75  # RFC 5545 §3.1, excluding the line break


@pytest.fixture
def store(tmp_path: Path) -> Iterator[tuple[Engine, TestClient]]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as client:
        yield engine, client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(store: tuple[Engine, TestClient]) -> TestClient:
    """Two projects' dates, written through the validated API and no other door."""
    client = store[1]

    def post(path: str, **body: Any) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    folio = post("/portfolios", name="Brands", business_id=post("/businesses", name="BRC"))
    for name in ("Alpha", "Beta"):
        post("/projects", name=name, portfolio_id=folio)
    for project, name, day in (
        (ALPHA, "Rough cut locked", "2026-08-15"),
        (ALPHA, SPECIAL, "2026-09-01"),
        (BETA, LONG, "2026-10-05"),
    ):
        post("/milestones", project_id=project, name=name, target_date=day)
    post("/sprints", project_id=ALPHA, name="S1", start_date="2026-08-03", end_date="2026-08-14")
    stream = post("/workstreams", name="Edit", project_id=ALPHA)
    post("/tasks", name="Colour grade", workstream_id=stream, estimate_unit="hours")
    return client


def _lines(body: str) -> list[str]:
    """The feed's content lines, folding undone exactly as a client undoes it."""
    return body.replace("\r\n ", "").split("\r\n")[:-1]


def _values(body: str, prop: str) -> list[str]:
    """Every value of ``prop`` in feed order, ignoring parameters (``;VALUE=DATE``)."""
    named = (line.split(":", 1) for line in _lines(body))
    return [value for key, value in named if key.split(";")[0] == prop]


def test_the_feed_is_one_vcalendar_carrying_an_event_per_dated_record(seeded: TestClient) -> None:
    response = seeded.get("/calendar.ics")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/calendar")
    lines = _lines(response.text)
    assert (lines[0], lines[1], lines[-1]) == ("BEGIN:VCALENDAR", "VERSION:2.0", "END:VCALENDAR")
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == EVENTS
    # A task carries no date of its own — its window belongs to a baseline line, one per
    # plan version — so it is deliberately not an event. See the module docstring.
    assert "Colour grade" not in response.text
    # Nothing in the feed reads a clock, DTSTAMP included, so a proxy may cache it.
    assert seeded.get("/calendar.ics").content == response.content


def test_a_milestone_and_a_sprint_are_all_day_with_an_exclusive_end(seeded: TestClient) -> None:
    """No invented hour, and an end one day past the last — RFC 5545's DTEND."""
    body = seeded.get("/calendar.ics").text
    assert "DTSTART;VALUE=DATE:20260815" in _lines(body)  # a DATE value, not a DATE-TIME
    assert _values(body, "SUMMARY")[0] == "Rough cut locked"
    assert (_values(body, "DTEND")[0], _values(body, "DTSTART")[-1]) == ("20260816", "20260803")
    assert _values(body, "DTEND")[-1] == "20260815"  # the sprint ends 14 Aug, exclusively


def test_uids_are_unique_stable_across_fetches_and_survive_a_rename(seeded: TestClient) -> None:
    """A client updates by UID: a UID that moved is a duplicate nobody can undo."""
    uids = _values(seeded.get("/calendar.ics").text, "UID")
    assert len(set(uids)) == len(uids) == EVENTS
    assert uids[0] == "milestone-1@driftless" and uids[-1] == "sprint-1@driftless"
    assert _values(seeded.get("/calendar.ics").text, "UID") == uids
    assert seeded.patch("/milestones/1", json={"name": "Rough cut locked (v2)"}).status_code == 200
    renamed = seeded.get("/calendar.ics").text
    assert _values(renamed, "UID") == uids
    assert _values(renamed, "SUMMARY")[0] == "Rough cut locked (v2)"


def test_names_are_escaped_and_long_lines_folded_at_75_octets(seeded: TestClient) -> None:
    """The two ways a name breaks a feed: an unescaped delimiter, and an over-long line."""
    body = seeded.get("/calendar.ics").text
    assert body.endswith("\r\n")
    assert _values(body, "SUMMARY")[1] == "Cut\\, locked\\; take 2\\\\final\\nand a second line"
    assert _values(body, "SUMMARY")[2] == LONG  # unfolds back to exactly what was written
    over = [line for line in body.split("\r\n") if len(line.encode()) > MAX_OCTETS]
    assert not over, over  # every fold here lands inside a two-octet character


def test_a_projects_feed_carries_only_that_projects_dates(seeded: TestClient) -> None:
    """Scope lives in the PATH: a subscription URL cannot change meaning under a client."""
    body = seeded.get(f"/projects/{ALPHA}/calendar.ics").text
    assert _lines(body).count("BEGIN:VEVENT") == EVENTS - 1
    assert LONG not in body  # Beta's milestone
    assert "X-WR-CALNAME:Alpha" in _lines(body)
    assert seeded.get("/projects/999/calendar.ics").status_code == 404


def test_the_feed_is_bounded_at_one_statement_per_dated_kind(
    store: tuple[Engine, TestClient], seeded: TestClient
) -> None:
    """Two selects whatever the store holds — a calendar must not walk row by row."""
    seen: list[Any] = []
    event.listen(store[0], "before_cursor_execute", lambda *_: seen.append(1))
    assert seeded.get("/calendar.ics").status_code == 200
    assert len(seen) <= 4, f"the whole-store feed ran {len(seen)} statements (measures 2)"


def test_a_viewer_may_subscribe(store: tuple[Engine, TestClient]) -> None:
    """Role gating is by METHOD and a subscription is a GET: a read-only viewer reads it."""
    with new_session_factory(store[0])() as db:
        db.add(user := User(username="jp", password_hash="x", role="viewer"))
        db.commit()
        headers = {"Authorization": f"Bearer {tokens.issue(db, user, label='calendar')}"}
        gate = TokenGate(app, "s3cr3t", session_scope=lambda: nullcontext(db))
        response = TestClient(gate).get("/calendar.ics", headers=headers)
    assert (response.status_code, response.text[:15]) == (200, "BEGIN:VCALENDAR")
