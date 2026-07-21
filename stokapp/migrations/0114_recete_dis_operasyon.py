from django.db import migrations, models
import django.db.models.deletion


def seed_dis_operasyon_tipleri_ekstra(apps, schema_editor):
    T = apps.get_model('stokapp', 'DisOperasyonTipi')
    seeds = [
        ('Galvaniz Kaplama', 'galvaniz_kaplama'),
        ('Boya İşlemi', 'boya_islemi'),
        ('Kumlama', 'kumlama'),
        ('Kaynak', 'kaynak'),
        ('Eloksal', 'eloksal'),
        ('Pasivasyon', 'pasivasyon'),
        ('Cilalama', 'cilalama'),
        ('Fason Torna', 'fason_torna'),
        ('Fason Freze', 'fason_freze'),
        ('Nikel Kaplama', 'nikel_kaplama'),
        ('Krom Kaplama', 'krom_kaplama'),
        ('Punch', 'punch'),
        ('Pres', 'pres'),
    ]
    for ad, kod in seeds:
        T.objects.get_or_create(
            operasyon_kodu=kod,
            defaults={'ad': ad, 'ic_dis_tipi': 'DIS', 'aktif': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0113_recete_operasyon_genel'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReceteDisOperasyon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dis_birim_fiyat', models.DecimalField(decimal_places=4, default=0, max_digits=14, verbose_name='Birim işlem fiyatı')),
                ('dis_para_birimi', models.CharField(choices=[('TL', 'Türk Lirası (₺)'), ('USD', 'Amerikan Doları ($)'), ('EUR', 'Euro (€)'), ('GBP', 'İngiliz Sterlini (£)')], default='TL', max_length=3, verbose_name='Para birimi')),
                ('dis_beklenen_donus_gun', models.PositiveSmallIntegerField(default=7, verbose_name='Beklenen dönüş (gün)')),
                ('aciklama', models.TextField(blank=True, verbose_name='Açıklama')),
                ('sira', models.IntegerField(default=0, verbose_name='Sıra')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dis_gonderim_deposu', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recete_dis_atama_gonderimleri', to='stokapp.depo', verbose_name='Gönderim deposu')),
                ('dis_operasyon_tipi', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recete_dis_atamalari', to='stokapp.disoperasyontipi', verbose_name='Dış operasyon tipi')),
                ('recete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dis_operasyon_atamalari', to='stokapp.recete')),
                ('recete_detay', models.ForeignKey(blank=True, help_text='Boş bırakılırsa ürün geneline atanır.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='dis_operasyon_atamalari', to='stokapp.recetedetay', verbose_name='Reçete bileşeni')),
                ('tedarikci', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recete_dis_atamalari', to='stokapp.tedarikci', verbose_name='Taşeron / tedarikçi')),
            ],
            options={
                'verbose_name': 'Reçete Dış Operasyonu',
                'verbose_name_plural': 'Reçete Dış Operasyonları',
                'ordering': ['recete_detay__sira', 'recete_detay_id', 'sira', 'id'],
            },
        ),
        migrations.RunPython(seed_dis_operasyon_tipleri_ekstra, migrations.RunPython.noop),
    ]
