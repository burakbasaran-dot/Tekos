import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0078_musteri_ilgili_kisi'),
    ]

    operations = [
        migrations.CreateModel(
            name='TedarikciIlgiliKisi',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ad_soyad', models.CharField(max_length=200, verbose_name='Adı Soyadı')),
                ('gorev', models.CharField(blank=True, max_length=120, verbose_name='Görevi')),
                ('telefon', models.CharField(blank=True, max_length=40, verbose_name='Telefon')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='E-posta')),
                ('ozel_not', models.TextField(blank=True, verbose_name='Özel not')),
                ('sira', models.PositiveSmallIntegerField(default=0, verbose_name='Sıra')),
                (
                    'tedarikci',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ilgili_kisiler',
                        to='stokapp.tedarikci',
                        verbose_name='Tedarikçi',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Tedarikçi ilgili kişi',
                'verbose_name_plural': 'Tedarikçi ilgili kişiler',
                'ordering': ['sira', 'id'],
            },
        ),
    ]
