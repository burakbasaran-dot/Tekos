from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0112_recete_operasyon_bilesen_agaci"),
    ]

    operations = [
        migrations.AlterField(
            model_name="receteoperasyon",
            name="recete_detay",
            field=models.ForeignKey(
                blank=True,
                help_text="Boş bırakılırsa operasyon Genel Operasyon altında listelenir.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="operasyonlar",
                to="stokapp.recetedetay",
                verbose_name="Reçete bileşeni",
            ),
        ),
    ]
