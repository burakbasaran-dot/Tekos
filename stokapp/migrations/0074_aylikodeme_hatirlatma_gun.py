# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0073_aylikodeme_plan_uid"),
    ]

    operations = [
        migrations.AddField(
            model_name="aylikodeme",
            name="hatirlatma_gun_once",
            field=models.PositiveIntegerField(
                default=7,
                help_text="Ödeme tarihinden kaç gün önce hatırlatma ve vurgu başlasın (panel, liste).",
                verbose_name="Hatırlatma (gün önce)",
            ),
        ),
    ]
