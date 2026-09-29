"""Contract for per-user API tokens: the store, the mint module, the CLI.

These primitives now grant access: ``api.secure.TokenGate._from_token`` answers a
request carrying a ``dfl_…`` bearer with exactly the ``Principal`` ``resolve``
returns here, so what is pinned below is what admits a caller (the gate's own
behaviour — precedence against a session cookie, the bootstrap credential — is
pinned in ``test_secure``).
Pinned: a token resolves to the *live* identity behind it (never the credential's
own claim), the plaintext exists once and is nowhere in the database afterwards,
and both revocations — of the token, of its owner — stop it dead.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import driftless.db.changelog  # noqa: F401 -- registers change_log on the metadata
from driftless import cli
from driftless.auth import tokens
from driftless.auth.principal import Principal
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import ApiToken, User

NOW = datetime(2026, 1, 1, tzinfo=UTC)  # a fixed as-of, so an expiry test never races the clock


@pytest.fixture
def jp(db: Session) -> User:
    """A live admin on the throwaway SQLite database ``db`` builds (see conftest)."""
    user = User(username="jp", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    return user


def _everything_stored(db: Session) -> str:
    """Every row of every table, as text — where a leaked plaintext would show up."""
    results = (db.execute(select(table)) for table in Base.metadata.sorted_tables)
    return " ".join(str(tuple(row)) for result in results for row in result)


def test_a_minted_token_resolves_to_its_owners_live_principal(db: Session, jp: User) -> None:
    token = tokens.issue(db, jp, label="ci")
    assert token.startswith(tokens.PREFIX)  # greppable: a leak is findable
    assert tokens.resolve(db, token, NOW) == Principal(uid=jp.id, username="jp", role="admin")
    assert token not in _everything_stored(db), "the plaintext must not survive the mint"
    db.add(ApiToken(user_id=jp.id, label="clone", token_digest=tokens.digest(token)))
    with pytest.raises(IntegrityError):  # the unique digest makes a collision a refused row
        db.commit()


def test_two_mints_never_collide() -> None:
    minted = {tokens.mint() for _ in range(200)}
    assert len({tokens.digest(token) for token in minted}) == len(minted) == 200


def test_a_wrong_garbage_or_empty_token_resolves_to_none_rather_than_raising(
    db: Session, jp: User
) -> None:
    live = tokens.issue(db, jp, label="ci")
    stored = db.scalars(select(ApiToken)).one().token_digest
    for candidate in ("", "   ", "not-a-token", tokens.mint(), stored, live[:-1], live + "x"):
        assert tokens.resolve(db, candidate, NOW) is None, candidate


def test_revoking_stops_one_token_and_deactivating_the_user_stops_the_rest(
    db: Session, jp: User
) -> None:
    doomed, spared = (tokens.issue(db, jp, label=name) for name in ("ci", "laptop"))
    ids = list(db.scalars(select(ApiToken.id).order_by(ApiToken.id)))
    assert tokens.revoke(db, ids[0]) is True
    assert tokens.revoke(db, ids[0]) is False  # already revoked: nothing left to revoke
    assert tokens.resolve(db, doomed, NOW) is None and tokens.resolve(db, spared, NOW) is not None
    jp.is_active = False
    db.commit()
    assert [tokens.resolve(db, token, NOW) for token in (doomed, spared)] == [None, None]


def test_an_expiry_and_a_revocation_resolve_identically_but_list_tells_them_apart(
    db: Session, jp: User
) -> None:
    """An expired token and a revoked token are the SAME refusal to a caller — ``resolve``
    returns ``None`` for both, on purpose, so a caller cannot learn which happened. Only
    the operator-facing ``token list`` (exercised in the CLI test below) tells them apart.
    """
    live_forever = tokens.issue(db, jp, label="no-expiry")
    not_yet = tokens.issue(db, jp, label="future", expires_at=NOW + timedelta(days=1))
    already = tokens.issue(db, jp, label="past", expires_at=NOW - timedelta(days=1))
    right_now = tokens.issue(db, jp, label="boundary", expires_at=NOW)

    assert tokens.resolve(db, live_forever, NOW) is not None
    assert tokens.resolve(db, not_yet, NOW) is not None
    assert tokens.resolve(db, already, NOW) is None
    assert tokens.resolve(db, right_now, NOW) is None  # expiry is inclusive: due now is expired


def test_a_resolution_stamps_last_use_coarsely_and_a_refusal_never_stamps(
    db: Session, jp: User
) -> None:
    """The stamp records *admission*, and records it coarsely.

    A token that resolved nobody must not look used — a rejected credential is exactly
    the one an operator wants to see going cold. Within ``STAMP_INTERVAL`` a further use
    rewrites nothing, so the authenticated read path stays free of a write per request.
    """
    token = tokens.issue(db, jp, label="ci")
    stored = db.scalars(select(ApiToken)).one()
    assert stored.last_used_at is None  # minted, never presented

    assert tokens.resolve(db, token, NOW) is not None
    db.expire_all()
    assert tokens.stamped(stored.last_used_at) == NOW  # type: ignore[arg-type]

    soon = NOW + tokens.STAMP_INTERVAL - timedelta(seconds=1)
    assert tokens.resolve(db, token, soon) is not None
    db.expire_all()
    assert tokens.stamped(stored.last_used_at) == NOW, "a use inside the interval rewrites nothing"

    later = NOW + tokens.STAMP_INTERVAL
    assert tokens.resolve(db, token, later) is not None
    db.expire_all()
    assert tokens.stamped(stored.last_used_at) == later  # due: restamped

    assert tokens.resolve(db, tokens.mint(), later + timedelta(days=1)) is None
    db.expire_all()
    assert tokens.stamped(stored.last_used_at) == later, "an unknown token stamps nobody"

    tokens.revoke(db, stored.id)
    assert tokens.resolve(db, token, later + timedelta(days=2)) is None
    db.expire_all()
    assert tokens.stamped(stored.last_used_at) == later, "a refused token is not a used one"


def test_stamping_last_use_writes_no_audit_row(tmp_path: Path) -> None:
    """The stamp must stay OUT of the audit trail.

    ``change_log`` answers "who changed what"; a token being presented is neither a change
    nor something an actor did to the domain. Were the stamp an ORM assignment, the flush
    listener would file a row on every authenticated request and the trail would be mostly
    noise. This runs on a factory with the listener actually registered — the ``db`` fixture
    has none, so the property could not be observed there at all.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'audited.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        user = User(username="jp", password_hash="x", role="admin")
        session.add(user)
        session.commit()
        token = tokens.issue(session, user, label="ci")
        minted = session.scalars(select(ChangeLog)).all()
        assert any(row.table_name == "api_token" for row in minted), "the mint IS audited"

        before = len(minted)
        assert tokens.resolve(session, token, NOW) is not None
        assert tokens.resolve(session, token, NOW + timedelta(hours=1)) is not None
        after = session.scalars(select(ChangeLog)).all()
        assert len(after) == before, "using a token filed an audit row"
        assert session.scalars(select(ApiToken)).one().last_used_at is not None  # yet it stamped


