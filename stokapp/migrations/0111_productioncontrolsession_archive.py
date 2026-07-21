from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0110_uretim_kontrol_modulu'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='productioncontrolsession',
            name='is_archived',
            field=models.BooleanField(default=False, verbose_name='Arşivlendi'),
        ),
        migrations.AddField(
            model_name='productioncontrolsession',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Arşivlenme tarihi'),
        ),
        migrations.AddField(
            model_name='productioncontrolsession',
            name='archived_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='arsivledigi_uretim_kontrolleri',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Arşivleyen',
            ),
        ),
    ]
