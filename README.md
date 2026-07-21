# TEKOS

Django tabanlı stok / üretim yönetim sistemi (TEKOS).

## Hızlı başlangıç (local)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env içinde DEBUG=True ve isteğe bağlı SECRET_KEY ayarlayın
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Varsayılan veritabanı: SQLite (`db.sqlite3`). PostgreSQL için `DATABASE_URL` veya legacy `TEKOS_POSTGRES_*` kullanın.

## Dokümantasyon

- [DEPLOYMENT.md](DEPLOYMENT.md) — Render production kurulumu, env değişkenleri, domain, checklist
- [BACKUP_RESTORE.md](BACKUP_RESTORE.md) — PostgreSQL yedekleme / geri yükleme
- [docs/POSTGRESQL.md](docs/POSTGRESQL.md) — PostgreSQL / pgvector
- [docs/MULTI_TENANT.md](docs/MULTI_TENANT.md) — Multi-tenant temel
- [docs/COMPANY_SETUP_WIZARD.md](docs/COMPANY_SETUP_WIZARD.md) — Firma kurulum sihirbazı
- [docs/SUBSCRIPTION_SYSTEM.md](docs/SUBSCRIPTION_SYSTEM.md) — Lisans / abonelik
- [docs/AUDIT_LOG.md](docs/AUDIT_LOG.md) — Platform audit log
- [docs/ROADMAP_NEXT.md](docs/ROADMAP_NEXT.md) — Sonraki adımlar
- [YEDEKLEME_REHBERI.md](YEDEKLEME_REHBERI.md) — Genel yedekleme notları
- [KLON_README.md](KLON_README.md) — Klon ortamı notları

## Deploy akışı

```
GitHub push → GitHub Actions (check / migrations / tests) → Render auto-deploy
```

Not: Render, CI başarısız olsa bile auto-deploy yapabilir. Branch protection önerilir (DEPLOYMENT.md).

## Health check

`GET /api/health/` → `{"status":"ok"}`
