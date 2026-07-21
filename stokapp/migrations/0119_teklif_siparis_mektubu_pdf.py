from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0118_cnc_dosya_agaci_makina_tabs'),
    ]

    operations = [
        migrations.AddField(
            model_name='siparis',
            name='siparis_mektubu',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='siparis_mektuplari/%Y/%m/',
                verbose_name='Sipariş mektubu (PDF)',
            ),
        ),
        migrations.AddField(
            model_name='teklif',
            name='siparis_mektubu',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='teklif_siparis_mektuplari/%Y/%m/',
                verbose_name='Sipariş mektubu (PDF)',
            ),
        ),
    ]
