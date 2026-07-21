"""Müşteri satış teklifleri (Teklifler modülü)."""
import json
from datetime import datetime
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

from .models import (
    BankaHesabi,
    GenelAyarlar,
    Musteri,
    Siparis,
    SiparisKalemi,
    StokItem,
    Teklif,
    TeklifGonderimGecmisi,
    TeklifKalemi,
)
from .satinalma_mail_send import (
    musteri_mail_recipient_choices,
    satinalma_mail_emails_from_keys,
    satinalma_mail_labels_from_keys,
)
from .teklif_pdf_mail import (
    build_teklif_pdf_bytes,
    default_teklif_mail_html,
    default_teklif_mail_subject,
    ensure_teklif_mail_footer,
    parse_extra_emails,
    teklif_mail_footer_text,
)
from .teklif_sartlari_registry import (
    build_numbered_text,
    client_meta_for_js,
    default_client_rows,
    gecerlilik_bitis_tarihi,
    persist_teklif_sartlari,
    rows_from_teklif,
)

TEKLIF_MAIL_SESSION_KEY = 'teklif_mail_wizard'

_TEKLIF_VALID_PB = frozenset({'TL', 'USD', 'EUR', 'GBP'})


def _normalize_offer_currency(pb) -> str:
    if pb is None or pb == '':
        return 'TL'
    x = str(pb).strip().upper()
    if x == 'TRY':
        return 'TL'
    return x[:3]


def _parse_teklif_banka_ids(post) -> list[int]:
    raw = post.get('teklif_banka_json') or '[]'
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    ids: list[int] = []
    for x in data:
        if isinstance(x, int) and x > 0:
            ids.append(x)
        elif isinstance(x, str) and x.strip().isdigit():
            ids.append(int(x.strip()))
    valid = set(
        BankaHesabi.objects.filter(aktif=True, pk__in=ids).values_list('pk', flat=True)
    )
    return [i for i in ids if i in valid]


def _apply_teklif_gecerlilik_ve_banka(teklif: Teklif, request, duzenleme) -> None:
    raw_sart = request.POST.get('teklif_sartlari_json') or '[]'
    try:
        sart_rows = json.loads(raw_sart)
    except json.JSONDecodeError:
        sart_rows = []
    if not isinstance(sart_rows, list):
        sart_rows = []
    teklif.vade_tarihi = gecerlilik_bitis_tarihi(duzenleme, sart_rows)
    teklif.teklif_banka_hesap_ids = _parse_teklif_banka_ids(request.POST)
    teklif.save(update_fields=['vade_tarihi', 'teklif_banka_hesap_ids', 'guncelleme_tarihi'])


def _teklif_bank_template_context(teklif=None):
    hesaplar = list(
        BankaHesabi.objects.filter(aktif=True)
        .order_by('banka_adi', 'hesap_adi')
        .values('id', 'hesap_adi', 'banka_adi', 'iban', 'para_birimi', 'sube_kodu', 'hesap_no')
    )
    initial_ids: list[int] = []
    if teklif is not None and getattr(teklif, 'pk', None):
        raw_ids = getattr(teklif, 'teklif_banka_hesap_ids', None) or []
        if isinstance(raw_ids, list):
            initial_ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]
    return {
        'banka_hesaplari_meta': hesaplar,
        'initial_teklif_banka_ids': initial_ids,
    }


def _teklif_sartlari_form_context(teklif=None):
    if teklif is not None and getattr(teklif, 'pk', None):
        rows = rows_from_teklif(teklif)
    else:
        rows = default_client_rows()
    return {
        'teklif_sartlari_meta': client_meta_for_js(),
        'initial_teklif_sartlari_rows': rows,
    }


@login_required
@require_POST
def teklif_sartlari_onizle(request):
    try:
        body = json.loads(request.body.decode())
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Geçersiz JSON'}, status=400)
    rows = body.get('satirlar')
    if not isinstance(rows, list):
        return JsonResponse({'ok': False, 'error': 'satirlar bir dizi olmalı'}, status=400)
    metin, hatalar = build_numbered_text(rows)
    return JsonResponse({'ok': True, 'metin': metin, 'hatalar': hatalar})


def _yeni_teklif_no():
    gun = timezone.now().strftime('%Y%m%d')
    n = Teklif.objects.filter(teklif_no__startswith=f'TKF-{gun}-').count() + 1
    return f'TKF-{gun}-{n:03d}'


def _satir_toplam_hesap(miktar: Decimal, birim_fiyat: Decimal, vergi_yuzdesi: Decimal) -> Decimal:
    net = miktar * birim_fiyat
    brut = net * (Decimal('1') + vergi_yuzdesi / Decimal('100'))
    return brut.quantize(Decimal('0.01'))


def _teklif_toplam_yeniden_hesapla(teklif: Teklif) -> None:
    kodlar = sorted(
        {
            _normalize_offer_currency(x)
            for x in TeklifKalemi.objects.filter(teklif=teklif).values_list(
                'para_birimi', flat=True
            )
        }
    )
    kodlar = [c for c in kodlar if c in _TEKLIF_VALID_PB]
    if len(kodlar) > 1:
        teklif.toplam_tutar = Decimal('0')
        teklif.para_birimi = 'MIX'
    elif len(kodlar) == 1:
        pb = kodlar[0]
        s = (
            TeklifKalemi.objects.filter(teklif=teklif, para_birimi=pb).aggregate(
                t=Sum('satir_toplam')
            )['t']
            or Decimal('0')
        )
        teklif.toplam_tutar = s
        teklif.para_birimi = pb
    else:
        teklif.toplam_tutar = Decimal('0')
        teklif.para_birimi = 'TL'
    teklif.save(update_fields=['toplam_tutar', 'para_birimi', 'guncelleme_tarihi'])


def _stok_items_queryset():
    return StokItem.objects.filter(arsivli=False).order_by('ad')


