from django.db import migrations, models
import django.db.models.deletion


def temizle_eski_operasyonlar(apps, schema_editor):
    ReceteOperasyon = apps.get_model("stokapp", "ReceteOperasyon")
    ReceteOperasyon.objects.all().delete()


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("stokapp", "0111_productioncontrolsession_archive"),
    ]

    operations = [
        migrations.RunPython(temizle_eski_operasyonlar, migrations.RunPython.noop),
        migrations.AddField(
            model_name="receteoperasyon",
            name="recete_detay",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="operasyonlar",
                to="stokapp.recetedetay",
                verbose_name="Reçete bileşeni",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="uretimasamasi",
            name="recete_detay",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uretim_asamalari",
                to="stokapp.recetedetay",
                verbose_name="Reçete bileşeni",
            ),
        ),
        migrations.AddField(
            model_name="uretimasamasi",
            name="recete_operasyon",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uretim_asamalari",
                to="stokapp.receteoperasyon",
                verbose_name="Reçete operasyonu",
            ),
        ),
    ]
