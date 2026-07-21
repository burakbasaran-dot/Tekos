# Yedekleme Rehberi

## Klasör Kopyalama ile Yedekleme

Proje klasörünü tamamen kopyaladığınızda aşağıdaki önemli dosyalar yedeklenir:

### ✅ Yedeklenen Dosyalar:

1. **Veritabanı**: `db.sqlite3` (proje kök dizininde)
   - Tüm verileriniz burada (stoklar, siparişler, üretim, personel, vb.)

2. **Media Dosyaları**: `media/` klasörü
   - Yüklenen fotoğraflar, PDF'ler, teknik resimler
   - Araç belgeleri, sigorta dosyaları, stok fotoğrafları

3. **Program Kodu**: `stokapp/`, `stok_sistemi/` klasörleri
   - Tüm uygulama kodu ve ayarlar

4. **Bağımlılıklar**: `requirements.txt`
   - Gerekli Python paketlerinin listesi

### ⚠️ Dikkat Edilmesi Gerekenler:

1. **Virtual Environment (stok_env/ veya venv/)**
   - Kopyalanabilir ama **önerilmez**
   - Farklı sistemde çalıştırırken sorun çıkarabilir
   - **Öneri**: Virtual environment'ı kopyalamayın, sadece `requirements.txt` yeterli

2. **Python Versiyonu**
   - Hedef sistemde aynı Python versiyonu olmalı (şu anda Python 3.12)
   - Farklı versiyonlarda sorun çıkabilir

3. **Sistem Dosyaları**
   - `__pycache__/` klasörleri kopyalanmasa da sorun olmaz
   - `.pyc` dosyaları otomatik oluşturulur

## Geri Yükleme Adımları:

1. **Klasörü geri kopyalayın**
   ```bash
   cp -r /yedek/uretim_stok /yeni/konum/uretim_stok
   ```

2. **Virtual environment oluşturun** (eğer kopyalamadıysanız)
   ```bash
   cd /yeni/konum/uretim_stok
   python3.12 -m venv stok_env
   source stok_env/bin/activate  # Linux/Mac
   # veya
   stok_env\Scripts\activate  # Windows
   ```

3. **Bağımlılıkları yükleyin**
   ```bash
   pip install -r requirements.txt
   ```

4. **Veritabanı migration'larını kontrol edin** (genellikle gerekmez)
   ```bash
   python manage.py migrate
   ```

5. **Sunucuyu başlatın**
   ```bash
   python manage.py runserver
   ```

## Tam Yedekleme İçin Kopyalanması Gerekenler:

```
uretim_stok/
├── db.sqlite3          ✅ MUTLAKA
├── media/              ✅ MUTLAKA
├── stokapp/            ✅ MUTLAKA
├── stok_sistemi/       ✅ MUTLAKA
├── manage.py           ✅ MUTLAKA
├── requirements.txt    ✅ MUTLAKA
├── staticfiles/        ✅ (varsa)
└── stok_env/           ⚠️ Opsiyonel (yeniden oluşturulabilir)
```

## Hızlı Yedekleme Komutu (Linux/Mac):

```bash
# Tüm klasörü yedekle (virtual env hariç)
tar -czf yedek_$(date +%Y%m%d_%H%M%S).tar.gz \
  --exclude='stok_env' \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  uretim_stok/
```

## Windows için:

1. Klasöre sağ tıklayın
2. "Send to" > "Compressed (zipped) folder" seçin
3. Veya WinRAR/7-Zip ile sıkıştırın

## Sonuç:

✅ **EVET**, klasörü tamamen kopyaladığınızda hem program hem veriler yedeklenmiş olur.

✅ Geri yerine taşıdığınızda eski haline döner (virtual environment'ı yeniden oluşturmanız gerekebilir).

⚠️ **Önemli**: Virtual environment'ı kopyalamak yerine, sadece `requirements.txt` dosyasını kopyalayıp hedef sistemde yeniden oluşturmanız daha güvenlidir.

