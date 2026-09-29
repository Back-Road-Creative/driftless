"""Every write path stamps a ``via`` channel, not just an actor.

``ACTOR_KEY`` is re-stamped by nested service functions (a session can credit several
actors across its life); ``VIA_KEY`` is the channel the *session* came through and is
set exactly once, at the point each entry point opens it — ``driftless.api.deps.get_session``
for every API and web request, and each CLI command's own session opener
(``driftless.notify.cli._open``, ``driftless.wizard.cli._open``, ``driftless.auth.cli._open``).
The source-scan guard below keeps that list honest: a new session opener that registers
the ChangeLog listener but never stamps a channel is a write path this suite would
otherwise never notice went unattributed.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from driftless import cli
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog

_DRIFTLESS_DIR = Path(__file__).resolve().parent.parent / "driftless"

#: Every module that activates change logging by opening its own session (as opposed
#: to a request-scoped one FastAPI hands it). Each of these must also credit a channel,
#: or its writes leave ``via`` null forever with no test ever noticing.
_SESSION_OPENERS = (
    "driftless/notify/cli.py",
    "driftless/wizard/cli.py",
    "driftless/auth/cli.py",
)


def test_every_source_session_opener_also_stamps_a_via_channel() -> None:
    for relpath in _SESSION_OPENERS:
        source = (_DRIFTLESS_DIR.parent / relpath).read_text(encoding="utf-8")
        assert "register_changelog(" in source, f"{relpath} no longer registers the audit log"
        assert "set_via(" in source, f"{relpath} registers writes but never credits a channel"


def test_the_api_session_provider_stamps_every_set_actor_call_site() -> None:
    """The one shared session provider is the channel for every ``set_actor`` call site
    that runs on a request-scoped session — ``api/deps.py`` itself, and every service
    function (``status_snapshots``, ``sign_offs``, ``wizard_writes``) that re-stamps the
    actor on a session it was handed rather than one it opened."""
    deps_source = (_DRIFTLESS_DIR / "api" / "deps.py").read_text(encoding="utf-8")
    assert 'set_via(db, "api")' in deps_source

    call_sites = {
        "driftless/api/deps.py",
        "driftless/services/status_snapshots.py",
        "driftless/services/wizard_writes.py",
        "driftless/notify/cli.py",
        "driftless/services/sign_offs.py",
    }
    found = set()
    for path in _DRIFTLESS_DIR.rglob("*.py"):
        calls = re.findall(r"^\s*set_actor\(", path.read_text(encoding="utf-8"), re.M)
        if calls:
            found.add(str(path.relative_to(_DRIFTLESS_DIR.parent)))
    assert found == call_sites, (
        "a set_actor call site was added or removed — review whether its session "
        f"reaches a set_via call: {found}"
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'via.db'}"
    Base.metadata.create_all(new_engine(url))
    return url


def test_a_notify_cli_write_is_credited_to_the_cli_channel(db_url: str) -> None:
    assert (
        cli.main(
            [
                "notify",
                "add",
                "--url",
                "https://example.test/hook",
                "--secret",
                "s3kret",  # pragma: allowlist secret
                "--events",
                "business",
                "--db-url",
                db_url,
            ]
        )
        == 0
    )

    with new_session_factory(new_engine(db_url))() as session:
        row = session.scalars(
            select(ChangeLog).where(ChangeLog.table_name == "webhook_subscription")
        ).one()
        assert row.via == "cli"


def test_a_user_cli_write_is_credited_to_the_cli_channel(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("s3cret-enough-passphrase\n"))
    assert cli.main(["user", "add", "--username", "jp", "--role", "admin", "--db-url", db_url]) == 0

    with new_session_factory(new_engine(db_url))() as session:
        row = session.scalars(select(ChangeLog).where(ChangeLog.table_name == "app_user")).one()
        assert row.via == "cli"


def test_a_wizard_cli_apply_is_credited_to_the_cli_channel(db_url: str) -> None:
    from driftless.models import Business, Portfolio, Project

    with new_session_factory(new_engine(db_url))() as session:
        project = Project(
            name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
        )
        session.add(project)
        session.commit()

    assert (
        cli.main(
            [
                "wizard",
                "apply",
                "--project",
                "GMS",
                "--kind",
                "scope_baseline",
                "--field",
                "planned_cost=1000",
                "--as-of",
                "2026-01-01",
                "--db-url",
                db_url,
            ]
        )
        == 0
    )

    with new_session_factory(new_engine(db_url))() as session:
        rows = session.scalars(select(ChangeLog).where(ChangeLog.table_name == "baseline")).all()
        assert rows and all(row.via == "cli" for row in rows)
