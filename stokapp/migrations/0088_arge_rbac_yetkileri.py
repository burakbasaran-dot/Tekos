# Ar-Ge modülü RBAC kayıtları ve rol bağlantıları

from django.db import migrations

ARGE_KODLAR = [
    'arge.goruntule',
    'arge.ekle',
    'arge.duzenle',
    'arge.sil',
    'arge.arsivle',
]

_AD = {
    'arge.goruntule': 'Ar-Ge — Görüntüle',
    'arge.ekle': 'Ar-Ge — Ekle',
    'arge.duzenle': 'Ar-Ge — Düzenle',
    'arge.sil': 'Ar-Ge — Sil',
    'arge.arsivle': 'Ar-Ge — Arşivle',
}


def forwards(apps, schema_editor):
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    Rol = apps.get_model('stokapp', 'Rol')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')

    for kod in ARGE_KODLAR:
        SistemYetkisi.objects.get_or_create(
            kod=kod,
            defaults={'ad': _AD[kod], 'modul': 'arge'},
        )

    all_y = {y.kod: y for y in SistemYetkisi.objects.all()}

    def link_arge(rol, kodlar):
        for k in kodlar:
            y = all_y.get(k)
            if y:
                RolYetkisi.objects.get_or_create(rol=rol, yetki=y)

    for slug, kodlar in (
        ('admin', ARGE_KODLAR),
        ('yonetici', ARGE_KODLAR),
        ('uretim', ARGE_KODLAR),
        ('izleyici', ['arge.goruntule']),
    ):
        rol = Rol.objects.filter(slug=slug).first()
        if rol:
            link_arge(rol, kodlar)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0087_arge_proje_revizyon_dosya'),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
