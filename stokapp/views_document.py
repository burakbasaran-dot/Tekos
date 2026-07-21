from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST
import json
from datetime import date, timedelta
from .models import (
    Document, DocumentType, DocumentFile, DocumentRenewal,
    DocumentLink, DocumentReminder, DocumentEvent
)
from .forms import (
    DocumentForm, DocumentTypeForm, DocumentFileForm, DocumentRenewalForm
)


@login_required
def document_listesi(request):
    """Belgeler Listesi"""
    documents = Document.objects.all().select_related('type', 'owner_user', 'created_by').order_by('-created_at')
    
    # Filtreler
    status = request.GET.get('status', '')
    type_id = request.GET.get('type', '')
    risk_level = request.GET.get('risk_level', '')
    owner_id = request.GET.get('owner', '')
    search = request.GET.get('search', '').strip()
    
    if status:
        documents = documents.filter(status=status)
    if type_id:
        documents = documents.filter(type_id=type_id)
    if risk_level:
        documents = documents.filter(risk_level=risk_level)
    if owner_id:
        documents = documents.filter(owner_user_id=owner_id)
    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(document_no__icontains=search) |
            Q(issuer_authority__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Belge türleri (filtre için)
    types = DocumentType.objects.filter(is_active=True).order_by('name')
    
    # Sorumlular (filtre için)
    owners = Document.objects.values('owner_user__id', 'owner_user__username', 'owner_user__first_name', 'owner_user__last_name').distinct()
    
    context = {
        'documents': documents,
        'types': types,
        'owners': owners,
        'status': status,
        'type_id': type_id,
        'risk_level': risk_level,
        'owner_id': owner_id,
        'search': search,
    }
    return render(request, 'stokapp/document_listesi.html', context)


@login_required
def document_detay(request, pk):
    """Belge Detay Sayfası"""
    document = get_object_or_404(Document, pk=pk)
    
    # Dosyalar
    files = document.files.filter(is_deleted=False).order_by('-version_no')
    current_file = document.get_current_file()
    
    # Yenilemeler
    renewals = document.renewals.all().order_by('-requested_at')
    
    # İlişkiler
    links = document.links.all()
    
    # Olaylar (audit log)
    events = document.events.all().order_by('-created_at')[:50]
    
    # Kalan gün
    days_remaining = document.get_days_remaining()
    
    context = {
        'document': document,
        'files': files,
        'current_file': current_file,
        'renewals': renewals,
        'links': links,
        'events': events,
        'days_remaining': days_remaining,
    }
    return render(request, 'stokapp/document_detay.html', context)


@login_required
def document_ekle(request):
    """Yeni Belge Ekle"""
    if request.method == 'POST':
        form = DocumentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    document = form.save(commit=False)
                    document.created_by = request.user
                    document.save()
                    
                    # Document'in PK'sını almak için refresh
                    document.refresh_from_db()
                    
                    # Dosya yükleme (opsiyonel)
                    if 'initial_file' in request.FILES:
                        uploaded_file = request.FILES['initial_file']
                        
                        # Dosya bilgileri
                        file_name_original = uploaded_file.name
                        file_size = uploaded_file.size
                        
                        # MIME type belirle
                        mime_type = uploaded_file.content_type or 'application/pdf'
                        
                        # İlk versiyon oluştur
                        doc_file = DocumentFile(
                            document=document,
                            version_no=1,
                            file=uploaded_file,
                            file_name_original=file_name_original,
                            file_size=file_size,
                            mime_type=mime_type,
                            uploaded_by=request.user,
                            is_current=True,
                            change_note=request.POST.get('initial_file_note', '')
                        )
                        doc_file.save()
                        
                        # Event log - dosya yükleme
                        DocumentEvent.objects.create(
                            document=document,
                            event_type='FILE_UPLOADED',
                            created_by=request.user,
                            payload=f'{{"version": 1, "file_name": "{file_name_original}"}}'
                        )
                    
                    # Event log - belge oluşturma
                    DocumentEvent.objects.create(
                        document=document,
                        event_type='CREATED',
                        created_by=request.user,
                        payload=f'{{"title": "{document.title}"}}'
                    )
                    
                    success_msg = f'Belge "{document.title}" başarıyla oluşturuldu.'
                    if 'initial_file' in request.FILES:
                        success_msg += ' İlk dosya yüklendi.'
                    messages.success(request, success_msg)
                    return redirect('stokapp:document_detay', pk=document.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DocumentForm()
    
    # Mevcut değerler (öneri listesi için)
    existing_titles = Document.objects.values_list('title', flat=True).distinct().order_by('title')[:50]
    existing_issuers = Document.objects.values_list('issuer_authority', flat=True).distinct().order_by('issuer_authority')[:50]
    existing_storage_locations = Document.objects.values_list('storage_location', flat=True).distinct().exclude(storage_location__isnull=True).exclude(storage_location='').order_by('storage_location')[:50]
    
    context = {
        'form': form,
        'existing_titles': existing_titles,
        'existing_issuers': existing_issuers,
        'existing_storage_locations': existing_storage_locations,
    }
    return render(request, 'stokapp/document_ekle.html', context)


@login_required
def document_duzenle(request, pk):
    """Belge Düzenle"""
    document = get_object_or_404(Document, pk=pk)
    
    if request.method == 'POST':
        old_status = document.status
        form = DocumentForm(request.POST, instance=document)
        if form.is_valid():
            try:
                with transaction.atomic():
                    document = form.save()
                    
                    # Status değiştiyse event log
                    if document.status != old_status:
                        DocumentEvent.objects.create(
                            document=document,
                            event_type='STATUS_CHANGED',
                            created_by=request.user,
                            payload=f'{{"old_status": "{old_status}", "new_status": "{document.status}"}}'
                        )
                    else:
                        DocumentEvent.objects.create(
                            document=document,
                            event_type='UPDATED',
                            created_by=request.user
                        )
                    
                    messages.success(request, f'Belge "{document.title}" güncellendi.')
                    return redirect('stokapp:document_detay', pk=document.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DocumentForm(instance=document)
    
    context = {
        'form': form,
        'document': document,
    }
    return render(request, 'stokapp/document_duzenle.html', context)


@login_required
def document_dosya_yukle(request, pk):
    """Belgeye Yeni Dosya Versiyonu Yükle"""
    document = get_object_or_404(Document, pk=pk)
    
    if request.method == 'POST':
        form = DocumentFileForm(request.POST, request.FILES, document=document)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Yeni versiyon numarası
                    max_version = document.files.filter(is_deleted=False).aggregate(max_v=Max('version_no'))['max_v'] or 0
                    new_version = max_version + 1
                    
                    file_obj = form.save(commit=False)
                    file_obj.document = document
                    file_obj.version_no = new_version
                    file_obj.uploaded_by = request.user
                    file_obj.is_current = True
                    
                    # Dosya bilgileri
                    if file_obj.file:
                        file_obj.file_name_original = file_obj.file.name
                        file_obj.file_size = file_obj.file.size
                    
                    file_obj.save()
                    
                    # Event log
                    DocumentEvent.objects.create(
                        document=document,
                        event_type='FILE_UPLOADED',
                        created_by=request.user,
                        payload=f'{{"version": {new_version}, "file_name": "{file_obj.file_name_original}"}}'
                    )
                    
                    messages.success(request, f'Dosya v{new_version} başarıyla yüklendi.')
                    return redirect('stokapp:document_detay', pk=document.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DocumentFileForm(document=document)
    
    context = {
        'form': form,
        'document': document,
    }
    return render(request, 'stokapp/document_dosya_yukle.html', context)


@login_required
def document_dosya_indir(request, file_id):
    """Belge Dosyasını İndir"""
    file_obj = get_object_or_404(DocumentFile, pk=file_id, is_deleted=False)
    
    if not file_obj.file:
        raise Http404("Dosya bulunamadı.")
    
    try:
        response = FileResponse(file_obj.file.open(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{file_obj.file_name_original}"'
        
        # Event log
        DocumentEvent.objects.create(
            document=file_obj.document,
            event_type='DOWNLOADED',
            created_by=request.user,
            payload=f'{{"version": {file_obj.version_no}, "file_name": "{file_obj.file_name_original}"}}'
        )
        
        return response
    except Exception as e:
        messages.error(request, f'Dosya indirilirken hata oluştu: {str(e)}')
        return redirect('stokapp:document_detay', pk=file_obj.document.pk)


@login_required
def document_dashboard(request):
    """Belgeler Dashboard"""
    today = date.today()
    
    # KPI'lar
    active_docs = Document.objects.filter(
        status__in=['ACTIVE', 'EXPIRING', 'PENDING_RENEWAL']
    ).count()
    
    expiring_30 = Document.objects.filter(
        valid_until__isnull=False,
        valid_until__gte=today,
        valid_until__lte=today + timedelta(days=30)
    ).count()
    
    expired_docs = Document.objects.filter(
        valid_until__isnull=False,
        valid_until__lt=today
    ).count()
    
    pending_renewal = Document.objects.filter(status='PENDING_RENEWAL').count()
    
    # Dağılımlar
    type_distribution = Document.objects.values('type__name').annotate(count=Count('id')).order_by('-count')
    risk_distribution = Document.objects.values('risk_level').annotate(count=Count('id')).order_by('risk_level')
    
    # Kritik belgeler (bugün aksiyon)
    critical_docs = Document.objects.filter(
        Q(risk_level='HIGH') | Q(status='EXPIRED') | Q(status='EXPIRING')
    ).order_by('risk_level', 'valid_until')[:10]
    
    context = {
        'active_docs': active_docs,
        'expiring_30': expiring_30,
        'expired_docs': expired_docs,
        'pending_renewal': pending_renewal,
        'type_distribution': type_distribution,
        'risk_distribution': risk_distribution,
        'critical_docs': critical_docs,
    }
    return render(request, 'stokapp/document_dashboard.html', context)


@login_required
@login_required
@require_POST
def api_document_type_category_ekle(request):
    """Belge türü kategorisi hızlı ekleme (CharField seçenekleri için)."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Geçersiz JSON'}, status=400)

    ad = (payload.get('ad') or '').strip()
    if not ad:
        return JsonResponse({'ok': False, 'error': 'Kategori adı boş olamaz'}, status=400)
    if len(ad) > 50:
        return JsonResponse({'ok': False, 'error': 'Kategori en fazla 50 karakter olabilir'}, status=400)

    for value, label in DocumentType.get_category_choices():
        if value.lower() == ad.lower() or str(label).lower() == ad.lower():
            return JsonResponse({'ok': True, 'category': value, 'ad': label})

    return JsonResponse({'ok': True, 'category': ad, 'ad': ad})


def document_type_listesi(request):
    """Belge Türleri Listesi"""
    types = DocumentType.objects.all().order_by('category', 'name')
    
    context = {
        'types': types,
    }
    return render(request, 'stokapp/document_type_listesi.html', context)


@login_required
def document_type_ekle(request):
    """Yeni Belge Türü Ekle"""
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST)
        if form.is_valid():
            try:
                type_obj = form.save()
                messages.success(request, f'Belge türü "{type_obj.name}" başarıyla eklendi.')
                return redirect('stokapp:document_type_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DocumentTypeForm()
    
    context = {
        'form': form,
    }
    return render(request, 'stokapp/document_type_ekle.html', context)


@login_required
def document_type_duzenle(request, pk):
    """Belge Türü Düzenle"""
    type_obj = get_object_or_404(DocumentType, pk=pk)
    
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, instance=type_obj)
        if form.is_valid():
            try:
                type_obj = form.save()
                messages.success(request, f'Belge türü "{type_obj.name}" güncellendi.')
                return redirect('stokapp:document_type_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DocumentTypeForm(instance=type_obj)
    
    context = {
        'form': form,
        'type': type_obj,
    }
    return render(request, 'stokapp/document_type_duzenle.html', context)
