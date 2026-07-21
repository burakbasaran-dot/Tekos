# Generated manually for ara ürün alt iş emirleri

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0103_tekoramemoryembedding"),
    ]

    operations = [
        migrations.AddField(
            model_name="uretimemri",
            name="alt_emir_otomatik",
            field=models.BooleanField(
                default=False,
                help_text="Reçete eksikliği için sistem tarafından oluşturuldu.",
                verbose_name="Otomatik alt emir",
            ),
        ),
        migrations.AddField(
            model_name="uretimemri",
            name="ust_uretim_emri",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alt_emirler",
                to="stokapp.uretimemri",
                verbose_name="Üst iş emri",
                help_text="Siparişten otomatik oluşturulan ara ürün emrinde ana ürün emrine bağlantı.",
            ),
        ),
    ]