def _apply_teklif_rapor_filters(qs, request):
    t0 = request.GET.get('tarih_baslangic')
    t1 = request.GET.get('tarih_bitis')
    if t0:
        try:
            d0 = datetime.strptime(t0, '%Y-%m-%d').date()
            qs = qs.filter(duzenleme_tarihi__gte=d0)
        except ValueError:
            pass
    if t1:
        try:
            d1 = datetime.strptime(t1, '%Y-%m-%d').date()
            qs = qs.filter(duzenleme_tarihi__lte=d1)
        except ValueError:
            pass
    mid = request.GET.get('musteri')
    if mid and str(mid).isdigit():
        qs = qs.filter(musteri_id=int(mid))
    dur = request.GET.get('durum_filtre')
    if dur:
        qs = qs.filter(durum=dur)
    oid = request.GET.get('olusturan')
    if oid and str(oid).isdigit():
        qs = qs.filter(olusturan_id=int(oid))
    pb = (request.GET.get('para_birimi') or '').strip()
    if pb:
        qs = qs.filter(para_birimi=pb)
    return qs


@login_required
def teklif_listesi(request):
    tab = request.GET.get('tab', 'cevap_bekliyor')
    base = Teklif.objects.filter(arsivlendi=False).select_related(
        'musteri', 'kaynak_siparis', 'olusturan'
    )

    qs = base.order_by('-duzenleme_tarihi', '-id')
    rapor_ctx = {}

    if tab == 'tum':
        pass
    elif tab == 'onaylanan':
        qs = qs.filter(durum='accepted')
    elif tab == 'red_edilen':
        qs = qs.filter(durum='rejected')
    elif tab == 'raporlar':
        rq = _apply_teklif_rapor_filters(base, request)
        n = rq.count()
        n_onay = rq.filter(durum='accepted').count()
        n_red = rq.filter(durum='rejected').count()
        n_bek = rq.filter(durum__in=['draft', 'sent']).count()
        sum_all = rq.aggregate(s=Sum('toplam_tutar'))['s'] or Decimal('0')
        sum_onay = rq.filter(durum='accepted').aggregate(s=Sum('toplam_tutar'))['s'] or Decimal(
            '0'
        )
        oran_onay = round((100 * n_onay / n), 1) if n else Decimal('0')
        oran_red = round((100 * n_red / n), 1) if n else Decimal('0')

        red_gr = (
            rq.filter(durum='rejected')
            .values('red_sebebi')
            .annotate(c=Count('id'))
            .order_by('-c')
        )
        red_labels = []
        red_counts = []
        reason_display = dict(Teklif.RED_SEBEP_SECENEKLERI)
        for row in red_gr:
            key = row['red_sebebi'] or ''
            lbl = 'Belirtilmemiş' if not key else reason_display.get(key, key)
            red_labels.append(lbl)
            red_counts.append(row['c'])

        rapor_ctx = {
            'rapor_toplam': n,
            'rapor_onay': n_onay,
            'rapor_red': n_red,
            'rapor_bekleyen': n_bek,
            'rapor_oran_onay': oran_onay,
            'rapor_oran_red': oran_red,
            'rapor_tutar_toplam': sum_all,
            'rapor_tutar_onay': sum_onay,
            'chart_status_labels_json': json.dumps(['Onaylanan', 'Reddedilen', 'Bekleyen']),
            'chart_status_data_json': json.dumps([n_onay, n_red, n_bek]),
            'chart_red_labels_json': json.dumps(red_labels),
            'chart_red_data_json': json.dumps(red_counts),
        }
        qs = base.none()
    else:
        qs = qs.filter(durum__in=['draft', 'sent'])

    counts = {
        'tum': Teklif.objects.filter(arsivlendi=False).count(),
        'cevap_bekliyor': Teklif.objects.filter(
            arsivlendi=False, durum__in=['draft', 'sent']
        ).count(),
        'onaylanan': Teklif.objects.filter(arsivlendi=False, durum='accepted').count(),
        'red_edilen': Teklif.objects.filter(arsivlendi=False, durum='rejected').count(),
    }

    genel_toplam = qs.aggregate(s=Sum('toplam_tutar'))['s'] or Decimal('0')

    paginator = Paginator(qs, 10)
    page = request.GET.get('page', 1)
    teklifler = paginator.get_page(page)

    context = {
        'teklifler': teklifler,
        'tab': tab,
        'counts': counts,
        'genel_toplam': genel_toplam,
        'musteriler': Musteri.objects.all().order_by('ad'),
        'olusturanlar': User.objects.filter(
            pk__in=Teklif.objects.exclude(olusturan=None)
            .values_list('olusturan_id', flat=True)
            .distinct()
        ).order_by('first_name', 'username'),
        'durum_secenekleri': Teklif.DURUM_SECENEKLERI,
        'red_sebep_secenekleri': Teklif.RED_SEBEP_SECENEKLERI,
        **rapor_ctx,
    }
    return render(request, 'stokapp/teklif_listesi.html', context)


def _musteri_snapshot_from_post(post, musteri_id_raw):
    """POST'tan müşteri FK ve anlık alanları döndürür."""
    musteri = None
    musteri_id = (musteri_id_raw or '').strip()
    if musteri_id.isdigit():
        musteri = Musteri.objects.filter(pk=int(musteri_id)).first()

    ad = (post.get('musteri_adi_snapshot') or '').strip()
    tel = (post.get('musteri_telefon') or '').strip()
    email = (post.get('musteri_email') or '').strip()
    adres = (post.get('musteri_adres') or '').strip()

    if musteri:
        ad = ad or musteri.ad
        tel = tel or (musteri.telefon or '')
        email = email or (musteri.email or '')
        adres = adres or (musteri.adres or '')

    return musteri, ad, tel, email, adres


