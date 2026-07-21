from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Max, Count
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache
import json
from .models import Recete, ReceteDetay, ReceteOperasyon, ReceteDisOperasyon, StokItem, Operasyon, Istasyon, UretimStandarti, Depo, DisOperasyonTipi, Tedarikci
from decimal import Decimal
from .models import (
    ReceteTalimat, ReceteTalimatOlcu, ReceteTalimatDosya, ReceteTalimatEkipman,
    ReceteTalimatProgram, ReceteTalimatFikstur, ReceteTalimatOlcuAleti,
    ReceteTalimatAciklama, ReceteTalimatKurulumDosyasi,
)
from .models import Ekipman, Fikstur
from .stok_search import stok_multi_term_filter


def _recete_dis_fields_from_post(operasyon: Operasyon, post) -> dict:
    """Reçete operasyonu için dış operasyon şablonu alanları (POST)."""
    if not operasyon.akis_dis_operasyon:
        return {
            'dis_operasyon_tipi_id': None,
            'dis_tedarikci_id': None,
            'dis_gonderim_deposu_id': None,
            'dis_birim_fiyat': Decimal('0'),
            'dis_para_birimi': 'TL',
            'dis_beklenen_donus_gun': 7,
            'dis_sevk_evrak_no': '',
        }
    tip_id = int(post.get('dis_operasyon_tipi_id') or 0)
    ted_id = int(post.get('dis_tedarikci_id') or 0)
    if not tip_id or not ted_id:
        raise ValueError('Dış operasyon için taşeron ve dış operasyon tipi zorunludur.')
    depo_raw = (post.get('dis_gonderim_deposu_id') or '').strip()
    depo_id = int(depo_raw) if depo_raw else None
    bf = Decimal(post.get('dis_birim_fiyat') or '0')
    try:
        gun = int(post.get('dis_beklenen_donus_gun') or '7')
    except ValueError:
        gun = 7
    if gun < 0:
        gun = 0
    pb = (post.get('dis_para_birimi') or 'TL').strip()[:3]
    sevk = (post.get('dis_sevk_evrak_no') or '').strip()[:120]
    return {
        'dis_operasyon_tipi_id': tip_id,
        'dis_tedarikci_id': ted_id,
        'dis_gonderim_deposu_id': depo_id,
        'dis_birim_fiyat': bf,
        'dis_para_birimi': pb,
        'dis_beklenen_donus_gun': gun,
        'dis_sevk_evrak_no': sevk,
    }


GENEL_OPERASYON_LABEL = 'Genel Operasyon'


def _serialize_recete_operasyon(op):
    bagimliliklar_list = [{'id': b.pk, 'ad': b.operasyon.ad} for b in op.bagimliliklar.all()]
    genel = not op.recete_detay_id
    return {
        'id': op.pk,
        'recete_detay_id': op.recete_detay_id,
        'genel_operasyon': genel,
        'bilesen_kod': GENEL_OPERASYON_LABEL if genel else op.recete_detay.stok_item.stok_kodu,
        'bilesen_ad': '' if genel else op.recete_detay.stok_item.ad,
        'operasyon_id': op.operasyon.pk,
        'operasyon_ad': op.operasyon.ad,
        'akis_dis_operasyon': bool(op.operasyon.akis_dis_operasyon),
        'istasyon_id': op.istasyon.pk if op.istasyon else None,
        'istasyon_ad': op.istasyon.ad if op.istasyon else '',
        'standart_id': op.uretim_standarti.pk if op.uretim_standarti else None,
        'standart_kod': op.uretim_standarti.kod if op.uretim_standarti else None,
        'standart_ad': op.uretim_standarti.ad if op.uretim_standarti else None,
        'bagimliliklar': bagimliliklar_list,
        'maliyet': str(op.maliyet),
        'sure_dakika': op.sure_dakika,
        'sure_formatted': op.get_sure_formatted(),
        'toplam_maliyet': str(op.toplam_maliyet),
        'aciklama': op.aciklama,
        'sira': op.sira,
        'dis_operasyon_tipi_id': op.dis_operasyon_tipi_id,
        'dis_operasyon_tipi_ad': op.dis_operasyon_tipi.ad if op.dis_operasyon_tipi else '',
        'dis_tedarikci_id': op.dis_tedarikci_id,
        'dis_tedarikci_ad': op.dis_tedarikci.ad if op.dis_tedarikci else '',
        'dis_gonderim_deposu_id': op.dis_gonderim_deposu_id,
        'dis_birim_fiyat': str(op.dis_birim_fiyat),
        'dis_para_birimi': op.dis_para_birimi,
        'dis_beklenen_donus_gun': op.dis_beklenen_donus_gun,
        'dis_sevk_evrak_no': op.dis_sevk_evrak_no or '',
    }


def _recete_operasyon_tree_payload(recete):
    detaylar = recete.detaylar.select_related('stok_item').order_by('sira', 'id')
    operasyonlar = recete.operasyonlar.select_related(
        'operasyon', 'istasyon', 'uretim_standarti', 'dis_operasyon_tipi', 'dis_tedarikci',
        'recete_detay', 'recete_detay__stok_item',
    ).prefetch_related('bagimliliklar').order_by('recete_detay__sira', 'recete_detay_id', 'sira', 'id')
    ops_by_detay = {}
    toplam = Decimal('0')
    for op in operasyonlar:
        ops_by_detay.setdefault(op.recete_detay_id, []).append(_serialize_recete_operasyon(op))
        toplam += op.toplam_maliyet or Decimal('0')
    tree = []
    if None in ops_by_detay:
        tree.append({
            'detay_id': 0,
            'genel': True,
            'stok_kodu': GENEL_OPERASYON_LABEL,
            'stok_ad': '',
            'operasyonlar': ops_by_detay[None],
        })
    for detay in detaylar:
        if detay.pk in ops_by_detay:
            tree.append({
                'detay_id': detay.pk,
                'stok_item_id': detay.stok_item_id,
                'stok_kodu': detay.stok_item.stok_kodu,
                'stok_ad': detay.stok_item.ad,
                'operasyonlar': ops_by_detay[detay.pk],
            })
    flat = [op for node in tree for op in node['operasyonlar']]
    return tree, flat, toplam


@login_required
def recete_listesi(request):
    """Reçete listesi"""
    search_query = request.GET.get('search', '')
    receteler = Recete.objects.select_related('urun').all()
    
    if search_query:
        receteler = receteler.filter(
            Q(urun__stok_kodu__icontains=search_query) |
            Q(urun__ad__icontains=search_query) |
            Q(versiyon__icontains=search_query)
        )
    
    # Aktif/Pasif filtresi
    aktif_filter = request.GET.get('aktif', '')
    if aktif_filter == 'aktif':
        receteler = receteler.filter(aktif=True)
    elif aktif_filter == 'pasif':
        receteler = receteler.filter(aktif=False)
    
    receteler = receteler.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(receteler, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'stokapp/recete_listesi.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'aktif_filter': aktif_filter,
    })


