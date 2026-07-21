"""
RBAC: modül/eylem tanımları, URL→yetki eşlemesi (ilk aşama: stok, teklif, satin_alma).

Yeni modül: RBAC_MODULE_ACTIONS'a ekleyip `python manage.py sync_rbac_permissions` çalıştırın.
"""

from __future__ import annotations

# modül_kodu: { 'label': str, 'actions': [str, ...] }
RBAC_MODULE_ACTIONS: dict[str, dict] = {
    'stok': {
        'label': 'Stok',
        'actions': ['goruntule', 'ekle', 'duzenle', 'sil', 'arsivle'],
    },
    'teklif': {
        'label': 'Teklif',
        'actions': ['goruntule', 'ekle', 'duzenle', 'sil', 'onayla', 'arsivle'],
    },
    'satin_alma': {
        'label': 'Satınalma',
        'actions': ['goruntule', 'ekle', 'duzenle', 'sil', 'arsivle'],
    },
    'sistem': {
        'label': 'Sistem',
        'actions': ['yetkilendirme'],
    },
    'arge': {
        'label': 'Ar-Ge',
        'actions': ['goruntule', 'ekle', 'duzenle', 'sil', 'arsivle'],
    },
    'dis_operasyon': {
        'label': 'Dış Operasyonlar (modül kaldırıldı — yalnızca yetki kodları)',
        'actions': ['goruntule', 'ekle', 'duzenle', 'donus_al', 'kalite_kontrol', 'arsivle'],
    },
}


def iter_permission_codes():
    for mod, spec in RBAC_MODULE_ACTIONS.items():
        for act in spec['actions']:
            yield f'{mod}.{act}'


def human_label(mod: str, act: str) -> str:
    spec = RBAC_MODULE_ACTIONS.get(mod, {})
    mod_label = spec.get('label', mod)
    act_labels = {
        'goruntule': 'Görüntüle',
        'ekle': 'Ekle',
        'duzenle': 'Düzenle',
        'sil': 'Sil',
        'onayla': 'Onayla',
        'arsivle': 'Arşivle',
        'yetkilendirme': 'Yetkilendirme yönetimi',
        'donus_al': 'Dönüş al',
        'kalite_kontrol': 'Kalite kontrol',
    }
    return f'{mod_label} — {act_labels.get(act, act)}'


