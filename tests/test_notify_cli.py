"""``driftless notify``: the CLI wiring around add/list/deliver."""

from __future__ import annotations

from pathlib import Path

import pytest

from driftless.cli import main
from driftless.db import Base, new_engine, new_session_factory
from driftless.models.notify import WebhookSubscription

SECRET = "s3kret"  # pragma: allowlist secret


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'notify.db'}"
    Base.metadata.create_all(new_engine(url))
    return url


def _add(db_url: str, events: str) -> int:
    return main(
        [
            "notify",
            "add",
            "--url",
            "https://example.test/hook",
            "--secret",
            SECRET,
            "--events",
            events,
            "--db-url",
            db_url,
        ]
    )


def test_add_then_list_shows_the_new_subscription(
    db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(db_url, "business") == 0
    assert main(["notify", "list", "--db-url", db_url]) == 0
    out = capsys.readouterr().out
    assert "https://example.test/hook" in out
    assert "active" in out
    assert "cursor=0" in out


def test_deliver_dry_run_reports_pending_without_advancing(
    db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _add(db_url, "*")
    assert main(["notify", "deliver", "--dry-run", "--db-url", db_url]) == 0
    assert "pending" in capsys.readouterr().out
    with new_session_factory(new_engine(db_url))() as session:
        assert session.get_one(WebhookSubscription, 1).last_delivered_changelog_id == 0
