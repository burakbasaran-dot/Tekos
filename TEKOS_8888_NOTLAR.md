# TEKOS_8888 — Deneme Ortamı Notları

Bu belge, **TEKOS_CLONE** klonunun Cursor/VS Code workspace'i (`TEKOS_8888`) için kurulum, çalıştırma ve sorun giderme rehberidir.

## Bu klon nedir?

| | **Orijinal (üretim)** | **TEKOS_8888 (klon)** |
|---|---|---|
| Dizin | `/Users/burakbasaran/uretim_stok` | `/Users/burakbasaran/TEKOS_CLONE` |
| Port | `8000` | `8888` |
| Veritabanı | PostgreSQL `tekos_db` | Boş **SQLite** (`db.sqlite3`) |
| Medya | Dolu `media/` | Boş `media/` klasörü |
| E-posta/IMAP | Aktif (.env) | Kapalı (`.env` içinde boş) |

Klon, orijinal TEKOS/üretim stok sisteminin **kaynak kod kopyasıdır**. Gerçek veri, yüklenmiş dosyalar ve posta kimlik bilgileri taşınmamıştır. Orijinal sistemle **aynı anda** çalışabilir; birbirini etkilemez.

---

## Workspace'i açma

Cursor veya VS Code'da:

1. **File → Open Workspace from File...** (Türkçe: **Dosya → Workspace'i Dosyadan Aç...**)
2. Şu dosyayı seçin:

   `/Users/burakbasaran/TEKOS_CLONE/TEKOS_8888.code-workspace`

Sol panelde klasör adı **TEKOS_8888** olarak görünür.

---

## Hızlı başlangıç

### 1. Sanal ortam (venv yoksa)

```bash
cd /Users/burakbasaran/TEKOS_CLONE
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pgvector
```

> `pgvector`, TEKORA embedding modelleri için gereklidir. `requirements.txt` içinde listelenmemiş olabilir; ayrıca kurulmalıdır.

### 2. Veritabanı şeması

```bash
source venv/bin/activate
python manage.py migrate
```

İlk kurulumda süper kullanıcı yoksa:

```bash
python manage.py createsuperuser
```

Deneme ortamında hazır hesap (migrate/fixture sonrası):

- **Kullanıcı:** `admin`
- **Şifre:** `admin123` *(üretimde değiştirin)*

### 3. Sunucuyu başlatma

**Önerilen (script):**

```bash
cd /Users/burakbasaran/TEKOS_CLONE
./scripts/run_clone.sh
```

**Manuel:**

```bash
cd /Users/burakbasaran/TEKOS_CLONE
source venv/bin/activate
python manage.py runserver 127.0.0.1:8888
```

### 4. Durdurma

Sunucunun çalıştığı terminalde **Ctrl+C**.

---

## Port 8888 — URL yolları

| Adres | Açıklama |
|---|---|
| http://127.0.0.1:8888/stok/ | Ana uygulama (stok modülü) |
| http://127.0.0.1:8888/stok/ana-sayfa/ | Dashboard |
| http://127.0.0.1:8888/admin/ | Django yönetim paneli |
| http://127.0.0.1:8888/ | `/stok/ana-sayfa/` adresine yönlendirir |
| http://127.0.0.1:8888/static/ | Statik dosyalar (DEBUG modunda) |
| http://127.0.0.1:8888/media/ | Yüklenen dosyalar (klonda boş) |

Orijinal sistem: http://127.0.0.1:8000/stok/ (farklı port, farklı veritabanı).

---

## Veritabanı

### Varsayılan: SQLite

- Dosya: `/Users/burakbasaran/TEKOS_CLONE/db.sqlite3`
- Orijinal PostgreSQL **`tekos_db`** veritabanına **dokunulmaz**.
- Klon boş bir veritabanı ile başlar; stok, sipariş, müşteri vb. kayıtlar yoktur.

### İsteğe bağlı: PostgreSQL

`.env` içinde `TEKOS_POSTGRES_*` satırlarının yorumunu kaldırın:

```env
TEKOS_POSTGRES_DB=tekos_clone_db
TEKOS_POSTGRES_USER=tekos_user
TEKOS_POSTGRES_PASSWORD=
TEKOS_POSTGRES_HOST=localhost
TEKOS_POSTGRES_PORT=5432
```

Ardından:

```bash
# PostgreSQL'de boş veritabanı oluşturun (örnek)
createdb tekos_clone_db

# pgvector eklentisi (TEKORA embedding için)
psql -d tekos_clone_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

source venv/bin/activate
python manage.py migrate
```

> **Önemli:** Üretim veritabanı `tekos_db` değil, ayrı bir isim (`tekos_clone_db`) kullanın.

---

## Kopyalanan / kopyalanmayan

| Kopyalandı | Kopyalanmadı |
|---|---|
| `stokapp/`, `stok_sistemi/` | `media/` içeriği (sadece boş klasör) |
| `manage.py`, `requirements.txt` | `venv/` (yeniden oluşturulur) |
| Şablonlar, statik kaynak kod | PostgreSQL verileri (`tekos_db`) |
| `scripts/run_clone.sh` | E-posta/IMAP hesapları |
| `.env` (IMAP/mail devre dışı) | SQLite/PostgreSQL veri dump'ı |

---

## `.env` yapılandırması

Dosya: `/Users/burakbasaran/TEKOS_CLONE/.env`

```env
# Boş SQLite (varsayılan) — PostgreSQL satırları yorumlu kalır
# TEKOS_POSTGRES_DB=tekos_clone_db
# ...

# E-posta/IMAP kapalı
IMAP_SERVER=
IMAP_PORT=993
MAIL_ACCOUNTS_JSON=[]
```

- **IMAP boş** → gelen posta takibi (TEKORA mail) çalışmaz.
- **MAIL_ACCOUNTS_JSON=[]** → mail hesabı tanımlı değil.
- SMTP ayarları `settings.py` içinde hâlâ tanımlıdır; deneme ortamında gerçek posta gönderilmemesi için IMAP/mail entegrasyonu kapalı tutulmuştur.

Değişiklikten sonra sunucuyu yeniden başlatın.

---

## Sık kullanılan Django komutları

```bash
cd /Users/burakbasaran/TEKOS_CLONE
source venv/bin/activate

python manage.py migrate          # şema güncelle
python manage.py makemigrations   # model değişikliği sonrası
python manage.py createsuperuser  # yeni admin
python manage.py collectstatic    # statik dosyalar (gerekirse)
python manage.py shell            # Django shell
```

---

## Sorun giderme

### `pgvector` bulunamadı / import hatası

```bash
source venv/bin/activate
pip install pgvector
```

PostgreSQL kullanıyorsanız sunucuda da extension gerekir:

```bash
psql -d tekos_clone_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Port 8888 kullanımda

```bash
lsof -i :8888
kill <PID>
```

Veya farklı port:

```bash
python manage.py runserver 127.0.0.1:8889
```

(Tarayıcıda portu buna göre değiştirin.)

### `venv bulunamadı` (run_clone.sh)

Script `venv` klasörü olmadan çalışmaz. Yukarıdaki venv kurulum adımlarını uygulayın.

### Migration hatası

```bash
python manage.py migrate --plan    # ne uygulanacağını gör
python manage.py showmigrations    # hangi migration'lar uygulandı
```

SQLite dosyasını sıfırlamak (tüm veri silinir):

```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Statik/medya dosyaları görünmüyor

Klon ortamında `media/` boştur; üretimdeki PDF, fotoğraf vb. kopyalanmamıştır. Statik CSS/JS kaynak kodda mevcuttur; gerekirse `collectstatic` çalıştırın.

### Orijinal sistemle karışıklık

- Klon: port **8888**, dizin `TEKOS_CLONE`
- Orijinal: port **8000**, dizin `uretim_stok`

İki terminal penceresinde farklı dizinlerde çalıştırdığınızdan emin olun.

---

## İlgili dosyalar

| Dosya | Açıklama |
|---|---|
| `TEKOS_8888.code-workspace` | Cursor/VS Code workspace |
| `TEKOS_8888_NOTLAR.md` | Bu belge |
| `KLON_README.md` | Kısa özet |
| `scripts/run_clone.sh` | Başlatma scripti |
| `.env` | Ortam değişkenleri |
| `db.sqlite3` | SQLite veritabanı (oluşturulunca) |

---

*Son güncelleme: TEKOS_8888 workspace kurulumu*