# url_name → gerekli yetki kodu (yalnızca kayıtlı rotalar kontrol edilir)
RBAC_URL_PERMISSIONS: dict[str, str] = {
    # --- Stok ---
    'stok_listesi': 'stok.goruntule',
    'stok_detay': 'stok.goruntule',
    'stok_ekle': 'stok.ekle',
    'stok_duzenle': 'stok.duzenle',
    'stok_sil': 'stok.sil',
    'stok_toplu_sil': 'stok.sil',
    'stok_giris': 'stok.duzenle',
    'stok_cikis': 'stok.duzenle',
    'stok_hareket_listesi': 'stok.goruntule',
    'stok_hareket_duzenle': 'stok.duzenle',
    'stok_hareket_sil': 'stok.sil',
    'stok_transfer': 'stok.duzenle',
    'stok_transfer_listesi': 'stok.goruntule',
    'stok_qrcode': 'stok.goruntule',
    'stok_kopyala': 'stok.ekle',
    'stok_recete_maliyetleri': 'stok.goruntule',
    'stok_etiket_yazdir': 'stok.goruntule',
    'stok_hizli_uretim_olustur': 'stok.duzenle',
    'stok_hareket_raporu': 'stok.goruntule',
    'stok_hareket_raporu_excel': 'stok.goruntule',
    'stok_hareket_raporu_pdf': 'stok.goruntule',
    'stok_listesi_export_excel': 'stok.goruntule',
    'stok_listesi_export_pdf': 'stok.goruntule',
    'stok_hareket_listesi_export_excel': 'stok.goruntule',
    'stok_hareket_listesi_export_pdf': 'stok.goruntule',
    'stok_sayim_listesi': 'stok.goruntule',
    'stok_sayim_baslat': 'stok.duzenle',
    'stok_sayim_basla': 'stok.duzenle',
    'stok_sayim_calis': 'stok.duzenle',
    'stok_sayim_rapor': 'stok.goruntule',
    'stok_sayim_rapor_excel': 'stok.goruntule',
    'stok_sayim_rapor_pdf': 'stok.goruntule',
    'stok_sayim_iptal': 'stok.duzenle',
    'stok_sayim_sil': 'stok.duzenle',
    'kritik_stok_raporu': 'stok.goruntule',
    'kritik_stok_raporu_excel': 'stok.goruntule',
    'kritik_stok_raporu_pdf': 'stok.goruntule',
    # --- Teklif ---
    'teklif_listesi': 'teklif.goruntule',
    'teklif_sartlari_onizle': 'teklif.goruntule',
    'teklif_ekle': 'teklif.ekle',
    'teklif_detay': 'teklif.goruntule',
    'teklif_pdf_indir': 'teklif.goruntule',
    'teklif_duzenle': 'teklif.duzenle',
    'teklif_sil': 'teklif.sil',
    'teklif_gonder': 'teklif.duzenle',
    'teklif_mail_alici_sec': 'teklif.duzenle',
    'teklif_mail_onay': 'teklif.duzenle',
    'teklif_onayla': 'teklif.onayla',
    'teklif_reddet': 'teklif.onayla',
    # --- Satınalma ---
    'satinalma_listesi': 'satin_alma.goruntule',
    'satinalma_ekle': 'satin_alma.ekle',
    'satinalma_detay': 'satin_alma.goruntule',
    'satinalma_items_api': 'satin_alma.goruntule',
    'satinalma_duzenle': 'satin_alma.duzenle',
    'satinalma_sil': 'satin_alma.sil',
    'satinalma_tamamini_teslim': 'satin_alma.duzenle',
    'satinalma_ksimi_teslim': 'satin_alma.duzenle',
    'satinalma_ksimi_teslim_modal': 'satin_alma.duzenle',
    'satinalma_detay_popup': 'satin_alma.goruntule',
    'satinalma_kismi_teslimat': 'satin_alma.duzenle',
    'satinalma_tam_teslimat': 'satin_alma.duzenle',
    'teklif_talep_formu': 'satin_alma.goruntule',
    'teklif_talep_formu_pdf': 'satin_alma.goruntule',
    'teklif_talep_formu_email': 'satin_alma.duzenle',
    'satinalma_mail_alici_sec': 'satin_alma.duzenle',
    'satinalma_mail_onay': 'satin_alma.duzenle',
    'teklif_formu_teknik_resim_isle': 'satin_alma.duzenle',
    'teklif_girisi': 'satin_alma.duzenle',
    # --- Ar-Ge ---
    'arge_proje_listesi': 'arge.goruntule',
    'arge_proje_detay': 'arge.goruntule',
    'arge_proje_ekle': 'arge.ekle',
    'arge_proje_duzenle': 'arge.duzenle',
    'arge_proje_arsivle': 'arge.arsivle',
    'arge_revizyon_listesi': 'arge.goruntule',
    'arge_revizyon_ekle': 'arge.ekle',
    'arge_revizyon_duzenle': 'arge.duzenle',
    'arge_revizyon_sil': 'arge.sil',
    'arge_dosya_listesi': 'arge.goruntule',
    'arge_dosya_ekle': 'arge.ekle',
    'arge_dosya_indir': 'arge.goruntule',
    'arge_dosya_sil': 'arge.sil',
    'arge_asama_yakinda': 'arge.goruntule',
    # --- Dış Operasyonlar (TEKOS menü/URL kapatıldı; kodlar mevcut roller için kalabilir) ---
}

# Yetkilendirme paneli URL'leri (views_yetkilendirme)
RBAC_ADMIN_URL_NAMES = frozenset(
    {
        'yetkilendirme_roller',
        'yetkilendirme_rol_ekle',
        'yetkilendirme_rol_duzenle',
        'yetkilendirme_rol_sil',
        'yetkilendirme_kullanicilar',
        'yetkilendirme_kullanici_roller',
        'yetkilendirme_yetkiler',
    }
)

for _name in RBAC_ADMIN_URL_NAMES:
    RBAC_URL_PERMISSIONS[_name] = 'sistem.yetkilendirme'
