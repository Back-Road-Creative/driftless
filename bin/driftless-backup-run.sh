#!/usr/bin/env sh
# What the systemd timer actually executes: decrypt the database password, run the backup,
# and leave one line behind saying how it went.
#
# A file rather than an `ExecStart=/bin/sh -c '…'` string: a unit-file one-liner cannot be
# tested or read, and this one handles a secret, chooses a timestamp and decides an exit code
# (tests/test_backup_schedule.py runs it against stubs). The password is EXPORTED, never passed
# as an argument: every argv here is readable through `ps` (OPERATIONS.md, Database access).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
: "${DRIFTLESS_SECRETS_ENC:=$(cd "$HERE/.." && pwd)/deploy/secrets.enc.env}"
# Beside the set it describes: no root-owned directory, and it travels with a copied backup.
: "${DRIFTLESS_BACKUP_LOG:=${DRIFTLESS_BACKUP_DIR:-./backups}/backup.log}"
mkdir -p "$(dirname "$DRIFTLESS_BACKUP_LOG")"

PGPASSWORD=$(sops -d --extract '["POSTGRES_PASSWORD"]' "$DRIFTLESS_SECRETS_ENC")
export PGPASSWORD

# driftless-backup.sh takes the stamp as an argument so a run is reproducible; this is where
# the scheduled run's stamp is chosen.
STAMP=$(date +%FT%H-%M-%S)

# `set -e` would abort before the result line is written, and a failed backup that leaves no
# trace is the failure mode this runner exists to close — so capture and re-raise instead.
set +e
"$HERE/driftless-backup.sh" "$STAMP" >>"$DRIFTLESS_BACKUP_LOG" 2>&1
rc=$?
set -e

# One machine-readable line per run for a watcher to scan; anything but exit=0 is a backup that
# did not happen. Re-raised below so systemd marks the unit failed too — a wrapper that logged
# the failure and exited 0 would spend the only signal an operator ever sees.
printf '%s driftless-backup stamp=%s exit=%s\n' "$(date -Is)" "$STAMP" "$rc" \
    >>"$DRIFTLESS_BACKUP_LOG"
exit "$rc"
