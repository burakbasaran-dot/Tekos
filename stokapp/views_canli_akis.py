"""
Canlı Üretim Akış Haritası — açık iş emirleri, istasyon sütunları, JSON API.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .nav_visibility import NAV_KEY_URETIM_CANLI_AKIS, hidden_nav_access_required
from .models import (
    DisOperasyon,
    Istasyon,
    Operasyon,
    ReceteOperasyon,
    UretimAsamaNot,
    UretimAsamasi,
    UretimEmri,
)


def _siparis_no_from_aciklama(aciklama: str) -> str | None:
    if not aciklama:
        return None
    m = re.search(r'Sipariş\s+([A-Za-z0-9\-_/]+)\s+için', aciklama, re.IGNORECASE)
    return m.group(1) if m else None


def _istasyon_emoji(ad: str, saved: str) -> str:
    if saved and saved.strip():
        return saved.strip()[:16]
    a = (ad or '').lower()
    pairs = [
        ('lazer', '⚡'),
        ('torna', '🔩'),
        ('freze', '🌀'),
        ('kılavuz', '🪛'),
        ('kilavuz', '🪛'),
        ('galvaniz', '🧪'),
        ('boya', '🎨'),
        ('kauçuk', '🛞'),
        ('kaucuk', '🛞'),
        ('montaj', '🧰'),
        ('kalite', '✅'),
        ('sevk', '🚚'),
        ('sevkiyat', '📦'),
        ('ham', '📦'),
        ('kaynak', '🔥'),
        ('büküm', '↩️'),
        ('bukum', '↩️'),
        ('havşa', '🪛'),
        ('havsa', '🪛'),
        ('cnc', '⚙️'),
    ]
    for k, e in pairs:
        if k in a:
            return e
    return '🏭'


def _recete_op_for_asama(emir: UretimEmri, asama: UretimAsamasi, cache: dict[int, list[ReceteOperasyon]]) -> ReceteOperasyon | None:
    lst = cache.get(emir.recete_id)
    if lst is None:
        lst = list(
            ReceteOperasyon.objects.filter(recete_id=emir.recete_id)
            .select_related('operasyon', 'istasyon')
            .order_by('sira', 'id')
        )
        cache[emir.recete_id] = lst
    by_sira = {op.sira: op for op in lst}
    ro = by_sira.get(asama.sira)
    if ro:
        return ro
    for op in lst:
        if op.operasyon and op.operasyon.ad.strip().lower() == (asama.ad or '').strip().lower():
            return op
    return None


def _current_asama(emir: UretimEmri) -> UretimAsamasi | None:
    for a in emir.asamalar.all():
        if a.durum != 'TAMAMLANDI':
            return a
    return emir.asamalar.order_by('-sira').first()


def _dis_active_qs():
    return DisOperasyon.objects.filter(arsivli=False).exclude(
        durum__in=['IPTAL', 'ARSIV', 'TASLAK', 'TAMAMLANDI']
    )


def _dis_matches_istasyon(dis: DisOperasyon, ist: Istasyon) -> bool:
    if not ist.akis_tip_dis:
        return False
    a = ist.ad.strip().lower()
    tip = (dis.operasyon_tipi.ad or '').strip().lower()
    kod = (dis.operasyon_tipi.operasyon_kodu or '').strip().lower()
    return tip in a or a in tip or kod in a or a in kod


def _pick_dis_for_emir(emir: UretimEmri, asama: UretimAsamasi, ro: ReceteOperasyon | None, dis_list: list[DisOperasyon]):
    """İş emrine ve mevcut aşamaya uygun açık dış operasyon kaydı (varsa)."""
    if not ro or not getattr(ro.operasyon, 'akis_dis_operasyon', False):
        return None
    aad = (asama.ad or '').strip().lower()
    for d in dis_list:
        if d.uretim_emri_id != emir.id:
            continue
        tip_ad = (d.operasyon_tipi.ad or '').strip().lower()
        tip_kod = (d.operasyon_tipi.operasyon_kodu or '').strip().lower()
        if tip_ad and (tip_ad in aad or aad in tip_ad):
            return d
        if tip_kod and tip_kod in aad:
            return d
    for d in dis_list:
        if d.uretim_emri_id == emir.id and d.stok_item_id == emir.recete.urun_id:
            return d
    return None


def _dis_variant(dis: DisOperasyon | None, asama: UretimAsamasi) -> str:
    """Kart renk sınıfı: dis_hazir | dis_disarda | dis_gecikti"""
    if not dis:
        return 'dis_hazir'
    today = date.today()
    gecikti = bool(dis.beklenen_donus_tarihi and dis.beklenen_donus_tarihi < today and dis.durum not in ('TAMAMLANDI', 'IPTAL', 'ARSIV'))
    if gecikti:
        return 'dis_gecikti'
    if dis.durum in ('TEDARIKCIDE', 'GONDERILDI', 'KISMI_DONUS', 'KALITE_BEKLIYOR', 'REDDEDILDI'):
        return 'dis_disarda'
    return 'dis_hazir'


def _internal_variant(asama: UretimAsamasi, emir: UretimEmri) -> str:
    if asama.durum == 'SORUNLU':
        return 'sorunlu'
    if asama.durum == 'DEVAM_EDIYOR':
        return 'isleniyor'
    if asama.durum == 'BEKLEMEDE':
        return 'beklemede'
    if asama.durum == 'TAMAMLANDI':
        return 'tamamlandi'
    if asama.durum == 'BEKLIYOR' and emir.planlanan_bitis and timezone.now() > emir.planlanan_bitis and emir.durum == 'BASLADI':
        return 'gecikti'
    return 'bekliyor'


def _build_card(
    emir: UretimEmri,
    asama: UretimAsamasi,
    ro: ReceteOperasyon | None,
    dis: DisOperasyon | None,
    dis_variant: str | None,
) -> dict:
    urun = emir.recete.urun
    plan_bit = emir.planlanan_bitis.isoformat() if emir.planlanan_bitis else None
    gecikme = bool(emir.planlanan_bitis and timezone.now() > emir.planlanan_bitis and emir.durum == 'BASLADI')

    if ro and ro.operasyon and ro.operasyon.akis_dis_operasyon:
        if dis:
            variant = dis_variant or _dis_variant(dis, asama)
            durum_label = {
                'dis_hazir': 'Dış operasyona hazır',
                'dis_disarda': 'Dış operasyonda',
                'dis_gecikti': 'Dış operasyon — gecikti',
            }.get(variant, 'Dış operasyon')
        else:
            variant = 'dis_hazir'
            durum_label = 'Dış operasyona hazır'
    else:
        variant = _internal_variant(asama, emir)
        durum_label = {
            'bekliyor': 'Bekliyor',
            'isleniyor': 'İşleniyor',
            'beklemede': 'Beklemede',
            'tamamlandi': 'Tamamlandı',
            'sorunlu': 'Sorunlu',
            'gecikti': 'Gecikmiş',
        }.get(variant, asama.durum)

    dis_info = None
    if dis:
        today = date.today()
        gun = 0
        if dis.gonderim_tarihi:
            gun = max(0, (today - dis.gonderim_tarihi).days)
        gec = bool(dis.beklenen_donus_tarihi and dis.beklenen_donus_tarihi < today and dis.durum not in ('TAMAMLANDI', 'IPTAL', 'ARSIV'))
        dis_info = {
            'taseron': dis.tedarikci.ad if dis.tedarikci else '',
            'gonderim': dis.gonderim_tarihi.isoformat() if dis.gonderim_tarihi else None,
            'plan_donus': dis.beklenen_donus_tarihi.isoformat() if dis.beklenen_donus_tarihi else None,
            'gun_disarda': gun,
            'gecikti': gec,
            'operasyon_no': dis.operasyon_no,
            'durum': dis.durum,
        }

    return {
        'tip': 'is_emri',
        'emir_id': emir.id,
        'emir_no': emir.emir_no,
        'urun_kodu': urun.stok_kodu,
        'urun_ad': urun.ad,
        'miktar': str(emir.miktar),
        'birim': urun.birim,
        'asama_ad': asama.ad,
        'asama_id': asama.id,
        'asama_durum': asama.durum,
        'variant': variant,
        'durum_label': durum_label,
        'plan_bitis': plan_bit,
        'gecikme': gecikme,
        'dis_info': dis_info,
        'siparis_no': _siparis_no_from_aciklama(emir.aciklama or ''),
        'operasyon_id': ro.operasyon_id if ro else None,
        'operasyon_ad': ro.operasyon.ad if ro and ro.operasyon else None,
    }


def _build_dis_only_card(dis: DisOperasyon) -> dict:
    today = date.today()
    gun = max(0, (today - dis.gonderim_tarihi).days) if dis.gonderim_tarihi else 0
    gec = bool(dis.beklenen_donus_tarihi and dis.beklenen_donus_tarihi < today and dis.durum not in ('TAMAMLANDI', 'IPTAL', 'ARSIV'))
    variant = 'dis_gecikti' if gec else 'dis_disarda'
    urun = dis.stok_item
    return {
        'tip': 'dis_operasyon',
        'dis_id': dis.id,
        'emir_id': dis.uretim_emri_id,
        'emir_no': dis.uretim_emri.emir_no if dis.uretim_emri_id else None,
        'operasyon_no': dis.operasyon_no,
        'urun_kodu': urun.stok_kodu,
        'urun_ad': urun.ad,
        'miktar': str(dis.gonderilen_miktar),
        'birim': dis.birim,
        'asama_ad': dis.operasyon_tipi.ad,
        'asama_id': None,
        'asama_durum': dis.durum,
        'variant': variant,
        'durum_label': 'Dış operasyon kaydı',
        'plan_bitis': dis.beklenen_donus_tarihi.isoformat() if dis.beklenen_donus_tarihi else None,
        'gecikme': gec,
        'dis_info': {
            'taseron': dis.tedarikci.ad if dis.tedarikci else '',
            'gonderim': dis.gonderim_tarihi.isoformat() if dis.gonderim_tarihi else None,
            'plan_donus': dis.beklenen_donus_tarihi.isoformat() if dis.beklenen_donus_tarihi else None,
            'gun_disarda': gun,
            'gecikti': gec,
            'operasyon_no': dis.operasyon_no,
            'durum': dis.durum,
        },
        'siparis_no': None,
        'operasyon_id': None,
        'operasyon_ad': dis.operasyon_tipi.ad,
    }


def _emir_detail_payload(emir: UretimEmri) -> dict:
    asamalar = []
    for a in emir.asamalar.all().order_by('sira', 'id'):
        notlar = [
            {'tarih': n.created_at.isoformat(), 'metin': n.not_metni, 'olusturan': n.olusturan.username if n.olusturan else ''}
            for n in a.not_kayitlari.all().order_by('-created_at')[:20]
        ]
        asamalar.append(
            {
                'sira': a.sira,
                'ad': a.ad,
                'durum': a.durum,
                'baslama': a.baslama_zamani.isoformat() if a.baslama_zamani else None,
                'bitis': a.bitis_zamani.isoformat() if a.bitis_zamani else None,
                'planlanan_sure': a.planlanan_sure,
                'gerceklesen_sure': a.gerceklesen_sure,
                'notlar': notlar,
            }
        )
    return {
        'emir_id': emir.id,
        'emir_no': emir.emir_no,
        'durum': emir.durum,
        'urun_kodu': emir.recete.urun.stok_kodu,
        'urun_ad': emir.recete.urun.ad,
        'miktar': str(emir.miktar),
        'plan_bitis': emir.planlanan_bitis.isoformat() if emir.planlanan_bitis else None,
        'asamalar': asamalar,
        'detay_url': f'/stok/uretim/emir/{emir.id}/',
    }


def _filtered_emirler(request_get: dict):
    qs = (
        UretimEmri.objects.filter(durum__in=['PLANLANDI', 'BASLADI'])
        .select_related('recete__urun')
        .prefetch_related(
            Prefetch(
                'asamalar',
                queryset=UretimAsamasi.objects.order_by('sira', 'id').prefetch_related(
                    Prefetch('not_kayitlari', queryset=UretimAsamaNot.objects.select_related('olusturan').order_by('-created_at'))
                ),
            )
        )
        .order_by('-created_at')[:250]
    )

    q_emir = (request_get.get('emir_no') or '').strip()
    q_urun = (request_get.get('urun_kodu') or '').strip()
    q_must = (request_get.get('musteri') or '').strip()
    op_id = request_get.get('operasyon_id')
    sadece_gec = request_get.get('sadece_geciken') == '1'
    sadece_dis = request_get.get('sadece_dis') == '1'

    if q_emir:
        qs = qs.filter(emir_no__icontains=q_emir)
    if q_urun:
        qs = qs.filter(Q(recete__urun__stok_kodu__icontains=q_urun) | Q(recete__urun__ad__icontains=q_urun))
    if q_must:
        qs = qs.filter(Q(aciklama__icontains=q_must))
    emirler = list(qs)
    if op_id and str(op_id).isdigit():
        oid = int(op_id)
        filtered = []
        for em in emirler:
            ca = _current_asama(em)
            if not ca:
                continue
            cache: dict[int, list] = {}
            ro = _recete_op_for_asama(em, ca, cache)
            if ro and ro.operasyon_id == oid:
                filtered.append(em)
        emirler = filtered
    if sadece_gec:
        now = timezone.now()
        emirler = [e for e in emirler if e.planlanan_bitis and now > e.planlanan_bitis and e.durum == 'BASLADI']
    if sadece_dis:
        cache: dict[int, list] = {}
        filt = []
        for e in emirler:
            ca = _current_asama(e)
            if not ca:
                continue
            ro = _recete_op_for_asama(e, ca, cache)
            if ro and ro.operasyon and ro.operasyon.akis_dis_operasyon:
                filt.append(e)
        emirler = filt
    return emirler


def build_canli_akis_payload(request_get: dict) -> dict:
    emirler = _filtered_emirler(request_get)
    dis_open = list(
        _dis_active_qs()
        .select_related('tedarikci', 'operasyon_tipi', 'stok_item', 'uretim_emri')
        .order_by('-created_at')[:200]
    )
    dis_by_emir = defaultdict(list)
    for d in dis_open:
        if d.uretim_emri_id:
            dis_by_emir[d.uretim_emri_id].append(d)

    istasyonlar_db = list(Istasyon.objects.filter(aktif=True, akis_harita_goster=True).order_by('sira', 'ad'))
    stations: dict[int | str, dict] = {}

    def ensure_st(st: Istasyon | None, key: str | int, ad: str, emoji: str, kisa: str, tip_dis: bool):
        if key not in stations:
            stations[key] = {
                'id': key if isinstance(key, int) else str(key),
                'db_id': st.pk if st else None,
                'ad': ad,
                'emoji': emoji,
                'kisa_aciklama': kisa,
                'akis_tip_dis': tip_dis,
                'bekleyen': 0,
                'isleniyor': 0,
                'dis_disarda': 0,
                'geciken': 0,
                'kartlar': [],
            }

    for st in istasyonlar_db:
        emoji = _istasyon_emoji(st.ad, st.akis_harita_emoji or '')
        kisa = (st.akis_harita_kisa_aciklama or st.aciklama or '')[:200]
        ensure_st(st, st.id, st.ad, emoji, kisa, st.akis_tip_dis)

    ensure_st(None, 'unassigned', 'İstasyon atanmamış', '⚙️', 'Reçete adımında istasyon seçilmemiş', False)
    ensure_st(None, 'tamamlanan_adim', 'Tamamlanan / bekleyen kuyruk', '✅', 'Tüm iç adımlar bitmiş iş emirleri (sevkiyat öncesi)', False)

    ro_cache: dict[int, list] = {}

    for emir in emirler:
        asama = _current_asama(emir)
        if not asama:
            continue
        ro = _recete_op_for_asama(emir, asama, ro_cache)
        dis = _pick_dis_for_emir(emir, asama, ro, dis_by_emir.get(emir.id, []))
        dis_var = _dis_variant(dis, asama) if dis else None

        card = _build_card(emir, asama, ro, dis, dis_var)

        if asama.durum == 'TAMAMLANDI':
            st_key = 'tamamlanan_adim'
        elif ro and ro.istasyon_id:
            st_key = ro.istasyon_id
        else:
            st_key = 'unassigned'

        if st_key not in stations and isinstance(st_key, int):
            ensure_st(None, st_key, f'İstasyon #{st_key}', '🏭', '', False)

        st = stations[st_key]
        st['kartlar'].append(card)

        if card['variant'] in ('bekliyor', 'dis_hazir', 'gecikti'):
            st['bekleyen'] += 1
        elif card['variant'] in ('isleniyor', 'beklemede', 'sorunlu'):
            st['isleniyor'] += 1
        elif card['variant'] in ('dis_disarda', 'dis_gecikti'):
            st['dis_disarda'] += 1
        if card['variant'] in ('gecikti', 'sorunlu', 'dis_gecikti') or card.get('gecikme'):
            st['geciken'] += 1

    for st in istasyonlar_db:
        if not st.akis_tip_dis:
            continue
        for dis in dis_open:
            if dis.uretim_emri_id:
                continue
            if not _dis_matches_istasyon(dis, st):
                continue
            c = _build_dis_only_card(dis)
            stations[st.id]['kartlar'].append(c)
            stations[st.id]['dis_disarda'] += 1
            if c['variant'] == 'dis_gecikti':
                stations[st.id]['geciken'] += 1

    orphan_dis = [d for d in dis_open if not d.uretim_emri_id and not any(_dis_matches_istasyon(d, s) for s in istasyonlar_db if s.akis_tip_dis)]
    if orphan_dis:
        ensure_st(None, 'dis_orphan', 'Dış operasyonlar', '🌐', 'İş emrine bağlı olmayan açık dış operasyonlar', True)
        for dis in orphan_dis:
            oc = _build_dis_only_card(dis)
            stations['dis_orphan']['kartlar'].append(oc)
            stations['dis_orphan']['dis_disarda'] += 1
            if oc['variant'] == 'dis_gecikti':
                stations['dis_orphan']['geciken'] += 1

    seen_db = {s.id for s in istasyonlar_db}
    st_list = [stations[s.id] for s in istasyonlar_db]
    for sid in sorted(k for k in stations if isinstance(k, int) and k not in seen_db):
        st_list.append(stations[sid])
    for k in ('unassigned', 'tamamlanan_adim', 'dis_orphan'):
        if k in stations and stations[k]['kartlar']:
            st_list.append(stations[k])

    ozet = {'toplam_acik': len(emirler), 'isleniyor': 0, 'bekleyen': 0, 'dis_disarda': 0, 'geciken': 0}
    for emir in emirler:
        asama = _current_asama(emir)
        if not asama:
            continue
        ro = _recete_op_for_asama(emir, asama, ro_cache)
        dis = _pick_dis_for_emir(emir, asama, ro, dis_by_emir.get(emir.id, []))
        dvr = _dis_variant(dis, asama) if dis else None
        card = _build_card(emir, asama, ro, dis, dvr)
        v = card['variant']
        if v in ('isleniyor', 'beklemede', 'sorunlu'):
            ozet['isleniyor'] += 1
        elif v in ('bekliyor', 'dis_hazir', 'gecikti'):
            ozet['bekleyen'] += 1
        elif v in ('dis_disarda', 'dis_gecikti'):
            ozet['dis_disarda'] += 1
        if v in ('gecikti', 'sorunlu', 'dis_gecikti') or card.get('gecikme'):
            ozet['geciken'] += 1
    operasyonlar = [{'id': o.id, 'ad': o.ad} for o in Operasyon.objects.filter(aktif=True).order_by('sira', 'ad')]

    return {
        'istasyonlar': st_list,
        'ozet': ozet,
        'filtre': dict(request_get),
        'operasyonlar': operasyonlar,
    }


@login_required
@hidden_nav_access_required(NAV_KEY_URETIM_CANLI_AKIS)
@require_GET
def canli_akis_haritasi(request):
    return render(
        request,
        'stokapp/canli_akis_haritasi.html',
        {
            'api_canli_akis_url': reverse('stokapp:api_canli_akis_haritasi'),
            'api_canli_akis_detay_tpl': reverse('stokapp:api_canli_akis_is_emri_detay', args=[0]).replace('/0/', '/__ID__/'),
        },
    )


@login_required
@hidden_nav_access_required(NAV_KEY_URETIM_CANLI_AKIS)
@require_GET
def api_canli_akis_haritasi(request):
    try:
        data = build_canli_akis_payload(request.GET)
        return JsonResponse({'success': True, **data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@hidden_nav_access_required(NAV_KEY_URETIM_CANLI_AKIS)
@require_GET
def api_canli_akis_is_emri_detay(request, pk):
    emir = get_object_or_404(
        UretimEmri.objects.select_related('recete__urun').prefetch_related(
            Prefetch(
                'asamalar',
                queryset=UretimAsamasi.objects.order_by('sira', 'id').prefetch_related(
                    Prefetch('not_kayitlari', queryset=UretimAsamaNot.objects.select_related('olusturan').order_by('-created_at'))
                ),
            )
        ),
        pk=pk,
    )
    return JsonResponse({'success': True, 'detay': _emir_detail_payload(emir)})
