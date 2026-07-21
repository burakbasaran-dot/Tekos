"""
Günlük Yönetim Paneli — özet API ve sayfa.

Faz 2 notları (genişletme):
- Bugünün işleri: sipariş/satınalma terminleri, üretim plan görevleri, talep istenen_termin.
- Yaklaşan yükümlülükler: araç/gayrimenkul belgeleri, ekipman kalibrasyon, AylikOdeme detay tablosu.
- Onay kalemleri: ONAYLANDI + satinalma boş (satınalmaya bekleyen); SIPARIS_VERILDI / KISMEN (kapatılmayı bekleyen).
"""

from __future__ import annotations

import datetime as dt
import logging
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import Satinalma, Siparis, StokItem, Talep, Teklif, UretimEmri

logger = logging.getLogger(__name__)

ROW_LIMIT = 50
TALEP_KAPALI = ('TAMAMLANDI', 'REDDEDILDI', 'IPTAL')


def _local_today():
    return timezone.localdate()


def _week_bounds(d):
    start = d - dt.timedelta(days=d.weekday())
    end = start + dt.timedelta(days=6)
    return start, end


def _month_bounds(d):
    start = d.replace(day=1)
    if d.month == 12:
        end = d.replace(day=31)
    else:
        next_month = d.replace(month=d.month + 1, day=1)
        end = next_month - dt.timedelta(days=1)
    return start, end


def _teklif_rows(qs, bugun: dt.date):
    rows = []
    for t in qs.select_related('musteri', 'olusturan')[:ROW_LIMIT]:
        taraf = ''
        if t.musteri:
            taraf = t.musteri.ad
        elif (t.musteri_adi or '').strip():
            taraf = t.musteri_adi.strip()
        else:
            taraf = '—'
        if t.olusturan_id:
            u = t.olusturan
            taraf += f' · {u.get_full_name() or u.username}'
        sinif = 'normal'
        if t.vade_tarihi and t.vade_tarihi < bugun and t.durum in ('draft', 'sent'):
            sinif = 'gecikti'
        elif t.vade_tarihi and t.vade_tarihi == bugun:
            sinif = 'yaklasiyor'
        rows.append(
            {
                'kayit_no': t.teklif_no,
                'aciklama': (t.ad or '').strip() or t.teklif_no,
                'taraf': taraf,
                'tarih': t.duzenleme_tarihi.isoformat() if t.duzenleme_tarihi else '',
                'termin': t.vade_tarihi.isoformat() if t.vade_tarihi else '',
                'durum': t.get_durum_display(),
                'durum_sinifi': sinif,
                'detay_url': reverse('stokapp:teklif_detay', args=[t.pk]),
            }
        )
    return rows


def _siparis_rows(qs, bugun: dt.date):
    rows = []
    for s in qs.select_related('musteri')[:ROW_LIMIT]:
        taraf = s.musteri.ad if s.musteri else (s.musteri_adi or '—')
        termin = s.tamamlanma_tarihi
        sinif = 'normal'
        if termin and termin < bugun and s.siparis_durumu not in ('TESLIM_EDILDI', 'RED'):
            sinif = 'gecikti'
        elif termin == bugun:
            sinif = 'yaklasiyor'
        if s.siparis_durumu == 'ONAY_BEKLIYOR':
            sinif = 'yaklasiyor'
        rows.append(
            {
                'kayit_no': s.siparis_numarasi,
                'aciklama': (s.aciklama or '')[:120] or '—',
                'taraf': taraf,
                'tarih': s.olusturulma_tarihi.isoformat() if s.olusturulma_tarihi else '',
                'termin': termin.isoformat() if termin else '',
                'durum': s.get_siparis_durumu_display(),
                'durum_sinifi': sinif,
                'detay_url': reverse('stokapp:siparis_detay', args=[s.pk]),
            }
        )
    return rows


def _talep_rows(qs):
    rows = []
    bugun = _local_today()
    for tp in qs.select_related('talep_eden')[:ROW_LIMIT]:
        te = tp.talep_eden
        taraf = f'{te.get_full_name() or te.username}'
        if (tp.departman or '').strip():
            taraf += f' · {tp.departman.strip()}'
        sinif = 'normal'
        if tp.gecikti_mi():
            sinif = 'gecikti'
        elif tp.istenen_termin == bugun:
            sinif = 'yaklasiyor'
        elif tp.durum in ('YENI', 'INCELEMEDE'):
            sinif = 'yaklasiyor'
        rows.append(
            {
                'kayit_no': tp.talep_no,
                'aciklama': (tp.baslik or '')[:200],
                'taraf': taraf,
                'tarih': tp.talep_tarihi.isoformat() if tp.talep_tarihi else '',
                'termin': tp.istenen_termin.isoformat() if tp.istenen_termin else '',
                'durum': tp.get_durum_display(),
                'durum_sinifi': sinif,
                'detay_url': reverse('stokapp:talep_detay', args=[tp.pk]),
            }
        )
    return rows


