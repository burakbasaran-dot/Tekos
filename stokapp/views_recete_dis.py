"""Reçete dış operasyon atamaları — API."""
import json
import re
import unicodedata

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from .models import (
    Recete,
    ReceteDetay,
    ReceteDisOperasyon,
    DisOperasyonTipi,
    Tedarikci,
    Depo,
)

URUN_GENELI_LABEL = 'Ürün Geneli'


def _slugify_tipi_ad(ad: str) -> str:
    ad = unicodedata.normalize('NFKD', ad).encode('ascii', 'ignore').decode('ascii')
    ad = ad.lower().strip()
    ad = re.sub(r'[^a-z0-9]+', '_', ad).strip('_')
    return ad[:60] or 'dis_operasyon'


def _unique_operasyon_kodu(ad: str) -> str:
    base = _slugify_tipi_ad(ad)
    kod = base
    n = 2
    while DisOperasyonTipi.objects.filter(operasyon_kodu=kod).exists():
        kod = f'{base}_{n}'
        n += 1
    return kod


def _serialize_dis_tipi(tip):
    return {'id': tip.pk, 'ad': tip.ad, 'kod': tip.operasyon_kodu}


def _serialize_recete_dis_operasyon(item):
    return {
        'id': item.pk,
        'recete_detay_id': item.recete_detay_id,
        'genel': not item.recete_detay_id,
        'dis_operasyon_tipi_id': item.dis_operasyon_tipi_id,
        'dis_operasyon_tipi_ad': item.dis_operasyon_tipi.ad,
        'tedarikci_id': item.tedarikci_id,
        'tedarikci_ad': item.tedarikci.ad if item.tedarikci_id else '',
        'dis_gonderim_deposu_id': item.dis_gonderim_deposu_id,
        'dis_gonderim_deposu_ad': item.dis_gonderim_deposu.ad if item.dis_gonderim_deposu_id else '',
        'dis_beklenen_donus_gun': item.dis_beklenen_donus_gun,
        'aciklama': item.aciklama,
        'sira': item.sira,
    }


def _recete_dis_operasyon_tree_payload(recete):
    detaylar = recete.detaylar.select_related('stok_item').order_by('sira', 'id')
    atamalar = recete.dis_operasyon_atamalari.select_related(
        'dis_operasyon_tipi', 'tedarikci', 'dis_gonderim_deposu', 'recete_detay', 'recete_detay__stok_item',
    ).order_by('recete_detay__sira', 'recete_detay_id', 'sira', 'id')
    by_detay = {}
    for item in atamalar:
        by_detay.setdefault(item.recete_detay_id, []).append(_serialize_recete_dis_operasyon(item))
    tree = []
    if None in by_detay:
        tree.append({
            'detay_id': 0,
            'genel': True,
            'label': URUN_GENELI_LABEL,
            'stok_kodu': URUN_GENELI_LABEL,
            'stok_ad': '',
            'atamalar': by_detay[None],
        })
    for detay in detaylar:
        if detay.pk in by_detay:
            tree.append({
                'detay_id': detay.pk,
                'genel': False,
                'label': f'{detay.stok_item.stok_kodu} — {detay.stok_item.ad}',
                'stok_item_id': detay.stok_item_id,
                'stok_kodu': detay.stok_item.stok_kodu,
                'stok_ad': detay.stok_item.ad,
                'atamalar': by_detay[detay.pk],
            })
    flat = [a for node in tree for a in node['atamalar']]
    return tree, flat


def _dis_tipleri_listesi():
    return [_serialize_dis_tipi(t) for t in DisOperasyonTipi.objects.filter(aktif=True, ic_dis_tipi='DIS').order_by('ad')]


def _parse_recete_detay(recete, post):
    genel = post.get('genel') == '1' or post.get('urun_geneli') == '1'
    if genel:
        return None
    detay_id = post.get('recete_detay_id')
    if not detay_id:
        return None
    return get_object_or_404(ReceteDetay, pk=detay_id, recete=recete)


@login_required
def recete_dis_operasyon_listesi(request, pk):
    recete = get_object_or_404(Recete, pk=pk)
    tree, results = _recete_dis_operasyon_tree_payload(recete)
    return JsonResponse({
        'success': True,
        'tree': tree,
        'results': results,
        'tipler': _dis_tipleri_listesi(),
    })


