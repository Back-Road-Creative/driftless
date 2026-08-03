"""``alembic/env.py`` must register every table, not merely most of them.

``target_metadata`` is ``Base.metadata``, and what lands on that object is
decided entirely by which modules ``env.py`` imports. A missing import does not
fail loudly: autogenerate and ``alembic check`` simply stop seeing those tables
and report that the schema is up to date, so the omission surfaces as a missing
table in production rather than as a red test.

``change_log`` is the table that makes this a real risk. It lives in
``driftless.db.changelog``, which ``driftless.models`` deliberately does not re-export
(activating its flush listener is meant to be an explicit call, never an import
side effect). A baseline generated from ``driftless.models`` alone therefore omits
it, and the first audited write after deploy fails on a table that was never
created. That is not hypothetical — it is what the first draft of the baseline
did.

The probe runs in a *fresh* interpreter on purpose. Inside the test process
other modules have already imported ``driftless.models``, so asserting against the
ambient ``Base.metadata`` would pass no matter what ``env.py`` does. In a clean
subprocess the only thing that can populate that metadata is ``env.py`` itself.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = SERVICE_ROOT / "alembic.ini"

#: Runs alembic far enough to execute env.py, then reports what env.py registered.
_PROBE = """
import sys
from alembic import command
from alembic.config import Config

config = Config(sys.argv[1])
config.set_main_option("sqlalchemy.url", "sqlite://")
command.current(config)

from driftless.db import Base

print(",".join(sorted(Base.metadata.tables)))
"""


def _tables_registered_by_env() -> set[str]:
    """The tables ``env.py`` puts on ``Base.metadata`` in a clean interpreter."""
    probe = subprocess.run(
        [sys.executable, "-c", _PROBE, str(ALEMBIC_INI)],
        capture_output=True,
        text=True,
        cwd=SERVICE_ROOT,
        check=True,
    )
    return set(probe.stdout.strip().splitlines()[-1].split(","))


def test_env_registers_the_audit_table() -> None:
    """The regression guard: ``driftless.models`` alone would leave ``change_log`` out."""
    assert "change_log" in _tables_registered_by_env()


def test_env_registers_every_table_in_the_schema() -> None:
    """Both import sources together account for the whole schema."""
    import driftless.db.changelog  # noqa: F401
    import driftless.models  # noqa: F401
    from driftless.db import Base

    assert _tables_registered_by_env() == set(Base.metadata.tables)


def test_url_is_required_rather_than_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing injected and nothing in the environment, the run refuses to guess."""
    monkeypatch.delenv("DRIFTLESS_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="DRIFTLESS_DATABASE_URL"):
        command.current(Config(str(ALEMBIC_INI)))


def test_url_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured URL is the one used — never a hardcoded fallback."""
    monkeypatch.setenv("PMHUB_DATABASE_URL", "sqlite://")
    command.current(Config(str(ALEMBIC_INI)))
