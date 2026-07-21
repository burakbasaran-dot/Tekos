# TEKOS_CLONE — Deneme Ortamı

Orijinal `uretim_stok` / TEKOS sisteminden bağımsız kopya. Veri ve dosyalar kopyalanmadı.

> Ayrıntılı kurulum ve sorun giderme: **[TEKOS_8888_NOTLAR.md](./TEKOS_8888_NOTLAR.md)**  
> Cursor workspace: **[TEKOS_8888.code-workspace](./TEKOS_8888.code-workspace)**

## Başlatma

```bash
cd ~/TEKOS_CLONE
./scripts/run_clone.sh
```

Tarayıcı: **http://127.0.0.1:8888/stok/**

## Giriş

- Kullanıcı: `admin`
- Şifre: `admin123` (deneme için; değiştirmeniz önerilir)

## Ne kopyalandı / kopyalanmadı

| Kopyalandı | Kopyalanmadı |
|---|---|
| `stokapp/`, `stok_sistemi/` | `media/` (boş klasör) |
| `manage.py`, `requirements.txt` | `venv/` (yeniden oluşturuldu) |
| Şablonlar, statik kaynak kod | Veritabanı verileri |
| | E-posta/IMAP ayarları (kapalı) |

## Veritabanı

Boş **SQLite** (`db.sqlite3`) — orijinal PostgreSQL `tekos_db`'ye dokunmaz.

PostgreSQL kullanmak isterseniz `.env` içinde `TEKOS_POSTGRES_DB=tekos_clone_db` satırının yorumunu kaldırın (DB oluşturma izni gerekir).

## Orijinal sistem

Orijinal TEKOS/uretim_stok farklı portta çalışmaya devam eder; birbirini etkilemez.
