# PostgreSQL Backup & Restore

Bu doküman Render / production PostgreSQL yedekleme ve geri yükleme için hazırlanmıştır.

Genel (SQLite dahil) notlar için ayrıca: [YEDEKLEME_REHBERI.md](YEDEKLEME_REHBERI.md).

---

## Önkoşullar

- `DATABASE_URL` ortam değişkeni (Render PostgreSQL connection string)
- Yerel veya CI makinede `pg_dump` / `pg_restore` (PostgreSQL client tools)

Şifreleri terminale yazdırmayın; URL’yi `echo` etmeyin.

---

## Manuel backup

```bash
export DATABASE_URL='postgresql://...'   # gerçek değeri paneldan alın; commit etmeyin
./scripts/backup_postgres.sh
```

Çıktı: `backups/tekos_YYYYMMDD_HHMMSS.dump`

`backups/` klasörü `.gitignore` içindedir.

---

## Manuel restore

**Uyarı:** Hedef veritabanındaki veriyi bozar / üzerine yazar.

```bash
export DATABASE_URL='postgresql://...'
CONFIRM=YES ./scripts/restore_postgres.sh backups/tekos_YYYYMMDD_HHMMSS.dump
```

`CONFIRM=YES` olmadan script çalışmaz.

---

## Render PostgreSQL backup seçenekleri

- Render Dashboard → PostgreSQL → backup / point-in-time (plana göre)
- Ücretli planlarda otomatik backup özellikleri kullanılabilir
- Free planlarda düzenli manuel `pg_dump` + harici depolama önerilir

---

## Harici object storage

Dump dosyalarını Render diskine bırakmayın (ephemeral). Öneriler:

- S3 / Cloudflare R2 / Backblaze B2
- Şifreli depolama ve erişim anahtarlarını yalnızca secret store’da tutun

---

## Saklama politikası (öneri)

- Günlük: son 7 gün
- Haftalık: son 4 hafta
- Aylık: son 6–12 ay
- Kritik değişiklik öncesi: ad-hoc snapshot

---

## Restore testi

Yedek “alınmış” sayılmaz; en az üç ayda bir staging DB’ye restore edin:

1. Ayrı bir test veritabanı oluşturun
2. Dump’ı restore edin
3. `python manage.py check` ve kritik sayfa smoke testleri çalıştırın

---

## Production öncesi yedek

Her major deploy / migration / domain değişikliği öncesi:

```bash
./scripts/backup_postgres.sh
# dump’ı harici depolamaya kopyalayın
```

---

## SQLite → PostgreSQL veri aktarımı (kontrollü)

Otomatik taşıma yapılmaz. Önerilen prosedür:

1. Kaynak (SQLite) ortamında:

```bash
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e sessions \
  -o data_export.json
```

2. Hedefte boş PostgreSQL + migration:

```bash
export DATABASE_URL='postgresql://...'
python manage.py migrate
```

3. Veriyi yükleyin:

```bash
python manage.py loaddata data_export.json
```

4. Media dosyalarını ayrı kopyalayın (`media/`). Render Free’de media kalıcı değildir; object storage planlayın.

5. `data_export.json` içinde hassas veri olabilir; commit etmeyin, iş bitince silin.

---

## Media notu

Veritabanı yedeği media dosyalarını içermez. Upload’lar için ayrı sync / object storage gerekir.