def test_the_cli_mints_once_lists_without_secrets_and_revokes(
    db: Session, jp: User, capsys: pytest.CaptureFixture[str]
) -> None:
    url = str(db.get_bind().url)
    assert cli.main(["token", "add", "--username", "jp", "--label", "ci", "--db-url", url]) == 0
    minted = capsys.readouterr().out.strip()  # stdout carries the token and nothing else
    stored = db.scalars(select(ApiToken)).one()
    assert tokens.resolve(db, minted, NOW) is not None
    assert stored.expires_at is None  # no --expires-in-days: this one never expires

    assert cli.main(["token", "list", "--db-url", url]) == 0
    listing = capsys.readouterr().out
    assert "jp" in listing and "ci" in listing and "live" in listing and "never" in listing
    assert minted not in listing and stored.token_digest not in listing

    assert cli.main(["token", "revoke", str(stored.id), "--db-url", url]) == 0
    db.expire_all()
    assert tokens.resolve(db, minted, NOW) is None

    assert cli.main(["token", "list", "--db-url", url]) == 0
    assert "revoked" in capsys.readouterr().out  # a revoked token lists as such, distinctly

    ghost = ["token", "add", "--username", "ghost", "--label", "x", "--db-url", url]
    assert cli.main(ghost) != 0 and cli.main(["token", "revoke", "999", "--db-url", url]) != 0


def test_the_cli_mints_a_token_that_expires_and_lists_it_as_such(
    db: Session, jp: User, capsys: pytest.CaptureFixture[str]
) -> None:
    url = str(db.get_bind().url)
    add = [
        "token",
        "add",
        "--username",
        "jp",
        "--label",
        "ci",
        "--expires-in-days",
        "7",
        "--db-url",
        url,
    ]
    assert cli.main(add) == 0
    capsys.readouterr()
    stored = db.scalars(select(ApiToken)).one()
    assert stored.expires_at is not None

    assert cli.main(["token", "list", "--db-url", url]) == 0
    listing = capsys.readouterr().out
    assert "live" in listing  # not yet due
    assert "never" not in listing

    stored.expires_at = NOW - timedelta(days=1)  # backdate it past due, without revoking it
    db.commit()
    assert cli.main(["token", "list", "--db-url", url]) == 0
    listing = capsys.readouterr().out
    assert "expired" in listing and "revoked" not in listing  # distinct from a revocation