def _kalemleri_kaydet(teklif: Teklif, kalemler_data: list):
    TeklifKalemi.objects.filter(teklif=teklif).delete()
    for idx, raw in enumerate(kalemler_data):
        tip = raw.get('tip') or 'product'
        miktar = Decimal(str(raw.get('miktar') or 0))
        birim_fiyat = Decimal(str(raw.get('birim_fiyat') or 0))
        vergi = Decimal(str(raw.get('vergi_yuzdesi') or 20))
        birim = (raw.get('birim') or 'Adet').strip() or 'Adet'
        aciklama = (raw.get('aciklama') or '').strip()
        satir_notu = (raw.get('satir_notu') or '').strip()

        stok_item = None
        if tip == 'product' and raw.get('stok_item'):
            stok_item = StokItem.objects.filter(pk=int(raw['stok_item'])).first()

        pb = _normalize_offer_currency(raw.get('para_birimi'))
        if pb not in _TEKLIF_VALID_PB:
            pb = 'TL'
        if tip == 'product' and stok_item and not (raw.get('para_birimi') or '').strip():
            pb = _normalize_offer_currency(stok_item.satis_para_birimi or 'TL')

        satir_toplam = _satir_toplam_hesap(miktar, birim_fiyat, vergi)
        TeklifKalemi.objects.create(
            teklif=teklif,
            tip=tip if tip in ('product', 'custom') else 'product',
            stok_item=stok_item,
            aciklama=aciklama,
            miktar=miktar,
            birim=birim,
            birim_fiyat=birim_fiyat,
            para_birimi=pb,
            vergi_yuzdesi=vergi,
            satir_toplam=satir_toplam,
            satir_notu=satir_notu,
            sira=idx,
        )
    _teklif_toplam_yeniden_hesapla(teklif)


@login_required
def teklif_ekle(request):
    siparis_prefill = None
    siparis_id = request.GET.get('siparis_id')
    if siparis_id:
        siparis_prefill = get_object_or_404(
            Siparis.objects.select_related('musteri'), pk=int(siparis_id)
        )

    if request.method == 'POST':
        try:
            kalemler_data = json.loads(request.POST.get('kalemler') or '[]')
        except json.JSONDecodeError:
            kalemler_data = []

        ad = (request.POST.get('ad') or '').strip()
        if not kalemler_data:
            messages.error(request, 'En az bir satır ekleyin.')
        else:
            musteri, m_ad, m_tel, m_email, m_adres = _musteri_snapshot_from_post(
                request.POST, request.POST.get('musteri')
            )
            try:
                duzenleme = datetime.strptime(
                    request.POST.get('duzenleme_tarihi') or '', '%Y-%m-%d'
                ).date()
            except ValueError:
                duzenleme = timezone.now().date()

            sartlar = request.POST.get('sartlar_metni') or ''
            kaynak_siparis_id = request.POST.get('kaynak_siparis_id') or ''
            kaynak_siparis = None
            if kaynak_siparis_id.isdigit():
                kaynak_siparis = Siparis.objects.filter(pk=int(kaynak_siparis_id)).first()

            try:
                with transaction.atomic():
                    teklif = Teklif.objects.create(
                        teklif_no=_yeni_teklif_no(),
                        ad=ad,
                        musteri=musteri,
                        musteri_adi=m_ad,
                        musteri_telefon=m_tel,
                        musteri_email=m_email,
                        musteri_adres=m_adres,
                        kaynak_siparis=kaynak_siparis,
                        duzenleme_tarihi=duzenleme,
                        vade_tarihi=None,
                        para_birimi='TL',
                        sartlar_metni=sartlar,
                        durum='draft',
                        olusturan=request.user,
                    )
                    _kalemleri_kaydet(teklif, kalemler_data)
                    persist_teklif_sartlari(
                        teklif, request.POST.get('teklif_sartlari_json') or '[]'
                    )
                    _apply_teklif_gecerlilik_ve_banka(teklif, request, duzenleme)
                messages.success(request, f'Teklif "{teklif.teklif_no}" kaydedildi.')
                return redirect('stokapp:teklif_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {e}')

    initial_kalemler = []
    ctx_musteri_id = ''
    ctx_musteri_adi = ''
    ctx_kaynak_siparis_id = ''
    ctx_ad = ''
    ctx_duzenleme = timezone.now().date().isoformat()
    ctx_sartlar = ''
    musteri_selected_pk = None

    if siparis_prefill and request.method != 'POST':
        ctx_kaynak_siparis_id = str(siparis_prefill.pk)
        ctx_ad = f'Teklif — {siparis_prefill.siparis_numarasi}'
        if siparis_prefill.musteri_id:
            ctx_musteri_id = str(siparis_prefill.musteri_id)
            musteri_selected_pk = siparis_prefill.musteri_id
            ctx_musteri_adi = siparis_prefill.musteri.ad
        else:
            ctx_musteri_adi = siparis_prefill.musteri_adi or ''
        ctx_duzenleme = siparis_prefill.olusturulma_tarihi.isoformat()
        spb = _normalize_offer_currency(siparis_prefill.para_birimi)
        for k in siparis_prefill.kalemler.all().select_related('stok_item'):
            if k.stok_item_id:
                initial_kalemler.append(
                    {
                        'tip': 'product',
                        'stok_item': k.stok_item_id,
                        'stok_kodu': k.stok_item.stok_kodu,
                        'stok_ad': k.stok_item.ad,
                        'birim': k.stok_item.birim or 'Adet',
                        'miktar': str(k.miktar),
                        'birim_fiyat': str(k.birim_fiyat),
                        'para_birimi': spb,
                        'vergi_yuzdesi': '20',
                        'aciklama': k.aciklama or '',
                        'satir_notu': '',
                    }
                )
            else:
                initial_kalemler.append(
                    {
                        'tip': 'custom',
                        'stok_item': '',
                        'stok_kodu': '',
                        'stok_ad': '',
                        'birim': 'Adet',
                        'miktar': str(k.miktar),
                        'birim_fiyat': str(k.birim_fiyat),
                        'para_birimi': spb,
                        'vergi_yuzdesi': '20',
                        'aciklama': k.aciklama or 'Serbest kalem',
                        'satir_notu': '',
                    }
                )

    context = {
        'teklif': None,
        'stok_items': _stok_items_queryset(),
        'musteriler': Musteri.objects.all().order_by('ad'),
        'initial_kalemler_json': json.dumps(initial_kalemler),
        'form_ad': ctx_ad,
        'form_musteri_id': ctx_musteri_id,
        'musteri_selected_pk': musteri_selected_pk,
        'form_musteri_adi_snapshot': ctx_musteri_adi,
        'form_duzenleme': ctx_duzenleme,
        'form_sartlar': ctx_sartlar,
        'kaynak_siparis_id': ctx_kaynak_siparis_id,
        'form_gecerlilik': '',
        **_teklif_sartlari_form_context(None),
        **_teklif_bank_template_context(None),
    }
    return render(request, 'stokapp/teklif_form.html', context)


