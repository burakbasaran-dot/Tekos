from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0128_aracbelgesidosya"),
    ]

    operations = [
        migrations.AddField(
            model_name="aracbelgesi",
            name="arsivlendi",
            field=models.BooleanField(default=False, verbose_name="Arşivlendi"),
        ),
        migrations.AddField(
            model_name="aracbelgesi",
            name="arsivlenme_tarihi",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Arşivlenme Tarihi"),
        ),
        migrations.AddField(
            model_name="aracbelgesi",
            name="onceki_belge",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="yenilemeler",
                to="stokapp.aracbelgesi",
                verbose_name="Önceki Belge",
            ),
        ),
    ]
