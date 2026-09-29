"""An agent actor is a ``Person`` bound to the ``ApiToken`` it writes through
(``Person.kind == "agent"``, ``Person.agent_token_id``). Nothing about authentication or
the audit trail changes for it — only one write is gated: ``create_sign_off`` refuses a
decision made through an agent-bound token unless ``DRIFTLESS_ALLOW_AGENT_SIGNOFF=1``.

Pinned here: the ``kind`` CHECK rejects anything outside ``PERSON_KINDS``, an agent's
token resolves ``Principal.is_agent`` while a human's does not, a sign-off through an
agent token is refused by default and allowed once the flag is set, and a human sign-off
is never touched by either.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.auth import tokens
from driftless.models import ApiToken, Person, User
from driftless.services import sign_offs

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def jp(db: Session) -> User:
    user = User(username="jp", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    return user


def _payload() -> s.SignOffIn:
    return s.SignOffIn(subject_kind="threat", subject_ref="cost:project:1", decision="waived")


def test_the_kind_check_rejects_anything_outside_the_vocabulary(db: Session) -> None:
    db.add(Person(name="Rogue", kind="robot"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_person_defaults_to_human(db: Session) -> None:
    person = Person(name="Jane")
    db.add(person)
    db.commit()
    assert person.kind == "human"
    assert person.agent_token_id is None


def test_an_agent_bound_token_resolves_as_an_agent_principal(db: Session, jp: User) -> None:
    plaintext = tokens.issue(db, jp, label="loop")
    token_row = db.query(ApiToken).one()
    db.add(Person(name="Loop", kind="agent", agent_token_id=token_row.id))
    db.commit()

    who = tokens.resolve(db, plaintext, NOW)
    assert who is not None
    assert who.is_agent is True


def test_an_unbound_token_resolves_as_human(db: Session, jp: User) -> None:
    plaintext = tokens.issue(db, jp, label="laptop")
    who = tokens.resolve(db, plaintext, NOW)
    assert who is not None
    assert who.is_agent is False


def test_an_agent_sign_off_is_refused_by_default(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sign_offs.ALLOW_AGENT_SIGNOFF_ENV, raising=False)
    with pytest.raises(HTTPException) as excinfo:
        sign_offs.create_sign_off(db, _payload(), "loop-agent", is_agent=True)
    assert excinfo.value.status_code == 403
    assert "agent" in str(excinfo.value.detail)


def test_an_agent_sign_off_is_allowed_once_the_flag_is_set(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(sign_offs.ALLOW_AGENT_SIGNOFF_ENV, "1")
    row = sign_offs.create_sign_off(db, _payload(), "loop-agent", is_agent=True)
    assert row.signed_by_kind == "agent"


def test_a_human_sign_off_is_unaffected_by_the_flag(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sign_offs.ALLOW_AGENT_SIGNOFF_ENV, raising=False)
    row = sign_offs.create_sign_off(db, _payload(), "jp", is_agent=False)
    assert row.signed_by_kind == "human"