@login_required
def teklif_duzenle(request, pk):
    teklif = get_object_or_404(Teklif.objects.select_related('musteri', 'kaynak_siparis'), pk=pk)

    if request.method == 'POST':
        try:
            kalemler_data = json.loads(request.POST.get('kalemler') or '[]')
        except json.JSONDecodeError:
            kalemler_data = []

        ad = (request.POST.get('ad') or '').strip()
        if not kalemler_data:
            messages.error(request, 'En az bir satır ekleyin.')
        else:
            musteri, m_ad, m_tel, m_email, m_adres = _musteri_snapshot_from_post(
                request.POST, request.POST.get('musteri')
            )
            try:
                duzenleme = datetime.strptime(
                    request.POST.get('duzenleme_tarihi') or '', '%Y-%m-%d'
                ).date()
            except ValueError:
                duzenleme = teklif.duzenleme_tarihi

            sartlar = request.POST.get('sartlar_metni') or ''

            try:
                with transaction.atomic():
                    teklif.ad = ad
                    teklif.musteri = musteri
                    teklif.musteri_adi = m_ad
                    teklif.musteri_telefon = m_tel
                    teklif.musteri_email = m_email
                    teklif.musteri_adres = m_adres
                    teklif.duzenleme_tarihi = duzenleme
                    teklif.sartlar_metni = sartlar
                    teklif.save()
                    _kalemleri_kaydet(teklif, kalemler_data)
                    persist_teklif_sartlari(
                        teklif, request.POST.get('teklif_sartlari_json') or '[]'
                    )
                    _apply_teklif_gecerlilik_ve_banka(teklif, request, duzenleme)
                messages.success(request, 'Teklif güncellendi.')
                return redirect('stokapp:teklif_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {e}')

    rows = []
    for k in teklif.kalemler.all().select_related('stok_item'):
        rows.append(
            {
                'tip': k.tip,
                'stok_item': k.stok_item_id or '',
                'stok_kodu': k.stok_item.stok_kodu if k.stok_item_id else '',
                'stok_ad': k.stok_item.ad if k.stok_item_id else '',
                'birim': k.birim,
                'miktar': str(k.miktar),
                'birim_fiyat': str(k.birim_fiyat),
                'para_birimi': _normalize_offer_currency(
                    getattr(k, 'para_birimi', None) or teklif.para_birimi
                ),
                'vergi_yuzdesi': str(k.vergi_yuzdesi),
                'aciklama': k.aciklama or '',
                'satir_notu': k.satir_notu or '',
            }
        )

    context = {
        'teklif': teklif,
        'stok_items': _stok_items_queryset(),
        'musteriler': Musteri.objects.all().order_by('ad'),
        'initial_kalemler_json': json.dumps(rows),
        'form_ad': teklif.ad,
        'form_musteri_id': str(teklif.musteri_id) if teklif.musteri_id else '',
        'musteri_selected_pk': teklif.musteri_id,
        'form_musteri_adi_snapshot': teklif.musteri_adi,
        'form_musteri_telefon': teklif.musteri_telefon,
        'form_musteri_email': teklif.musteri_email,
        'form_musteri_adres': teklif.musteri_adres,
        'form_duzenleme': teklif.duzenleme_tarihi.isoformat(),
        'form_sartlar': teklif.sartlar_metni,
        'kaynak_siparis_id': str(teklif.kaynak_siparis_id) if teklif.kaynak_siparis_id else '',
        'form_gecerlilik': teklif.vade_tarihi.isoformat() if teklif.vade_tarihi else '',
        **_teklif_sartlari_form_context(teklif),
        **_teklif_bank_template_context(teklif),
    }
    return render(request, 'stokapp/teklif_form.html', context)


@login_required
def teklif_sil(request, pk):
    teklif = get_object_or_404(Teklif, pk=pk)
    if request.method == 'POST':
        if teklif.olusturulan_siparisler.exists():
            messages.error(request, 'Bu teklife bağlı siparişler var; silinemez.')
        else:
            teklif.delete()
            messages.success(request, 'Teklif silindi.')
        return redirect('stokapp:teklif_listesi')
    siparise_bagli = teklif.olusturulan_siparisler.exists()
    return render(
        request,
        'stokapp/teklif_sil.html',
        {'teklif': teklif, 'siparise_bagli': siparise_bagli},
    )


def _next_siparis_numarasi():
    son_siparis = Siparis.objects.order_by('-id').first()
    if son_siparis:
        try:
            num = int(str(son_siparis.siparis_numarasi).replace('SO-', '').strip()) + 1
        except ValueError:
            num = Siparis.objects.count() + 1
    else:
        num = 1
    return f'SO-{num}'


def _build_siparis_aciklama(teklif):
    ad_goster = (teklif.ad or '').strip() or teklif.teklif_no
    parts = [f'Kaynak teklif: {teklif.teklif_no}', ad_goster]
    if (teklif.sartlar_metni or '').strip():
        parts.append('\n--- Teklif şartları ---\n' + teklif.sartlar_metni.strip())
    return '\n'.join(parts)


