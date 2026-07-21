from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0115_stokitem_urun_agirligi'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='siparis',
            name='siparis_unique_kaynak_teklif',
        ),
        migrations.AddField(
            model_name='sipariskalemi',
            name='kaynak_teklif_kalemi',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='siparis_kalemleri',
                to='stokapp.teklifkalemi',
                verbose_name='Kaynak teklif kalemi',
            ),
        ),
        migrations.AddConstraint(
            model_name='sipariskalemi',
            constraint=models.UniqueConstraint(
                condition=Q(kaynak_teklif_kalemi__isnull=False),
                fields=('kaynak_teklif_kalemi',),
                name='siparis_kalem_unique_kaynak_teklif_kalemi',
            ),
        ),
    ]
