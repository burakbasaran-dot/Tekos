from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0061_uretimasamasi_duraklatma_toplam_saniye_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="uretimemri",
            name="production_type",
            field=models.CharField(
                choices=[("ORDER", "Sipariş"), ("STOCK", "Stok Üretimi")],
                default="ORDER",
                max_length=10,
            ),
        ),
    ]
