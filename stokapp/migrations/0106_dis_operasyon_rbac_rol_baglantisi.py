# Yeni dış operasyon yetkilerini varsayılan rollere bağlar (mevcut kurulumlar için).

from django.db import migrations

_DIS_OP_KODLAR = [
    'dis_operasyon.goruntule',
    'dis_operasyon.ekle',
    'dis_operasyon.duzenle',
    'dis_operasyon.donus_al',
    'dis_operasyon.kalite_kontrol',
    'dis_operasyon.arsivle',
]


def forward(apps, schema_editor):
    Rol = apps.get_model('stokapp', 'Rol')
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')
    yetkiler = {y.kod: y for y in SistemYetkisi.objects.filter(kod__in=_DIS_OP_KODLAR)}
    for slug, kodlar in (
        ('yonetici', _DIS_OP_KODLAR),
        ('uretim', ['dis_operasyon.goruntule']),
        ('izleyici', ['dis_operasyon.goruntule']),
    ):
        rol = Rol.objects.filter(slug=slug).first()
        if not rol:
            continue
        for kod in kodlar:
            y = yetkiler.get(kod)
            if y:
                RolYetkisi.objects.get_or_create(rol=rol, yetki=y)


def reverse(apps, schema_editor):
    Rol = apps.get_model('stokapp', 'Rol')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    y_ids = list(SistemYetkisi.objects.filter(kod__in=_DIS_OP_KODLAR).values_list('id', flat=True))
    for slug in ('yonetici', 'uretim', 'izleyici'):
        rol = Rol.objects.filter(slug=slug).first()
        if rol and y_ids:
            RolYetkisi.objects.filter(rol=rol, yetki_id__in=y_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0105_dis_operasyon_modulu'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