def _stok_kritik_rows(qs):
    rows = []
    for si in qs.select_related('kategori')[:ROW_LIMIT]:
        sinif = 'kritik'
        rows.append(
            {
                'kayit_no': si.stok_kodu,
                'aciklama': si.ad[:200],
                'taraf': si.kategori.ad if si.kategori else '—',
                'tarih': '',
                'termin': '',
                'durum': f"Mevcut {si.mevcut_miktar} · min {si.minimum_stok}"
                + (f" · güv. {si.guvenlik_stoku}" if si.guvenlik_stoku else ''),
                'durum_sinifi': sinif,
                'detay_url': reverse('stokapp:stok_duzenle', args=[si.pk]),
            }
        )
    return rows


def _satinalma_geciken_rows(qs):
    rows = []
    bugun = _local_today()
    for sa in qs.select_related('tedarikci')[:ROW_LIMIT]:
        taraf = sa.tedarikci.ad if sa.tedarikci else (sa.tedarikci_adi or '—')
        termin = sa.tamamlanma_tarihi
        rows.append(
            {
                'kayit_no': sa.satinalma_numarasi,
                'aciklama': (sa.notlar or '')[:120] or '—',
                'taraf': taraf,
                'tarih': sa.olusturulma_tarihi.isoformat() if sa.olusturulma_tarihi else '',
                'termin': termin.isoformat() if termin else '',
                'durum': sa.get_teslim_durumu_display(),
                'durum_sinifi': 'gecikti',
                'detay_url': reverse('stokapp:satinalma_duzenle', args=[sa.pk]),
            }
        )
    return rows


def _uretim_geciken_rows(qs):
    rows = []
    for em in qs.select_related('recete', 'recete__urun')[:ROW_LIMIT]:
        urun_ad = em.recete.urun.ad if em.recete_id else '—'
        rows.append(
            {
                'kayit_no': em.emir_no,
                'aciklama': urun_ad,
                'taraf': '—',
                'tarih': em.planlanan_baslama.date().isoformat() if em.planlanan_baslama else '',
                'termin': em.planlanan_bitis.date().isoformat() if em.planlanan_bitis else '',
                'durum': em.get_durum_display(),
                'durum_sinifi': 'gecikti',
                'detay_url': reverse('stokapp:uretim_emri_detay', args=[em.pk]),
            }
        )
    return rows


def _count_bugunku_is(bugun: dt.date) -> int:
    n = 0
    try:
        n += Siparis.objects.filter(
            tamamlanma_tarihi=bugun,
            siparis_durumu__in=('ONAY_BEKLIYOR', 'ONAYLANDI'),
        ).count()
        n += Satinalma.objects.filter(
            arsivlendi=False,
            teslim_durumu__in=('BEKLIYOR', 'KISMI_TESLIM'),
            tamamlanma_tarihi=bugun,
        ).count()
        n += Talep.objects.filter(
            arsivlendi=False,
            istenen_termin=bugun,
        ).exclude(durum__in=TALEP_KAPALI).count()
        n += UretimEmri.objects.filter(
            durum__in=('PLANLANDI', 'BASLADI'),
            planlanan_bitis__date=bugun,
        ).count()
    except Exception as e:
        logger.exception('count_bugunku_is: %s', e)
    return n


def _count_yaklasan_odeme_30() -> int:
    try:
        from .models import AylikOdeme

        bugun = _local_today()
        son = bugun + dt.timedelta(days=30)
        return AylikOdeme.objects.filter(
            aktif=True,
            odeme_durumu='BEKLEMEDE',
            odeme_tarihi__gte=bugun,
            odeme_tarihi__lte=son,
        ).count()
    except Exception:
        return 0


