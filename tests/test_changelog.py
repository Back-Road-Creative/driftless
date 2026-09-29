"""Contract tests for the append-only ChangeLog audit trail.

The listener is the whole point, so these tests never call the logger: they drive real
hierarchy rows through a session and assert the log rows appear on their own. Comment out
the ``event.listen`` calls in ``register_changelog`` and these go red — that is the check
that they are not vacuous.
"""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.db import Base, new_engine, new_session_factory
from driftless.db import changelog as changelog_module
from driftless.db.changelog import (
    CHANGE_CHANNELS,
    ChangeLog,
    register_changelog,
    set_actor,
    set_via,
)
from driftless.models import ArtifactLink, Business


def _factory(*, activated: bool) -> sessionmaker[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    if activated:
        register_changelog(factory)
    return factory


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory session whose factory has change logging activated."""
    with _factory(activated=True)() as db:
        yield db


def _rows(session: Session) -> list[ChangeLog]:
    return list(session.scalars(select(ChangeLog).order_by(ChangeLog.id)))


def _snapshot(session: Session) -> list[tuple[Any, ...]]:
    return [(r.id, r.table_name, r.row_id, r.operation, r.actor, r.detail) for r in _rows(session)]


def _business(session: Session, name: str = "Back Road Creative") -> Business:
    business = Business(name=name)
    session.add(business)
    session.commit()
    return business


def test_insert_is_logged_with_the_row_id_and_the_new_values(session: Session) -> None:
    business = _business(session)

    (row,) = _rows(session)
    assert (row.table_name, row.operation, row.row_id) == ("business", "insert", str(business.id))
    assert json.loads(row.detail)["new"]["name"] == "Back Road Creative"
    assert row.changed_at is not None


def test_update_is_logged_with_old_and_new_values(session: Session) -> None:
    business = _business(session, "Back Road")
    business.name = "BRC"
    session.commit()
    business.name = "BRC"  # a rewrite with the current value is not a change
    session.commit()

    row = _rows(session)[-1]
    assert [r.operation for r in _rows(session)] == ["insert", "update"]
    assert (row.table_name, row.row_id) == ("business", str(business.id))
    assert json.loads(row.detail)["changed"] == {"name": {"old": "Back Road", "new": "BRC"}}


def test_delete_is_logged_with_the_values_the_row_had(session: Session) -> None:
    business = _business(session)
    business_id = business.id
    session.delete(business)
    session.commit()

    row = _rows(session)[-1]
    assert (row.table_name, row.operation, row.row_id) == ("business", "delete", str(business_id))
    assert json.loads(row.detail)["old"]["name"] == "Back Road Creative"


def test_actor_is_none_by_default_and_settable_per_session(session: Session) -> None:
    _business(session, "System write")
    set_actor(session, "jp")
    _business(session, "Attributed write")

    assert [row.actor for row in _rows(session)] == [None, "jp"]


def test_via_is_none_by_default_and_settable_per_session(session: Session) -> None:
    _business(session, "Unattributed channel")
    set_via(session, "cli")
    _business(session, "CLI channel")

    assert [row.via for row in _rows(session)] == [None, "cli"]


def test_set_via_refuses_a_channel_outside_the_vocabulary(session: Session) -> None:
    with pytest.raises(ValueError, match="via"):
        set_via(session, "carrier-pigeon")


@pytest.mark.parametrize("channel", CHANGE_CHANNELS)
def test_set_via_accepts_every_vocabulary_member(session: Session, channel: str) -> None:
    set_via(session, channel)
    _business(session, f"{channel} channel")

    assert _rows(session)[-1].via == channel


def test_an_artifact_link_is_logged_like_any_other_row(session: Session) -> None:
    link = ArtifactLink(
        record_kind="department",
        record_id="1",
        uri="https://example.test/handbook.pdf",
        title="Handbook",
        actor="sam",
        as_of=date(2026, 3, 31),
    )
    session.add(link)
    session.commit()

    (row,) = _rows(session)
    assert (row.table_name, row.operation, row.row_id) == ("artifact_link", "insert", str(link.id))


def test_the_log_never_logs_itself(session: Session) -> None:
    session.add(ChangeLog(table_name="business", row_id="1", operation="insert", detail="{}"))
    session.commit()

    rows = _rows(session)
    assert len(rows) == 1 and rows[0].table_name == "business"


def test_the_log_never_logs_deleting_itself(session: Session) -> None:
    entry = ChangeLog(table_name="business", row_id="1", operation="insert", detail="{}")
    session.add(entry)
    session.commit()

    session.delete(entry)
    session.commit()

    assert _rows(session) == []  # the delete of a log row produced no new log row


def test_the_log_is_append_only(session: Session) -> None:
    business = _business(session)
    before = _snapshot(session)
    business.name = "BRC"
    session.commit()
    session.delete(business)
    session.commit()

    after = _snapshot(session)
    assert after[: len(before)] == before  # earlier rows survive later writes untouched
    assert len(after) == len(before) + 2


def test_the_module_never_updates_or_deletes_a_log_row() -> None:
    """Append-only has to hold in the source too, not just along one test's timeline."""
    source = Path(changelog_module.__file__).read_text(encoding="utf-8")

    assert "delete(" not in source  # no ORM session.delete and no Core delete()
    assert "update(" not in source


def test_activation_is_explicit_so_importing_the_module_instruments_nothing() -> None:
    with _factory(activated=False)() as db:
        db.add(Business(name="Unwatched"))
        db.commit()

        assert _rows(db) == []
