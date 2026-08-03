"""The task board: ``/projects/{id}/board`` — every task in the column its status names.

``TASK_STATUSES`` has always been a closed vocabulary on the model, and no view showed a
project's work laid out by it. These pin the page: a column per status DERIVED from that
vocabulary (asserted against the tuple itself, so a status added to the model fails the page
rather than silently vanishing from it), each task in its own column and labelled with its
workstream, blocked legible with every class attribute stripped off, an empty column that
says so, the shared empty state where a project has no tasks, a statement count flat in the
task count, and a viewer able to read the whole thing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import TASK_STATUSES
from test_perf_n1 import count_route
import test_web_csrf
from test_web_csrf import Gate, _client

# The gated app and its per-credential clients, reused as is (the fixture assigned, not
# imported: this file's own ``gated`` parameter must not read as a redefined import —
# ``test_web_a11y`` borrows its seeded store the same way).
gated = test_web_csrf.gated

PAGE, BARE_PAGE = "/projects/1/board", "/projects/2/board"
# Measured 2 — the project, then ONE query for its tasks with each task's workstream and
# assignee joined into the same round trip — and identical with twelve more tasks. Two of
# headroom; a lazy load per card trips the equality below before it reaches this.
MAX_BOARD_STMTS = 4
_CLASS = re.compile(r'\sclass="[^"]*"')
_SECTION = re.compile(r'<section[^>]*data-column="([^"]+)"[^>]*>(.*?)</section>', re.S)
_CARD = re.compile(r'<li[^>]*data-task="([^"]+)"[^>]*>(.*?)</li>', re.S)
_COUNT = re.compile(r'data-count="[^"]*">(\d+)<')


def _seed(db: Session) -> None:
    """Project 1: three tasks across two workstreams, one in every status but ``done`` —
    so a populated column and an empty one are both live. Project 2 has no tasks at all."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add_all([project, m.Project(name="Fresh", portfolio=portfolio, delivery_mode="predictive")])
    db.commit()  # GMS is added first, so it is project 1 and Fresh is project 2
    streams = {name: m.Workstream(name=name, project=project) for name in ("Edit", "Finish")}
    dana = m.Person(name="Dana")
    db.add_all(
        m.Task(name=n, workstream=streams[w], status=s, percent_complete=p, estimate=e, assignee=a)
        for n, w, s, p, e, a in (
            ("Cut", "Edit", "todo", 0, 8.0, dana),
            ("Grade", "Edit", "in_progress", 60, 12.0, dana),
            ("Colour", "Finish", "blocked", 0, None, None),
        )
    )
    db.commit()


def _pile_on(db: Session, count: int) -> None:
    """More tasks on project 1's first workstream — the volume the cost test adds."""
    stream = db.get(m.Workstream, 1)
    for n in range(count):
        db.add(m.Task(name=f"Extra {n}", workstream=stream, status="blocked"))
    db.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:  # a file: TestClient serves on another thread
    engine = new_engine(f"sqlite:///{tmp_path / 'board.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """https: an http jar drops the Secure CSRF cookie, which then remints per render."""
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as browser:
        yield browser
    real_app.dependency_overrides.clear()


def _columns(body: str) -> dict[str, str]:
    """Each rendered column's markup, keyed by the status it is the column for."""
    return dict(_SECTION.findall(body))


def _cards(markup: str) -> dict[str, str]:
    """Each card in ``markup``, keyed by its task name."""
    return dict(_CARD.findall(markup))


def test_the_column_set_is_the_models_vocabulary_and_nothing_else(client: TestClient) -> None:
    """Asserted against ``TASK_STATUSES`` itself, in its order: a status added to the model
    has to appear here without anyone editing the template, and one dropped cannot linger.
    Byte-identity rides along — nothing on this page reads a clock or a random."""
    body = client.get(PAGE).text
    assert list(_columns(body)) == list(TASK_STATUSES), "the columns are not the vocabulary"
    assert client.get(PAGE).text == body, "a refetch did not regenerate byte-identically"


def test_each_task_sits_in_the_column_its_status_names(client: TestClient) -> None:
    """And carries enough to act on without becoming a second project hub."""
    columns = _columns(client.get(PAGE).text)
    where = {name: status for status, inner in columns.items() for name in _cards(inner)}
    assert where == {"Cut": "todo", "Grade": "in_progress", "Colour": "blocked"}
    grade = _cards(columns["in_progress"])["Grade"]
    for shown in ("Edit", "Dana", "60%", "12"):
        assert shown in grade, f"a card omits {shown!r}: workstream, assignee, percent, estimate"
    assert "Unassigned" in _cards(columns["blocked"])["Colour"], "an unowned card says nothing"


def test_blocked_reads_as_blocked_with_every_class_stripped(client: TestClient) -> None:
    """RAG hue is never the only carrier of meaning (#1635). Strip every ``class`` — the
    only thing that can colour a card, since the palette lives entirely in base.html — and
    the card still says the word, so it reads as blocked in greyscale and out of context."""
    card = _cards(_columns(client.get(PAGE).text)["blocked"])["Colour"]
    assert "style=" not in card, "a card spells its own styling, out of the token set's reach"
    assert "Blocked" in _CLASS.sub("", card), "blocked is carried by colour alone"


def test_an_empty_column_says_so_and_every_column_counts_itself(client: TestClient) -> None:
    columns = _columns(client.get(PAGE).text)
    counts = [int(n) for s in TASK_STATUSES for n in _COUNT.findall(columns[s])]
    assert counts == [1, 1, 1, 0], "a column's count is not its own card count"
    done = columns["done"]
    assert not _cards(done) and 'data-empty-column="done"' in done
    assert "No done tasks" in done, "an empty column renders an unexplained empty box"


def test_a_project_with_no_tasks_renders_the_shared_empty_state(client: TestClient) -> None:
    body = client.get(BARE_PAGE).text
    assert not _columns(body), "four empty boxes shipped where there is no work at all"
    section = re.search(r'<section class="empty-state".*?</section>', body, re.S)
    assert section, "a project with no tasks renders no designed empty state"
    assert "<code" in section.group(0) or "<a " in section.group(0), "it names no next step"


def test_the_board_does_not_query_per_task(client: TestClient, db: Session) -> None:
    """One query for the tasks with workstream and assignee batched in, never one per card:
    so fifteen tasks cost exactly what three cost."""
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    few, status = count_route(engine, client, PAGE)
    assert status == 200, status
    _pile_on(db, 12)
    many, status = count_route(engine, client, PAGE)
    assert (status, many) == (200, few) and many <= MAX_BOARD_STMTS, (few, many)


def test_a_viewer_can_read_the_board(gated: Gate) -> None:
    """The board is a read, so the role gate must let a viewer's token through to it."""
    reader = _client(gated, Authorization=f"Bearer {gated.viewer}")
    page = reader.get("/projects/1/board")
    assert page.status_code == 200, page.text
    assert "Grade" in page.text, "the seeded task never reached the board"