def _teklif_pb_ozet_from_kalemler(kalemler) -> list[dict]:
    """Satır para birimlerine göre net / KDV / brüt özet (detay & şablon yardımcı)."""
    from collections import defaultdict

    net_map: dict[str, Decimal] = defaultdict(Decimal)
    brut_map: dict[str, Decimal] = defaultdict(Decimal)
    for k in kalemler:
        pb = _normalize_offer_currency(getattr(k, 'para_birimi', None))
        if pb not in _TEKLIF_VALID_PB:
            pb = 'TL'
        net_map[pb] += k.miktar * k.birim_fiyat
        brut_map[pb] += k.satir_toplam or Decimal('0')
    rows = []
    for pb in sorted(brut_map.keys()):
        brut = brut_map[pb]
        net = net_map[pb]
        rows.append(
            {
                'para': pb,
                'net': net,
                'kdv': brut - net,
                'brut': brut,
            }
        )
    return rows


def _distinct_kalem_paralari(teklif: Teklif) -> list[str]:
    kodlar = sorted(
        {
            _normalize_offer_currency(x)
            for x in teklif.kalemler.values_list('para_birimi', flat=True)
        }
    )
    return [c for c in kodlar if c in _TEKLIF_VALID_PB]


def _distinct_kalem_paralari_for_kalemler(kalemler) -> list[str]:
    kodlar = sorted(
        {
            _normalize_offer_currency(k.para_birimi)
            for k in kalemler
        }
    )
    return [c for c in kodlar if c in _TEKLIF_VALID_PB]


def _teklif_siparise_aktarilmis_kalem_ids(teklif: Teklif) -> set[int]:
    aktarilan_ids = set(
        SiparisKalemi.objects.filter(
            kaynak_teklif_kalemi__teklif_id=teklif.pk
        ).values_list('kaynak_teklif_kalemi_id', flat=True)
    )
    # Legacy kayıtlarda sipariş kalemleri kaynak_teklif_kalemi'ne bağlı olmayabilir.
    # Teklif "accepted" durumundaysa iş kuralı gereği tüm kalemler siparişe aktarılmış olmalıdır.
    if teklif.durum == 'accepted':
        tum_kalem_ids = set(teklif.kalemler.values_list('id', flat=True))
        if tum_kalem_ids:
            return tum_kalem_ids
    return aktarilan_ids


def _teklif_kalem_etiketi(kalem: TeklifKalemi) -> str:
    if kalem.stok_item_id:
        parts = [kalem.stok_item.stok_kodu, kalem.stok_item.ad]
    else:
        parts = [(kalem.aciklama or '').strip() or 'Serbest kalem']
    if kalem.aciklama and kalem.stok_item_id:
        parts.append(kalem.aciklama.strip())
    return ' — '.join(p for p in parts if p)


def _teklif_onay_kalemler_payload(teklif: Teklif) -> dict:
    converted_ids = _teklif_siparise_aktarilmis_kalem_ids(teklif)
    kalemler = []
    for k in teklif.kalemler.select_related('stok_item').order_by('sira', 'id'):
        kalemler.append(
            {
                'id': k.id,
                'label': _teklif_kalem_etiketi(k),
                'miktar': str(k.miktar),
                'birim': k.birim,
                'birim_fiyat': str(k.birim_fiyat),
                'para_birimi': k.para_birimi,
                'satir_toplam': str(k.satir_toplam),
                'siparise_aktarildi': k.id in converted_ids,
            }
        )
    bekleyen = sum(1 for x in kalemler if not x['siparise_aktarildi'])
    return {
        'teklif_no': teklif.teklif_no,
        'kalemler': kalemler,
        'bekleyen_sayisi': bekleyen,
    }


def _create_siparis_from_teklif(teklif, siparis_numarasi=None, kalem_ids=None, siparis_mektubu_name=None):
    """Tekliften Siparis oluşturur (transaction içinde çağrılmalı).

    kalem_ids: onaylanacak TeklifKalemi pk listesi. Boş/None ise bekleyen tüm kalemler.
    """
    already_converted = _teklif_siparise_aktarilmis_kalem_ids(teklif)
    all_kalemler = list(teklif.kalemler.all().order_by('sira', 'id'))
    if kalem_ids is not None:
        try:
            selected_ids = {int(x) for x in kalem_ids}
        except (TypeError, ValueError):
            return None
        selected = [k for k in all_kalemler if k.id in selected_ids]
    else:
        selected = [k for k in all_kalemler if k.id not in already_converted]
    selected = [k for k in selected if k.id not in already_converted]
    if not selected:
        return None

    pb_list = _distinct_kalem_paralari_for_kalemler(selected)
    if len(pb_list) != 1:
        return None
    sip_pb = pb_list[0]
    raw_no = (siparis_numarasi or '').strip()
    sip_no = raw_no if raw_no else _next_siparis_numarasi()
    siparis = Siparis.objects.create(
        siparis_numarasi=sip_no,
        musteri=teklif.musteri,
        musteri_adi=teklif.musteri_adi or (teklif.musteri.ad if teklif.musteri_id else ''),
        toplam=Decimal('0'),
        para_birimi=sip_pb,
        olusturulma_tarihi=timezone.now().date(),
        tamamlanma_tarihi=None,
        siparis_durumu='ONAY_BEKLIYOR',
        kaynak_teklif=teklif,
        aciklama=_build_siparis_aciklama(teklif),
        siparis_mektubu=siparis_mektubu_name or None,
    )
    for k in selected:
        if k.tip == 'product' and k.stok_item_id:
            SiparisKalemi.objects.create(
                siparis=siparis,
                stok_item=k.stok_item,
                kaynak_teklif_kalemi=k,
                miktar=k.miktar,
                birim_fiyat=k.birim_fiyat,
                indirim_yuzdesi=Decimal('0'),
                aciklama=k.aciklama or '',
            )
        else:
            SiparisKalemi.objects.create(
                siparis=siparis,
                stok_item=None,
                kaynak_teklif_kalemi=k,
                miktar=k.miktar,
                birim_fiyat=k.birim_fiyat,
                indirim_yuzdesi=Decimal('0'),
                aciklama=(k.aciklama or '').strip() or 'Serbest kalem',
            )
    ara = (
        SiparisKalemi.objects.filter(siparis=siparis).aggregate(t=Sum('toplam'))['t']
        or Decimal('0')
    )
    siparis.toplam = ara
    siparis.save(update_fields=['toplam', 'updated_at'])
    return siparis


