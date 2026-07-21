from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from .models import CncProgram, CncProgramRevision, CncProgramLog, StokItem
from .forms import CncProgramForm, CncProgramRevisionForm
from collections import defaultdict


@login_required
def cnc_program_listesi(request):
    """CNC Program listesi"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    search_query = request.GET.get('search', '').strip()
    product_id = request.GET.get('product', None)
    machine_type = request.GET.get('machine_type', '')
    
    # Base queryset
    if hepsini_goster:
        programlar = CncProgram.objects.all().select_related('product').order_by('-created_at')
    else:
        programlar = CncProgram.objects.filter(status='active').select_related('product').order_by('-created_at')
    
    # Ürün filtresi
    if product_id:
        try:
            programlar = programlar.filter(product_id=product_id)
        except ValueError:
            pass
    
    # Makine tipi filtresi
    if machine_type:
        programlar = programlar.filter(machine_type=machine_type)
    
    # Arama filtresi
    if search_query:
        programlar = programlar.filter(
            Q(program_name__icontains=search_query) |
            Q(program_number__icontains=search_query) |
            Q(machine_name__icontains=search_query) |
            Q(product__stok_kodu__icontains=search_query) |
            Q(product__ad__icontains=search_query) |
            Q(urun_parcasi__icontains=search_query)
        )
    
    grouped_programs_map = defaultdict(list)
    for program in programlar:
        stok_kodu = program.product.stok_kodu if program.product else ''
        grouped_programs_map[stok_kodu].append(program)

    grouped_programlar = []
    for stok_kodu, grouped_items in grouped_programs_map.items():
        if len(grouped_items) > 1:
            grouped_programlar.append({
                'is_group': True,
                'group_key': stok_kodu,
                'product': grouped_items[0].product,
                'items': grouped_items,
                'count': len(grouped_items),
            })
        else:
            grouped_programlar.append({
                'is_group': False,
                'program': grouped_items[0],
            })

    context = {
        'programlar': programlar,
        'grouped_programlar': grouped_programlar,
        'hepsini_goster': hepsini_goster,
        'search_query': search_query,
        'product_id': product_id,
        'machine_type': machine_type,
    }
    return render(request, 'stokapp/cnc_program_listesi.html', context)


@login_required
@require_http_methods(["GET"])
def cnc_program_urun_ara(request):
    """AJAX: CNC program formu için ürün arama (stok kodu / ad)."""
    search_query = request.GET.get('q', '').strip()
    qs = StokItem.objects.filter(stok_tipi='URUN')
    if search_query:
        qs = qs.filter(
            Q(stok_kodu__icontains=search_query) | Q(ad__icontains=search_query)
        )
    results = [
        {'id': item.pk, 'stok_kodu': item.stok_kodu, 'ad': item.ad}
        for item in qs.order_by('stok_kodu')[:20]
    ]
    return JsonResponse({'results': results})


def _cnc_program_secili_urun(form, request):
    product_id = None
    if request.method == 'POST' and form.is_bound:
        product_id = (form.data.get('product') or '').strip()
    else:
        product_id = (request.GET.get('product') or form.initial.get('product') or '')
        if product_id:
            product_id = str(product_id).strip()
    if not product_id:
        return None
    try:
        urun = StokItem.objects.get(pk=product_id, stok_tipi='URUN')
        return {'id': urun.pk, 'stok_kodu': urun.stok_kodu, 'ad': urun.ad}
    except (StokItem.DoesNotExist, ValueError, TypeError):
        return None


@login_required
def cnc_program_ekle(request):
    """Yeni CNC program ekle - opsiyonel olarak ilk program dosyası (R01) ile birlikte"""
    if request.method == 'POST':
        form = CncProgramForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    program = form.save()

                    # Log oluştur
                    CncProgramLog.objects.create(
                        program=program,
                        action='created',
                        user=request.user,
                        notes=f'Program oluşturuldu: {program.program_name}'
                    )

                    # İlk program dosyası yüklendiyse, R01 revizyonunu otomatik oluştur
                    program_file = form.cleaned_data.get('program_file')
                    if program_file:
                        revision_note = form.cleaned_data.get('revision_note') or 'İlk program tanımı'
                        revision = CncProgramRevision.objects.create(
                            program=program,
                            revision_code='R01',
                            revision_type='new',
                            file_path=program_file,
                            revision_note=revision_note,
                            created_by=request.user,
                            is_active=True,
                        )
                        # Dosya hash'ini hesapla
                        revision.calculate_file_hash()

                        CncProgramLog.objects.create(
                            program=program,
                            revision=revision,
                            action='revision_added',
                            user=request.user,
                            notes=f'İlk revizyon eklendi: R01 - {revision_note[:100]}'
                        )

                        messages.success(
                            request,
                            f'CNC programı "{program.program_name}" başarıyla eklendi ve R01 revizyonu oluşturuldu.'
                        )
                    else:
                        messages.success(request, f'CNC programı "{program.program_name}" başarıyla eklendi.')
                    return redirect('stokapp:cnc_program_detay', program_id=program.program_id)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = CncProgramForm()
        product_id = request.GET.get('product', None)
        if product_id:
            try:
                form.fields['product'].initial = product_id
            except Exception:
                pass

    context = {
        'form': form,
        'initial_product': _cnc_program_secili_urun(form, request),
    }
    return render(request, 'stokapp/cnc_program_ekle.html', context)


@login_required
def cnc_program_detay(request, program_id):
    """CNC program detay sayfası - revizyon geçmişi dahil"""
    program = get_object_or_404(CncProgram, program_id=program_id)
    
    # Tüm revizyonları getir
    revizyonlar = CncProgramRevision.objects.filter(program=program).order_by('-created_at')
    
    # Aktif revizyon
    aktif_revizyon = program.get_active_revision()
    
    # Log kayıtları
    loglar = CncProgramLog.objects.filter(program=program).order_by('-created_at')[:50]
    
    context = {
        'program': program,
        'revizyonlar': revizyonlar,
        'aktif_revizyon': aktif_revizyon,
        'loglar': loglar,
    }
    return render(request, 'stokapp/cnc_program_detay.html', context)


@login_required
def cnc_program_duzenle(request, program_id):
    """CNC program düzenle - hiç revizyonu yoksa ilk dosya da yüklenebilir"""
    program = get_object_or_404(CncProgram, program_id=program_id)
    has_existing_revisions = program.revisions.exists()

    if request.method == 'POST':
        form = CncProgramForm(request.POST, request.FILES, instance=program)
        if form.is_valid():
            try:
                with transaction.atomic():
                    program = form.save()

                    # Eğer program henüz revizyona sahip değilse ve dosya yüklendiyse,
                    # ilk revizyonu (R01) otomatik oluştur.
                    program_file = form.cleaned_data.get('program_file')
                    if program_file and not has_existing_revisions:
                        revision_note = form.cleaned_data.get('revision_note') or 'İlk program tanımı'
                        revision = CncProgramRevision.objects.create(
                            program=program,
                            revision_code='R01',
                            revision_type='new',
                            file_path=program_file,
                            revision_note=revision_note,
                            created_by=request.user,
                            is_active=True,
                        )
                        revision.calculate_file_hash()

                        CncProgramLog.objects.create(
                            program=program,
                            revision=revision,
                            action='revision_added',
                            user=request.user,
                            notes=f'İlk revizyon eklendi: R01 - {revision_note[:100]}'
                        )

                        messages.success(
                            request,
                            f'CNC programı "{program.program_name}" güncellendi ve R01 revizyonu oluşturuldu.'
                        )
                    else:
                        messages.success(request, f'CNC programı "{program.program_name}" güncellendi.')
                    return redirect('stokapp:cnc_program_detay', program_id=program.program_id)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = CncProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
        'has_existing_revisions': has_existing_revisions,
    }
    return render(request, 'stokapp/cnc_program_duzenle.html', context)


@login_required
def cnc_program_sil(request, program_id):
    """CNC program sil (soft delete - archived yap)"""
    program = get_object_or_404(CncProgram, program_id=program_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                program.status = 'archived'
                program.save()
                
                # Log oluştur
                CncProgramLog.objects.create(
                    program=program,
                    action='archived',
                    user=request.user,
                    notes=f'Program arşivlendi: {program.program_name}'
                )
                
                messages.success(request, f'CNC programı "{program.program_name}" arşivlendi.')
                return redirect('stokapp:cnc_program_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'program': program,
    }
    return render(request, 'stokapp/cnc_program_sil.html', context)


@login_required
def cnc_program_revizyon_ekle(request, program_id):
    """CNC program için yeni revizyon ekle"""
    program = get_object_or_404(CncProgram, program_id=program_id)
    
    if request.method == 'POST':
        form = CncProgramRevisionForm(request.POST, request.FILES, program=program)
        if form.is_valid():
            try:
                with transaction.atomic():
                    revision = form.save(commit=False)
                    revision.program = program
                    revision.created_by = request.user
                    
                    # Eğer aktif yapılıyorsa, diğer revizyonları pasif yap
                    if revision.is_active:
                        CncProgramRevision.objects.filter(program=program, is_active=True).update(is_active=False)
                        program.current_revision = revision.revision_code
                        program.save()
                    
                    revision.save()
                    
                    # Dosya hash'ini hesapla
                    if revision.file_path:
                        revision.calculate_file_hash()
                    
                    # Log oluştur
                    action = 'revision_added'
                    if revision.is_active:
                        action = 'revision_activated'
                    
                    CncProgramLog.objects.create(
                        program=program,
                        revision=revision,
                        action=action,
                        user=request.user,
                        notes=f'Revizyon eklendi: {revision.revision_code} - {revision.revision_note[:100]}'
                    )
                    
                    messages.success(request, f'Revizyon "{revision.revision_code}" başarıyla eklendi.')
                    return redirect('stokapp:cnc_program_detay', program_id=program.program_id)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = CncProgramRevisionForm(program=program)
        # Varsayılan olarak aktif yap
        form.fields['is_active'].initial = True
    
    context = {
        'form': form,
        'program': program,
    }
    return render(request, 'stokapp/cnc_program_revizyon_ekle.html', context)


@login_required
def cnc_program_revizyon_indir(request, revision_id):
    """CNC program revizyon dosyasını indir"""
    revision = get_object_or_404(CncProgramRevision, revision_id=revision_id)
    
    if not revision.file_path:
        raise Http404("Dosya bulunamadı.")
    
    try:
        # Log oluştur
        CncProgramLog.objects.create(
            program=revision.program,
            revision=revision,
            action='file_downloaded',
            user=request.user,
            notes=f'Dosya indirildi: {revision.file_path.name}'
        )
        
        response = FileResponse(revision.file_path.open(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{revision.file_path.name}"'
        return response
    except Exception as e:
        messages.error(request, f'Dosya indirilirken hata oluştu: {str(e)}')
        return redirect('stokapp:cnc_program_detay', program_id=revision.program.program_id)


@login_required
def cnc_program_revizyon_rollback(request, revision_id):
    """Eski bir revizyonu aktif yap (rollback)"""
    revision = get_object_or_404(CncProgramRevision, revision_id=revision_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Tüm revizyonları pasif yap
                CncProgramRevision.objects.filter(program=revision.program, is_active=True).update(is_active=False)
                
                # Bu revizyonu aktif yap
                revision.is_active = True
                revision.save()
                
                # Program'ın current_revision'ını güncelle
                revision.program.current_revision = revision.revision_code
                revision.program.save()
                
                # Log oluştur
                CncProgramLog.objects.create(
                    program=revision.program,
                    revision=revision,
                    action='revision_rolled_back',
                    user=request.user,
                    notes=f'Revizyon geri alındı: {revision.revision_code}'
                )
                
                messages.success(request, f'Revizyon "{revision.revision_code}" aktif yapıldı.')
                return redirect('stokapp:cnc_program_detay', program_id=revision.program.program_id)
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'revision': revision,
        'program': revision.program,
    }
    return render(request, 'stokapp/cnc_program_revizyon_rollback.html', context)


@login_required
@require_http_methods(["GET"])
def api_cnc_programlar_urun(request, product_id):
    """Ürüne ait aktif CNC programlarını JSON olarak döndür (AJAX için)"""
    try:
        product = get_object_or_404(StokItem, pk=product_id)
        programlar = CncProgram.objects.filter(
            product=product,
            status='active'
        ).select_related('product')
        
        # Her program için aktif revizyonu al
        result = []
        for program in programlar:
            aktif_revizyon = program.get_active_revision()
            if aktif_revizyon:
                result.append({
                    'program_id': str(program.program_id),
                    'program_name': program.program_name,
                    'machine_type': program.get_machine_type_display(),
                    'machine_name': program.machine_name or '',
                    'revision_id': str(aktif_revizyon.revision_id),
                    'revision_code': aktif_revizyon.revision_code,
                    'revision_type': aktif_revizyon.get_revision_type_display(),
                })
        
        return JsonResponse({'programlar': result}, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
