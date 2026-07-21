#!/usr/bin/env bash
# TEKOS deneme ortamı — orijinal sistemden bağımsız, port 8888
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d venv ]]; then
  echo "venv bulunamadı. Önce: python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source venv/bin/activate
echo "TEKOS_CLONE → http://127.0.0.1:8888/stok/"
echo "Veritabanı: ${TEKOS_POSTGRES_DB:-tekos_clone_db}"
exec python manage.py runserver 127.0.0.1:8888
