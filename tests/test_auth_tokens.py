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

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import driftless.db.changelog  # noqa: F401 -- registers change_log on the metadata
from driftless import cli
from driftless.auth import tokens
from driftless.auth.principal import Principal
from driftless.db import Base
from driftless.models import ApiToken, User


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
    assert tokens.resolve(db, token) == Principal(uid=jp.id, username="jp", role="admin")
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
        assert tokens.resolve(db, candidate) is None, candidate


def test_revoking_stops_one_token_and_deactivating_the_user_stops_the_rest(
    db: Session, jp: User
) -> None:
    doomed, spared = (tokens.issue(db, jp, label=name) for name in ("ci", "laptop"))
    ids = list(db.scalars(select(ApiToken.id).order_by(ApiToken.id)))
    assert tokens.revoke(db, ids[0]) is True
    assert tokens.revoke(db, ids[0]) is False  # already revoked: nothing left to revoke
    assert tokens.resolve(db, doomed) is None and tokens.resolve(db, spared) is not None
    jp.is_active = False
    db.commit()
    assert [tokens.resolve(db, token) for token in (doomed, spared)] == [None, None]


def test_the_cli_mints_once_lists_without_secrets_and_revokes(
    db: Session, jp: User, capsys: pytest.CaptureFixture[str]
) -> None:
    url = str(db.get_bind().url)
    assert cli.main(["token", "add", "--username", "jp", "--label", "ci", "--db-url", url]) == 0
    minted = capsys.readouterr().out.strip()  # stdout carries the token and nothing else
    stored = db.scalars(select(ApiToken)).one()
    assert tokens.resolve(db, minted) is not None

    assert cli.main(["token", "list", "--db-url", url]) == 0
    listing = capsys.readouterr().out
    assert "jp" in listing and "ci" in listing and "live" in listing
    assert minted not in listing and stored.token_digest not in listing

    assert cli.main(["token", "revoke", str(stored.id), "--db-url", url]) == 0
    db.expire_all()
    assert tokens.resolve(db, minted) is None
    ghost = ["token", "add", "--username", "ghost", "--label", "x", "--db-url", url]
    assert cli.main(ghost) != 0 and cli.main(["token", "revoke", "999", "--db-url", url]) != 0
