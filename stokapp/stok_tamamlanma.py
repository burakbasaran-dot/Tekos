"""
Stok kartı tamamlanma kontrolü — kural tanımları, doluluk hesabı ve rapor verisi.
"""
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q

from .models import GenelAyarlar, Recete, StokItem

STOK_TIPLERI = ('HAM_MADDE', 'YARI_MAMUL', 'URUN')

STOK_TAMAMLANMA_ALANLARI = [
    {'key': 'fotograf', 'label': 'Ürün Fotoğrafı'},
    {'key': 'teknik_resim', 'label': 'Teknik Resim'},
    {'key': 'ek_dosya', 'label': 'Ek Dosya'},
    {'key': 'barkod', 'label': 'Barkod'},
    {'key': 'aciklama', 'label': 'Açıklama'},
    {'key': 'tedarikci', 'label': 'Tedarikçi'},
    {'key': 'depo', 'label': 'Depo'},
    {'key': 'raf', 'label': 'Raf'},
    {'key': 'alis_fiyati', 'label': 'Alış Fiyatı'},
    {'key': 'satis_fiyati', 'label': 'Satış Fiyatı'},
    {'key': 'urun_agirligi', 'label': 'Ürün Ağırlığı'},
    {'key': 'aktif_recete', 'label': 'Aktif Reçete', 'only_uretim': True},
]

VARSAYILAN_KURALLAR = {
    'HAM_MADDE': {
        'fotograf': False,
        'teknik_resim': False,
        'ek_dosya': False,
        'barkod': False,
        'aciklama': False,
        'tedarikci': True,
        'depo': False,
        'raf': False,
        'alis_fiyati': True,
        'satis_fiyati': False,
        'urun_agirligi': False,
        'aktif_recete': False,
    },
    'YARI_MAMUL': {
        'fotograf': False,
        'teknik_resim': True,
        'ek_dosya': False,
        'barkod': False,
        'aciklama': False,
        'tedarikci': True,
        'depo': False,
        'raf': False,
        'alis_fiyati': True,
        'satis_fiyati': False,
        'urun_agirligi': False,
        'aktif_recete': True,
    },
    'URUN': {
        'fotograf': True,
        'teknik_resim': True,
        'ek_dosya': False,
        'barkod': True,
        'aciklama': False,
        'tedarikci': True,
        'depo': False,
        'raf': False,
        'alis_fiyati': True,
        'satis_fiyati': True,
        'urun_agirligi': True,
        'aktif_recete': True,
    },
}


def alan_tanimlari_dict():
    return {a['key']: a for a in STOK_TAMAMLANMA_ALANLARI}


def get_stok_tamamlanma_kurallari():
    ayarlar = GenelAyarlar.get_ayarlar()
    kayitli = getattr(ayarlar, 'stok_tamamlanma_kurallari', None) or {}
    birlesik = {}
    for tip in STOK_TIPLERI:
        varsayilan = dict(VARSAYILAN_KURALLAR.get(tip, {}))
        if isinstance(kayitli.get(tip), dict):
            for alan in varsayilan:
                if alan in kayitli[tip]:
                    varsayilan[alan] = bool(kayitli[tip][alan])
        birlesik[tip] = varsayilan
    return birlesik


def kaydet_stok_tamamlanma_kurallari(post_data):
    """POST checkbox verisinden kuralları kaydeder."""
    kurallar = {}
    for tip in STOK_TIPLERI:
        tip_kurallari = {}
        for alan in STOK_TAMAMLANMA_ALANLARI:
            key = alan['key']
            field_name = f'kural_{tip}_{key}'
            tip_kurallari[key] = post_data.get(field_name) in ('1', 'on', 'true')
        kurallar[tip] = tip_kurallari
    ayarlar = GenelAyarlar.get_ayarlar()
    ayarlar.stok_tamamlanma_kurallari = kurallar
    ayarlar.save(update_fields=['stok_tamamlanma_kurallari', 'updated_at'])
    return kurallar


def stok_tipi_coz(stok_item):
    tip = stok_item.get_stok_tipi()
    if tip in STOK_TIPLERI:
        return tip
    return 'URUN'


def _urun_stok_takibi_acik(stok_item):
    """Ürün tipinde stok takibi açıksa depo/raf tamamlanmaya dahil edilir."""
    return stok_tipi_coz(stok_item) == 'URUN' and bool(stok_item.stok_takip)


def _urunu_uretiyoruz(stok_item):
    """Ürünü üretiyoruz modunda tedarikçi ve alış fiyatı uygulanmaz."""
    return (
        getattr(stok_item, 'urun_tipi', None) == 'URETIM'
        or getattr(stok_item, 'urun_rolu', None) == 'NIHAI_URUN'
    )


