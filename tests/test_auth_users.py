"""Contract for stored identity: the ``app_user`` row and the ``driftless user`` CLI.

Storage only. Pinned: roles and username uniqueness are the database's job, the
password reaches the CLI on stdin not argv, and no surface prints the digest.
"""

import io
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from driftless import cli
from driftless.auth.passwords import verify_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import User


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    Base.metadata.create_all(new_engine(url))
    return url


_PW = "s3cret-enough-passphrase"  # every fixture here clears the CLI's length floor


def _add(db_url: str, name: str, role: str, password: str, mp: pytest.MonkeyPatch) -> int:
    mp.setattr(sys, "stdin", io.StringIO(f"{password}\n"))  # on stdin, never in argv
    return cli.main(["user", "add", "--username", name, "--role", role, "--db-url", db_url])


def test_a_short_password_is_refused_before_anything_is_stored(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The floor is 12, pinned here as a literal rather than read off the module.

    ``deploy/entrypoint.sh`` refuses a machine secret under 24 characters, while this
    command took a one-character admin password — the weakest credential the service
    would accept, and the one a human types. Refused before the hash and before the row.
    """
    for weak in ("abc", "a" * 11):  # the boundary is one character short
        with pytest.raises(SystemExit, match="12 characters"):
            _add(db_url, "jp", "admin", weak, monkeypatch)
    with new_session_factory(new_engine(db_url))() as session:
        assert session.scalars(select(User)).all() == []  # nothing reached the store
    assert _add(db_url, "jp", "admin", "a" * 12, monkeypatch) == 0  # exactly the floor passes


def test_the_defaults_are_safe_and_the_role_check_refuses_an_invented_role(db_url: str) -> None:
    with new_session_factory(new_engine(db_url))() as session:
        session.add(User(username="jp", password_hash="x"))
        session.commit()
        user = session.scalars(select(User)).one()
        assert user.is_active is True and user.role == "viewer" and user.created_at is not None
        session.add(User(username="root", password_hash="x", role="superuser"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_the_cli_round_trips_a_user_and_never_prints_the_hash(
    db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(db_url, "jp", "admin", _PW, monkeypatch) == 0
    with new_session_factory(new_engine(db_url))() as session:
        stored = session.scalars(select(User)).one()
        assert stored.role == "admin" and verify_password(_PW, stored.password_hash)
    capsys.readouterr()
    assert cli.main(["user", "list", "--db-url", db_url]) == 0
    out = capsys.readouterr().out
    assert "jp" in out and "admin" in out
    assert stored.password_hash not in out and "scrypt" not in out
    assert _add(db_url, "jp", "viewer", _PW, monkeypatch) != 0  # username already taken
    with pytest.raises(SystemExit):  # nothing on stdin
        _add(db_url, "ghost", "viewer", "", monkeypatch)
    with pytest.raises(SystemExit):  # off-vocabulary role, refused by the parser
        _add(db_url, "x", "superuser", _PW, monkeypatch)


def test_disable_revokes_live_sessions_and_enable_does_not_bring_them_back(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _add(db_url, "jp", "admin", _PW, monkeypatch) == 0
    factory = new_session_factory(new_engine(db_url))
    with factory() as session:
        assert session.scalars(select(User)).one().session_epoch == 0
    assert cli.main(["user", "disable", "jp", "--db-url", db_url]) == 0
    with factory() as session:
        disabled = session.scalars(select(User)).one()
        assert disabled.is_active is False and disabled.session_epoch == 1  # the bump is the revoke
    assert cli.main(["user", "enable", "jp", "--db-url", db_url]) == 0
    with factory() as session:
        restored = session.scalars(select(User)).one()
        # Signing in works again, but the counter never walks back: those cookies stay dead.
        assert restored.is_active is True and restored.session_epoch == 1
    assert cli.main(["user", "disable", "ghost", "--db-url", db_url]) != 0  # no such user