@login_required
@require_http_methods(['POST'])
def recete_dis_operasyon_ekle(request, pk):
    recete = get_object_or_404(Recete, pk=pk)
    tip_id = request.POST.get('dis_operasyon_tipi_id')
    genel = request.POST.get('genel') == '1' or request.POST.get('urun_geneli') == '1'
    detay_id = request.POST.get('recete_detay_id')

    if not tip_id:
        return JsonResponse({'success': False, 'error': 'Dış operasyon tipi seçimi zorunludur.'}, status=400)
    if not genel and not detay_id:
        return JsonResponse({'success': False, 'error': 'Ürün geneli veya bileşen seçimi zorunludur.'}, status=400)

    try:
        tip = get_object_or_404(DisOperasyonTipi, pk=tip_id, aktif=True, ic_dis_tipi='DIS')
        recete_detay = None if genel else get_object_or_404(ReceteDetay, pk=detay_id, recete=recete)

        tedarikci = None
        if request.POST.get('tedarikci_id'):
            tedarikci = get_object_or_404(Tedarikci, pk=request.POST.get('tedarikci_id'))
        depo = None
        if request.POST.get('dis_gonderim_deposu_id'):
            depo = get_object_or_404(Depo, pk=request.POST.get('dis_gonderim_deposu_id'))

        q = ReceteDisOperasyon.objects.filter(recete=recete, recete_detay=recete_detay)
        max_sira = q.aggregate(Max('sira'))['sira__max'] or 0

        item = ReceteDisOperasyon.objects.create(
            recete=recete,
            recete_detay=recete_detay,
            dis_operasyon_tipi=tip,
            tedarikci=tedarikci,
            dis_gonderim_deposu=depo,
            dis_birim_fiyat=request.POST.get('dis_birim_fiyat', '0') or '0',
            dis_para_birimi=request.POST.get('dis_para_birimi', 'TL') or 'TL',
            dis_beklenen_donus_gun=int(request.POST.get('dis_beklenen_donus_gun') or 7),
            aciklama=request.POST.get('aciklama', ''),
            sira=max_sira + 1,
        )
        return JsonResponse({'success': True, 'item': _serialize_recete_dis_operasyon(item)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(['POST'])
def recete_dis_operasyon_duzenle(request, pk, item_id):
    recete = get_object_or_404(Recete, pk=pk)
    item = get_object_or_404(ReceteDisOperasyon, pk=item_id, recete=recete)
    tip_id = request.POST.get('dis_operasyon_tipi_id')
    if not tip_id:
        return JsonResponse({'success': False, 'error': 'Dış operasyon tipi seçimi zorunludur.'}, status=400)
    try:
        tip = get_object_or_404(DisOperasyonTipi, pk=tip_id, aktif=True, ic_dis_tipi='DIS')
        item.dis_operasyon_tipi = tip
        if request.POST.get('tedarikci_id'):
            item.tedarikci = get_object_or_404(Tedarikci, pk=request.POST.get('tedarikci_id'))
        else:
            item.tedarikci = None
        if request.POST.get('dis_gonderim_deposu_id'):
            item.dis_gonderim_deposu = get_object_or_404(Depo, pk=request.POST.get('dis_gonderim_deposu_id'))
        else:
            item.dis_gonderim_deposu = None
        item.dis_birim_fiyat = request.POST.get('dis_birim_fiyat', item.dis_birim_fiyat) or 0
        item.dis_para_birimi = request.POST.get('dis_para_birimi', item.dis_para_birimi) or 'TL'
        item.dis_beklenen_donus_gun = int(request.POST.get('dis_beklenen_donus_gun') or item.dis_beklenen_donus_gun)
        item.aciklama = request.POST.get('aciklama', item.aciklama)
        item.save()
        return JsonResponse({'success': True, 'item': _serialize_recete_dis_operasyon(item)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(['POST'])
def recete_dis_operasyon_sil(request, pk, item_id):
    recete = get_object_or_404(Recete, pk=pk)
    item = get_object_or_404(ReceteDisOperasyon, pk=item_id, recete=recete)
    item.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def dis_operasyon_tipi_ekle(request):
    """AJAX: Yeni dış operasyon tipi ekle (reçete modalındaki + butonu)."""
    ad = (request.POST.get('ad') or '').strip()
    if not ad:
        return JsonResponse({'success': False, 'error': 'Dış operasyon adı zorunludur.'}, status=400)
    if DisOperasyonTipi.objects.filter(ad__iexact=ad, ic_dis_tipi='DIS').exists():
        tip = DisOperasyonTipi.objects.filter(ad__iexact=ad, ic_dis_tipi='DIS').first()
        return JsonResponse({'success': True, 'tip': _serialize_dis_tipi(tip), 'existing': True})
    kod = _unique_operasyon_kodu(ad)
    tip = DisOperasyonTipi.objects.create(ad=ad, operasyon_kodu=kod, ic_dis_tipi='DIS', aktif=True)
    return JsonResponse({'success': True, 'tip': _serialize_dis_tipi(tip), 'existing': False})
