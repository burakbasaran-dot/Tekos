# TalepKalemi: stok ve tahmini fiyat alanlarının kaldırılması

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0075_talep_yonetimi_modulu"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="talepkalemi",
            name="para_birimi",
        ),
        migrations.RemoveField(
            model_name="talepkalemi",
            name="stok_cikis_planlanan_miktar",
        ),
        migrations.RemoveField(
            model_name="talepkalemi",
            name="stok_item",
        ),
        migrations.RemoveField(
            model_name="talepkalemi",
            name="tahmini_birim_fiyat",
        ),
    ]