def build_panel_payload(
    *,
    period: str,
    departman: str,
    sorumlu_id: int | None,
    bugun: dt.date | None = None,
) -> dict:
    bugun = bugun or _local_today()
    period = (period or 'open').strip().lower()
    if period not in ('today', 'week', 'month', 'open'):
        period = 'open'
    dep_norm = (departman or '').strip()

    # --- Onay bekleyen teklifler ---
    teklif_qs = Teklif.objects.filter(arsivlendi=False, durum__in=('draft', 'sent'))
    if sorumlu_id:
        teklif_qs = teklif_qs.filter(olusturan_id=sorumlu_id)
    if period == 'today':
        teklif_qs = teklif_qs.filter(Q(duzenleme_tarihi=bugun) | Q(vade_tarihi=bugun))
    elif period == 'week':
        a, b = _week_bounds(bugun)
        teklif_qs = teklif_qs.filter(
            Q(duzenleme_tarihi__gte=a, duzenleme_tarihi__lte=b)
            | Q(vade_tarihi__gte=a, vade_tarihi__lte=b)
        )
    elif period == 'month':
        a, b = _month_bounds(bugun)
        teklif_qs = teklif_qs.filter(
            Q(duzenleme_tarihi__gte=a, duzenleme_tarihi__lte=b)
            | Q(vade_tarihi__gte=a, vade_tarihi__lte=b)
        )

    # --- Onay bekleyen siparişler ---
    sip_qs = Siparis.objects.filter(siparis_durumu='ONAY_BEKLIYOR')
    if period != 'open':
        if period == 'today':
            sip_qs = sip_qs.filter(
                Q(olusturulma_tarihi=bugun) | Q(tamamlanma_tarihi=bugun)
            )
        elif period == 'week':
            a, b = _week_bounds(bugun)
            sip_qs = sip_qs.filter(
                Q(olusturulma_tarihi__gte=a, olusturulma_tarihi__lte=b)
                | Q(tamamlanma_tarihi__gte=a, tamamlanma_tarihi__lte=b)
            )
        elif period == 'month':
            a, b = _month_bounds(bugun)
            sip_qs = sip_qs.filter(
                Q(olusturulma_tarihi__gte=a, olusturulma_tarihi__lte=b)
                | Q(tamamlanma_tarihi__gte=a, tamamlanma_tarihi__lte=b)
            )

    # --- Açık talepler ---
    talep_qs = Talep.objects.filter(arsivlendi=False).exclude(durum__in=TALEP_KAPALI)
    if dep_norm:
        talep_qs = talep_qs.filter(departman__iexact=dep_norm)
    if sorumlu_id:
        talep_qs = talep_qs.filter(talep_eden_id=sorumlu_id)
    if period != 'open':
        if period == 'today':
            talep_qs = talep_qs.filter(Q(talep_tarihi=bugun) | Q(istenen_termin=bugun))
        elif period == 'week':
            a, b = _week_bounds(bugun)
            talep_qs = talep_qs.filter(
                Q(talep_tarihi__gte=a, talep_tarihi__lte=b)
                | Q(istenen_termin__gte=a, istenen_termin__lte=b)
            )
        elif period == 'month':
            a, b = _month_bounds(bugun)
            talep_qs = talep_qs.filter(
                Q(talep_tarihi__gte=a, talep_tarihi__lte=b)
                | Q(istenen_termin__gte=a, istenen_termin__lte=b)
            )

    # --- Kritik stok ---
    kritik_qs = StokItem.objects.filter(stok_takip=True, arsivli=False).filter(
        Q(mevcut_miktar__lte=F('minimum_stok'))
        | (Q(guvenlik_stoku__gt=0) & Q(mevcut_miktar__lte=F('guvenlik_stoku')))
    )

    # --- Geciken ---
    now = timezone.now()
    gec_sip = Siparis.objects.filter(
        tamamlanma_tarihi__isnull=False,
        tamamlanma_tarihi__lt=bugun,
        siparis_durumu__in=('ONAY_BEKLIYOR', 'ONAYLANDI'),
    ).order_by('tamamlanma_tarihi')
    gec_sat = (
        Satinalma.objects.filter(
            arsivlendi=False,
            tamamlanma_tarihi__isnull=False,
            tamamlanma_tarihi__lt=bugun,
        )
        .exclude(teslim_durumu='TESLIM_ALINDI')
        .order_by('tamamlanma_tarihi')
    )
    gec_talep = (
        Talep.objects.filter(
            arsivlendi=False,
            istenen_termin__isnull=False,
            istenen_termin__lt=bugun,
        )
        .exclude(durum__in=TALEP_KAPALI)
        .order_by('istenen_termin')
    )
    if dep_norm:
        gec_talep = gec_talep.filter(departman__iexact=dep_norm)
    if sorumlu_id:
        gec_talep = gec_talep.filter(talep_eden_id=sorumlu_id)

    gec_emir = UretimEmri.objects.filter(
        durum__in=('PLANLANDI', 'BASLADI'),
        planlanan_bitis__lt=now,
    ).order_by('planlanan_bitis')

    teklif_rows = _teklif_rows(teklif_qs.order_by('-duzenleme_tarihi'), bugun)
    sip_rows = _siparis_rows(sip_qs.order_by('-olusturulma_tarihi'), bugun)
    talep_rows = _talep_rows(talep_qs.order_by('-talep_tarihi'))
    kritik_rows = _stok_kritik_rows(kritik_qs.order_by('mevcut_miktar'))
    geciken_rows_sip = _siparis_rows(gec_sip, bugun)
    geciken_rows_sat = _satinalma_geciken_rows(gec_sat)
    geciken_rows_talep = _talep_rows(gec_talep)
    geciken_rows_emir = _uretim_geciken_rows(gec_emir)

    onay_count = len(teklif_rows) + len(sip_rows) + len(talep_rows)
    # Sayılar tam liste için değil üst kart için gerçek count kullan
    onay_count = (
        teklif_qs.count()
        + sip_qs.count()
        + talep_qs.count()
    )
    geciken_count = gec_sip.count() + gec_sat.count() + gec_talep.count() + gec_emir.count()

    summary = {
        'bugunku_is': _count_bugunku_is(bugun),
        'geciken': geciken_count,
        'onay_bekleyen': onay_count,
        'kritik_stok': kritik_qs.count(),
        'yaklasan_odeme': _count_yaklasan_odeme_30(),
    }

    list_urls = {
        'teklif_listesi': reverse('stokapp:teklif_listesi') + '?tab=cevap_bekliyor',
        'siparis_listesi': reverse('stokapp:siparis_listesi'),
        'talep_listesi': reverse('stokapp:talep_listesi'),
        'stok_listesi': reverse('stokapp:stok_listesi'),
        'satinalma_listesi': reverse('stokapp:satinalma_listesi'),
        'uretim_emirleri': reverse('stokapp:uretim_emri_listesi'),
        'aylik_odemeler_listesi': reverse('stokapp:aylik_odemeler_listesi'),
    }

    return {
        'summary_counts': summary,
        'sections': {
            'onay_teklifler': teklif_rows,
            'onay_siparisler': sip_rows,
            'acik_talepler': talep_rows,
            'kritik_stok': kritik_rows,
            'geciken': {
                'siparis': geciken_rows_sip,
                'satinalma': geciken_rows_sat,
                'talep': geciken_rows_talep,
                'uretim_emri': geciken_rows_emir,
            },
        },
        'list_urls': list_urls,
        'meta': {'period': period, 'bugun': bugun.isoformat()},
    }


