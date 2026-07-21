import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0077_teklif_models_ve_vergi'),
    ]

    operations = [
        migrations.CreateModel(
            name='MusteriIlgiliKisi',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ad_soyad', models.CharField(max_length=200, verbose_name='Adı Soyadı')),
                ('gorev', models.CharField(blank=True, max_length=120, verbose_name='Görevi')),
                ('telefon', models.CharField(blank=True, max_length=40, verbose_name='Telefon')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='E-posta')),
                ('ozel_not', models.TextField(blank=True, verbose_name='Özel not')),
                ('sira', models.PositiveSmallIntegerField(default=0, verbose_name='Sıra')),
                (
                    'musteri',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ilgili_kisiler',
                        to='stokapp.musteri',
                        verbose_name='Müşteri',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Müşteri ilgili kişi',
                'verbose_name_plural': 'Müşteri ilgili kişiler',
                'ordering': ['sira', 'id'],
            },
        ),
    ]
