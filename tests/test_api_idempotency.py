"""A retried write must not create a second row.

``bin/driftless-import.py`` POSTs a CSV row at a time and resumes with ``--skip N``. A
crash between the POST landing and the client recording it makes the client retry a row
the store already holds -- and a create carries no natural key, so nothing could tell the
duplicate apart. It stays invisible until a report reads wrong.
"""

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api import idempotency
from driftless.api.app import app, get_session
from driftless.api.idempotency import HEADER
from driftless.db import Base, new_engine, new_session_factory
from driftless.models.idempotency import IdempotencyRecord

BODY = {"name": "Back Road Creative"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """One store behind BOTH routes and gate: the gate reaches it via ``session_scope``,
    so overriding only the request dependency would leave it on another database and
    every assertion here would pass for the wrong reason."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    @contextlib.contextmanager
    def _scope() -> Iterator[Session]:
        with factory() as db:
            yield db
            db.commit()

    monkeypatch.setattr(idempotency, "session_scope", _scope)
    app.dependency_overrides[get_session] = _session
    with TestClient(app) as bound:
        yield bound
    app.dependency_overrides.clear()


def _rows(client: TestClient) -> list[dict[str, object]]:
    return list(client.get("/businesses").json())


def test_a_retried_post_creates_one_row_and_replays_the_first_answer(
    client: TestClient,
) -> None:
    """The bug: one key twice leaves ONE business, answered with the first attempt's reply."""
    first = client.post("/businesses", json=BODY, headers={HEADER: "import-row-1"})
    second = client.post("/businesses", json=BODY, headers={HEADER: "import-row-1"})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replay") == "true"
    assert len(_rows(client)) == 1, "the retry must not have created a second row"


def test_different_keys_still_create_different_rows(client: TestClient) -> None:
    """Only a REPLAYED key is a retry; a fresh key is a new row."""
    client.post("/businesses", json=BODY, headers={HEADER: "row-1"})
    client.post("/businesses", json={"name": "Second Brand"}, headers={HEADER: "row-2"})

    assert len(_rows(client)) == 2


def test_a_write_without_a_key_is_untouched(client: TestClient) -> None:
    """Opt-in: a client that sends no key keeps exactly its current behaviour."""
    client.post("/businesses", json=BODY)
    client.post("/businesses", json={"name": "Second Brand"})

    assert len(_rows(client)) == 2
    assert client.get("/businesses", headers={HEADER: "reads-ignore-this"}).status_code == 200


def test_a_key_reused_on_another_endpoint_is_refused(client: TestClient) -> None:
    """The business's stored body would hide a client bug behind a plausible response."""
    client.post("/businesses", json=BODY, headers={HEADER: "shared"})
    reused = client.post(
        "/portfolios", json={"name": "Content Brands", "business_id": 1}, headers={HEADER: "shared"}
    )

    assert reused.status_code == 422, reused.text
    assert "already used for POST /businesses" in reused.json()["detail"]


def test_an_attempt_that_never_finished_is_answered_unknown_not_retried(
    client: TestClient, tmp_path: Path
) -> None:
    """The crash the importer actually hits. A reservation with no stored response means
    the previous attempt died between writing and answering, so the write MAY have
    landed -- re-running it is the duplicate this exists to prevent, and 409 is the
    honest answer where a silent second row is not."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    with new_session_factory(engine)() as db:
        db.add(IdempotencyRecord(key="died", method="POST", path="/businesses"))
        db.commit()

    refused = client.post("/businesses", json=BODY, headers={HEADER: "died"})

    assert refused.status_code == 409, refused.text
    assert "outcome is unknown" in refused.json()["detail"]
    assert not _rows(client), "the refused retry must not have written anything"
