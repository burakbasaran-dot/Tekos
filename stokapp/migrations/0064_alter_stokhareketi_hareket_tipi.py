from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0063_personelizin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stokhareketi",
            name="hareket_tipi",
            field=models.CharField(
                max_length=15,
                choices=[
                    ("GIRIS", "Stok Girişi"),
                    ("CIKIS", "Stok Çıkışı"),
                    ("SATIS_STOK", "Stoktan Satış Çıkışı"),
                    ("TRANSFER", "Depo Transferi"),
                    ("SAYIM", "Sayım Düzeltmesi"),
                    ("URETIM_GIRIS", "Üretim Girişi"),
                    ("URETIM_CIKIS", "Üretim Çıkışı"),
                ],
            ),
        ),
    ]
