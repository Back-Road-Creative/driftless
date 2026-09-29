"""Contract tests for ``Note``: append-only, filed against any record like
``ArtifactLink``. Proof the append-only claim holds, not just asserted:
mutating a persisted row is refused at the model layer (an ORM event listener
raises before the flush reaches SQLite), the API never registers PATCH/DELETE
routes for it, and an insert still lands in the ChangeLog like any other row.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import Note
from driftless.models.annotations import NoteIsAppendOnly

AS_OF = date(2026, 3, 31)


def test_updating_a_persisted_note_is_refused_at_the_model_layer(db: Session) -> None:
    note = Note(record_kind="department", record_id="1", body="first", actor="sam", as_of=AS_OF)
    db.add(note)
    db.commit()

    note.body = "edited"
    with pytest.raises(NoteIsAppendOnly):
        db.commit()


def test_deleting_a_persisted_note_is_refused_at_the_model_layer(db: Session) -> None:
    note = Note(record_kind="department", record_id="1", body="first", actor="sam", as_of=AS_OF)
    db.add(note)
    db.commit()

    db.delete(note)
    with pytest.raises(NoteIsAppendOnly):
        db.commit()


def test_a_superseding_note_references_the_prior_note(db: Session) -> None:
    first = Note(record_kind="department", record_id="1", body="v1", actor="sam", as_of=AS_OF)
    db.add(first)
    db.commit()

    second = Note(
        record_kind="department",
        record_id="1",
        body="v2",
        actor="sam",
        as_of=AS_OF,
        supersedes_id=first.id,
    )
    db.add(second)
    db.commit()

    assert second.supersedes_id == first.id


def test_a_note_is_logged_like_any_other_row(db: Session) -> None:
    engine = db.get_bind()
    factory = sessionmaker(bind=engine)
    register_changelog(factory)
    with factory() as logged_session:
        note = Note(record_kind="department", record_id="1", body="first", actor="sam", as_of=AS_OF)
        logged_session.add(note)
        logged_session.commit()

        rows = list(logged_session.scalars(select(ChangeLog).order_by(ChangeLog.id)))
        (row,) = rows
        assert (row.table_name, row.operation, row.row_id) == ("note", "insert", str(note.id))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)

    def _session() -> Iterator[Session]:
        with new_session_factory(engine)() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_note(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "record_kind": "department",
        "record_id": "1",
        "body": "first note",
        "actor": "sam",
        "as_of": AS_OF.isoformat(),
        **overrides,
    }
    response = client.post("/notes", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_the_api_creates_and_reads_a_note(client: TestClient) -> None:
    created = _create_note(client)

    got = client.get(f"/notes/{created['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["body"] == "first note"


def test_the_api_accepts_a_supersedes_id(client: TestClient) -> None:
    first = _create_note(client)
    second = _create_note(client, body="revised", supersedes_id=first["id"])

    assert second["supersedes_id"] == first["id"]


def test_the_api_refuses_patch_and_delete_on_a_note(client: TestClient) -> None:
    created = _create_note(client)

    patched = client.patch(f"/notes/{created['id']}", json={"body": "edited"})
    assert patched.status_code == 405, patched.text

    deleted = client.delete(f"/notes/{created['id']}")
    assert deleted.status_code == 405, deleted.text