@login_required
def recete_ekle(request):
    """Yeni reçete oluştur"""
    if request.method == 'POST':
        urun_id = request.POST.get('urun')
        versiyon = request.POST.get('versiyon', '1.0')
        aciklama = request.POST.get('aciklama', '')
        
        if not urun_id:
            messages.error(request, 'Lütfen bir stok seçin.')
            return redirect('stokapp:recete_ekle')
        
        urun = get_object_or_404(StokItem, pk=urun_id)
        
        # Aynı ürün ve versiyon kontrolü
        if Recete.objects.filter(urun=urun, versiyon=versiyon).exists():
            messages.error(request, f'{urun.stok_kodu} için {versiyon} versiyonu zaten mevcut.')
            return redirect('stokapp:recete_ekle')
        
        recete = Recete.objects.create(
            urun=urun,
            versiyon=versiyon,
            aciklama=aciklama,
            aktif=True
        )
        
        messages.success(request, f'{urun.stok_kodu} için reçete başarıyla oluşturuldu.')
        return redirect('stokapp:recete_detay', pk=recete.pk)
    
    # GET isteği - Tüm stok tipleri (Ham Madde, Yarı Mamül, Ürün)
    search_query = request.GET.get('search', '')
    stok_items = StokItem.objects.all()
    
    if search_query:
        stok_items = stok_items.filter(
            Q(stok_kodu__icontains=search_query) |
            Q(ad__icontains=search_query)
        )
    
    stok_items = stok_items.select_related('kategori').order_by('stok_kodu')
    
    return render(request, 'stokapp/recete_ekle.html', {
        'stok_items': stok_items,
        'search_query': search_query,
    })


@login_required
def recete_detay(request, pk):
    """Reçete detay sayfası"""
    from decimal import Decimal
    
    recete = get_object_or_404(Recete, pk=pk)
    detaylar = recete.detaylar.select_related('stok_item').order_by('sira', 'id')
    operasyonlar = recete.operasyonlar.select_related(
        'operasyon', 'istasyon', 'uretim_standarti', 'dis_operasyon_tipi', 'dis_tedarikci',
        'dis_gonderim_deposu', 'recete_detay', 'recete_detay__stok_item',
    ).prefetch_related('bagimliliklar').order_by('recete_detay__sira', 'recete_detay_id', 'sira', 'id')

    operasyon_agaci = []
    ops_by_detay = {}
    for op in operasyonlar:
        ops_by_detay.setdefault(op.recete_detay_id, []).append(op)
    if None in ops_by_detay:
        operasyon_agaci.append({
            'genel': True,
            'detay': None,
            'operasyonlar': ops_by_detay[None],
        })
    for detay in detaylar:
        if detay.pk in ops_by_detay:
            operasyon_agaci.append({
                'detay': detay,
                'operasyonlar': ops_by_detay[detay.pk],
            })
    
    # Operasyon, istasyon ve standart listelerini al (modal için)
    tum_operasyonlar = Operasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    tum_istasyonlar = Istasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    tum_standartlar = UretimStandarti.objects.filter(aktif=True).order_by('sira', 'kod')
    
    # Detaylar için birim fiyat ve tutar bilgilerini hazırla
    detaylar_with_prices = []
    toplam_by_para_birimi = {}  # Para birimi bazında toplamlar
    
    for detay in detaylar:
        birim_fiyat = detay.stok_item.alis_fiyati or Decimal('0')
        para_birimi = detay.stok_item.alis_para_birimi or 'TL'
        tutar = detay.miktar * birim_fiyat
        
        # Para birimi sembolünü belirle
        para_sembol = '₺' if para_birimi == 'TL' else \
                     '$' if para_birimi == 'USD' else \
                     '€' if para_birimi == 'EUR' else \
                     '£' if para_birimi == 'GBP' else para_birimi
        
        # Para birimi bazında toplam tut
        if para_birimi not in toplam_by_para_birimi:
            toplam_by_para_birimi[para_birimi] = {
                'toplam': Decimal('0'),
                'para_sembol': para_sembol,
            }
        toplam_by_para_birimi[para_birimi]['toplam'] += tutar
        
        detaylar_with_prices.append({
            'detay': detay,
            'birim_fiyat': birim_fiyat,
            'para_birimi': para_birimi,
            'para_sembol': para_sembol,
            'tutar': tutar,
        })
    
    # Operasyonlar toplam maliyetini hesapla
    operasyonlar_toplam_maliyet = Decimal('0')
    for op in operasyonlar:
        operasyonlar_toplam_maliyet += op.toplam_maliyet or Decimal('0')
    
    # Ekipman, fikstür ve ölçü aleti listeleri (talimatlar için)
    from .models import OlcuAleti
    tum_ekipmanlar = Ekipman.objects.filter(aktif=True).order_by('sira', 'ekipman_numarasi')
    tum_fiksturler = Fikstur.objects.filter(aktif=True).order_by('sira', 'fikstur_numarasi')
    tum_olcu_aletleri = OlcuAleti.objects.filter(aktif=True).order_by('seri_no')
    dis_tipleri = DisOperasyonTipi.objects.filter(aktif=True, ic_dis_tipi='DIS').order_by('ad')
    dis_tedarikciler = Tedarikci.objects.filter(aktif=True).order_by('ad')[:400]
    dis_depolar = Depo.objects.all().order_by('ad')
    para_birimleri = list(StokItem.PARA_BIRIMLERI)

    detay_sira_post_url = reverse('stokapp:recete_detay_sira_kaydet', kwargs={'pk': recete.pk})
    operasyon_sira_post_url = reverse('stokapp:recete_operasyon_sira_kaydet', kwargs={'pk': recete.pk})

    return render(request, 'stokapp/recete_detay.html', {
        'recete': recete,
        'detaylar': detaylar,
        'detaylar_with_prices': detaylar_with_prices,
        'toplam_by_para_birimi': toplam_by_para_birimi,
        'operasyonlar': operasyonlar,
        'operasyon_agaci': operasyon_agaci,
        'operasyonlar_toplam_maliyet': operasyonlar_toplam_maliyet,  # Operasyonlar toplam maliyeti
        'tum_operasyonlar': tum_operasyonlar,
        'tum_istasyonlar': tum_istasyonlar,
        'tum_standartlar': tum_standartlar,
        'tum_ekipmanlar': tum_ekipmanlar,
        'tum_fiksturler': tum_fiksturler,
        'tum_olcu_aletleri': tum_olcu_aletleri,
        'dis_tipleri': dis_tipleri,
        'dis_tedarikciler': dis_tedarikciler,
        'dis_depolar': dis_depolar,
        'para_birimleri': para_birimleri,
        'detay_sira_post_url': detay_sira_post_url,
        'operasyon_sira_post_url': operasyon_sira_post_url,
    })


def _para_sembol(para_birimi):
    return {
        'TL': '₺',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
    }.get(para_birimi or 'TL', para_birimi or 'TL')


def _build_recete_bilesen_fiyatlari(detaylar):
    detaylar_with_prices = []
    toplam_by_para_birimi = {}
    for detay in detaylar:
        birim_fiyat = detay.stok_item.alis_fiyati or Decimal('0')
        para_birimi = detay.stok_item.alis_para_birimi or 'TL'
        tutar = detay.miktar * birim_fiyat
        para_sembol = _para_sembol(para_birimi)
        if para_birimi not in toplam_by_para_birimi:
            toplam_by_para_birimi[para_birimi] = {
                'toplam': Decimal('0'),
                'para_sembol': para_sembol,
            }
        toplam_by_para_birimi[para_birimi]['toplam'] += tutar
        detaylar_with_prices.append({
            'detay': detay,
            'birim_fiyat': birim_fiyat,
            'para_birimi': para_birimi,
            'para_sembol': para_sembol,
            'tutar': tutar,
        })
    return detaylar_with_prices, toplam_by_para_birimi


