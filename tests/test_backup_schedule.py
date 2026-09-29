"""The schedule is what turns "there is a backup script" into "there are backups".

``tests/test_backup_script_drill.py`` proves the script makes a good backup; nothing proved one
ever ran. These check the units that fire it and the runner they fire — the runner executed
against stubs, as the backup drill is, because a scheduling bug stays invisible until the day
you need the backup that was never taken.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TIMER = (ROOT / "deploy" / "driftless-backup.timer").read_text(encoding="utf-8")
SERVICE = (ROOT / "deploy" / "driftless-backup.service").read_text(encoding="utf-8")
RUNNER = ROOT / "bin" / "driftless-backup-run.sh"


def test_a_host_that_was_off_at_the_scheduled_time_still_backs_up() -> None:
    """``Persistent=true`` is the difference between "daily backups" and "daily backups on the
    days the host was awake at 03:00": without it a missed run is skipped, and the operator's
    belief that RPO is 24h silently stops being true.
    """
    for setting in ("Persistent=true", "OnCalendar=", "RandomizedDelaySec="):
        assert setting in TIMER, f"the timer does not set {setting!r}:\n{TIMER}"


def test_the_database_password_never_reaches_a_process_listing() -> None:
    """OPERATIONS.md warns that every argv on this host is world-readable through ``ps``. The
    decrypted POSTGRES_PASSWORD is the one secret this runner handles, so it is exported into
    the child's environment and never passed as an argument. The unit calls the runner rather
    than an ``ExecStart=`` one-liner for the same reason: this is logic worth testing.
    """
    body = RUNNER.read_text(encoding="utf-8")
    assert "export PGPASSWORD" in body, body
    for leak in ("--password", "-W "):
        assert leak not in body, f"{leak!r} would put the password where `ps` can read it"
    assert "Type=oneshot" in SERVICE and "driftless-backup-run.sh" in SERVICE, SERVICE


def drill(tmp_path: Path, backup_rc: int) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the runner for real, with the backup script and sops stubbed on PATH."""
    binf, stubs = tmp_path / "bin", tmp_path / "stubs"
    binf.mkdir()
    stubs.mkdir()
    # The runner finds the backup script beside itself, so that stub goes in bin/, not on PATH.
    files = {
        binf / "driftless-backup-run.sh": RUNNER.read_text(encoding="utf-8"),
        binf / "driftless-backup.sh": f'#!/bin/sh\necho "stub ran: $*"\nexit {backup_rc}\n',
        stubs / "sops": "#!/bin/sh\necho not-a-real-password\n",
    }
    for path, body in files.items():
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    log = tmp_path / "backup.log"
    env = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "DRIFTLESS_BACKUP_LOG": str(log),
        "DRIFTLESS_AGE_KEY": str(tmp_path / "age-key.txt"),
        "DRIFTLESS_KEY_ESCROW": "<a password-manager entry>",
        "DRIFTLESS_SECRETS_ENC": str(tmp_path / "secrets.enc.env"),
    }
    done = subprocess.run(
        [str(binf / "driftless-backup-run.sh")],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    return done, log


@pytest.mark.parametrize("rc", [0, 1])
def test_every_run_records_its_outcome_and_a_failure_is_not_swallowed(
    rc: int, tmp_path: Path
) -> None:
    """Both halves of the failure signal. A wrapper that logged a failure and still exited 0
    would be worse than none: systemd would record a healthy unit, spending the one signal an
    operator ever notices — so the script's exit code is re-raised as well as logged.
    """
    done, log = drill(tmp_path, backup_rc=rc)
    assert done.returncode == rc, f"exit {done.returncode} != backup's {rc}:\n{done.stdout}"
    assert f"exit={rc}" in log.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")