@login_required
def gunluk_yonetim_paneli(request):
    departman_secenekleri = (
        Talep.objects.exclude(arsivlendi=True)
        .exclude(departman='')
        .values_list('departman', flat=True)
        .distinct()
        .order_by('departman')[:200]
    )
    kullanicilar = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')[:300]
    return render(
        request,
        'stokapp/gunluk_yonetim_paneli.html',
        {
            'departman_secenekleri': list(departman_secenekleri),
            'kullanicilar': kullanicilar,
            'api_url': reverse('stokapp:api_gunluk_yonetim_ozet'),
        },
    )


@login_required
def api_gunluk_yonetim_ozet(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    period = request.GET.get('period', 'open')
    departman = request.GET.get('departman', '')
    sorumlu_raw = request.GET.get('sorumlu', '').strip()
    sorumlu_id = None
    if sorumlu_raw.isdigit():
        sorumlu_id = int(sorumlu_raw)
    try:
        payload = build_panel_payload(
            period=period,
            departman=departman,
            sorumlu_id=sorumlu_id,
        )
        return JsonResponse(payload, safe=False)
    except Exception as e:
        logger.exception('api_gunluk_yonetim_ozet')
        return JsonResponse(
            {
                'error': str(e),
                'summary_counts': {
                    'bugunku_is': 0,
                    'geciken': 0,
                    'onay_bekleyen': 0,
                    'kritik_stok': 0,
                    'yaklasan_odeme': 0,
                },
                'sections': {
                    'onay_teklifler': [],
                    'onay_siparisler': [],
                    'acik_talepler': [],
                    'kritik_stok': [],
                    'geciken': {
                        'siparis': [],
                        'satinalma': [],
                        'talep': [],
                        'uretim_emri': [],
                    },
                },
                'list_urls': {},
            },
            status=200,
        )
