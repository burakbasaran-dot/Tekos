# Üretim rolüne dış operasyon operasyonel yetkileri (0106 yalnızca görüntüleme vermişti).

from django.db import migrations

_KODLAR = [
    'dis_operasyon.ekle',
    'dis_operasyon.duzenle',
    'dis_operasyon.donus_al',
    'dis_operasyon.kalite_kontrol',
]


def forward(apps, schema_editor):
    Rol = apps.get_model('stokapp', 'Rol')
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')
    rol = Rol.objects.filter(slug='uretim').first()
    if not rol:
        return
    for kod in _KODLAR:
        y = SistemYetkisi.objects.filter(kod=kod).first()
        if y:
            RolYetkisi.objects.get_or_create(rol=rol, yetki=y)


def reverse(apps, schema_editor):
    Rol = apps.get_model('stokapp', 'Rol')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    rol = Rol.objects.filter(slug='uretim').first()
    if not rol:
        return
    y_ids = list(SistemYetkisi.objects.filter(kod__in=_KODLAR).values_list('id', flat=True))
    RolYetkisi.objects.filter(rol=rol, yetki_id__in=y_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0106_dis_operasyon_rbac_rol_baglantisi'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