def _recete_detay_json(detay):
    """Reçete bileşeni JSON — birim fiyat her zaman stok kartındaki güncel alış fiyatından."""
    birim_fiyat = float(detay.stok_item.alis_fiyati or 0)
    para_birimi = detay.stok_item.alis_para_birimi or 'TL'
    tutar = float(detay.miktar) * birim_fiyat
    para_sembol = _para_sembol(para_birimi)
    return {
        'id': detay.pk,
        'stok_item_id': detay.stok_item_id,
        'stok_kodu': detay.stok_item.stok_kodu,
        'ad': detay.stok_item.ad,
        'miktar': str(detay.miktar),
        'birim': detay.birim,
        'sira': detay.sira,
        'birim_fiyat': birim_fiyat,
        'tutar': tutar,
        'para_birimi': para_birimi,
        'para_sembol': para_sembol,
    }


def _recete_bilesen_toplam_list(recete):
    toplam_by_para_birimi = {}
    for d in recete.detaylar.select_related('stok_item').all():
        bf = d.stok_item.alis_fiyati or Decimal('0')
        pb = d.stok_item.alis_para_birimi or 'TL'
        t = d.miktar * bf
        ps = _para_sembol(pb)
        if pb not in toplam_by_para_birimi:
            toplam_by_para_birimi[pb] = {'toplam': Decimal('0'), 'para_sembol': ps}
        toplam_by_para_birimi[pb]['toplam'] += t
    return [
        {
            'para_birimi': k,
            'toplam': float(v['toplam']),
            'para_sembol': v['para_sembol'],
        }
        for k, v in toplam_by_para_birimi.items()
    ]


def _build_recete_operasyon_agaci(operasyonlar, detaylar):
    operasyon_agaci = []
    ops_by_detay = {}
    for op in operasyonlar:
        ops_by_detay.setdefault(op.recete_detay_id, []).append(op)
    if None in ops_by_detay:
        operasyon_agaci.append({
            'genel': True,
            'detay': None,
            'operasyonlar': ops_by_detay[None],
        })
    for detay in detaylar:
        if detay.pk in ops_by_detay:
            operasyon_agaci.append({
                'genel': False,
                'detay': detay,
                'operasyonlar': ops_by_detay[detay.pk],
            })
    return operasyon_agaci


def _build_recete_dis_operasyon_agaci(recete, detaylar):
    atamalar = recete.dis_operasyon_atamalari.select_related(
        'dis_operasyon_tipi', 'tedarikci', 'dis_gonderim_deposu',
        'recete_detay', 'recete_detay__stok_item',
    ).order_by('recete_detay__sira', 'recete_detay_id', 'sira', 'id')
    by_detay = {}
    for item in atamalar:
        by_detay.setdefault(item.recete_detay_id, []).append(item)
    agaci = []
    if None in by_detay:
        agaci.append({'genel': True, 'detay': None, 'atamalar': by_detay[None]})
    for detay in detaylar:
        if detay.pk in by_detay:
            agaci.append({'genel': False, 'detay': detay, 'atamalar': by_detay[detay.pk]})
    return agaci, atamalar


def _build_recete_talimatlar(recete):
    return recete.talimatlar.prefetch_related(
        'olculer', 'dosyalar', 'ekipmanlar', 'programlar',
        'fiksturler', 'olcu_aletleri', 'ek_aciklamalar',
        'kurulum_dosyalari__kurulum_dosyasi__urun',
        'kurulum_dosyalari__kurulum_dosyasi__istasyon',
    ).order_by('sira', 'id')


def _build_recete_dosya_ozeti(talimatlar):
    dosyalar = []
    for talimat in talimatlar:
        for dosya in talimat.dosyalar.all():
            dosyalar.append({
                'talimat_sira': talimat.sira,
                'kaynak': f'Talimat #{talimat.sira}',
                'aciklama': dosya.aciklama,
                'dosya_adi': dosya.dosya_adi or (dosya.dosya.name.split('/')[-1] if dosya.dosya else ''),
                'dosya_tipi': dosya.dosya_tipi or '-',
            })
        for kurulum in talimat.kurulum_dosyalari.all():
            kd = kurulum.kurulum_dosyasi
            dosyalar.append({
                'talimat_sira': talimat.sira,
                'kaynak': f'Talimat #{talimat.sira} — Kurulum',
                'aciklama': kd.aciklama or '',
                'dosya_adi': f'{kd.urun.stok_kodu} v{kd.versiyon}' if kd.urun_id else f'Kurulum v{kd.versiyon}',
                'dosya_tipi': 'kurulum_pdf',
            })
    return dosyalar


def _recete_detay_pdf_context(recete):
    detaylar = recete.detaylar.select_related('stok_item').order_by('sira', 'id')
    operasyonlar = recete.operasyonlar.select_related(
        'operasyon', 'istasyon', 'uretim_standarti', 'dis_operasyon_tipi', 'dis_tedarikci',
        'dis_gonderim_deposu', 'recete_detay', 'recete_detay__stok_item',
    ).prefetch_related('bagimliliklar').order_by('recete_detay__sira', 'recete_detay_id', 'sira', 'id')
    detaylar_with_prices, toplam_by_para_birimi = _build_recete_bilesen_fiyatlari(detaylar)
    operasyon_agaci = _build_recete_operasyon_agaci(operasyonlar, detaylar)
    operasyonlar_toplam_maliyet = sum(
        (op.toplam_maliyet or Decimal('0')) for op in operasyonlar
    )
    dis_operasyon_agaci, dis_operasyonlar = _build_recete_dis_operasyon_agaci(recete, detaylar)
    talimatlar = _build_recete_talimatlar(recete)
    dosya_ozeti = _build_recete_dosya_ozeti(talimatlar)
    return {
        'recete': recete,
        'detaylar': detaylar,
        'detaylar_with_prices': detaylar_with_prices,
        'toplam_by_para_birimi': toplam_by_para_birimi,
        'operasyonlar': operasyonlar,
        'operasyon_agaci': operasyon_agaci,
        'operasyonlar_toplam_maliyet': operasyonlar_toplam_maliyet,
        'dis_operasyon_agaci': dis_operasyon_agaci,
        'dis_operasyonlar': dis_operasyonlar,
        'talimatlar': talimatlar,
        'dosya_ozeti': dosya_ozeti,
    }


