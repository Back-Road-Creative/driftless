"""The ``driftless user`` and ``driftless token`` commands.

The password arrives on stdin (a terminal gets a no-echo prompt), never as an
argv flag — argv is world-readable through ``ps`` — and one shorter than
``MIN_PASSWORD_LENGTH`` is refused before it is hashed or stored. Writes run through an ordinary
session with the ChangeLog listener registered, so creating a login is audited;
``list`` never prints the digest. ``disable`` also bumps ``session_epoch``, which
is what revokes the cookies already issued to that user (see
``driftless/auth/principal.py``); ``enable`` never lowers it back. ``passwd``
bumps it too — rotating a password is a revocation, or the cookies the old
password issued would keep working after the new one is set.

``token`` is the same shape for API tokens: ``add`` puts the minted token on stdout
alone — its digest is all that is stored, so this is the one moment it exists — and
warns on stderr, so a pipe still receives just the token.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.auth.passwords import hash_password
from driftless.auth.tokens import issue, revoke, stamped
from driftless.db import new_engine, new_session_factory
from driftless.db.changelog import register_changelog, set_via
from driftless.db.config import database_url
from driftless.models import USER_ROLES, ApiToken, User

#: The shortest password this command will store. ``deploy/entrypoint.sh`` refuses a
#: machine secret under 24 characters; this one is typed by a human and remembered, so
#: the floor is lower — but there is one, because scrypt only buys time against a
#: digest, and a password short enough to guess is guessed before the KDF matters.
MIN_PASSWORD_LENGTH = 12


def _validated_email(raw: str) -> str:
    """The one shape check this command makes: an ``@`` with something on both sides.

    Refused before the row, like the password floor — no partial write, no store-side
    surprise for a value the API/CLI could have caught first.
    """
    local, sep, domain = raw.partition("@")
    if not sep or not local or not domain:
        raise SystemExit(f"error: {raw!r} is not a valid email address")
    return raw


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit("error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL")
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # creating a login is audited, like the API's writes
    session = factory()
    set_via(session, "cli")
    return session


def _read_password() -> str:
    password = getpass.getpass() if sys.stdin.isatty() else sys.stdin.readline().strip("\n")
    if not password:
        raise SystemExit("error: empty password — nothing arrived on stdin")
    if len(password) < MIN_PASSWORD_LENGTH:  # refused before the hash and before the row
        raise SystemExit(f"error: password is shorter than {MIN_PASSWORD_LENGTH} characters")
    return password


def _run_add(args: argparse.Namespace) -> int:
    email = _validated_email(args.email) if args.email else None
    digest = hash_password(_read_password())
    with _open(args.db_url) as session:
        session.add(User(username=args.username, password_hash=digest, role=args.role, email=email))
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
            email = user.email or "-"
            print(f"{user.username:20} {user.role:12} {live:9} {email:30} {user.created_at}")
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


def _run_passwd(args: argparse.Namespace) -> int:
    digest = hash_password(_read_password())
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        user.password_hash = digest
        user.session_epoch += 1  # the bump is the revocation: rotation kills every live cookie
        session.commit()  # audited like every other write through this session
    return 0


def _run_email(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        user.email = None if args.clear else _validated_email(args.address)
        session.commit()  # audited like every other write through this session
    return 0


def _run_oidc_subject(args: argparse.Namespace) -> int:
    """Bind (or clear) the IdP ``sub`` ``driftless.auth.oidc`` maps back to a user.

    Closed-world by design, like ``email``: no auto-provisioning happens on sign-in,
    only here. Uniqueness is the store's job, not a racy pre-check, same as ``add``.
    """
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        user.oidc_subject = None if args.clear else args.subject
        try:
            session.commit()  # audited like every other write through this session
        except IntegrityError:
            print(
                f"error: subject {args.subject!r} is already bound to another user", file=sys.stderr
            )
            return 2
    return 0


def add_user_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``user`` command onto a parent's subparsers, as every domain does."""
    user = commands.add_parser("user", help="create and list the logins the service knows")
    sub = user.add_subparsers(dest="user_command", required=True)
    add = sub.add_parser("add", help="create a user; the password is read from stdin")
    add.add_argument("--username", required=True)
    add.add_argument("--role", required=True, choices=USER_ROLES)
    add.add_argument("--email", default=None, help="optional; used as the digest recipient")
    listing = sub.add_parser("list", help="list users — username, role, state, email, created")
    off = sub.add_parser("disable", help="deactivate a user and revoke their live sessions")
    on = sub.add_parser("enable", help="reactivate a user; already-revoked sessions stay revoked")
    passwd = sub.add_parser(
        "passwd", help="rotate a user's password, revoking their live sessions; read from stdin"
    )
    email = sub.add_parser("email", help="set or clear a user's email address")
    email.add_argument("username")
    address_group = email.add_mutually_exclusive_group(required=True)
    address_group.add_argument("--address", help="the new email address")
    address_group.add_argument("--clear", action="store_true", help="unset the email address")
    oidc_subject = sub.add_parser(
        "oidc-subject", help="bind or clear the OIDC IdP 'sub' this user signs in as"
    )
    oidc_subject.add_argument("username")
    subject_group = oidc_subject.add_mutually_exclusive_group(required=True)
    subject_group.add_argument("--subject", help="the IdP's 'sub' claim to bind")
    subject_group.add_argument("--clear", action="store_true", help="unbind the subject")
    for parser in (off, on, passwd):
        parser.add_argument("username")
    leaves = (
        (add, _run_add),
        (listing, _run_list),
        (off, _run_disable),
        (on, _run_enable),
        (passwd, _run_passwd),
        (email, _run_email),
        (oidc_subject, _run_oidc_subject),
    )
    for parser, handler in leaves:
        parser.add_argument("--db-url", default=None, metavar="URL", help="SQLAlchemy database URL")
        parser.set_defaults(handler=handler)


