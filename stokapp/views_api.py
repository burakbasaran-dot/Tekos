
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.contrib.auth.decorators import login_required
import json

from .models import (
    StokItem, Kategori, Tedarikci, Birim, Depo, Raf
)

@require_GET
def api_check_stok_kodu(request):
    """?q=STOKKODU -> {'exists': True/False}"""
    q = (request.GET.get('q') or '').strip()
    exists = False
    if q:
        exists = StokItem.objects.filter(stok_kodu__iexact=q).exists()
    return JsonResponse({'exists': exists})

@require_GET
def api_shelves(request):
    """?depo_id=1 -> [{'id':..,'ad':..}, ...]"""
    depo_id = request.GET.get('depo_id')
    data = []
    if depo_id:
        for r in Raf.objects.filter(depo_id=depo_id).order_by('ad'):
            data.append({'id': r.id, 'ad': r.ad})
    return JsonResponse(data, safe=False)


@require_GET
def api_stok_fiyat(request, pk):
    """
    Stok için siparişte kullanılacak birim fiyatı döndürür.
    Öncelik: satis_fiyati > 0 ise onu, değilse alis_fiyati.
    """
    try:
        stok = StokItem.objects.get(pk=pk)
    except StokItem.DoesNotExist:
        return JsonResponse({"success": False, "error": "Stok bulunamadı."}, status=404)

    satis = stok.satis_fiyati or 0
    alis = stok.alis_fiyati or 0
    effective = satis if satis and satis > 0 else alis
    return JsonResponse(
        {
            "success": True,
            "stok_id": stok.pk,
            "satis_fiyati": str(satis),
            "alis_fiyati": str(alis),
            "effective_fiyat": str(effective or 0),
        }
    )

@require_POST
def api_quick_add(request, kind):
    """Hızlı ekleme:
    kind in {'category','supplier','unit','warehouse','shelf'}
    - category: {'ad': 'Kategori Adı'}
    - supplier: {'ad': 'Tedarikçi Adı'}
    - unit: {'ad': 'Birim Adı'}
    - warehouse: {'ad': 'Depo Adı'}
    - shelf: {'ad': 'Raf Adı', 'depo_id': <id>}
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Geçersiz JSON'}, status=400)

    ad = (payload.get('ad') or '').strip()
    if not ad:
        return JsonResponse({'ok': False, 'error': 'Ad boş olamaz'}, status=400)

    with transaction.atomic():
        if kind == 'category':
            obj, _ = Kategori.objects.get_or_create(ad=ad)
        elif kind == 'supplier':
            obj, _ = Tedarikci.objects.get_or_create(ad=ad)
        elif kind == 'unit':
            obj, _ = Birim.objects.get_or_create(ad=ad)
        elif kind == 'warehouse':
            obj, _ = Depo.objects.get_or_create(ad=ad)
        elif kind == 'shelf':
            depo_id = payload.get('depo_id')
            if not depo_id:
                return JsonResponse({'ok': False, 'error': 'depo_id gerekli'}, status=400)
            try:
                depo = Depo.objects.get(id=depo_id)
            except Depo.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Depo bulunamadı'}, status=404)
            obj, _ = Raf.objects.get_or_create(depo=depo, ad=ad)
        else:
            return JsonResponse({'ok': False, 'error': 'Geçersiz tür'}, status=400)

    return JsonResponse({'ok': True, 'id': obj.id, 'ad': str(obj)})

@login_required
def api_personel_bilgi(request, pk):
    """Personel bilgilerini JSON olarak döndür"""
    from .models import Personel
    from django.http import JsonResponse
    
    try:
        personel = Personel.objects.get(pk=pk)
        return JsonResponse({
            'saatlik_ucret': str(personel.saatlik_ucret) if personel.saatlik_ucret else '0',
        })
    except Personel.DoesNotExist:
        return JsonResponse({'error': 'Personel bulunamadı'}, status=404)
