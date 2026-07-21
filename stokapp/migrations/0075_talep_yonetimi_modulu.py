# Generated manually — Talep Yönetimi modülü

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("stokapp", "0074_aylikodeme_hatirlatma_gun"),
    ]

    operations = [
        migrations.CreateModel(
            name="Talep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("talep_no", models.CharField(editable=False, max_length=40, unique=True, verbose_name="Talep No")),
                ("talep_tarihi", models.DateField(verbose_name="Talep Tarihi")),
                ("departman", models.CharField(blank=True, max_length=200, verbose_name="Departman / Bölüm")),
                (
                    "kategori",
                    models.CharField(
                        choices=[
                            ("SARF", "Sarf Malzemesi"),
                            ("URETIM_MALZ", "Üretim Malzemesi"),
                            ("BAKIM_ONARIM", "Bakım / Onarım"),
                            ("EKIPMAN", "Ekipman"),
                            ("OFIS", "Ofis Malzemesi"),
                            ("HIZMET", "Hizmet"),
                            ("YEDEK_PARCA", "Yedek Parça"),
                            ("DIGER", "Diğer"),
                        ],
                        default="DIGER",
                        max_length=20,
                        verbose_name="Kategori",
                    ),
                ),
                ("baslik", models.CharField(max_length=500, verbose_name="Talep Başlığı")),
                (
                    "oncelik",
                    models.CharField(
                        choices=[
                            ("DUSUK", "Düşük"),
                            ("NORMAL", "Normal"),
                            ("ACIL", "Acil"),
                            ("KRITIK", "Kritik"),
                        ],
                        default="NORMAL",
                        max_length=20,
                        verbose_name="Öncelik",
                    ),
                ),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("YENI", "Yeni Talep"),
                            ("INCELEMEDE", "İncelemede"),
                            ("ONAYLANDI", "Onaylandı"),
                            ("SATINALMAYA_AKTARILDI", "Satınalmaya Aktarıldı"),
                            ("SIPARIS_VERILDI", "Sipariş Verildi"),
                            ("KISMEN_KARSILANDI", "Kısmen Karşılandı"),
                            ("TAMAMLANDI", "Tamamlandı"),
                            ("REDDEDILDI", "Reddedildi"),
                            ("IPTAL", "İptal Edildi"),
                        ],
                        default="YENI",
                        max_length=30,
                        verbose_name="Durum",
                    ),
                ),
                ("istenen_termin", models.DateField(blank=True, null=True, verbose_name="İstenen Termin Tarihi")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama / İhtiyaç Nedeni")),
                ("arsivlendi", models.BooleanField(default=False, verbose_name="Arşivlendi")),
                (
                    "kapanis_tipi",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("TAMAMLANDI", "Tamamlandı"),
                            ("KISMEN", "Kısmen karşılandı"),
                            ("RED", "Reddedildi"),
                            ("IPTAL", "İptal"),
                        ],
                        max_length=20,
                        verbose_name="Kapanış Tipi",
                    ),
                ),
                (
                    "gerceklesen_toplam_tutar",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=14, null=True, verbose_name="Gerçekleşen Toplam Tutar"
                    ),
                ),
                ("fatura_no", models.CharField(blank=True, max_length=120, verbose_name="Fatura No")),
                ("irsaliye_no", models.CharField(blank=True, max_length=120, verbose_name="İrsaliye No")),
                ("alim_tarihi", models.DateField(blank=True, null=True, verbose_name="Alım Tarihi")),
                ("teslim_alan_kisi", models.CharField(blank=True, max_length=200, verbose_name="Teslim Alan Kişi")),
                ("kapanis_notu", models.TextField(blank=True, verbose_name="Kapanış Notu")),
                ("kapanis_tarihi", models.DateTimeField(blank=True, null=True, verbose_name="Kapanış Tarihi")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kapanis_tedarikci",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="talep_kapanislari",
                        to="stokapp.tedarikci",
                        verbose_name="Satın Alınan Firma / Tedarikçi",
                    ),
                ),
                (
                    "satinalma",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kaynak_talepler",
                        to="stokapp.satinalma",
                        verbose_name="Bağlı Satın Alma",
                    ),
                ),
                (
                    "talep_eden",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="talepler",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Talep Eden",
                    ),
                ),
            ],
            options={
                "verbose_name": "Satın Alma Talebi",
                "verbose_name_plural": "Satın Alma Talepleri",
                "ordering": ["-talep_tarihi", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="TalepKalemi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kalem_adi", models.CharField(max_length=300, verbose_name="Kalem Adı")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("miktar", models.DecimalField(decimal_places=3, default=1, max_digits=12, verbose_name="Miktar")),
                ("marka_model_tercihi", models.CharField(blank=True, max_length=300, verbose_name="Marka / Model Tercihi")),
                (
                    "tahmini_birim_fiyat",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Tahmini Birim Fiyat"
                    ),
                ),
                ("kullanim_yeri", models.CharField(blank=True, max_length=200, verbose_name="Kullanım Yeri")),
                ("not_text", models.TextField(blank=True, verbose_name="Not")),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("BEKLIYOR", "Bekliyor"),
                            ("ONAYLANDI", "Onaylandı"),
                            ("ALINDI", "Alındı"),
                            ("REDDEDILDI", "Reddedildi"),
                            ("IPTAL", "İptal"),
                        ],
                        default="BEKLIYOR",
                        max_length=20,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "stok_cikis_planlanan_miktar",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        help_text="Stok düşümü ileride kayıt altına alınacak; şimdilik planlama alanı.",
                        max_digits=12,
                        null=True,
                        verbose_name="Stoktan düşülecek miktar (plan)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "birim",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="stokapp.birim",
                        verbose_name="Birim",
                    ),
                ),
                (
                    "para_birimi",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="stokapp.parabirimi",
                        verbose_name="Para Birimi",
                    ),
                ),
                (
                    "stok_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="stokapp.stokitem",
                        verbose_name="Stok Kartı (opsiyonel)",
                    ),
                ),
                (
                    "talep",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kalemler",
                        to="stokapp.talep",
                        verbose_name="Talep",
                    ),
                ),
            ],
            options={
                "verbose_name": "Talep Kalemi",
                "verbose_name_plural": "Talep Kalemleri",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="TalepDosya",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dosya", models.FileField(upload_to="talep_dosyalari/%Y/%m/", verbose_name="Dosya")),
                ("aciklama", models.CharField(blank=True, max_length=300, verbose_name="Açıklama")),
                (
                    "tip",
                    models.CharField(
                        choices=[
                            ("TALEP", "Talep eki"),
                            ("KAPANIS", "Kapanış belgesi"),
                            ("DIGER", "Diğer"),
                        ],
                        default="TALEP",
                        max_length=20,
                        verbose_name="Tip",
                    ),
                ),
                ("yuklenme_zamani", models.DateTimeField(auto_now_add=True)),
                (
                    "talep",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dosyalar",
                        to="stokapp.talep",
                        verbose_name="Talep",
                    ),
                ),
                (
                    "yukleyen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="talep_dosyalari",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Talep Dosyası",
                "verbose_name_plural": "Talep Dosyaları",
                "ordering": ["-yuklenme_zamani"],
            },
        ),
        migrations.CreateModel(
            name="TalepGecmisi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("olay", models.CharField(max_length=80, verbose_name="Olay")),
                ("eski_durum", models.CharField(blank=True, max_length=30)),
                ("yeni_durum", models.CharField(blank=True, max_length=30)),
                ("mesaj", models.TextField(blank=True)),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "kullanici",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "talep",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gecmis",
                        to="stokapp.talep",
                        verbose_name="Talep",
                    ),
                ),
            ],
            options={
                "verbose_name": "Talep Geçmişi",
                "verbose_name_plural": "Talep Geçmişi",
                "ordering": ["-olusturulma"],
            },
        ),
        migrations.CreateModel(
            name="TalepSatinalmaBilgisi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("teklif_alindi", models.BooleanField(default=False, verbose_name="Teklif Alındı mı?")),
                ("siparis_verildi", models.BooleanField(default=False, verbose_name="Sipariş Verildi mi?")),
                (
                    "alim_yontemi",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("FIRMA_SIPARIS", "Firmaya sipariş verildi"),
                            ("ELDEN", "Elden / dışarıdan alındı"),
                            ("STOKTAN", "Stoktan karşılandı"),
                            ("IPTAL", "İptal edildi"),
                        ],
                        max_length=20,
                        verbose_name="Alım Yöntemi",
                    ),
                ),
                ("notlar", models.TextField(blank=True, verbose_name="Satınalma Notları")),
                ("aktarilma_zamani", models.DateTimeField(blank=True, null=True, verbose_name="Satınalmaya Aktarılma Zamanı")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "satinalma_sorumlusu",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sorumlu_oldugu_talepler",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Satınalma Sorumlusu",
                    ),
                ),
                (
                    "tedarikci",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="stokapp.tedarikci",
                        verbose_name="Tedarikçi",
                    ),
                ),
                (
                    "talep",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="satinalma_bilgi",
                        to="stokapp.talep",
                        verbose_name="Talep",
                    ),
                ),
            ],
            options={
                "verbose_name": "Talep Satınalma Bilgisi",
                "verbose_name_plural": "Talep Satınalma Bilgileri",
            },
        ),
    ]
