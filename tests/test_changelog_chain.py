"""``ChangeLog`` is tamper-evident: each row hashes its own content and its predecessor's
hash, so an edit or a deletion anywhere in the log breaks the chain at that row, not just
at the tampered one. ``verify_chain`` is the read side of that proof.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog, verify_chain
from driftless.models import Business

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
#: The revision just before the hash-chain migration — the target upgraded to first, so
#: the rows inserted below predate ``prev_hash``/``row_hash`` and exercise the backfill.
_PRE_HASH_REVISION = "3c7c1aded10d"  # pragma: allowlist secret  (revision, not a secret)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = new_session_factory(engine)
    register_changelog(factory)
    with factory() as db:
        yield db


def _business(session: Session, name: str) -> Business:
    business = Business(name=name)
    session.add(business)
    session.commit()
    return business


def test_an_intact_chain_verifies(session: Session) -> None:
    _business(session, "Back Road Creative")
    _business(session, "GoMoveShift")

    assert verify_chain(session) is None


def test_editing_a_rows_content_through_raw_sql_is_reported_at_that_row(
    session: Session,
) -> None:
    _business(session, "Back Road Creative")
    _business(session, "GoMoveShift")
    rows = (
        session.connection().execute(text("SELECT id FROM change_log ORDER BY id")).scalars().all()
    )
    tampered_id = rows[0]

    session.connection().execute(
        text("UPDATE change_log SET actor = 'someone-else' WHERE id = :id"),
        {"id": tampered_id},
    )
    session.commit()

    broken = verify_chain(session)
    assert broken is not None
    assert broken.row_id == tampered_id


def test_deleting_a_middle_row_is_reported(session: Session) -> None:
    _business(session, "Back Road Creative")
    _business(session, "GoMoveShift")
    _business(session, "Driftless")
    rows = (
        session.connection().execute(text("SELECT id FROM change_log ORDER BY id")).scalars().all()
    )
    middle_id, last_id = rows[1], rows[2]

    session.connection().execute(text("DELETE FROM change_log WHERE id = :id"), {"id": middle_id})
    session.commit()

    broken = verify_chain(session)
    assert broken is not None
    assert broken.row_id == last_id


def test_prev_hash_chains_row_hash_and_the_first_row_uses_the_genesis_value(
    session: Session,
) -> None:
    _business(session, "Back Road Creative")
    _business(session, "GoMoveShift")

    rows = list(session.scalars(select(ChangeLog).order_by(ChangeLog.id)))
    first, second = rows
    assert first.prev_hash == "0" * 64
    assert second.prev_hash == first.row_hash
    assert first.row_hash != second.row_hash


def test_the_migration_backfill_leaves_the_chain_intact(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'backfill.db'}"
    engine = new_engine(url)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, _PRE_HASH_REVISION)

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO business (id, name, row_revision) VALUES (1, 'BRC', 1)")
        )
        connection.execute(
            text(
                "INSERT INTO change_log (table_name, row_id, operation, changed_at, detail)"
                " VALUES ('business', '1', 'insert', '2026-06-01 12:00:00', '{\"new\": {}}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO change_log (table_name, row_id, operation, changed_at, detail)"
                " VALUES ('business', '1', 'update', '2026-06-02 12:00:00',"
                " '{\"changed\": {}}')"
            )
        )

    command.upgrade(config, "head")

    factory: sessionmaker[Session] = new_session_factory(engine)
    with factory() as db:
        assert verify_chain(db) is None