def alan_uygulanir_mi(stok_item, alan_key):
    if alan_key == 'aktif_recete':
        return stok_item.urun_tipi == 'URETIM'
    if _urunu_uretiyoruz(stok_item) and alan_key in ('tedarikci', 'alis_fiyati'):
        return False
    if alan_key in ('depo', 'raf'):
        return _urun_stok_takibi_acik(stok_item)
    return True


def alan_gerekli_mi(stok_item, alan_key, tip_kurallari):
    uygulanir = alan_uygulanir_mi(stok_item, alan_key)
    if not uygulanir:
        return False
    if alan_key in ('depo', 'raf'):
        return _urun_stok_takibi_acik(stok_item)
    return bool(tip_kurallari.get(alan_key, False))


def alan_dolu_mu(stok_item, alan_key, ek_dosya_sayisi=0, has_aktif_recete=False):
    if alan_key == 'fotograf':
        return bool(stok_item.fotograf)
    if alan_key == 'teknik_resim':
        return bool(stok_item.teknik_resim)
    if alan_key == 'ek_dosya':
        return ek_dosya_sayisi > 0
    if alan_key == 'barkod':
        return bool((stok_item.barkod or '').strip())
    if alan_key == 'aciklama':
        return bool((stok_item.aciklama or '').strip())
    if alan_key == 'tedarikci':
        return stok_item.tedarikci_id is not None
    if alan_key == 'depo':
        return stok_item.depo_id is not None
    if alan_key == 'raf':
        return stok_item.raf_id is not None
    if alan_key == 'alis_fiyati':
        return Decimal(str(stok_item.alis_fiyati or 0)) > 0
    if alan_key == 'satis_fiyati':
        return Decimal(str(stok_item.satis_fiyati or 0)) > 0
    if alan_key == 'urun_agirligi':
        return stok_item.urun_agirligi is not None and Decimal(str(stok_item.urun_agirligi)) > 0
    if alan_key == 'aktif_recete':
        return bool(has_aktif_recete)
    return False


def stok_tamamlanma_detay_for_item(stok_item):
    """Stok detay sayfası için tamamlanma özeti."""
    kurallar = get_stok_tamamlanma_kurallari()
    ek_dosya_sayisi = stok_item.ek_dosyalar.count() if hasattr(stok_item, 'ek_dosyalar') else 0
    has_aktif_recete = Recete.objects.filter(urun=stok_item, aktif=True).exists()
    durum = hesapla_stok_tamamlanma(
        stok_item,
        kurallar,
        ek_dosya_sayisi=ek_dosya_sayisi,
        has_aktif_recete=has_aktif_recete,
    )
    eksik_liste = [
        {'key': key, 'label': durum['alanlar'][key]['label']}
        for key in durum['eksik_keys']
    ]
    return durum, eksik_liste


def hesapla_stok_tamamlanma(stok_item, kurallar, ek_dosya_sayisi=0, has_aktif_recete=False):
    """
    Tek stok için tamamlanma durumu.
    Dönüş: {yuzde, tamam, alanlar: {key: {label, gerekli, dolu, uygulanir}}}
    """
    tip = stok_tipi_coz(stok_item)
    tip_kurallari = kurallar.get(tip, VARSAYILAN_KURALLAR.get(tip, {}))
    alanlar = {}
    gerekli_say = 0
    dolu_say = 0
    eksik_keys = []

    for tanim in STOK_TAMAMLANMA_ALANLARI:
        key = tanim['key']
        uygulanir = alan_uygulanir_mi(stok_item, key)
        gerekli = alan_gerekli_mi(stok_item, key, tip_kurallari)
        dolu = alan_dolu_mu(stok_item, key, ek_dosya_sayisi, has_aktif_recete)
        alanlar[key] = {
            'label': tanim['label'],
            'gerekli': gerekli,
            'dolu': dolu,
            'uygulanir': uygulanir,
        }
        if gerekli:
            gerekli_say += 1
            if dolu:
                dolu_say += 1
            else:
                eksik_keys.append(key)

    yuzde = int(round((dolu_say / gerekli_say) * 100)) if gerekli_say else 100
    return {
        'yuzde': yuzde,
        'tamam': gerekli_say > 0 and dolu_say == gerekli_say,
        'gerekli_say': gerekli_say,
        'dolu_say': dolu_say,
        'eksik_keys': eksik_keys,
        'alanlar': alanlar,
        'stok_tipi': tip,
    }


