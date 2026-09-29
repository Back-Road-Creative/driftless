"""The backup drill is *executed* here, not read.

``tests/test_backup_restore_drill.py`` compares the script's text against OPERATIONS.md, which
is why the script could count `information_schema.tables` for months and still pass everything
written about it: a `--schema-only` dump restores every table and not one row, and a table count
calls that a good backup. Nothing ran it, so nothing could tell.

A real run needs Postgres, which no test host here has. So the four programs the script shells
out to are stubbed on PATH — the dump file carries the mode of the run, `pg_restore` turns that
into the row counts the restored database reports back through `psql` — and the script is run
for real against them. What is asserted is what an operator would find afterwards: a full dump
verifies, a schema-only dump is refused, nothing in the set is readable by anyone else, and a
timestamp with a path in it stays a file name.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "driftless-backup.sh"

# Everything the script calls is looked up on PATH, so nothing in it has to know it is under
# test. `$DRILL_STATE/<db>.rows` is the whole fake cluster: one `table|rows` line per table.
STUBS: dict[str, str] = {
    "sops": "#!/bin/sh\nexit 0\n",
    "pg_dump": '#!/bin/sh\nprintf %s "$DRILL_MODE"\n',
    # age stands in for the real binary the same way pg_dump does, but it TRANSFORMS rather
    # than returning a canned answer: prefixing on encrypt and stripping on decrypt is what
    # makes "the dump never reaches disk in the clear" an assertion instead of a hope. A stub
    # that passed bytes through unchanged would keep every test below green with the pipeline
    # wired backwards.
    "age-keygen": '#!/bin/sh\nfor a; do [ "$a" = -y ] && { echo age1stubrecipient; exit 0; }; done\n',
    "age": """#!/bin/sh
for a; do [ "$a" = -d ] && { sed 's/^AGE://'; exit 0; }; done
printf 'AGE:'
cat
""",
    "createdb": '#!/bin/sh\nfor db; do :; done\n: >"$DRILL_STATE/$db.rows"\n',
    "dropdb": '#!/bin/sh\nfor db; do :; done\nrm -f "$DRILL_STATE/$db.rows"\n',
    "pg_restore": """#!/bin/sh
db=""; dump=""
while [ $# -gt 0 ]; do
  case "$1" in
    -d) db="$2"; shift 2 ;;
    -h|-p|-U) shift 2 ;;
    *) dump="$1"; shift ;;
  esac
done
# No file argument means the dump arrives on stdin, which is how it reaches pg_restore once
# it is decrypted in flight rather than staged in the clear next to the ciphertext.
[ -n "$dump" ] || { dump="$(mktemp)"; cat >"$dump"; }
if [ "$(cat "$dump")" = full ]; then
  cp "$DRILL_STATE/$DRILL_SOURCE.rows" "$DRILL_STATE/$db.rows"
else
  sed 's/|.*/|0/' "$DRILL_STATE/$DRILL_SOURCE.rows" >"$DRILL_STATE/$db.rows"
fi
""",
    # The two questions a verify may ask, answered differently on purpose: counting tables is
    # what cannot tell a schema-only restore from a full one. `query_to_xml` is how a single
    # statement reaches the rows of every table; anything else is a query this stub did not
    # model, and it says so rather than answering something that was not asked.
    "psql": """#!/bin/sh
db=""; sql=""
while [ $# -gt 0 ]; do
  case "$1" in
    -d) db="$2"; shift 2 ;;
    -tAc) sql="$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "$sql" in
  *alembic_version*) echo 0009_head ;;
  *query_to_xml*) cat "$DRILL_STATE/$db.rows" ;;
  *information_schema.tables*) grep -c . "$DRILL_STATE/$db.rows" ;;
  *) echo "stub psql: unmodelled query: $sql" >&2; exit 1 ;;
