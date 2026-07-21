"""CNC Dosya Ağacı (istasyon/makina tabanlı klasör hiyerarşisi) view'ları."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_http_methods

from .models import (
    CncDosyaAgaciKlasor,
    CncDosyaAgaciMakina,
    CncProgram,
    Istasyon,
    istasyon_effective_cnc_makine_grubu,
)

MACHINE_TYPE_CHOICES = (
    ('cnc_lathe', 'CNC Torna'),
    ('cnc_mill', 'CNC Freze'),
)
VALID_MACHINE_TYPES = {code for code, _ in MACHINE_TYPE_CHOICES}
MACHINE_TYPE_LABELS = dict(MACHINE_TYPE_CHOICES)


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _machine_label(makina):
    if makina is None:
        return ''
    return makina.istasyon.ad


def _serialize_makina(makina):
    if makina is None:
        return None
    machine_type = makina.effective_machine_type
    return {
        'id': makina.pk,
        'slug': makina.slug,
        'label': _machine_label(makina),
        'machine_type': machine_type,
        'machine_type_display': MACHINE_TYPE_LABELS.get(machine_type, machine_type),
    }


def _resolve_makina_id(makina_id):
    try:
        makina_pk = int(makina_id)
    except (TypeError, ValueError):
        return None
    return (
        CncDosyaAgaciMakina.objects
        .select_related('istasyon')
        .filter(pk=makina_pk, aktif=True)
        .first()
    )


def _resolve_makina_by_machine_type(machine_type):
    if machine_type not in VALID_MACHINE_TYPES:
        return None
    for makina in (
        CncDosyaAgaciMakina.objects
        .select_related('istasyon')
        .filter(aktif=True)
        .order_by('sira', 'istasyon__ad', 'id')
    ):
        if makina.effective_machine_type == machine_type:
            return makina
    return None


def _serialize_program(prog):
    """Klasör altındaki bir CNC programını ağaç-yaprağı için serialize et."""
    return {
        'kind': 'program',
        'id': str(prog.program_id),
        'program_name': prog.program_name,
        'program_number': prog.program_number or '',
        'current_revision': prog.current_revision or '',
        'machine_type': prog.machine_type,
        'machine_type_display': MACHINE_TYPE_LABELS.get(prog.machine_type, prog.machine_type),
        'machine_name': prog.machine_name or '',
        'product_kodu': prog.product.stok_kodu if prog.product_id else '',
        'product_ad': prog.product.ad if prog.product_id else '',
        'urun_parcasi': prog.urun_parcasi or '',
        'file_format': prog.file_format,
        'status': prog.status,
        'detay_url': f'/stok/uretim/cnc-programlar/{prog.program_id}/',
    }


def _serialize_node_for_response(node):
    """Tek bir klasörü create/update sonrası response için serialize et (program listesi dahil)."""
    progs = list(
        CncProgram.objects.filter(dosya_konumu=node).select_related('product').order_by('program_name')
    )
    return _serialize_node(node, progs)


def _serialize_node(node, programs=None):
    data = {
        'kind': 'folder',
        'id': node.pk,
        'name': node.name,
        'parent_id': node.parent_id,
        'makina_id': node.makina_id,
        'makina_label': _machine_label(node.makina),
        'sira': node.sira,
        'aciklama': node.aciklama or '',
        'full_path': node.full_path(),
        'program_count': len(programs) if programs is not None else 0,
        'children': [],
        'programs': [_serialize_program(p) for p in (programs or [])],
    }
    return data


def _build_tree(makina):
    """Tek seferde tüm klasörleri çekip bellek içinde ağaca dönüştür.

    Aynı zamanda klasörlere bağlı CNC programlarını (dosya yaprakları) ekler.
    """
    nodes = list(
        CncDosyaAgaciKlasor.objects
        .filter(makina=makina)
        .select_related('makina__istasyon')
        .order_by('sira', 'name')
    )

    # Bu makine tipindeki klasörlere bağlı programları toplu çek
    programs_by_folder = {}
    if nodes:
        folder_ids = [n.pk for n in nodes]
        programs_qs = (
            CncProgram.objects
            .filter(dosya_konumu_id__in=folder_ids)
            .select_related('product')
            .order_by('program_name')
        )
        for prog in programs_qs:
            programs_by_folder.setdefault(prog.dosya_konumu_id, []).append(prog)

    by_id = {n.pk: _serialize_node(n, programs_by_folder.get(n.pk)) for n in nodes}
    roots = []
    for n in nodes:
        item = by_id[n.pk]
        if n.parent_id and n.parent_id in by_id:
            by_id[n.parent_id]['children'].append(item)
        else:
            roots.append(item)
    return roots


@login_required
def cnc_dosya_agaci_listesi(request):
    """Modern UI: Tab tab makinalar arasında geçiş, ağaç görünümü, inline aksiyonlar."""
    makineler = list(
        CncDosyaAgaciMakina.objects
        .select_related('istasyon')
        .filter(aktif=True)
        .order_by('sira', 'istasyon__ad', 'id')
    )
    active_makina_id = request.GET.get('makina_id')
    aktif_makina = _resolve_makina_id(active_makina_id)
    if aktif_makina is None and makineler:
        aktif_makina = makineler[0]

    context = {
        'makineler': makineler,
        'aktif_makina_id': aktif_makina.pk if aktif_makina else None,
    }
    return render(request, 'stokapp/cnc_dosya_agaci_listesi.html', context)


@login_required
@require_http_methods(['GET'])
def cnc_dosya_agaci_api_tree(request):
    """JSON: Belirtilen makina (veya machine_type fallback) için klasör ağacını döndür."""
    makina_id = request.GET.get('makina_id')
    machine_type = request.GET.get('machine_type')

    makina = None
    if makina_id:
        makina = _resolve_makina_id(makina_id)
        if makina is None:
            return HttpResponseBadRequest('Geçersiz makina.')
    elif machine_type:
        if machine_type not in VALID_MACHINE_TYPES:
            return HttpResponseBadRequest('Geçersiz makine tipi.')
        makina = _resolve_makina_by_machine_type(machine_type)
        if makina is None:
            return JsonResponse({'tree': [], 'makina': None})
    else:
        makina = (
            CncDosyaAgaciMakina.objects
            .select_related('istasyon')
            .filter(aktif=True)
            .order_by('sira', 'istasyon__ad', 'id')
            .first()
        )
        if makina is None:
            return JsonResponse({'tree': [], 'makina': None})

    return JsonResponse({'tree': _build_tree(makina), 'makina': _serialize_makina(makina)})


@login_required
@require_POST
def cnc_dosya_agaci_api_create(request):
    """Yeni klasör oluştur. POST: name, makina_id, parent_id (opsiyonel), aciklama, sira"""
    name = (request.POST.get('name') or '').strip()
    makina_id = request.POST.get('makina_id')
    parent_id = request.POST.get('parent_id') or None
    aciklama = (request.POST.get('aciklama') or '').strip()
    try:
        sira = int(request.POST.get('sira') or 0)
    except ValueError:
        sira = 0

    if not name:
        return JsonResponse({'success': False, 'error': 'Klasör adı boş olamaz.'}, status=400)
    makina = _resolve_makina_id(makina_id)
    if makina is None:
        return JsonResponse({'success': False, 'error': 'Geçersiz makina.'}, status=400)

    parent = None
    if parent_id:
        parent = get_object_or_404(CncDosyaAgaciKlasor.objects.select_related('makina'), pk=parent_id)
        if parent.makina_id != makina.pk:
            return JsonResponse(
                {'success': False, 'error': 'Üst klasörün makinası farklı.'},
                status=400,
            )

    if CncDosyaAgaciKlasor.objects.filter(
        parent=parent, name=name, makina=makina
    ).exists():
        return JsonResponse(
            {'success': False, 'error': f'Aynı seviyede "{name}" adlı bir klasör zaten var.'},
            status=400,
        )

    try:
        with transaction.atomic():
            klasor = CncDosyaAgaciKlasor.objects.create(
                name=name,
                makina=makina,
                parent=parent,
                aciklama=aciklama,
                sira=sira,
                created_by=request.user,
            )
        return JsonResponse({'success': True, 'klasor': _serialize_node_for_response(klasor)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def cnc_dosya_agaci_api_update(request, pk):
    """Klasörü yeniden adlandır / açıklama güncelle / sıra güncelle."""
    klasor = get_object_or_404(CncDosyaAgaciKlasor.objects.select_related('makina'), pk=pk)

    new_name = request.POST.get('name')
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            return JsonResponse({'success': False, 'error': 'Klasör adı boş olamaz.'}, status=400)
        # Aynı seviyede çakışma kontrolü
        qs = CncDosyaAgaciKlasor.objects.filter(
            parent=klasor.parent, name=new_name, makina=klasor.makina,
        ).exclude(pk=klasor.pk)
        if qs.exists():
            return JsonResponse(
                {'success': False, 'error': f'Aynı seviyede "{new_name}" adlı bir klasör zaten var.'},
                status=400,
            )
        klasor.name = new_name

    if 'aciklama' in request.POST:
        klasor.aciklama = (request.POST.get('aciklama') or '').strip()

    if 'sira' in request.POST:
        try:
            klasor.sira = int(request.POST.get('sira') or 0)
        except ValueError:
            pass

    try:
        klasor.save()
        return JsonResponse({'success': True, 'klasor': _serialize_node_for_response(klasor)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def cnc_dosya_agaci_api_delete(request, pk):
    """Klasör sil. Alt klasörler ve bağlı CNC programlarındaki dosya_konumu referansları davranışı:
    - Alt klasörler CASCADE ile silinir.
    - Bağlı CNC programlarında dosya_konumu SET_NULL.
    """
    klasor = get_object_or_404(CncDosyaAgaciKlasor.objects.select_related('makina'), pk=pk)
    try:
        with transaction.atomic():
            silinen_id = klasor.pk
            silinen_yol = klasor.full_path()
            klasor.delete()
        return JsonResponse({
            'success': True,
            'deleted_id': silinen_id,
            'message': f'"{silinen_yol}" silindi.',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def cnc_dosya_agaci_api_move(request, pk):
    """Klasörü farklı bir parent altına taşı. POST: new_parent_id (boş => kök)."""
    klasor = get_object_or_404(CncDosyaAgaciKlasor.objects.select_related('makina'), pk=pk)
    new_parent_id = request.POST.get('new_parent_id') or None

    new_parent = None
    if new_parent_id:
        new_parent = get_object_or_404(CncDosyaAgaciKlasor.objects.select_related('makina'), pk=new_parent_id)
        if new_parent.makina_id != klasor.makina_id:
            return JsonResponse(
                {'success': False, 'error': 'Hedef klasörün makinası farklı.'},
                status=400,
            )
        # Döngü kontrolü: new_parent kendisi veya altında bir klasör mü?
        cur = new_parent
        depth = 0
        while cur is not None and depth < 50:
            if cur.pk == klasor.pk:
                return JsonResponse(
                    {'success': False, 'error': 'Klasör kendi alt klasörüne taşınamaz.'},
                    status=400,
                )
            cur = cur.parent
            depth += 1

    # Aynı seviyede çakışma kontrolü
    qs = CncDosyaAgaciKlasor.objects.filter(
        parent=new_parent, name=klasor.name, makina=klasor.makina,
    ).exclude(pk=klasor.pk)
    if qs.exists():
        return JsonResponse(
            {'success': False, 'error': f'Hedef altında "{klasor.name}" adlı bir klasör zaten var.'},
            status=400,
        )

    klasor.parent = new_parent
    try:
        klasor.save()
        return JsonResponse({'success': True, 'klasor': _serialize_node_for_response(klasor)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def cnc_dosya_agaci_makina_listesi(request):
    makineler = (
        CncDosyaAgaciMakina.objects
        .select_related('istasyon')
        .order_by('sira', 'istasyon__ad', 'id')
    )
    mevcut_ids = set(makineler.values_list('istasyon_id', flat=True))
    aday_istasyonlar = []
    for istasyon in Istasyon.objects.filter(aktif=True).order_by('sira', 'ad', 'id'):
        if istasyon.pk in mevcut_ids:
            continue
        machine_type = istasyon_effective_cnc_makine_grubu(istasyon)
        if machine_type not in VALID_MACHINE_TYPES:
            continue
        aday_istasyonlar.append({
            'id': istasyon.pk,
            'ad': istasyon.ad,
            'machine_type_display': MACHINE_TYPE_LABELS.get(machine_type, machine_type),
        })
    return render(
        request,
        'stokapp/cnc_dosya_agaci_makina_listesi.html',
        {'makineler': makineler, 'aday_istasyonlar': aday_istasyonlar},
    )


@login_required
@require_POST
def cnc_dosya_agaci_makina_ekle(request):
    istasyon_id = request.POST.get('istasyon_id')
    try:
        sira = int(request.POST.get('sira') or 0)
    except ValueError:
        sira = 0

    try:
        istasyon = Istasyon.objects.get(pk=istasyon_id, aktif=True)
    except (Istasyon.DoesNotExist, ValueError, TypeError):
        msg = 'Geçersiz istasyon.'
        if _is_ajax(request):
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('stokapp:cnc_dosya_agaci_makina_listesi')

    effective = istasyon_effective_cnc_makine_grubu(istasyon)
    if effective not in VALID_MACHINE_TYPES:
        msg = 'Seçilen istasyon CNC torna/freze grubuna uygun değil.'
        if _is_ajax(request):
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('stokapp:cnc_dosya_agaci_makina_listesi')

    if CncDosyaAgaciMakina.objects.filter(istasyon=istasyon).exists():
        msg = 'Bu istasyon için makina tanımı zaten var.'
        if _is_ajax(request):
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.warning(request, msg)
        return redirect('stokapp:cnc_dosya_agaci_makina_listesi')

    makina = CncDosyaAgaciMakina.objects.create(
        istasyon=istasyon,
        sira=sira,
        aktif=True,
    )
    if _is_ajax(request):
        return JsonResponse({'success': True, 'makina': _serialize_makina(makina)})
    messages.success(request, f'«{istasyon.ad}» için makina tanımı eklendi.')
    return redirect('stokapp:cnc_dosya_agaci_makina_listesi')


@login_required
@require_POST
def cnc_dosya_agaci_makina_sil(request):
    makina_id = request.POST.get('makina_id')
    makina = get_object_or_404(
        CncDosyaAgaciMakina.objects.select_related('istasyon'),
        pk=makina_id,
    )
    if makina.klasorler.exists():
        msg = 'Bu makina altında klasör bulunduğu için silinemez.'
        if _is_ajax(request):
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('stokapp:cnc_dosya_agaci_makina_listesi')

    ad = makina.istasyon.ad
    makina.delete()
    if _is_ajax(request):
        return JsonResponse({'success': True})
    messages.success(request, f'«{ad}» makina tanımı silindi.')
    return redirect('stokapp:cnc_dosya_agaci_makina_listesi')


@login_required
@require_http_methods(['GET'])
def cnc_dosya_agaci_makina_api_istasyonlar(request):
    mevcut_ids = set(CncDosyaAgaciMakina.objects.values_list('istasyon_id', flat=True))
    adaylar = []
    for istasyon in Istasyon.objects.filter(aktif=True).order_by('sira', 'ad', 'id'):
        if istasyon.pk in mevcut_ids:
            continue
        machine_type = istasyon_effective_cnc_makine_grubu(istasyon)
        if machine_type not in VALID_MACHINE_TYPES:
            continue
        adaylar.append({
            'id': istasyon.pk,
            'ad': istasyon.ad,
            'machine_type': machine_type,
            'machine_type_display': MACHINE_TYPE_LABELS.get(machine_type, machine_type),
        })
    return JsonResponse({'istasyonlar': adaylar})
