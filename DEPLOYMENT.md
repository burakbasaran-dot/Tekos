# TEKOS Deployment Guide

## Local kurulum

1. Python 3.12+ önerilir.
2. Virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Ortam dosyası:

```bash
cp .env.example .env
```

Local için örnek:

```
DEBUG=True
SECRET_KEY=local-dev-key
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
SECURE_SSL_REDIRECT=False
```

4. Migration ve superuser:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Veritabanı önceliği: `DATABASE_URL` → `TEKOS_POSTGRES_*` → SQLite.

SQLite verisini otomatik PostgreSQL’e taşımıyoruz. Aktarım için [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

---

## Render Web Service kurulumu

1. GitHub reposunu Render’a bağlayın (auto-deploy açık olabilir).
2. **Build Command:** `./build.sh`
3. **Start Command:** `gunicorn stok_sistemi.wsgi:application`
4. **Health Check Path:** `/api/health/`

`build.sh` sırası: pip install → collectstatic → migrate → `create_default_admin`.

---

## Render PostgreSQL kurulumu

1. Render Dashboard → **New → PostgreSQL**.
2. Web Service’e bağlayın (Internal Database) veya `DATABASE_URL` değerini kopyalayın.
3. Web Service Environment’a `DATABASE_URL` ekleyin (Render genelde otomatik bağlar).

Free / ephemeral disk üzerinde SQLite kullanmayın; veri kaybı riski yüksektir.

---

## Environment variables (Render)

Gerçek değerleri repoya yazmayın. Panelde tanımlayın:

| Variable | Örnek / not |
|----------|-------------|
| `SECRET_KEY` | Uzun rastgele string (zorunlu, `DEBUG=False`) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `tekos-9155.onrender.com,app.ornekdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://tekos-9155.onrender.com,https://app.ornekdomain.com` |
| `DATABASE_URL` | Render PostgreSQL connection string |
| `DJANGO_SUPERUSER_USERNAME` | İlk admin kullanıcı adı |
| `DJANGO_SUPERUSER_EMAIL` | Admin e-posta |
| `DJANGO_SUPERUSER_PASSWORD` | Güçlü şifre (yalnızca ilk oluşturmada kullanılır) |
| `SECURE_SSL_REDIRECT` | `True` (production) |
| `SITE_URL` | `https://tekos-9155.onrender.com` |
| `SECURE_HSTS_SECONDS` | Başlangıçta `0`; HTTPS doğrulandıktan sonra artırın |

Opsiyonel e-posta / IMAP değişkenleri için `.env.example` dosyasına bakın.

### Custom domain örnekleri

```
ALLOWED_HOSTS:
tekos-9155.onrender.com,app.ornekdomain.com

CSRF_TRUSTED_ORIGINS:
https://tekos-9155.onrender.com,https://app.ornekdomain.com
```

---

## HTTPS ve proxy

Render HTTPS’i sonlandırır. Uygulama `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` kullanır.

`DEBUG=False` iken güvenli cookie’ler, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY` ve referrer policy etkinleşir.

---

## Admin oluşturma (güvenli)

`create_default_admin` komutu yalnızca `DJANGO_SUPERUSER_*` değişkenleri tam ise kullanıcı oluşturur.

- Kullanıcı varsa şifreyi **değiştirmez**.
- Değişkenler eksikse hata vermeden çıkar (deploy kırılmaz).
- Şifre loglanmaz.

### Güvenlik uyarısı — eski hardcoded admin şifresi

Daha önce kod içinde sabit bir admin şifresi bulunuyordu. Bu şifre **artık güvenli değildir** (git geçmişinde açığa çıkmış kabul edilmelidir).

Render’da:

1. Yeni güçlü bir `DJANGO_SUPERUSER_PASSWORD` tanımlayın (veya mevcut admin şifresini panelden / Django admin’den değiştirin).
2. Eski bilinen şifreyi kullanmayı bırakın.
3. Mümkünse mevcut Admin kullanıcısının şifresini hemen rotasyonlayın.

---

## Health check

`GET /api/health/`

Başarılı: `{"status":"ok"}`  
Veritabanı sorunu: `{"status":"error"}` + HTTP 503  

Hassas bilgi dönmez.

---

## Static ve media

- Static: WhiteNoise + `collectstatic` (build sırasında).
- Media: `MEDIA_ROOT` yerel disk. Render Free instance diski **kalıcı değildir**; production’da ileride S3 uyumlu object storage önerilir. Mevcut upload özellikleri bozulmaz; kalıcılık için harici depolama planlayın.

---

## CI / GitHub Actions

`.github/workflows/django-ci.yml` her push/PR’da:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py test`

Akış:

```
GitHub push → GitHub Actions test → (başarılıysa) Render auto-deploy
```

**Önemli:** Render auto-deploy, CI başarısız olsa bile çalışabilir. `main` için branch protection (required status checks) önerilir.

---

## Deploy sonrası kontrol listesi

- [ ] Ana sayfa / login açılıyor mu?
- [ ] Admin paneli (`/admin/`) açılıyor mu?
- [ ] Static dosyalar geliyor mu?
- [ ] Migration tamam mı?
- [ ] Form gönderimleri / CSRF hatası yok mu?
- [ ] Upload alanları çalışıyor mu? (ephemeral disk notunu bil)
- [ ] `/api/health/` → ok?
- [ ] `DEBUG=False` mi?
- [ ] 404/500 sayfaları teknik traceback göstermiyor mu?
- [ ] Eski hardcoded admin şifresi değiştirildi mi?
- [ ] İlk PostgreSQL backup alındı mı?

---

## Sorun giderme

| Belirti | Kontrol |
|---------|---------|
| DisallowedHost | `ALLOWED_HOSTS` |
| CSRF verification failed | `CSRF_TRUSTED_ORIGINS` (https://…) |
| Static 404 | build collectstatic, WhiteNoise middleware |
| DB connection error | `DATABASE_URL`, SSL, Render PG durumu |
| SECRET_KEY ImproperlyConfigured | Production’da `SECRET_KEY` zorunlu |
| Admin oluşmadı | `DJANGO_SUPERUSER_*` eksik olabilir (bilinçli skip) |

---

## Rollback

1. Render’da önceki başarılı deploy’a rollback.
2. Gerekirse PostgreSQL’i son bilinen dump’tan restore edin ([BACKUP_RESTORE.md](BACKUP_RESTORE.md)).
3. Env değişkenlerini yanlışlıkla silmediğinizi doğrulayın.