esac
""",
}
SOURCE_ROWS = "alembic_version|1\napp_user|3\ntask|17\n"  # 3 tables, 21 rows
STAMP = "2026-07-22T09-00-00"
SUFFIXES = (".dump.age", ".manifest", ".secrets.enc.env")
SET = [f"driftless-{STAMP}{suffix}" for suffix in SUFFIXES]


def drill(tmp_path: Path, stamp: str, mode: str = "full") -> subprocess.CompletedProcess[str]:
    """Run bin/driftless-backup.sh for real against the stub cluster, as a cron would."""
    stubs, state = tmp_path / "stubs", tmp_path / "state"
    stubs.mkdir()
    state.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text(body, encoding="utf-8")
        (stubs / name).chmod(0o755)
    (state / "driftless.rows").write_text(SOURCE_ROWS, encoding="utf-8")
    secrets = tmp_path / "secrets.enc.env"
    secrets.write_text("POSTGRES_PASSWORD=ENC[fake]\n", encoding="utf-8")
    secrets.chmod(0o644)  # the checkout's copy is public; the one in the backup set must not be
    env = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PGPASSWORD": "not-a-password",  # pragma: allowlist secret
        "DRIFTLESS_KEY_ESCROW": "<a password-manager entry>",
        "DRIFTLESS_AGE_KEY": str(tmp_path / "age-key.txt"),
        "DRIFTLESS_SECRETS_ENC": str(secrets),
        "DRIFTLESS_BACKUP_DIR": str(tmp_path / "backups"),
        "DRILL_STATE": str(state),
        "DRILL_SOURCE": "driftless",
        "DRILL_MODE": mode,
    }
    # `umask 022` is the default a systemd timer or cron job hands the script: the modes below
    # are only proof of anything if the caller did not set them.
    return subprocess.run(
        ["sh", "-c", 'umask 022; exec "$1" "$2"', "sh", str(SCRIPT), stamp],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


def test_a_full_dump_restore_verifies_and_leaves_the_whole_set(tmp_path: Path) -> None:
    done = drill(tmp_path, STAMP)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert sorted(p.name for p in (tmp_path / "backups").iterdir()) == SET
    assert "21 rows" in done.stdout, f"the run never says how much it restored: {done.stdout!r}"
    manifest = (tmp_path / "backups" / SET[1]).read_text(encoding="utf-8")
    assert "0009_head" in manifest
    assert "3 tables / 21 rows" in manifest, manifest


def test_the_dump_is_encrypted_and_no_plaintext_copy_is_left_behind(tmp_path: Path) -> None:
    """The dump is the whole database, and `chmod 0600` only protects it while it sits on a
    host that is still yours: a stolen disk, a copied backup directory, or the off-host replica
    this set is supposed to grow all read a plaintext `.dump` straight out. So it is encrypted
    to the age key that is *already* escrowed for the overlay — no second secret to lose — and
    encrypted **in flight**, because a script that writes the dump and encrypts it afterwards
    leaves the cleartext on disk for exactly as long as the encryption takes, and forever if
    the run dies in between.
    """
    done = drill(tmp_path, STAMP)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    backups = tmp_path / "backups"

    dump = backups / f"driftless-{STAMP}.dump.age"
    body = dump.read_bytes()
    assert body.startswith(b"AGE:"), (
        f"{dump.name} is not the output of `age`: {body[:40]!r}. The dump must be piped through "
        "encryption on the way to disk."
    )
    assert body != b"full", "the dump reached disk as the raw pg_dump output"

    leftovers = [p.name for p in backups.iterdir() if p.name.endswith(".dump")]
    assert not leftovers, (
        f"{leftovers} — a cleartext dump survived the run beside its ciphertext, which hands an "
        "attacker the database and makes the encryption decorative"
    )


def test_a_schema_only_dump_does_not_pass_restore_verify(tmp_path: Path) -> None:
    done = drill(tmp_path, STAMP, mode="schema-only")
    assert done.returncode != 0, (
        "a dump that restored every table and zero rows was certified as a backup — which is "
        f"exactly what a --schema-only pg_dump produces:\n{done.stdout}"
    )
    assert "restore-verify FAILED" in done.stderr, done.stderr
    assert not (tmp_path / "backups" / SET[1]).exists(), (
        "the manifest is what the restore procedure accepts as a complete set, so a run that "
        "failed to verify must not leave one"
    )


def test_the_backup_set_is_not_readable_by_the_rest_of_the_host(tmp_path: Path) -> None:
    done = drill(tmp_path, STAMP)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    backups = tmp_path / "backups"
    wide = {
        p.name: oct(stat.S_IMODE(p.stat().st_mode))
        for p in [backups, *backups.iterdir()]
        if stat.S_IMODE(p.stat().st_mode) & 0o077
    }
    assert not wide, (
        f"{wide} — the dump is the whole database in the clear and the manifest names where the "
        "age key is escrowed. Under a scheduler's default umask every account on the host can "
        "read both; set the umask in the script rather than trusting the caller's."
    )


def test_a_stamp_with_a_path_in_it_cannot_write_outside_the_backup_directory(
    tmp_path: Path,
) -> None:
    backups = tmp_path / "backups"
    (backups / "driftless-x").mkdir(parents=True)  # the one directory the traversal needs
    done = drill(tmp_path, "x/../../escaped")
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert sorted(p.name for p in backups.iterdir() if p.is_file()) == [
        f"driftless-x_.._.._escaped{suffix}" for suffix in SUFFIXES
    ]
    strays = sorted(p.name for p in tmp_path.iterdir() if p.is_file() and "escaped" in p.name)
    assert not strays, (
        f"the timestamp argument put {strays} outside $DRIFTLESS_BACKUP_DIR. The verify database "
        "name has always been sanitised; the three file names built from the same argument were "
        "not, so a caller's `date` format string chooses where the dump lands."
    )