def _teklif_secili_bankalar_detay(teklif: Teklif) -> list[dict]:
    raw_ids = getattr(teklif, 'teklif_banka_hesap_ids', None) or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return []
    order = {}
    for i, x in enumerate(raw_ids):
        try:
            order[int(x)] = i
        except (TypeError, ValueError):
            continue
    if not order:
        return []
    hesaplar = list(BankaHesabi.objects.filter(pk__in=list(order.keys()), aktif=True))
    hesaplar.sort(key=lambda h: order.get(h.pk, 9999))
    return [
        {
            'banka_adi': h.banka_adi,
            'hesap_adi': h.hesap_adi,
            'iban': h.iban,
            'para_birimi': h.para_birimi,
            'sube_kodu': h.sube_kodu or '',
            'hesap_no': h.hesap_no or '',
        }
        for h in hesaplar
    ]


@login_required
def teklif_detay(request, pk):
    teklif = get_object_or_404(
        Teklif.objects.select_related('musteri', 'kaynak_siparis', 'olusturan', 'reddeden_kullanici'),
        pk=pk,
    )
    kalemler = teklif.kalemler.all().select_related('stok_item').order_by('sira', 'id')
    gonderimler = teklif.gonderim_gecmisi.select_related('gonderen_kullanici').order_by(
        '-gonderim_tarihi'
    )[:50]
    olusan_siparisler = list(teklif.olusturulan_siparisler.order_by('-id'))
    olusan_siparis = olusan_siparisler[0] if olusan_siparisler else None
    siparise_aktarilmis_kalem_ids = _teklif_siparise_aktarilmis_kalem_ids(teklif)
    bekleyen_kalem_sayisi = teklif.kalemler.exclude(id__in=siparise_aktarilmis_kalem_ids).count()
    pb_ozet = _teklif_pb_ozet_from_kalemler(kalemler)
    return render(
        request,
        'stokapp/teklif_detay.html',
        {
            'teklif': teklif,
            'kalemler': kalemler,
            'gonderimler': gonderimler,
            'olusan_siparis': olusan_siparis,
            'olusan_siparisler': olusan_siparisler,
            'siparise_aktarilmis_kalem_ids': siparise_aktarilmis_kalem_ids,
            'bekleyen_kalem_sayisi': bekleyen_kalem_sayisi,
            'teklif_pb_ozet': pb_ozet,
            'teklif_banka_satirlari': _teklif_secili_bankalar_detay(teklif),
        },
    )


@login_required
def teklif_pdf_indir(request, pk):
    teklif = get_object_or_404(Teklif, pk=pk)
    pdf_bytes = build_teklif_pdf_bytes(teklif)
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{teklif.teklif_no}.pdf"'
    return resp


@login_required
def teklif_gonder(request, pk):
    """Taslak teklifi gönderim sihirbazına yönlendirir."""
    teklif = get_object_or_404(Teklif, pk=pk)
    if teklif.durum != 'draft':
        messages.warning(
            request,
            'Gönderim yalnızca taslak teklifler için kullanılabilir.',
        )
        return redirect('stokapp:teklif_listesi')
    return redirect('stokapp:teklif_mail_alici_sec', pk=pk)


@login_required
def teklif_mail_alici_sec(request, pk):
    teklif = get_object_or_404(Teklif.objects.select_related('musteri'), pk=pk)
    if teklif.durum != 'draft':
        messages.warning(request, 'Bu teklif taslak değil.')
        return redirect('stokapp:teklif_detay', pk=teklif.pk)
    choices = musteri_mail_recipient_choices(teklif.musteri)
    if request.method == 'POST':
        selected = request.POST.getlist('alici_keys')
        emails = satinalma_mail_emails_from_keys(choices, selected)
        cc_list = parse_extra_emails(request.POST.get('cc', ''))
        bcc_list = parse_extra_emails(request.POST.get('bcc', ''))
        if not emails:
            messages.error(
                request,
                'En az bir alıcı seçin. Müşteri kartında firma veya ilgili kişi e-postası tanımlı olmalıdır.',
            )
            return render(
                request,
                'stokapp/teklif_mail_alici_sec.html',
                {
                    'teklif': teklif,
                    'choices': choices,
                    'selected_keys': selected,
                    'cc_value': request.POST.get('cc', ''),
                    'bcc_value': request.POST.get('bcc', ''),
                },
            )
        labels = satinalma_mail_labels_from_keys(choices, selected)
        request.session[TEKLIF_MAIL_SESSION_KEY] = {
            'teklif_id': teklif.pk,
            'emails': emails,
            'labels': labels,
            'cc': cc_list,
            'bcc': bcc_list,
            'uid': request.user.pk,
        }
        return redirect('stokapp:teklif_mail_onay', pk=pk)
    return render(
        request,
        'stokapp/teklif_mail_alici_sec.html',
        {
            'teklif': teklif,
            'choices': choices,
            'selected_keys': [],
            'cc_value': '',
            'bcc_value': '',
        },
    )


