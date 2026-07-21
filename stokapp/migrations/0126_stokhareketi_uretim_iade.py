from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0125_genelayarlar_stok_tamamlanma_kurallari'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stokhareketi',
            name='hareket_tipi',
            field=models.CharField(
                choices=[
                    ('GIRIS', 'Stok Girişi'),
                    ('CIKIS', 'Stok Çıkışı'),
                    ('SATIS_STOK', 'Stoktan Satış Çıkışı'),
                    ('TRANSFER', 'Depo Transferi'),
                    ('SAYIM', 'Sayım Düzeltmesi'),
                    ('URETIM_GIRIS', 'Üretim Girişi'),
                    ('URETIM_CIKIS', 'Üretim Çıkışı'),
                    ('URETIM_IADE', 'Üretim İadesi'),
                    ('DISOP_GONDERIM', 'Dış Operasyon Gönderim'),
                    ('DISOP_DONUS', 'Dış Operasyon Dönüş'),
                    ('DISOP_FIRE', 'Dış Operasyon Fire'),
                    ('DISOP_RED', 'Dış Operasyon Red / Hurda'),
                    ('DISOP_EKSIK', 'Dış Operasyon Eksik'),
                    ('DISOP_TESLIM_KALITE', 'Dış Operasyon Teslim (Kalite Bekliyor)'),
                    ('DISOP_QC_KABUL', 'Dış Operasyon Kalite Kabul (Stoğa)'),
                ],
                max_length=22,
            ),
        ),
    ]