def _run_token_add(args: argparse.Namespace) -> int:
    expires_at = None
    if args.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=args.expires_in_days)
    with _open(args.db_url) as session:
        user = session.scalars(select(User).where(User.username == args.username)).one_or_none()
        if user is None:
            print(f"error: no such user {args.username!r}", file=sys.stderr)
            return 2
        token = issue(session, user, args.label, expires_at=expires_at)  # audited too
    print(token)  # stdout carries the secret alone, so piping it somewhere safe works
    print("store it now: only the digest is kept, so it cannot be shown again", file=sys.stderr)
    return 0


def _token_state(tok: ApiToken, now: datetime) -> str:
    """``revoked``, ``expired`` or ``live`` — the one distinction ``resolve`` withholds
    from a caller (both refuse alike) but an operator deciding what to rotate needs."""
    if tok.revoked_at is not None:
        return "revoked"
    if tok.expires_at is not None and stamped(tok.expires_at) <= now:
        return "expired"
    return "live"


def _run_token_list(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    with _open(args.db_url) as session:
        for tok in session.scalars(select(ApiToken).order_by(ApiToken.id)):
            state = _token_state(tok, now)  # the digest is never printed
            expiry = tok.expires_at.isoformat() if tok.expires_at else "never"
            # ``unused``, not ``never``: the two columns sit side by side, and one word
            # meaning "never expires" in one and "never used" in the other reads as the
            # same fact twice. Last use is coarse (``tokens.STAMP_INTERVAL``) by design.
            used = tok.last_used_at.isoformat() if tok.last_used_at else "unused"
            print(
                f"{tok.id:<5} {tok.user.username:20} {tok.label:20} {state:8} "
                f"{tok.created_at} {expiry} {used}"
            )
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
    add.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        metavar="N",
        help="expire the token N days from now; omitted, it never expires",
    )
    listing = sub.add_parser(
        "list", help="list tokens — id, user, label, state, created, expiry, last use"
    )
    off = sub.add_parser("revoke", help="revoke one token by the id `list` prints")
    off.add_argument("token_id", type=int)
    leaves = ((add, _run_token_add), (listing, _run_token_list), (off, _run_token_revoke))
    for parser, handler in leaves:
        parser.add_argument("--db-url", default=None, metavar="URL", help="SQLAlchemy database URL")
        parser.set_defaults(handler=handler)