@login_required
def teklif_mail_onay(request, pk):
    from django.utils.html import strip_tags

    teklif = get_object_or_404(Teklif.objects.select_related('musteri'), pk=pk)
    data = request.session.get(TEKLIF_MAIL_SESSION_KEY)
    if (
        not data
        or data.get('teklif_id') != teklif.pk
        or data.get('uid') != request.user.pk
    ):
        messages.error(
            request,
            'Oturum süresi doldu veya geçersiz akış. Lütfen alıcı seçimini yeniden yapın.',
        )
        return redirect('stokapp:teklif_mail_alici_sec', pk=pk)

    konu_varsayilan = default_teklif_mail_subject(teklif)
    mesaj_varsayilan = default_teklif_mail_html(teklif)

    if request.method == 'POST':
        konu = (request.POST.get('konu') or '').strip() or konu_varsayilan
        mesaj = ensure_teklif_mail_footer(
            (request.POST.get('mesaj') or '').strip() or mesaj_varsayilan
        )

        otomatik_cc = GenelAyarlar.get_musteri_mail_cc_adresi()
        cc_list = list(data.get('cc') or [])
        alici_set = {str(a).strip().lower() for a in (data.get('emails') or [])}
        if otomatik_cc.lower() not in {str(c).strip().lower() for c in cc_list} and otomatik_cc.lower() not in alici_set:
            cc_list.append(otomatik_cc)

        pdf_bytes = None
        hata_txt = ''
        try:
            pdf_bytes = build_teklif_pdf_bytes(teklif)
        except Exception as exc:
            hata_txt = str(exc)

        if not pdf_bytes:
            TeklifGonderimGecmisi.objects.create(
                teklif=teklif,
                alicilar=data['emails'],
                cc=cc_list,
                bcc=data.get('bcc') or [],
                konu=konu,
                mesaj=mesaj,
                gonderen_kullanici=request.user,
                durum='HATA',
                hata_mesaji=hata_txt or 'PDF oluşturulamadı.',
            )
            messages.error(request, f'PDF oluşturulamadı: {hata_txt}')
            return redirect('stokapp:teklif_mail_onay', pk=pk)

        plain = strip_tags(mesaj)
        if 'tescilli dijital yönetim platformlarıdır' not in plain:
            plain = f'{plain.rstrip()}\n\n{teklif_mail_footer_text()}'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or None
        email = EmailMultiAlternatives(
            subject=konu,
            body=plain or strip_tags(mesaj_varsayilan),
            from_email=from_email,
            to=data['emails'],
            cc=cc_list,
            bcc=data.get('bcc') or [],
        )
        email.attach_alternative(mesaj, 'text/html')
        email.attach(f'teklif_{teklif.teklif_no}.pdf', pdf_bytes, 'application/pdf')
        try:
            email.send(fail_silently=False)
        except Exception as exc:
            TeklifGonderimGecmisi.objects.create(
                teklif=teklif,
                alicilar=data['emails'],
                cc=cc_list,
                bcc=data.get('bcc') or [],
                konu=konu,
                mesaj=mesaj,
                gonderen_kullanici=request.user,
                durum='HATA',
                hata_mesaji=str(exc),
            )
            messages.error(request, f'E-posta gönderilemedi: {exc}')
            return redirect('stokapp:teklif_mail_onay', pk=pk)

        now = timezone.now()
        teklif.durum = 'sent'
        teklif.son_gonderim_tarihi = now
        teklif.pdf_dosyasi.save(
            f'{teklif.teklif_no}.pdf',
            ContentFile(pdf_bytes),
            save=False,
        )
        teklif.save(update_fields=['durum', 'son_gonderim_tarihi', 'pdf_dosyasi', 'guncelleme_tarihi'])

        gec = TeklifGonderimGecmisi(
            teklif=teklif,
            alicilar=data['emails'],
            cc=cc_list,
            bcc=data.get('bcc') or [],
            konu=konu,
            mesaj=mesaj,
            gonderen_kullanici=request.user,
            durum='GONDERILDI',
        )
        gec.save()
        gec.pdf_dosyasi.save(
            f'{teklif.teklif_no}_{now:%Y%m%d_%H%M%S}.pdf',
            ContentFile(pdf_bytes),
            save=True,
        )

        request.session.pop(TEKLIF_MAIL_SESSION_KEY, None)
        messages.success(request, 'Teklif e-postası gönderildi.')
        return redirect('stokapp:teklif_detay', pk=teklif.pk)

    return render(
        request,
        'stokapp/teklif_mail_onay.html',
        {
            'teklif': teklif,
            'alici_etiketleri': data.get('labels') or [],
            'alici_mailler': data.get('emails') or [],
            'cc_list': data.get('cc') or [],
            'bcc_list': data.get('bcc') or [],
            'konu_varsayilan': konu_varsayilan,
            'mesaj_varsayilan': mesaj_varsayilan,
        },
    )


@login_required
def teklif_onay_kalemler_json(request, pk):
    """Onay modalı için teklif kalemlerini JSON döner."""
    teklif = get_object_or_404(Teklif, pk=pk)
    if teklif.durum not in ('sent', 'draft'):
        return JsonResponse({'error': 'Bu teklif durumu için kalem listesi alınamaz.'}, status=400)
    return JsonResponse(_teklif_onay_kalemler_payload(teklif))


