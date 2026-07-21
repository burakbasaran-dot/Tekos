# Generated manually — varsayılan yetkiler, roller ve kullanıcı atamaları

from django.db import migrations

_MODS = {
    'stok': ['goruntule', 'ekle', 'duzenle', 'sil', 'arsivle'],
    'teklif': ['goruntule', 'ekle', 'duzenle', 'sil', 'onayla', 'arsivle'],
    'satin_alma': ['goruntule', 'ekle', 'duzenle', 'sil', 'arsivle'],
    'sistem': ['yetkilendirme'],
}
_ACT_LABEL = {
    'goruntule': 'Görüntüle',
    'ekle': 'Ekle',
    'duzenle': 'Düzenle',
    'sil': 'Sil',
    'onayla': 'Onayla',
    'arsivle': 'Arşivle',
    'yetkilendirme': 'Yetkilendirme yönetimi',
}
_MOD_LABEL = {'stok': 'Stok', 'teklif': 'Teklif', 'satin_alma': 'Satınalma', 'sistem': 'Sistem'}


def _perm_codes():
    for mod, acts in _MODS.items():
        for act in acts:
            yield f'{mod}.{act}'


def _human(mod, act):
    return f'{_MOD_LABEL.get(mod, mod)} — {_ACT_LABEL.get(act, act)}'


def seed_permissions(apps, schema_editor):
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    for kod in _perm_codes():
        mod = kod.split('.', 1)[0]
        act = kod.split('.', 1)[1]
        SistemYetkisi.objects.get_or_create(
            kod=kod,
            defaults={'ad': _human(mod, act), 'modul': mod},
        )


def seed_roles(apps, schema_editor):
    Rol = apps.get_model('stokapp', 'Rol')
    SistemYetkisi = apps.get_model('stokapp', 'SistemYetkisi')
    RolYetkisi = apps.get_model('stokapp', 'RolYetkisi')
    KullaniciRolu = apps.get_model('stokapp', 'KullaniciRolu')
    User = apps.get_model('auth', 'User')

    specs = [
        ('admin', 'Admin', 'Tüm yetkiler', 'all'),
        ('yonetici', 'Yönetici', 'Çoğu yetki; sistem yetkilendirmesi hariç', 'no_sistem_yetki'),
        ('uretim', 'Üretim', 'Stok görüntüleme', 'uretim_set'),
        ('satinalma', 'Satınalma', 'Satınalma + stok görüntüleme', 'satinalma_set'),
        ('satis', 'Satış', 'Teklif modülü', 'satis_set'),
        ('izleyici', 'İzleyici', 'Yalnızca görüntüleme', 'izleyici_set'),
    ]
    rol_by_slug = {}
    for slug, ad, aciklama, _ in specs:
        r, _ = Rol.objects.get_or_create(slug=slug, defaults={'ad': ad, 'aciklama': aciklama})
        if r.ad != ad or r.aciklama != aciklama:
            r.ad = ad
            r.aciklama = aciklama
            r.save(update_fields=['ad', 'aciklama'])
        rol_by_slug[slug] = r

    all_y = {y.kod: y for y in SistemYetkisi.objects.all()}

    def link(rol, kodlar):
        RolYetkisi.objects.filter(rol=rol).delete()
        for k in kodlar:
            y = all_y.get(k)
            if y:
                RolYetkisi.objects.get_or_create(rol=rol, yetki=y)

    all_codes = list(all_y.keys())
    link(rol_by_slug['admin'], all_codes)

    yon_codes = [c for c in all_codes if c != 'sistem.yetkilendirme']
    link(rol_by_slug['yonetici'], yon_codes)

    link(rol_by_slug['uretim'], [c for c in all_codes if c == 'stok.goruntule'])

    sat_set = ['stok.goruntule'] + [c for c in all_codes if c.startswith('satin_alma.')]
    link(rol_by_slug['satinalma'], sat_set)

    satis_set = [c for c in all_codes if c.startswith('teklif.')]
    link(rol_by_slug['satis'], satis_set)

    izl = [c for c in all_codes if c.endswith('.goruntule')]
    link(rol_by_slug['izleyici'], izl)

    for u in User.objects.all():
        KullaniciRolu.objects.filter(user=u).delete()
        if u.is_superuser:
            KullaniciRolu.objects.get_or_create(user=u, rol=rol_by_slug['admin'])
        else:
            KullaniciRolu.objects.get_or_create(user=u, rol=rol_by_slug['yonetici'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stokapp', '0085_rbac_models'),
    ]

    operations = [
        migrations.RunPython(seed_permissions, noop_reverse),
        migrations.RunPython(seed_roles, noop_reverse),
    ]
