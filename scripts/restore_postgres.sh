#!/usr/bin/env bash
# Restore PostgreSQL from a dump file. Requires explicit confirmation.
# Usage: CONFIRM=YES ./scripts/restore_postgres.sh path/to/backup.dump
set -o errexit
set -o nounset
set -o pipefail

DUMP_FILE="${1:-}"

if [[ -z "$DUMP_FILE" ]]; then
  echo "Usage: CONFIRM=YES $0 /path/to/backup.dump" >&2
  exit 1
fi

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ERROR: Dump file not found: $DUMP_FILE" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  exit 1
fi

if [[ "${CONFIRM:-}" != "YES" ]]; then
  echo "ERROR: Refusing to restore without CONFIRM=YES" >&2
  echo "This will overwrite data in the target database." >&2
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "ERROR: pg_restore is not installed or not on PATH." >&2
  exit 1
fi

echo "Restoring from: $DUMP_FILE"
if ! pg_restore --clean --if-exists --no-owner --no-acl --dbname="$DATABASE_URL" "$DUMP_FILE"; then
  echo "ERROR: pg_restore failed." >&2
  exit 1
fi

echo "Restore completed successfully."