@login_required
def teklif_musteri_cevabi_onay(request, pk):
    if request.method != 'POST':
        return redirect('stokapp:teklif_listesi')
    teklif = get_object_or_404(Teklif, pk=pk)
    if teklif.durum not in ('sent', 'draft'):
        messages.warning(request, 'Bu işlem bu teklif durumu için geçerli değil.')
        return redirect('stokapp:teklif_listesi')
    istenen_no = (request.POST.get('siparis_numarasi') or '').strip()
    siparis_mektubu = request.FILES.get('siparis_mektubu')
    kalem_ids_raw = request.POST.getlist('kalem_ids')
    _onay_err_redirect = (
        redirect('stokapp:teklif_listesi')
        if (request.POST.get('onay_error_redirect') or '').strip() == 'list'
        else redirect('stokapp:teklif_detay', pk=pk)
    )
    if not kalem_ids_raw:
        messages.error(request, 'Siparişe aktarılacak en az bir kalem seçmelisiniz.')
        return _onay_err_redirect
    try:
        kalem_ids = [int(x) for x in kalem_ids_raw]
    except (TypeError, ValueError):
        messages.error(request, 'Geçersiz kalem seçimi.')
        return _onay_err_redirect
    if istenen_no:
        if len(istenen_no) > 50:
            messages.error(request, 'Sipariş numarası en fazla 50 karakter olabilir.')
            return _onay_err_redirect
        if Siparis.objects.filter(siparis_numarasi=istenen_no).exists():
            messages.error(
                request,
                f'«{istenen_no}» sipariş numarası zaten kullanılıyor; farklı bir numara girin veya boş bırakın.',
            )
            return _onay_err_redirect
    if siparis_mektubu:
        mektup_adi = (getattr(siparis_mektubu, 'name', '') or '').lower()
        if not mektup_adi.endswith('.pdf'):
            messages.error(request, 'Sipariş mektubu sadece PDF formatında olmalıdır.')
            return _onay_err_redirect
    siparis_yeni = None
    secilen_adet = 0
    bekleyen_sonra = 0
    try:
        with transaction.atomic():
            teklif_locked = Teklif.objects.select_for_update().get(pk=pk)
            if teklif_locked.durum not in ('sent', 'draft'):
                messages.warning(request, 'Bu işlem bu teklif durumu için geçerli değil.')
                return redirect('stokapp:teklif_listesi')

            teklif_kalem_ids = set(teklif_locked.kalemler.values_list('id', flat=True))
            if not set(kalem_ids).issubset(teklif_kalem_ids):
                messages.error(request, 'Seçilen kalemler bu teklife ait değil.')
                return _onay_err_redirect

            already_converted = _teklif_siparise_aktarilmis_kalem_ids(teklif_locked)
            if set(kalem_ids) & already_converted:
                messages.error(request, 'Seçilen kalemlerden bazıları zaten siparişe aktarılmış.')
                return _onay_err_redirect

            selected_kalemler = list(
                teklif_locked.kalemler.filter(id__in=kalem_ids).order_by('sira', 'id')
            )
            secilen_adet = len(selected_kalemler)
            pbler = _distinct_kalem_paralari_for_kalemler(selected_kalemler)
            if len(pbler) > 1:
                messages.error(
                    request,
                    'Seçilen kalemlerde birden fazla para birimi var; aynı para biriminden kalemleri birlikte onaylayın.',
                )
                return _onay_err_redirect
            if len(pbler) == 0:
                messages.error(request, 'Seçilen kalemler için para birimi bulunamadı.')
                return _onay_err_redirect

            if siparis_mektubu:
                teklif_locked.siparis_mektubu = siparis_mektubu
                teklif_locked.save(update_fields=['siparis_mektubu', 'guncelleme_tarihi'])

            siparis_mektubu_name = teklif_locked.siparis_mektubu.name if teklif_locked.siparis_mektubu else None
            siparis_yeni = _create_siparis_from_teklif(
                teklif_locked,
                siparis_numarasi=istenen_no or None,
                kalem_ids=kalem_ids,
                siparis_mektubu_name=siparis_mektubu_name,
            )
            if siparis_yeni is None:
                messages.error(request, 'Sipariş oluşturulamadı; kalem bilgilerini kontrol edin.')
                return _onay_err_redirect

            converted_after = _teklif_siparise_aktarilmis_kalem_ids(teklif_locked)
            total_kalem = teklif_locked.kalemler.count()
            bekleyen_sonra = total_kalem - len(converted_after)
            if bekleyen_sonra <= 0:
                teklif_locked.durum = 'accepted'
                teklif_locked.save(update_fields=['durum', 'guncelleme_tarihi'])
    except IntegrityError:
        messages.error(
            request,
            'Sipariş oluşturulamadı (benzersizlik kısıtı). Kayıt kontrol edin.',
        )
        return redirect('stokapp:teklif_listesi')

    if bekleyen_sonra > 0:
        messages.success(
            request,
            f'{secilen_adet} kalem sipariş «{siparis_yeni.siparis_numarasi}» olarak oluşturuldu. '
            f'Teklifte {bekleyen_sonra} kalem bekliyor.',
        )
    else:
        messages.success(
            request,
            f'Teklif tamamen onaylandı. Sipariş «{siparis_yeni.siparis_numarasi}» oluşturuldu (onay bekliyor).',
        )
    return redirect('stokapp:siparis_detay', pk=siparis_yeni.pk)


@login_required
def teklif_musteri_cevabi_red(request, pk):
    if request.method != 'POST':
        return redirect('stokapp:teklif_listesi')
    teklif = get_object_or_404(Teklif, pk=pk)
    if teklif.durum not in ('sent', 'draft'):
        messages.warning(request, 'Bu işlem bu teklif durumu için geçerli değil.')
        return redirect('stokapp:teklif_listesi')
    red_sebebi = (request.POST.get('red_sebebi') or '').strip()
    valid_codes = {c[0] for c in Teklif.RED_SEBEP_SECENEKLERI}
    if not red_sebebi or red_sebebi not in valid_codes:
        messages.error(request, 'Geçerli bir red sebebi seçin.')
        return redirect('stokapp:teklif_listesi')
    diger = (request.POST.get('red_sebebi_diger_aciklama') or '').strip()
    if red_sebebi != 'DIGER':
        diger = ''
    notu = (request.POST.get('red_notu') or '').strip()
    teklif.red_sebebi = red_sebebi
    teklif.red_sebebi_diger_aciklama = diger
    teklif.red_notu = notu
    teklif.red_tarihi = timezone.now()
    teklif.reddeden_kullanici = request.user
    teklif.durum = 'rejected'
    teklif.save(
        update_fields=[
            'durum',
            'red_sebebi',
            'red_sebebi_diger_aciklama',
            'red_notu',
            'red_tarihi',
            'reddeden_kullanici',
            'guncelleme_tarihi',
        ]
    )
    messages.success(request, 'Teklif reddedildi.')
    return redirect('stokapp:teklif_listesi')
