from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0114_recete_dis_operasyon'),
    ]

    operations = [
        migrations.AddField(
            model_name='stokitem',
            name='urun_agirligi',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=14,
                null=True,
                verbose_name='Ürün / Bileşen Ağırlığı',
            ),
        ),
        migrations.AddField(
            model_name='stokitem',
            name='urun_agirlik_birimi',
            field=models.CharField(
                blank=True,
                choices=[('kg', 'kg'), ('g', 'g'), ('ton', 'ton'), ('mg', 'mg'), ('lb', 'lb')],
                default='kg',
                max_length=10,
                verbose_name='Ağırlık birimi',
            ),
        ),
    ]
