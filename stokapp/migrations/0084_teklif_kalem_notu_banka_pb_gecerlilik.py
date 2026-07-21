# Generated manually for teklif kalem notu, banka para birimi, teklif banka seçimi.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0083_teklif_satir_para_ve_ad_opsiyonel'),
    ]

    operations = [
        migrations.AddField(
            model_name='teklifkalemi',
            name='satir_notu',
            field=models.TextField(blank=True, verbose_name='Satır notu'),
        ),
        migrations.AddField(
            model_name='bankahesabi',
            name='para_birimi',
            field=models.CharField(
                choices=[
                    ('TL', 'Türk Lirası (₺)'),
                    ('USD', 'Amerikan Doları ($)'),
                    ('EUR', 'Euro (€)'),
                    ('GBP', 'İngiliz Sterlini (£)'),
                ],
                default='TL',
                max_length=3,
                verbose_name='Hesap para birimi',
            ),
        ),
        migrations.AddField(
            model_name='teklif',
            name='teklif_banka_hesap_ids',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='PDF/teklif özeti için sıralı banka hesabı pk listesi.',
                verbose_name='Seçili banka hesabı kimlikleri',
            ),
        ),
    ]