def _stok_tamamlanma_queryset():
    aktif_recete = Recete.objects.filter(urun_id=OuterRef('pk'), aktif=True)
    return (
        StokItem.objects.filter(arsivli=False)
        .select_related('kategori', 'tedarikci', 'depo', 'raf')
        .annotate(
            ek_dosya_sayisi=Count('ek_dosyalar'),
            has_aktif_recete=Exists(aktif_recete),
        )
        .order_by('stok_kodu')
    )


def stok_tamamlanma_rapor_verisi(request):
    """Filtrelenmiş rapor satırları ve özet istatistikler."""
    kurallar = get_stok_tamamlanma_kurallari()
    stok_tipi = request.GET.get('tip', 'TUMU')
    sadece_eksik = request.GET.get('sadece_eksik') in ('1', 'true', 'on')
    eksik_alan = (request.GET.get('eksik_alan') or '').strip()
    arama = (request.GET.get('q') or '').strip()
    sort = request.GET.get('sort', 'yuzde_asc')

    qs = _stok_tamamlanma_queryset()
    if stok_tipi != 'TUMU':
        qs = qs.filter(
            Q(stok_tipi=stok_tipi)
            | Q(stok_tipi__isnull=True, kategori__stok_tipi=stok_tipi)
        )
    if arama:
        qs = qs.filter(Q(stok_kodu__icontains=arama) | Q(ad__icontains=arama))

    aktif_alanlar = [a for a in STOK_TAMAMLANMA_ALANLARI]
    gosterilecek_alanlar = []
    for alan in aktif_alanlar:
        tip_listesi = [
            tip for tip in STOK_TIPLERI
            if kurallar.get(tip, {}).get(alan['key'], False)
        ]
        if tip_listesi:
            gosterilecek_alanlar.append({**alan, 'aktif_tipler': tip_listesi})

    satirlar = []
    alan_eksik_ozet = {a['key']: 0 for a in aktif_alanlar}

    for stok in qs:
        durum = hesapla_stok_tamamlanma(
            stok,
            kurallar,
            ek_dosya_sayisi=getattr(stok, 'ek_dosya_sayisi', 0),
            has_aktif_recete=getattr(stok, 'has_aktif_recete', False),
        )
        if sadece_eksik and durum['tamam']:
            continue
        if eksik_alan:
            alan_info = durum['alanlar'].get(eksik_alan)
            if not alan_info or not alan_info['gerekli'] or alan_info['dolu']:
                continue

        for key in durum['eksik_keys']:
            alan_eksik_ozet[key] = alan_eksik_ozet.get(key, 0) + 1

        alan_hucreleri = []
        for alan in gosterilecek_alanlar:
            info = durum['alanlar'].get(alan['key'], {})
            if info.get('gerekli'):
                durum_kod = 'var' if info.get('dolu') else 'eksik'
            else:
                durum_kod = 'opsiyonel'
            alan_hucreleri.append(durum_kod)

        satirlar.append({
            'stok': stok,
            'durum': durum,
            'alan_hucreleri': alan_hucreleri,
        })

    if sort == 'yuzde_desc':
        satirlar.sort(key=lambda x: (x['durum']['yuzde'], x['stok'].stok_kodu), reverse=True)
    elif sort == 'stok_kodu':
        satirlar.sort(key=lambda x: x['stok'].stok_kodu)
    else:
        satirlar.sort(key=lambda x: (x['durum']['yuzde'], x['stok'].stok_kodu))

    toplam = len(satirlar)
    tam_say = sum(1 for s in satirlar if s['durum']['tamam'])
    eksik_say = toplam - tam_say

    eksik_ozet_list = [
        {'label': next((a['label'] for a in aktif_alanlar if a['key'] == key), key), 'sayi': say}
        for key, say in alan_eksik_ozet.items()
        if say > 0
    ]
    eksik_ozet_list.sort(key=lambda x: -x['sayi'])

    return {
        'kurallar': kurallar,
        'satirlar': satirlar,
        'ozet': {
            'toplam': toplam,
            'tam': tam_say,
            'eksik': eksik_say,
            'tam_yuzde': int(round((tam_say / toplam) * 100)) if toplam else 0,
        },
        'alan_eksik_ozet': alan_eksik_ozet,
        'eksik_ozet_list': eksik_ozet_list,
        'gosterilecek_alanlar': gosterilecek_alanlar,
        'filtreler': {
            'tip': stok_tipi,
            'sadece_eksik': sadece_eksik,
            'eksik_alan': eksik_alan,
            'q': arama,
            'sort': sort,
        },
        'stok_tipleri': STOK_TIPLERI,
        'alan_tanimlari': STOK_TAMAMLANMA_ALANLARI,
    }
