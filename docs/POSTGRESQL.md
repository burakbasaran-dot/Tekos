# PostgreSQL (TEKOS)

## Amaç

Render production’da kalıcı PostgreSQL kullanımı; local’de SQLite fallback.

## Mimari

Bağlantı önceliği (`stok_sistemi/settings.py`):

1. `DATABASE_URL` (Render / production)
2. `TEKOS_POSTGRES_*` (local Postgres klon)
3. SQLite (`db.sqlite3`) — yalnızca local geliştirme

Render (`RENDER` / `RENDER_SERVICE_ID` / `RENDER_EXTERNAL_HOSTNAME`) üzerinde `DATABASE_URL` yoksa uygulama başlamaz (SQLite yasak).

Production Postgres için `conn_max_age=600`, `conn_health_checks=True`, `sslmode=require` (DEBUG=False).

## Kullanılan paketler

- `dj-database-url`
- `psycopg[binary]`
- `pgvector` (TEKORA embedding — extension gerekir)

## pgvector

PostgreSQL’de extension, migration `0102_enable_pgvector_extension` ile
`VectorField` tablolarından (`0103_tekoramemoryembedding`) **önce** açılır:

```python
from pgvector.django import VectorExtension
# CREATE EXTENSION IF NOT EXISTS vector  (PostgreSQL only; SQLite no-op)
```

Render’da `CREATE EXTENSION` yetkisi yoksa dashboard’dan `vector` uzantısını
manuel etkinleştirin. Extension yoksa TEKORA embedding migration’ı başarısız olur.

## Health / ops

- HTTP: `GET /api/health/` → `{"status":"ok"}` veya 503
- CLI: `python manage.py report_database` (engine, migration özeti; URL/şifre basmaz)

## Backup / restore

```bash
bash -n scripts/backup_postgres.sh
bash -n scripts/restore_postgres.sh
export DATABASE_URL='postgresql://...'
./scripts/backup_postgres.sh
CONFIRM=YES ./scripts/restore_postgres.sh backups/tekos_YYYYMMDD_HHMMSS.dump
```

Ayrıntılar: [BACKUP_RESTORE.md](../BACKUP_RESTORE.md)

## Kalıcılık testi (manuel)

1. Render’da PostgreSQL oluşturup Web Service’e bağlayın.
2. Deploy sonrası `report_database` veya shell yoksa health + uygulama login.
3. Admin ile bir kayıt oluşturun, redeploy edin, kaydın durduğunu doğrulayın.
4. SQLite dosyasının Render diskine yazılmadığını doğrulayın (`DATABASE_URL` zorunlu).

## SQLite → PostgreSQL (kontrollü)

Otomatik taşıma yok.

```bash
# Kaynak (SQLite)
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e sessions -o data_export.json

# Hedef (DATABASE_URL=postgres)
python manage.py migrate
python manage.py loaddata data_export.json
```

`data_export.json` commit edilmemeli.

## Güvenlik

- Connection string’i loglamayın.
- Production’da `DEBUG=False` ve `SECRET_KEY` zorunlu.

## Testler

- `core.tests` health endpoint
- `manage.py check` / `makemigrations --check`

## Manuel işlemler (Render)

1. PostgreSQL instance
2. `DATABASE_URL` Web Service env
3. Deploy / migrate (`build.sh`)
4. `CREATE EXTENSION vector` (TEKORA için)
5. İlk backup

## Gelecek

- Media için object storage (S3)
- Managed backup politikası
