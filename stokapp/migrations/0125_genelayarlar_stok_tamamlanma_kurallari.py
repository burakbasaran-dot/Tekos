from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0124_satinalma_kaynak_siparis_tekliftalebi_kaynak_siparis'),
    ]

    operations = [
        migrations.AddField(
            model_name='genelayarlar',
            name='stok_tamamlanma_kurallari',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Stok tipine göre tamamlanması beklenen alanlar (true=gerekli).',
                verbose_name='Stok Tamamlanma Kuralları',
            ),
        ),
    ]
