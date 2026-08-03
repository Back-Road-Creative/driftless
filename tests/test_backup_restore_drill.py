"""The backup script and the restore procedure are one artefact, checked against each other.

The failure this closes is not a wrong command — it is the two halves drifting apart while
each stays individually true. ``bin/driftless-backup.sh`` dumped Postgres alone for as long as
``OPERATIONS.md`` said "restore the pre-upgrade dump" without saying how, and nothing could
tell: a script writing one file and a procedure needing three each pass every test written
about themselves. So the sets are compared — every file the script writes is one the
*Restoring* section reads back, and nothing else is.

The age private key is the deliberate asymmetry: the third thing a restore needs and the one
thing no job may write, because it decrypts the overlay beside the dump, so a copy in the set
turns one stolen archive into every secret here. "Secret" is not a filename this test knows —
it is read from the repo's own ignore files, as ``test_docs_no_secrets_in_repo`` reads them.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path

from test_docs_no_secrets_in_repo import secret_globs

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "bin" / "driftless-backup.sh").read_text(encoding="utf-8")
OPERATIONS = (ROOT / "OPERATIONS.md").read_text(encoding="utf-8")
WRITES = re.compile(r"\$BACKUP_DIR/driftless-\$STAMP([\w.-]*)")  # what one run leaves behind
READS = re.compile(r"backups/driftless-<stamp>([\w.-]*)")  # what the procedure opens
REQUIRED = re.compile(r"\$\{([A-Z][A-Z0-9_]*):\?")  # a variable the script refuses to run without
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)


def section(heading: str) -> str:
    """One ``##`` section of OPERATIONS.md — ``###`` subsections included, the next ``##`` not."""
    for chunk in OPERATIONS.split("\n## ")[1:]:
        if chunk.startswith(heading):
            return chunk
    raise AssertionError(f"OPERATIONS.md has no '## {heading}' section")


def test_the_restore_consumes_exactly_what_the_backup_writes() -> None:
    written = set(WRITES.findall(SCRIPT))
    read = set(READS.findall(section("Restoring")))
    assert written, f"no $BACKUP_DIR artefact found in bin/driftless-backup.sh: {SCRIPT[:200]!r}"
    assert written == read, (
        f"the backup writes {sorted(written)} and the restore procedure opens {sorted(read)}. "
        "A drill can only pass if those are the same set: an artefact nobody restores is dead "
        "weight, and one nobody backs up is the disaster. Fix bin/driftless-backup.sh or "
        "OPERATIONS.md → Restoring, whichever is wrong."
    )


def test_the_backup_set_never_carries_a_file_the_repo_calls_a_secret() -> None:
    globs = secret_globs()
    assert globs, "no secret pattern in the ignore files: this guard has nothing to enforce"
    names = [f"driftless-2026-01-01T00-00-00{suffix}" for suffix in WRITES.findall(SCRIPT)]
    carried = [name for name in names if any(fnmatch(name, glob) for glob in globs)]
    assert not carried, (
        f"the backup writes {carried} into the same directory as the dump. The age private "
        "key decrypts the overlay beside it, so one stolen archive would open every secret in "
        "it — escrow the key by hand, off this host, and record only its location."
    )


def test_the_operator_is_told_every_variable_the_backup_refuses_to_run_without() -> None:
    backups, restoring = section("Backups"), section("Restoring")
    unmentioned = [
        name
        for name in sorted(set(REQUIRED.findall(SCRIPT)))
        if name not in backups and name not in restoring
    ]
    assert not unmentioned, (
        f"bin/driftless-backup.sh refuses to start without {unmentioned}, and OPERATIONS.md "
        "never names them — the nightly timer fails on its first run with a message no "
        "document explains."
    )


def test_the_restore_ends_by_asking_the_store_the_question_the_service_asks_at_boot() -> None:
    restoring = section("Restoring")
    for check, why in (
        ("alembic_version", "the revision the image compares against at boot"),
        ("app_user", "rows, not an exit code: a restore that dropped its data still exits 0"),
        ("/health/ready", "the one answer that covers reachable AND correctly stamped"),
    ):
        assert check in restoring, (
            f"OPERATIONS.md → Restoring never checks {check} — {why}. Without it the procedure "
            "proves a command exited 0, which is what a silently empty restore also does."
        )


def test_every_documented_pg_restore_can_actually_run_unattended() -> None:
    found, faults = 0, []
    for path in sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("docs/*.md")):
        for body in FENCE.findall(path.read_text(encoding="utf-8")):
            if "pg_restore " not in body:
                continue
            found += 1
            where = str(path.relative_to(ROOT))
            if "PGPASSWORD" not in body:
                faults.append(
                    f"{where}: pg_restore with no PGPASSWORD in the same block. A recovery is a "
                    "fresh shell on a host that has decrypted nothing yet, so it stops at a "
                    "password prompt no unattended run can answer."
                )
            if "--clean" in body and "--if-exists" not in body:
                faults.append(
                    f"{where}: --clean without --if-exists. Every DROP for an object the newer "
                    "schema added is then an error, and what survives breaks the next "
                    "`alembic upgrade head` — a restart loop after a successful-looking restore."
                )
    assert found, "no documented pg_restore block was found, so this guard checked nothing"
    assert not faults, "\n".join(faults)
