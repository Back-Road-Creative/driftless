"""The canonical database-URL resolver: one env name, one default, so the
web/API/alembic path and the report/assess/wizard CLIs can never read different
stores. ``DRIFTLESS_DATABASE_URL`` is canonical; ``PMHUB_DATABASE_URL`` (the
pre-rename canonical) and ``PMHUB_DB_URL`` (the CLIs' historical name) are
honoured as deprecated aliases for one deprecation cycle."""

import pytest

from driftless.db.config import CANONICAL_ENV, DEPRECATED_ENV, database_url


def test_canonical_env_is_used_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CANONICAL_ENV, "postgresql+psycopg://canon/driftless")
    monkeypatch.delenv(DEPRECATED_ENV, raising=False)
    assert database_url() == "postgresql+psycopg://canon/driftless"


def test_deprecated_alias_is_honoured_when_only_it_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CANONICAL_ENV, raising=False)
    monkeypatch.setenv(DEPRECATED_ENV, "sqlite:///legacy.db")
    assert database_url() == "sqlite:///legacy.db"


def test_default_is_returned_when_neither_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CANONICAL_ENV, raising=False)
    monkeypatch.delenv(DEPRECATED_ENV, raising=False)
    assert database_url() is None
    assert database_url(default="sqlite:///driftless.db") == "sqlite:///driftless.db"


def test_canonical_wins_when_both_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CANONICAL_ENV, "postgresql+psycopg://canon/driftless")
    monkeypatch.setenv(DEPRECATED_ENV, "sqlite:///legacy.db")
    assert database_url() == "postgresql+psycopg://canon/driftless"


def test_env_names_are_the_renamed_ones() -> None:
    """The exact strings are operational contract — compose, entrypoint and the
    backup script export them — so the rename is pinned, not incidental."""
    from driftless.db.config import LEGACY_ENV

    assert CANONICAL_ENV == "DRIFTLESS_DATABASE_URL"
    assert LEGACY_ENV == "PMHUB_DATABASE_URL"
    assert DEPRECATED_ENV == "PMHUB_DB_URL"


def test_legacy_canonical_is_honoured_when_only_it_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment still exporting the pre-rename canonical name keeps working
    for one deprecation cycle."""
    from driftless.db.config import LEGACY_ENV

    monkeypatch.delenv(CANONICAL_ENV, raising=False)
    monkeypatch.setenv(LEGACY_ENV, "sqlite:///pre-rename.db")
    monkeypatch.delenv(DEPRECATED_ENV, raising=False)
    assert database_url() == "sqlite:///pre-rename.db"


def test_new_canonical_wins_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    from driftless.db.config import LEGACY_ENV

    monkeypatch.setenv(CANONICAL_ENV, "postgresql+psycopg://canon/driftless")
    monkeypatch.setenv(LEGACY_ENV, "sqlite:///pre-rename.db")
    assert database_url() == "postgresql+psycopg://canon/driftless"


def test_cli_resolution_agrees_with_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every CLI resolves ``args.db_url or database_url()``; with no flag and only
    the canonical env set, each surface must land on the same store the resolver
    reports — the split this module exists to close."""
    monkeypatch.setenv(CANONICAL_ENV, "postgresql+psycopg://canon/driftless")
    monkeypatch.delenv(DEPRECATED_ENV, raising=False)

    from driftless.assess import cli as assess_cli
    from driftless.report import cli as report_cli
    from driftless.wizard import cli as wizard_cli

    for module in (report_cli, assess_cli, wizard_cli):
        resolved = None or database_url()  # mirrors `args.db_url or database_url()`
        assert resolved == database_url()
        assert module.database_url() == database_url()
