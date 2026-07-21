#!/usr/bin/env bash
# PostgreSQL backup using DATABASE_URL. Does not echo credentials.
set -o errexit
set -o nounset
set -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/tekos_${TIMESTAMP}.dump"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump is not installed or not on PATH." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Creating backup at: $OUT_FILE"
if ! pg_dump --format=custom --file="$OUT_FILE" "$DATABASE_URL"; then
  echo "ERROR: pg_dump failed." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

echo "Backup completed successfully."
