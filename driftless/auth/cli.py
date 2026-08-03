"""The ``driftless user`` and ``driftless token`` commands.

The password arrives on stdin (a terminal gets a no-echo prompt), never as an
argv flag — argv is world-readable through ``ps`` — and one shorter than
``MIN_PASSWORD_LENGTH`` is refused before it is hashed or stored. Writes run through an ordinary
session with the ChangeLog listener registered, so creating a login is audited;
``list`` never prints the digest. ``disable`` also bumps ``session_epoch``, which
is what revokes the cookies already issued to that user (see
``driftless/auth/principal.py``); ``enable`` never lowers it back.

``token`` is the same shape for API tokens: ``add`` puts the minted token on stdout
alone — its digest is all that is stored, so this is the one moment it exists — and
warns on stderr, so a pipe still receives just the token.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.auth.passwords import hash_password
from driftless.auth.tokens import issue, revoke
from driftless.db import new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.db.config import database_url
from driftless.models import USER_ROLES, ApiToken, User

#: The shortest password this command will store. ``deploy/entrypoint.sh`` refuses a
#: machine secret under 24 characters; this one is typed by a human and remembered, so
#: the floor is lower — but there is one, because scrypt only buys time against a
#: digest, and a password short enough to guess is guessed before the KDF matters.
MIN_PASSWORD_LENGTH = 12


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit("error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL")
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # creating a login is audited, like the API's writes
    return factory()


def _run_add(args: argparse.Namespace) -> int:
    password = getpass.getpass() if sys.stdin.isatty() else sys.stdin.readline().strip("\n")
    if not password:
        raise SystemExit("error: empty password — nothing arrived on stdin")
    if len(password) < MIN_PASSWORD_LENGTH:  # refused before the hash and before the row
        raise SystemExit(f"error: password is shorter than {MIN_PASSWORD_LENGTH} characters")
    digest = hash_password(password)
    with _open(args.db_url) as session:
        session.add(User(username=args.username, password_hash=digest, role=args.role))
        try:
            session.commit()
        except IntegrityError:  # uniqueness is the store's job, not a racy pre-check
            print(f"error: user {args.username!r} already exists", file=sys.stderr)
            return 2
    return 0


def _run_list(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        for user in session.scalars(select(User).order_by(User.username)):
            live = "active" if user.is_active else "disabled"
            print(f"{user.username:20} {user.role:12} {live:9} {user.created_at}")
    return 0


def _set_active(args: argparse.Namespace, active: bool) -> int:
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        user.is_active = active
        if not active:  # the bump is the revocation: every cookie already issued stops resolving
            user.session_epoch += 1
        session.commit()  # audited like every other write through this session
    return 0


def _run_disable(args: argparse.Namespace) -> int:
    return _set_active(args, active=False)


def _run_enable(args: argparse.Namespace) -> int:
    # Deliberately leaves ``session_epoch`` alone: re-enabling a login must not
    # resurrect the cookies the disable revoked. The holder signs in again.
    return _set_active(args, active=True)


def add_user_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``user`` command onto a parent's subparsers, as every domain does."""
    user = commands.add_parser("user", help="create and list the logins the service knows")
    sub = user.add_subparsers(dest="user_command", required=True)
    add = sub.add_parser("add", help="create a user; the password is read from stdin")
    add.add_argument("--username", required=True)
    add.add_argument("--role", required=True, choices=USER_ROLES)
    listing = sub.add_parser("list", help="list users — username, role, state, created")
    off = sub.add_parser("disable", help="deactivate a user and revoke their live sessions")
    on = sub.add_parser("enable", help="reactivate a user; already-revoked sessions stay revoked")
    for parser in (off, on):
        parser.add_argument("username")
    leaves = ((add, _run_add), (listing, _run_list), (off, _run_disable), (on, _run_enable))
    for parser, handler in leaves:
        parser.add_argument("--db-url", default=None, metavar="URL", help="SQLAlchemy database URL")
        parser.set_defaults(handler=handler)


def _run_token_add(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        token = issue(session, user, args.label)  # audited like every other write
    print(token)  # stdout carries the secret alone, so piping it somewhere safe works
    print("store it now: only the digest is kept, so it cannot be shown again", file=sys.stderr)
    return 0


def _run_token_list(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        for tok in session.scalars(select(ApiToken).order_by(ApiToken.id)):
            state = "revoked" if tok.revoked_at else "live"  # the digest is never printed
            print(f"{tok.id:<5} {tok.user.username:20} {tok.label:20} {state:8} {tok.created_at}")
    return 0


def _run_token_revoke(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        if not revoke(session, args.token_id):
            print(f"error: no live token with id {args.token_id}", file=sys.stderr)
            return 2
    return 0


def add_token_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``token`` command — per-user API tokens, minted here and revocable."""
    tokens = commands.add_parser("token", help="mint, list and revoke per-user API tokens")
    sub = tokens.add_subparsers(dest="token_command", required=True)
    add = sub.add_parser("add", help="mint a token for a user; shown once, never recoverable")
    add.add_argument("--username", required=True)
    add.add_argument("--label", required=True, help="what holds it, for the revoke decision")
    listing = sub.add_parser("list", help="list tokens — id, user, label, state, created")
    off = sub.add_parser("revoke", help="revoke one token by the id `list` prints")
    off.add_argument("token_id", type=int)
    leaves = ((add, _run_token_add), (listing, _run_token_list), (off, _run_token_revoke))
    for parser, handler in leaves:
        parser.add_argument("--db-url", default=None, metavar="URL", help="SQLAlchemy database URL")
        parser.set_defaults(handler=handler)