@login_required
@never_cache
def recete_detay_export_pdf(request, pk):
    recete = get_object_or_404(Recete, pk=pk)

    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:recete_detay', pk=pk)

    from django.template.loader import get_template
    from django.utils import timezone

    olusturma_tarihi = timezone.localtime(timezone.now())
    template = get_template('stokapp/recete_detay_pdf.html')
    context = _recete_detay_pdf_context(recete)
    context['olusturma_tarihi'] = olusturma_tarihi
    html = template.render(context)
    css = CSS(string="""
        @page { size: A4 portrait; margin: 10mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9pt; color: #111827; }
        h1 { font-size: 14pt; margin: 0 0 4px 0; }
        h2 { font-size: 11pt; margin: 16px 0 6px 0; page-break-after: avoid; }
        h3 { font-size: 9.5pt; margin: 10px 0 4px 0; color: #374151; page-break-after: avoid; }
        .meta { color: #6b7280; font-size: 8pt; margin-bottom: 10px; }
        .section { margin-bottom: 14px; page-break-inside: avoid; }
        .node-box { border: 1px solid #d1d5db; border-radius: 4px; margin-bottom: 8px; overflow: hidden; }
        .node-header { background: #f3f4f6; padding: 6px 8px; font-weight: 600; font-size: 8.5pt; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
        th { background: #34495e; color: #fff; border: 1px solid #d1d5db; padding: 5px 4px; text-align: left; font-size: 7.5pt; }
        td { border: 1px solid #e5e7eb; padding: 4px; vertical-align: top; font-size: 7.5pt; }
        .num { text-align: right; white-space: nowrap; }
        .empty { text-align: center; color: #6b7280; padding: 16px; font-size: 8pt; }
        .talimat-block { border: 1px solid #e5e7eb; border-radius: 4px; padding: 8px; margin-bottom: 10px; page-break-inside: avoid; }
        .talimat-title { font-weight: 700; margin-bottom: 6px; }
        .sub-table th { background: #f3f4f6; color: #111827; }
        .muted { color: #6b7280; font-size: 7pt; }
        .pre-wrap { white-space: pre-wrap; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:recete_detay', pk=pk)

    filename = f'recete_detay_{recete.urun.stok_kodu}_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def recete_duzenle(request, pk):
    """Reçete düzenle"""
    recete = get_object_or_404(Recete, pk=pk)

    search_query = request.GET.get('search', '')

    def stok_items_queryset(ensure_pks=None):
        """Arama daraltılmış olsa bile seçili reçete ürünü (ve hata durumunda denenen ürün) listede kalsın."""
        qs = StokItem.objects.all()
        if search_query:
            qs = qs.filter(
                Q(stok_kodu__icontains=search_query) |
                Q(ad__icontains=search_query)
            )
        ids = list(qs.values_list('pk', flat=True))
        for pk in (ensure_pks or []):
            if pk and pk not in ids:
                ids.append(pk)
        if recete.urun_id not in ids:
            ids.append(recete.urun_id)
        return StokItem.objects.filter(pk__in=ids).select_related('kategori').order_by('stok_kodu')

    if request.method == 'POST':
        urun_id = request.POST.get('urun')
        versiyon = (request.POST.get('versiyon') or recete.versiyon or '1.0').strip() or '1.0'
        aciklama = request.POST.get('aciklama', '')
        aktif = request.POST.get('aktif') == 'on'

        ctx_base = {
            'recete': recete,
            'stok_items': stok_items_queryset(),
            'search_query': search_query,
        }

        if not urun_id:
            messages.error(request, 'Lütfen bir stok seçin.')
            ctx_base['posted'] = {
                'versiyon': versiyon,
                'aciklama': aciklama,
                'aktif': aktif,
                'urun_id': str(recete.urun.pk),
            }
            return render(request, 'stokapp/recete_duzenle.html', ctx_base)

        yeni_urun = get_object_or_404(StokItem, pk=urun_id)

        if Recete.objects.filter(urun=yeni_urun, versiyon=versiyon).exclude(pk=recete.pk).exists():
            messages.error(
                request,
                f'{yeni_urun.stok_kodu} için {versiyon} versiyonu zaten başka bir reçetede mevcut.',
            )
            ctx_base['stok_items'] = stok_items_queryset(ensure_pks=[yeni_urun.pk])
            ctx_base['posted'] = {
                'versiyon': versiyon,
                'aciklama': aciklama,
                'aktif': aktif,
                'urun_id': str(yeni_urun.pk),
            }
            return render(request, 'stokapp/recete_duzenle.html', ctx_base)

        recete.urun = yeni_urun
        recete.versiyon = versiyon
        recete.aciklama = aciklama
        recete.aktif = aktif
        recete.save()

        messages.success(request, 'Reçete başarıyla güncellendi.')
        return redirect('stokapp:recete_detay', pk=recete.pk)

    return render(request, 'stokapp/recete_duzenle.html', {
        'recete': recete,
        'stok_items': stok_items_queryset(),
        'search_query': search_query,
    })


@login_required
def recete_sil(request, pk):
    """Reçete sil"""
    from django.db.models.deletion import ProtectedError
    
    recete = get_object_or_404(Recete, pk=pk)
    
    if request.method == 'POST':
        try:
            urun_kodu = recete.urun.stok_kodu
            
            # Silmeden önce kontrol et - UretimEmri ile bağlantısı var mı?
            try:
                from .models import UretimEmri
                uretim_emirleri = UretimEmri.objects.filter(recete=recete)
                if uretim_emirleri.exists():
                    uretim_listesi = []
                    for emir in uretim_emirleri[:10]:  # İlk 10'unu göster
                        uretim_listesi.append(f"{emir.emir_no} ({emir.durum})")
                    
                    if len(uretim_emirleri) > 10:
                        uretim_listesi.append(f"... ve {len(uretim_emirleri) - 10} adet daha")
                    
                    if len(uretim_listesi) > 0:
                        messages.error(
                            request, 
                            f'"{urun_kodu}" reçetesi silinemiyor çünkü {uretim_emirleri.count()} üretim emrinde kullanılıyor. '
                            f'Önce ilgili üretim emirlerini silmeniz veya farklı bir reçete atamanız gerekiyor.\n\n'
                            f'İlgili üretim emirleri: {", ".join(uretim_listesi)}'
                        )
                    else:
                        messages.error(
                            request, 
                            f'"{urun_kodu}" reçetesi silinemiyor çünkü {uretim_emirleri.count()} üretim emrinde kullanılıyor. '
                            f'Önce ilgili üretim emirlerini silmeniz veya farklı bir reçete atamanız gerekiyor.'
                        )
                    return redirect('stokapp:recete_listesi')
            except ImportError:
                pass  # UretimEmri modeli yoksa devam et
            
            recete.delete()
            messages.success(request, f'"{urun_kodu}" reçetesi başarıyla silindi.')
            return redirect('stokapp:recete_listesi')
            
        except ProtectedError as e:
            # Django'nun ProtectedError'unu yakala
            urun_kodu = recete.urun.stok_kodu
            protected_objects = e.protected_objects
            
            error_msg = f'"{urun_kodu}" reçetesi silinemiyor çünkü başka kayıtlarda kullanılıyor:\n\n'
            
            # UretimEmri kontrolü
            try:
                from .models import UretimEmri
                uretim_emirleri = UretimEmri.objects.filter(recete=recete)
                if uretim_emirleri.exists():
                    uretim_listesi = []
                    for emir in uretim_emirleri[:10]:
                        uretim_listesi.append(f"{emir.emir_no} ({emir.durum})")
                    
                    if len(uretim_emirleri) > 10:
                        uretim_listesi.append(f"... ve {len(uretim_emirleri) - 10} adet daha")
                    
                    error_msg += f"• {uretim_emirleri.count()} üretim emrinde kullanılıyor: {', '.join(uretim_listesi)}\n\n"
                    error_msg += "Önce ilgili üretim emirlerini silmeniz veya farklı bir reçete atamanız gerekiyor."
                    
                    messages.error(request, error_msg)
                    return redirect('stokapp:recete_listesi')
            except ImportError:
                pass
            
            messages.error(request, f'"{urun_kodu}" reçetesi silinemiyor: Başka kayıtlarda kullanılıyor.')
            return redirect('stokapp:recete_listesi')
            
        except Exception as e:
            import traceback
            urun_kodu = recete.urun.stok_kodu
            messages.error(request, f'Reçete silinirken hata oluştu: {str(e)}')
            print(f"Error: {str(e)}")
            print(traceback.format_exc())
            return redirect('stokapp:recete_listesi')
    
    return render(request, 'stokapp/recete_sil.html', {
        'recete': recete,
    })


@login_required
@require_POST
def recete_kopyala(request, pk):
    """Reçeteyi tüm bilgileri (detaylar, operasyonlar, talimatlar ve alt kayıtlar) ile birlikte kopyala.

    Aynı ürün için yeni bir versiyon (örn. 'X' -> 'X_kopya', çakışma varsa 'X_kopya_1', 'X_kopya_2', ...)
    oluşturulur.
    """
    orijinal = get_object_or_404(
        Recete.objects.select_related('urun'),
        pk=pk,
    )

    try:
        with transaction.atomic():
            yeni_versiyon = f"{orijinal.versiyon}_kopya"
            sayac = 1
            while Recete.objects.filter(urun=orijinal.urun, versiyon=yeni_versiyon).exists():
                yeni_versiyon = f"{orijinal.versiyon}_kopya_{sayac}"
                sayac += 1

            yeni_recete = Recete.objects.create(
                urun=orijinal.urun,
                versiyon=yeni_versiyon,
                aktif=orijinal.aktif,
                aciklama=orijinal.aciklama,
            )

            detay_map = {}
            for detay in orijinal.detaylar.all():
                yeni_detay = ReceteDetay.objects.create(
                    recete=yeni_recete,
                    stok_item=detay.stok_item,
                    miktar=detay.miktar,
                    birim=detay.birim,
                    sira=detay.sira,
                )
                detay_map[detay.pk] = yeni_detay

            operasyon_map = {}
            for op in orijinal.operasyonlar.all():
                if op.recete_detay_id:
                    yeni_detay = detay_map.get(op.recete_detay_id)
                    if yeni_detay is None:
                        continue
                else:
                    yeni_detay = None
                yeni_op = ReceteOperasyon.objects.create(
                    recete=yeni_recete,
                    recete_detay=yeni_detay,
                    operasyon=op.operasyon,
                    istasyon=op.istasyon,
                    uretim_standarti=op.uretim_standarti,
                    maliyet=op.maliyet,
                    sure_dakika=op.sure_dakika,
                    toplam_maliyet=op.toplam_maliyet,
                    aciklama=op.aciklama,
                    sira=op.sira,
                    dis_operasyon_tipi_id=op.dis_operasyon_tipi_id,
                    dis_tedarikci_id=op.dis_tedarikci_id,
                    dis_gonderim_deposu_id=op.dis_gonderim_deposu_id,
                    dis_birim_fiyat=op.dis_birim_fiyat,
                    dis_para_birimi=op.dis_para_birimi,
                    dis_beklenen_donus_gun=op.dis_beklenen_donus_gun,
                    dis_sevk_evrak_no=op.dis_sevk_evrak_no or '',
                )
                operasyon_map[op.pk] = yeni_op

            # Operasyonlar arası bağımlılıkları yeni operasyon nesnelerine taşı
            for op in orijinal.operasyonlar.all():
                yeni_op = operasyon_map.get(op.pk)
                if yeni_op is None:
                    continue
                bagimli_yeniler = [
                    operasyon_map[bag.pk]
                    for bag in op.bagimliliklar.all()
                    if bag.pk in operasyon_map
                ]
                if bagimli_yeniler:
                    yeni_op.bagimliliklar.set(bagimli_yeniler)

            for dis_atama in orijinal.dis_operasyon_atamalari.all():
                if dis_atama.recete_detay_id:
                    yeni_detay = detay_map.get(dis_atama.recete_detay_id)
                    if yeni_detay is None:
                        continue
                else:
                    yeni_detay = None
                ReceteDisOperasyon.objects.create(
                    recete=yeni_recete,
                    recete_detay=yeni_detay,
                    dis_operasyon_tipi=dis_atama.dis_operasyon_tipi,
                    tedarikci=dis_atama.tedarikci,
                    dis_gonderim_deposu=dis_atama.dis_gonderim_deposu,
                    dis_birim_fiyat=dis_atama.dis_birim_fiyat,
                    dis_para_birimi=dis_atama.dis_para_birimi,
                    dis_beklenen_donus_gun=dis_atama.dis_beklenen_donus_gun,
                    aciklama=dis_atama.aciklama,
                    sira=dis_atama.sira,
                )

            for tal in orijinal.talimatlar.all():
                yeni_tal = ReceteTalimat.objects.create(
                    recete=yeni_recete,
                    sira=tal.sira,
                    aciklama=tal.aciklama,
                )

                for olcu in tal.olculer.all():
                    ReceteTalimatOlcu.objects.create(
                        talimat=yeni_tal,
                        aciklama=olcu.aciklama,
                        nominal_deger=olcu.nominal_deger,
                        birim=olcu.birim,
                        min_deger=olcu.min_deger,
                        max_deger=olcu.max_deger,
                        sira=olcu.sira,
                    )

                for dosya in tal.dosyalar.all():
                    # Dosya referansı paylaşılır (FileField aynı dosyayı işaret eder)
                    ReceteTalimatDosya.objects.create(
                        talimat=yeni_tal,
                        aciklama=dosya.aciklama,
                        dosya=dosya.dosya,
                        dosya_adi=dosya.dosya_adi,
                        dosya_tipi=dosya.dosya_tipi,
                    )

                for ekp in tal.ekipmanlar.all():
                    ReceteTalimatEkipman.objects.create(
                        talimat=yeni_tal,
                        ekipman=ekp.ekipman,
                        sira=ekp.sira,
                    )

                for fks in tal.fiksturler.all():
                    ReceteTalimatFikstur.objects.create(
                        talimat=yeni_tal,
                        fikstur=fks.fikstur,
                        sira=fks.sira,
                    )

                for prg in tal.programlar.all():
                    ReceteTalimatProgram.objects.create(
                        talimat=yeni_tal,
                        program_adi=prg.program_adi,
                        aciklama=prg.aciklama,
                        sira=prg.sira,
                    )

                for ol_aleti in tal.olcu_aletleri.all():
                    ReceteTalimatOlcuAleti.objects.create(
                        talimat=yeni_tal,
                        olcu_aleti=ol_aleti.olcu_aleti,
                        sira=ol_aleti.sira,
                    )

                for ek_acik in tal.ek_aciklamalar.all():
                    ReceteTalimatAciklama.objects.create(
                        talimat=yeni_tal,
                        aciklama=ek_acik.aciklama,
                        sira=ek_acik.sira,
                    )

                # Kurulum dosyaları (ileri uyumlu - varsa kopyala, yoksa atla)
                try:
                    for krl in tal.kurulum_dosyalari.all():
                        ReceteTalimatKurulumDosyasi.objects.create(
                            talimat=yeni_tal,
                            kurulum_dosyasi=krl.kurulum_dosyasi,
                            sira=krl.sira,
                        )
                except Exception:
                    pass

        messages.success(
            request,
            f'Reçete kopyalandı: "{orijinal.urun.stok_kodu} v{orijinal.versiyon}" → '
            f'"{orijinal.urun.stok_kodu} v{yeni_versiyon}"'
        )
        return redirect('stokapp:recete_detay', pk=yeni_recete.pk)

    except Exception as e:
        messages.error(request, f'Reçete kopyalanırken hata oluştu: {str(e)}')
        return redirect('stokapp:recete_listesi')


@login_required
@require_http_methods(["GET"])
def recete_stok_ara(request):
    """AJAX: Reçete bileşeni için stok arama - Tüm stok tiplerini getir"""
    search_query = request.GET.get('q', '')
    
    # Tüm stok tiplerini getir (Ham Madde, Yarı Mamül, Ürün)
    stok_items = StokItem.objects.select_related('kategori').all()
    
    if search_query:
        stok_items = stok_multi_term_filter(stok_items, search_query)
    
    stok_items = stok_items.order_by('stok_kodu')[:20]  # İlk 20 sonuç
    
    results = []
    for item in stok_items:
        birim_fiyat = float(item.alis_fiyati or 0)
        para_birimi = item.alis_para_birimi or 'TL'
        
        # Para birimi sembolünü belirle
        para_sembol = '₺' if para_birimi == 'TL' else \
                     '$' if para_birimi == 'USD' else \
                     '€' if para_birimi == 'EUR' else \
                     '£' if para_birimi == 'GBP' else para_birimi
        
        # Stok tipini belirle: önce stok_tipi alanını kontrol et, yoksa kategori'den al
        # item.stok_tipi None veya boş string olabilir
        if item.stok_tipi:
            # stok_tipi string ise strip yap, değilse direkt kullan
            stok_tipi = item.stok_tipi.strip() if isinstance(item.stok_tipi, str) else item.stok_tipi
            if not stok_tipi:  # Boş string ise
                stok_tipi = None
        else:
            stok_tipi = None
        
        # Eğer stok_tipi yoksa kategori'den al
        if not stok_tipi and item.kategori:
            stok_tipi = item.kategori.stok_tipi
        
        # Hala yoksa varsayılan
        if not stok_tipi:
            stok_tipi = 'HAM_MADDE'
        
        results.append({
            'id': item.pk,
            'stok_kodu': item.stok_kodu,
            'ad': item.ad,
            'birim': item.birim,
            'stok_tipi': stok_tipi,
            'birim_fiyat': birim_fiyat,
            'para_birimi': para_birimi,
            'para_sembol': para_sembol,
        })
    
    return JsonResponse({'results': results})


@login_required
@require_http_methods(["GET"])
def recete_kaynak_ara(request):
    """AJAX: Başka reçeteden kopyalamak için ürün/reçete arama."""
    search_query = (request.GET.get("q") or "").strip()
    exclude_pk = request.GET.get("exclude")
    tip = (request.GET.get("tip") or "").strip()  # bilesenler | operasyonlar | dis_operasyonlar

    qs = Recete.objects.select_related("urun").annotate(
        bilesen_count=Count("detaylar", distinct=True),
        op_count=Count("operasyonlar", distinct=True),
        dis_count=Count("dis_operasyon_atamalari", distinct=True),
    )
    if exclude_pk:
        try:
            qs = qs.exclude(pk=int(exclude_pk))
        except (TypeError, ValueError):
            pass
    if search_query:
        qs = stok_multi_term_filter(
            qs, search_query, kod_field="urun__stok_kodu", ad_field="urun__ad"
        )
    if tip == "bilesenler":
        qs = qs.filter(bilesen_count__gt=0)
    elif tip == "operasyonlar":
        qs = qs.filter(op_count__gt=0)
    elif tip == "dis_operasyonlar":
        qs = qs.filter(dis_count__gt=0)

    qs = qs.order_by("-aktif", "-id")[:20]
    results = [
        {
            "recete_id": r.pk,
            "stok_kodu": r.urun.stok_kodu,
            "ad": r.urun.ad,
            "versiyon": r.versiyon,
            "aktif": r.aktif,
            "bilesen_count": r.bilesen_count,
            "op_count": r.op_count,
            "dis_count": r.dis_count,
        }
        for r in qs
    ]
    return JsonResponse({"results": results})


def _hedef_detay_by_stok(hedef: Recete) -> dict:
    return {d.stok_item_id: d for d in hedef.detaylar.all()}


@login_required
@require_http_methods(["POST"])
def recete_disaridan_kopyala(request, pk):
    """
    Başka bir reçetenin bileşen / operasyon / dış operasyon kayıtlarını
    bu reçeteye kopyalar (üzerine ekler).
    """
    hedef = get_object_or_404(Recete, pk=pk)
    kaynak_id = request.POST.get("kaynak_recete_id")
    tip = (request.POST.get("tip") or "").strip()

    if tip not in ("bilesenler", "operasyonlar", "dis_operasyonlar"):
        return JsonResponse({"success": False, "error": "Geçersiz kopyalama tipi."}, status=400)
    try:
        kaynak = Recete.objects.select_related("urun").get(pk=int(kaynak_id))
    except (TypeError, ValueError, Recete.DoesNotExist):
        return JsonResponse({"success": False, "error": "Kaynak reçete bulunamadı."}, status=404)
    if kaynak.pk == hedef.pk:
        return JsonResponse(
            {"success": False, "error": "Aynı reçeteden kopyalama yapılamaz."},
            status=400,
        )

    eklenen = 0
    atlanan = 0

    try:
        with transaction.atomic():
            if tip == "bilesenler":
                mevcut = set(
                    hedef.detaylar.values_list("stok_item_id", flat=True)
                )
                max_sira = hedef.detaylar.aggregate(m=Max("sira")).get("m") or 0
                for detay in kaynak.detaylar.order_by("sira", "id"):
                    if detay.stok_item_id in mevcut:
                        atlanan += 1
                        continue
                    max_sira += 1
                    ReceteDetay.objects.create(
                        recete=hedef,
                        stok_item=detay.stok_item,
                        miktar=detay.miktar,
                        birim=detay.birim,
                        sira=max_sira,
                    )
                    mevcut.add(detay.stok_item_id)
                    eklenen += 1

            elif tip == "operasyonlar":
                hedef_by_stok = _hedef_detay_by_stok(hedef)
                max_sira = hedef.operasyonlar.aggregate(m=Max("sira")).get("m") or 0
                operasyon_map = {}
                for op in kaynak.operasyonlar.select_related(
                    "recete_detay", "operasyon"
                ).order_by("sira", "id"):
                    if op.recete_detay_id and op.recete_detay:
                        hedef_detay = hedef_by_stok.get(op.recete_detay.stok_item_id)
                    else:
                        hedef_detay = None
                    max_sira += 1
                    yeni_op = ReceteOperasyon.objects.create(
                        recete=hedef,
                        recete_detay=hedef_detay,
                        operasyon=op.operasyon,
                        istasyon=op.istasyon,
                        uretim_standarti=op.uretim_standarti,
                        maliyet=op.maliyet,
                        sure_dakika=op.sure_dakika,
                        toplam_maliyet=op.toplam_maliyet,
                        aciklama=op.aciklama,
                        sira=max_sira,
                        dis_operasyon_tipi_id=op.dis_operasyon_tipi_id,
                        dis_tedarikci_id=op.dis_tedarikci_id,
                        dis_gonderim_deposu_id=op.dis_gonderim_deposu_id,
                        dis_birim_fiyat=op.dis_birim_fiyat,
                        dis_para_birimi=op.dis_para_birimi,
                        dis_beklenen_donus_gun=op.dis_beklenen_donus_gun,
                        dis_sevk_evrak_no=op.dis_sevk_evrak_no or "",
                    )
                    operasyon_map[op.pk] = yeni_op
                    eklenen += 1

                for op in kaynak.operasyonlar.prefetch_related("bagimliliklar"):
                    yeni_op = operasyon_map.get(op.pk)
                    if yeni_op is None:
                        continue
                    bagimli = [
                        operasyon_map[b.pk]
                        for b in op.bagimliliklar.all()
                        if b.pk in operasyon_map
                    ]
                    if bagimli:
                        yeni_op.bagimliliklar.set(bagimli)

            else:  # dis_operasyonlar
                hedef_by_stok = _hedef_detay_by_stok(hedef)
                max_sira = (
                    hedef.dis_operasyon_atamalari.aggregate(m=Max("sira")).get("m") or 0
                )
                for dis in kaynak.dis_operasyon_atamalari.select_related(
                    "recete_detay", "dis_operasyon_tipi"
                ).order_by("sira", "id"):
                    if dis.recete_detay_id and dis.recete_detay:
                        hedef_detay = hedef_by_stok.get(dis.recete_detay.stok_item_id)
                    else:
                        hedef_detay = None
                    max_sira += 1
                    ReceteDisOperasyon.objects.create(
                        recete=hedef,
                        recete_detay=hedef_detay,
                        dis_operasyon_tipi=dis.dis_operasyon_tipi,
                        tedarikci=dis.tedarikci,
                        dis_gonderim_deposu=dis.dis_gonderim_deposu,
                        dis_birim_fiyat=dis.dis_birim_fiyat,
                        dis_para_birimi=dis.dis_para_birimi,
                        dis_beklenen_donus_gun=dis.dis_beklenen_donus_gun,
                        aciklama=dis.aciklama,
                        sira=max_sira,
                    )
                    eklenen += 1
    except Exception as exc:
        return JsonResponse(
            {"success": False, "error": f"Kopyalama sırasında hata: {exc}"},
            status=500,
        )

    tip_label = {
        "bilesenler": "bileşen",
        "operasyonlar": "operasyon",
        "dis_operasyonlar": "dış operasyon",
    }[tip]
    msg = f"{eklenen} {tip_label} kopyalandı"
    if atlanan:
        msg += f" ({atlanan} zaten vardı, atlandı)"
    msg += f" — kaynak: {kaynak.urun.stok_kodu} v{kaynak.versiyon}"

    return JsonResponse(
        {
            "success": True,
            "message": msg,
            "eklenen": eklenen,
            "atlanan": atlanan,
            "tip": tip,
        }
    )


@login_required
@require_http_methods(["POST"])
def recete_detay_ekle(request, pk):
    """AJAX: Reçete bileşeni ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    
    stok_item_id = request.POST.get('stok_item_id')
    miktar = request.POST.get('miktar')
    birim = request.POST.get('birim')
    sira = request.POST.get('sira', 0)
    
    if not stok_item_id or not miktar:
        return JsonResponse({'success': False, 'error': 'Stok ve miktar zorunludur.'}, status=400)
    
    try:
        stok_item = get_object_or_404(StokItem, pk=stok_item_id)
        
        # Aynı stok item'ın bu reçetede zaten olup olmadığını kontrol et
        if ReceteDetay.objects.filter(recete=recete, stok_item=stok_item).exists():
            return JsonResponse({'success': False, 'error': 'Bu stok zaten reçetede mevcut.'}, status=400)
        
        # Sıra numarasını belirle
        if not sira or sira == '0':
            max_sira = ReceteDetay.objects.filter(recete=recete).aggregate(Max('sira'))['sira__max']
            sira = (max_sira or 0) + 1
        
        detay = ReceteDetay.objects.create(
            recete=recete,
            stok_item=stok_item,
            miktar=miktar,
            birim=birim or stok_item.birim,
            sira=int(sira)
        )
        
        # Birim fiyat ve tutar bilgilerini hesapla (alış fiyatını kullan)
        birim_fiyat = float(detay.stok_item.alis_fiyati or 0)
        para_birimi = detay.stok_item.alis_para_birimi or 'TL'
        tutar = float(detay.miktar) * birim_fiyat
        
        # Para birimi sembolünü belirle
        para_sembol = '₺' if para_birimi == 'TL' else \
                     '$' if para_birimi == 'USD' else \
                     '€' if para_birimi == 'EUR' else \
                     '£' if para_birimi == 'GBP' else para_birimi
        
        return JsonResponse({
            'success': True,
            'detay': {
                'id': detay.pk,
                'stok_item_id': detay.stok_item_id,
                'stok_kodu': detay.stok_item.stok_kodu,
                'ad': detay.stok_item.ad,
                'miktar': str(detay.miktar),
                'birim': detay.birim,
                'sira': detay.sira,
                'birim_fiyat': birim_fiyat,
                'tutar': tutar,
                'para_birimi': para_birimi,
                'para_sembol': para_sembol,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_detay_degistir(request, pk, detay_id):
    """AJAX: Reçete bileşeninde stok ve/veya miktar güncelle."""
    recete = get_object_or_404(Recete, pk=pk)
    detay = get_object_or_404(ReceteDetay, pk=detay_id, recete=recete)
    stok_item_id = request.POST.get('stok_item_id')
    miktar_raw = request.POST.get('miktar')

    if not stok_item_id and (miktar_raw is None or str(miktar_raw).strip() == ''):
        return JsonResponse({'success': False, 'error': 'Stok veya miktar bilgisi gerekli.'}, status=400)

    try:
        if stok_item_id:
            stok_item = get_object_or_404(StokItem, pk=stok_item_id)
            if ReceteDetay.objects.filter(recete=recete, stok_item=stok_item).exclude(pk=detay.pk).exists():
                return JsonResponse({'success': False, 'error': 'Bu stok zaten reçetede mevcut.'}, status=400)
            detay.stok_item = stok_item
            detay.birim = stok_item.birim

        if miktar_raw is not None and str(miktar_raw).strip() != '':
            miktar = Decimal(str(miktar_raw).replace(',', '.'))
            if miktar <= 0:
                return JsonResponse({'success': False, 'error': 'Miktar 0\'dan büyük olmalıdır.'}, status=400)
            detay.miktar = miktar

        detay.save()
        detay = ReceteDetay.objects.select_related('stok_item').get(pk=detay.pk)

        return JsonResponse({
            'success': True,
            'detay': _recete_detay_json(detay),
            'toplam_by_para_birimi': _recete_bilesen_toplam_list(recete),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_detay_sil(request, pk, detay_id):
    """AJAX: Reçete bileşeni sil"""
    recete = get_object_or_404(Recete, pk=pk)
    detay = get_object_or_404(ReceteDetay, pk=detay_id, recete=recete)
    
    try:
        detay.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def recete_operasyon_listesi(request, pk):
    """AJAX: Reçete operasyonları — bileşen ağacı."""
    recete = get_object_or_404(Recete, pk=pk)
    tree, results, toplam = _recete_operasyon_tree_payload(recete)
    return JsonResponse({
        'tree': tree,
        'results': results,
        'toplam_maliyet': str(toplam),
    })


@login_required
@require_http_methods(["POST"])
def recete_operasyon_ekle(request, pk):
    """AJAX: Reçete operasyonu ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    
    operasyon_id = request.POST.get('operasyon_id')
    recete_detay_id = request.POST.get('recete_detay_id')
    istasyon_id = request.POST.get('istasyon_id')
    standart_id = request.POST.get('standart_id', '')
    maliyet = request.POST.get('maliyet', '0')
    sure_dakika = request.POST.get('sure_dakika', '0')
    aciklama = request.POST.get('aciklama', '')
    sira = request.POST.get('sira', '0')
    bagimliliklar_ids = request.POST.getlist('bagimliliklar[]')
    
    genel_operasyon = request.POST.get('genel_operasyon') == '1'
    if not operasyon_id:
        return JsonResponse({'success': False, 'error': 'Operasyon seçimi zorunludur.'}, status=400)
    if genel_operasyon:
        recete_detay = None
    elif not recete_detay_id:
        return JsonResponse({'success': False, 'error': 'Reçete bileşeni seçimi zorunludur.'}, status=400)
    else:
        recete_detay = get_object_or_404(ReceteDetay, pk=recete_detay_id, recete=recete)
    
    try:
        operasyon = get_object_or_404(Operasyon, pk=operasyon_id)
        istasyon = None
        if istasyon_id:
            istasyon = get_object_or_404(Istasyon, pk=istasyon_id)
        
        uretim_standarti = None
        if standart_id:
            uretim_standarti = get_object_or_404(UretimStandarti, pk=standart_id)
        
        # Sıra numarasını belirle
        if not sira or sira == '0':
            q = ReceteOperasyon.objects.filter(recete=recete, recete_detay=recete_detay)
            max_sira = q.aggregate(Max('sira'))['sira__max']
            sira = (max_sira or 0) + 1

        dis_kw = _recete_dis_fields_from_post(operasyon, request.POST)
        
        recete_op = ReceteOperasyon.objects.create(
            recete=recete,
            recete_detay=recete_detay,
            operasyon=operasyon,
            istasyon=istasyon,
            uretim_standarti=uretim_standarti,
            maliyet=maliyet,
            sure_dakika=int(sure_dakika),
            aciklama=aciklama,
            sira=int(sira),
            **dis_kw,
        )
        
        # Bağımlılıkları ekle
        if bagimliliklar_ids:
            bagimliliklar = ReceteOperasyon.objects.filter(
                recete=recete,
                pk__in=bagimliliklar_ids
            )
            recete_op.bagimliliklar.set(bagimliliklar)
        
        return JsonResponse({
            'success': True,
            'operasyon': _serialize_recete_operasyon(recete_op),
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_operasyon_duzenle(request, pk, operasyon_id):
    """AJAX: Reçete operasyonu düzenle"""
    recete = get_object_or_404(Recete, pk=pk)
    recete_op = get_object_or_404(ReceteOperasyon, pk=operasyon_id, recete=recete)
    
    operasyon_id_new = request.POST.get('operasyon_id')
    istasyon_id = request.POST.get('istasyon_id')
    standart_id = request.POST.get('standart_id', '')
    maliyet = request.POST.get('maliyet', '0')
    sure_dakika = request.POST.get('sure_dakika', '0')
    aciklama = request.POST.get('aciklama', '')
    sira = request.POST.get('sira', '0')
    bagimliliklar_ids = request.POST.getlist('bagimliliklar[]')
    
    if not operasyon_id_new:
        return JsonResponse({'success': False, 'error': 'Operasyon seçimi zorunludur.'}, status=400)
    
    try:
        operasyon = get_object_or_404(Operasyon, pk=operasyon_id_new)
        istasyon = None
        if istasyon_id:
            istasyon = get_object_or_404(Istasyon, pk=istasyon_id)
        
        uretim_standarti = None
        if standart_id:
            uretim_standarti = get_object_or_404(UretimStandarti, pk=standart_id)
        
        dis_kw = _recete_dis_fields_from_post(operasyon, request.POST)
        for k, v in dis_kw.items():
            setattr(recete_op, k, v)

        recete_op.operasyon = operasyon
        recete_op.istasyon = istasyon
        recete_op.uretim_standarti = uretim_standarti
        recete_op.maliyet = maliyet
        recete_op.sure_dakika = int(sure_dakika)
        recete_op.aciklama = aciklama
        if sira and sira != '0':
            recete_op.sira = int(sira)
        recete_op.save()
        
        # Bağımlılıkları güncelle
        if bagimliliklar_ids:
            bagimliliklar = ReceteOperasyon.objects.filter(
                recete=recete,
                pk__in=bagimliliklar_ids
            ).exclude(pk=recete_op.pk)  # Kendisini bağımlılık olarak ekleyemez
            recete_op.bagimliliklar.set(bagimliliklar)
        else:
            recete_op.bagimliliklar.clear()
        
        return JsonResponse({
            'success': True,
            'operasyon': _serialize_recete_operasyon(recete_op),
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def istasyon_maliyet_getir(request, istasyon_id):
    """AJAX: İstasyon maliyet bilgisini getir"""
    try:
        istasyon = get_object_or_404(Istasyon, pk=istasyon_id)
        return JsonResponse({
            'success': True,
            'maliyet': str(istasyon.maliyet or Decimal('0')),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_operasyon_sil(request, pk, operasyon_id):
    """AJAX: Reçete operasyonu sil"""
    recete = get_object_or_404(Recete, pk=pk)
    recete_op = get_object_or_404(ReceteOperasyon, pk=operasyon_id, recete=recete)
    
    try:
        recete_op.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def recete_detay_sira_kaydet(request, pk):
    """AJAX (JSON): Reçete bileşen satırlarının sırasını günceller. Gövde: {\"ids\": [detay_pk, ...]}"""
    recete = get_object_or_404(Recete, pk=pk)
    try:
        payload = json.loads(request.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'Geçersiz istek gövdesi.'}, status=400)
    ids = payload.get('ids')
    if not isinstance(ids, list) or len(ids) == 0:
        return JsonResponse({'success': False, 'error': 'Sıra listesi boş olamaz.'}, status=400)
    try:
        id_list = [int(x) for x in ids]
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Geçersiz kimlik.'}, status=400)
    if len(set(id_list)) != len(id_list):
        return JsonResponse({'success': False, 'error': 'Yinelenen kimlik.'}, status=400)
    cnt = ReceteDetay.objects.filter(recete=recete, pk__in=id_list).count()
    if cnt != len(id_list):
        return JsonResponse({'success': False, 'error': 'Tüm satırlar bu reçeteye ait değil.'}, status=400)
    with transaction.atomic():
        for idx, did in enumerate(id_list, start=1):
            ReceteDetay.objects.filter(pk=did, recete=recete).update(sira=idx)
    return JsonResponse({'success': True})


@login_required
@require_POST
def recete_operasyon_sira_kaydet(request, pk):
    """AJAX (JSON): Reçete operasyon sırasını günceller. Gövde: {\"ids\": [recete_operasyon_pk, ...]}"""
    recete = get_object_or_404(Recete, pk=pk)
    try:
        payload = json.loads(request.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'Geçersiz istek gövdesi.'}, status=400)
    ids = payload.get('ids')
    recete_detay_id = payload.get('recete_detay_id')
    if not isinstance(ids, list) or len(ids) == 0:
        return JsonResponse({'success': False, 'error': 'Sıra listesi boş olamaz.'}, status=400)
    if recete_detay_id is None:
        return JsonResponse({'success': False, 'error': 'Bileşen kimliği gerekli.'}, status=400)
    try:
        recete_detay_id = int(recete_detay_id)
        id_list = [int(x) for x in ids]
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Geçersiz kimlik.'}, status=400)
    if len(set(id_list)) != len(id_list):
        return JsonResponse({'success': False, 'error': 'Yinelenen kimlik.'}, status=400)
    op_qs = ReceteOperasyon.objects.filter(recete=recete, pk__in=id_list)
    if recete_detay_id == 0:
        op_qs = op_qs.filter(recete_detay__isnull=True)
    else:
        op_qs = op_qs.filter(recete_detay_id=recete_detay_id)
    if op_qs.count() != len(id_list):
        return JsonResponse({'success': False, 'error': 'Tüm satırlar bu bileşene ait değil.'}, status=400)
    with transaction.atomic():
        for idx, oid in enumerate(id_list, start=1):
            upd = ReceteOperasyon.objects.filter(pk=oid, recete=recete)
            if recete_detay_id == 0:
                upd = upd.filter(recete_detay__isnull=True)
            else:
                upd = upd.filter(recete_detay_id=recete_detay_id)
            upd.update(sira=idx)
    return JsonResponse({'success': True})

