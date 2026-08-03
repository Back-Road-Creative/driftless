#!/usr/bin/env sh
# Back up the driftless database and PROVE the backup restores.
#
# A backup that has never been restored is a hope, not a backup. This dumps the
# database, restores the dump into a throwaway database, and compares the row count
# of every table; only a matching restore is treated as a good backup. The timestamp is
# passed in (argument 1) rather than read from the clock, so a caller can make
# the run reproducible.
#
# A restore needs THREE things (OPERATIONS.md, Restoring): this dump, the encrypted
# overlay, and the age private key that decrypts it. Both files are written here. The
# key never is — a copy beside the dump makes one stolen archive open every secret in
# it — so it is proved instead: each run decrypts the overlay with it before dumping
# anything, and DRIFTLESS_KEY_ESCROW records where the off-host copy lives. The day
# the key goes missing is then a failed backup, not a failed disaster.
#
# Usage: PGPASSWORD=... bin/driftless-backup.sh 2026-07-22T09-00-00
set -eu

STAMP="${1:?usage: driftless-backup.sh <timestamp>}"
# The stamp names three files, so anything but a file name in it chooses where they land — a
# caller's `date` format string is enough. The verify database below has always been sanitised;
# the paths are too now, and by the same rule: what is not [A-Za-z0-9._-] becomes an underscore.
STAMP=$(printf '%s' "$STAMP" | tr -c 'a-zA-Z0-9._-' '_')
: "${DRIFTLESS_DB_HOST:=127.0.0.1}"
: "${DRIFTLESS_DB_PORT:=55432}"
: "${DRIFTLESS_DB_USER:=driftless}"
: "${DRIFTLESS_DB_NAME:=driftless}"
: "${PGPASSWORD:?set PGPASSWORD — source the decrypted secrets first}"
export PGPASSWORD
BACKUP_DIR="${DRIFTLESS_BACKUP_DIR:-./backups}"
REPO=$(cd "$(dirname "$0")/.." && pwd)
SECRETS="${DRIFTLESS_SECRETS_ENC:-$REPO/deploy/secrets.enc.env}"
: "${DRIFTLESS_KEY_ESCROW:?set DRIFTLESS_KEY_ESCROW — one line naming where the OFF-HOST copy of the age private key lives (a password-manager entry, offline media). Name the place, never the key: this file sits beside the dump. A host is not a backup of itself.}"
: "${SOPS_AGE_KEY_FILE:=${DRIFTLESS_AGE_KEY:?set DRIFTLESS_AGE_KEY — the age private key that decrypts $SECRETS}}"
export SOPS_AGE_KEY_FILE

# Before anything is dumped: prove the secrets still decrypt. A certified dump beside
# an overlay nobody can open restores a database and starts no service.
sops -d "$SECRETS" >/dev/null || {
    echo "driftless-backup: $SECRETS does not decrypt with $SOPS_AGE_KEY_FILE — restoring this dump would leave a service that cannot start; fix the key before backing up" >&2
    exit 1
}

# The dump is the whole database in the clear and the manifest names where the key is escrowed.
# A scheduler hands the script a 022 umask, which would leave both readable by every account on
# the host; set it here rather than trusting the caller (deploy/entrypoint.sh does the same).
umask 077
mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/driftless-$STAMP.dump"

pg() { psql -h "$DRIFTLESS_DB_HOST" -p "$DRIFTLESS_DB_PORT" -U "$DRIFTLESS_DB_USER" "$@"; }
# Tables prove nothing: a --schema-only dump restores every table and not one row, and a count
# of information_schema.tables calls that a good backup. So compare the ROWS, per table — one
# statement, because query_to_xml runs a count against each table the catalogue lists.
rows_per_table() {
    pg -d "$1" -tAc "select table_name,
            (xpath('/row/c/text()',
                   query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name),
                                false, true, '')))[1]::text
        from information_schema.tables
        where table_schema='public' and table_type='BASE TABLE'
        order by 1"
}

echo "Dumping $DRIFTLESS_DB_NAME -> $DUMP"
pg_dump -h "$DRIFTLESS_DB_HOST" -p "$DRIFTLESS_DB_PORT" -U "$DRIFTLESS_DB_USER" -Fc "$DRIFTLESS_DB_NAME" >"$DUMP"

VERIFY_DB="driftless_verify_$(echo "$STAMP" | tr -c 'a-zA-Z0-9' '_')"
echo "Restore-verify into $VERIFY_DB"
createdb -h "$DRIFTLESS_DB_HOST" -p "$DRIFTLESS_DB_PORT" -U "$DRIFTLESS_DB_USER" "$VERIFY_DB"
trap 'dropdb -h "$DRIFTLESS_DB_HOST" -p "$DRIFTLESS_DB_PORT" -U "$DRIFTLESS_DB_USER" "$VERIFY_DB" 2>/dev/null || true' EXIT
pg_restore -h "$DRIFTLESS_DB_HOST" -p "$DRIFTLESS_DB_PORT" -U "$DRIFTLESS_DB_USER" -d "$VERIFY_DB" "$DUMP"

SRC=$(rows_per_table "$DRIFTLESS_DB_NAME")
DST=$(rows_per_table "$VERIFY_DB")
if [ "$SRC" != "$DST" ]; then
    echo "restore-verify FAILED: the restore is not the source. table|rows —" >&2
    echo "  source:  $SRC" >&2
    echo "  restore: $DST" >&2
    exit 1
fi
TOTALS=$(printf '%s\n' "$SRC" | awk -F'|' 'NF == 2 { t += 1; r += $2 } END { print t + 0, r + 0 }')
TABLES=${TOTALS% *}
ROWS=${TOTALS#* }
if [ "$TABLES" -eq 0 ] || [ "$ROWS" -eq 0 ]; then
    echo "restore-verify FAILED: $TABLES tables / $ROWS rows — matching nothing is not a restore" >&2
    exit 1
fi
echo "restore-verify OK: $TABLES tables / $ROWS rows restored. Backup kept at $DUMP"

# Only now — a set is complete if and only if its manifest is there, so a run that
# died half way leaves a dump the restore procedure will not accept as a backup.
cp "$SECRETS" "$BACKUP_DIR/driftless-$STAMP.secrets.enc.env"
cat >"$BACKUP_DIR/driftless-$STAMP.manifest" <<MANIFEST
driftless backup $STAMP — restore with OPERATIONS.md, Restoring
code:     $(git -C "$REPO" describe --tags --always --dirty 2>/dev/null || echo unknown)
revision: $(pg -d "$DRIFTLESS_DB_NAME" -tAc 'select version_num from alembic_version' 2>/dev/null || echo unstamped)
dump:     driftless-$STAMP.dump ($TABLES tables / $ROWS rows, restore-verified)
overlay:  driftless-$STAMP.secrets.enc.env (encrypted; the checkout's may have rotated)
key:      NOT here and never will be — the age private key is escrowed by hand at:
          $DRIFTLESS_KEY_ESCROW
MANIFEST
echo "Backup set complete: $BACKUP_DIR/driftless-$STAMP.manifest"
