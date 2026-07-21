from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0059_gelistirme_talebi"),
    ]

    operations = [
        migrations.AddField(
            model_name="siparis",
            name="red_nedeni",
            field=models.TextField(blank=True, verbose_name="Red Nedeni"),
        ),
        migrations.AddField(
            model_name="siparis",
            name="red_tarihi",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Red Tarihi"),
        ),
    ]
