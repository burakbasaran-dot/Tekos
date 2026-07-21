# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0047_hatalog_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stokitem',
            name='stok_tipi',
            field=models.CharField(blank=True, choices=[('HAM_MADDE', 'Ham Madde'), ('YARI_MAMUL', 'Yarı Mamül'), ('URUN', 'Ürün')], max_length=15, null=True, verbose_name='Stok Tipi'),
        ),
    ]

