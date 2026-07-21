"""
Kalite Yönetimi Modülü Views
Müşteri Şikayet & Uygunsuzluk (NCR/Complaint) + CAPA + ECO + Üretim Uyarı
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
import threading

from .models import (
    Complaint, ComplaintAttachment, CapaAction, EcoChange, AlertRule,
    ControlPlan, ControlItem, AuditLog, Musteri, StokItem, Siparis,
    UretimEmri
)
from .forms import (
    ComplaintForm, ComplaintAttachmentForm, CapaActionForm, EcoChangeForm,
    AlertRuleForm, ControlPlanForm, ControlItemForm
)


# ============================================================================
# Helper Functions
# ============================================================================

def set_request_user(user):
    """Request user'ı thread-local'a kaydet (audit log için)"""
    try:
        threading.current_thread().request_user = user
    except:
        pass


def get_matching_alerts(product=None, product_revision=None, customer=None, category=None):
    """Verilen parametrelere göre eşleşen aktif uyarıları döndür"""
    alerts = AlertRule.objects.filter(active=True)
    matching = []
    
    for alert in alerts:
        if alert.is_valid() and alert.matches(product, product_revision, customer, category):
            matching.append(alert)
    
    return matching


# ============================================================================
# Complaint Views
# ============================================================================

@login_required
def complaint_listesi(request):
    """Şikayet/Uygunsuzluk listesi"""
    complaints = Complaint.objects.all().select_related('customer', 'product', 'created_by').order_by('-created_at')
    
    # Filtreleme
    customer_id = request.GET.get('customer')
    product_id = request.GET.get('product')
    status = request.GET.get('status')
    category = request.GET.get('category')
    
    if customer_id:
        complaints = complaints.filter(customer_id=customer_id)
    if product_id:
        complaints = complaints.filter(product_id=product_id)
    if status:
        complaints = complaints.filter(status=status)
    if category:
        complaints = complaints.filter(category__icontains=category)
    
    # Sayfalama
    paginator = Paginator(complaints, 20)
    page = request.GET.get('page')
    complaints = paginator.get_page(page)
    
    context = {
        'complaints': complaints,
        'customers': Musteri.objects.all().order_by('ad'),
        'products': StokItem.objects.filter(arsivli=False).order_by('ad'),
        'statuses': Complaint.STATUS_CHOICES,
    }
    return render(request, 'stokapp/kalite/complaint_listesi.html', context)


@login_required
def complaint_detay(request, pk):
    """Şikayet/Uygunsuzluk detay"""
    complaint = get_object_or_404(Complaint.objects.select_related('customer', 'product', 'created_by'), pk=pk)
    attachments = complaint.attachments.all()
    capa_actions = complaint.capa_actions.all()
    eco_changes = complaint.eco_changes.all()
    audit_logs = AuditLog.objects.filter(content_type='Complaint', object_id=pk).order_by('-timestamp')
    
    context = {
        'complaint': complaint,
        'attachments': attachments,
        'capa_actions': capa_actions,
        'eco_changes': eco_changes,
        'audit_logs': audit_logs,
    }
    return render(request, 'stokapp/kalite/complaint_detay.html', context)


@login_required
def complaint_ekle(request):
    """Yeni şikayet/uygunsuzluk ekle"""
    set_request_user(request.user)
    
    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.created_by = request.user
            complaint.save()
            
            # Fotoğraf yükleme
            foto = request.FILES.get('foto')
            if foto:
                ComplaintAttachment.objects.create(
                    complaint=complaint,
                    file=foto,
                    note='Fotoğraf',
                    uploaded_by=request.user
                )
            
            # PDF doküman yükleme
            dokuman = request.FILES.get('dokuman')
            if dokuman:
                ComplaintAttachment.objects.create(
                    complaint=complaint,
                    file=dokuman,
                    note=request.POST.get('dokuman_notu', 'PDF Doküman'),
                    uploaded_by=request.user
                )
            
            messages.success(request, f'Şikayet/Uygunsuzluk başarıyla eklendi.')
            
            # Eğer severity threshold varsa ve AlertRule oluşturma seçeneği aktifse
            # Burada otomatik AlertRule oluşturulabilir
            
            return redirect('stokapp:complaint_detay', pk=complaint.pk)
    else:
        form = ComplaintForm()
    
    # Ürün listesini context'e ekle (autocomplete için)
    urunler = StokItem.objects.filter(arsivli=False).order_by('ad')
    urunler_list = [{'id': u.pk, 'stok_kodu': u.stok_kodu, 'ad': u.ad} for u in urunler]
    
    return render(request, 'stokapp/kalite/complaint_ekle.html', {
        'form': form,
        'urunler': urunler_list
    })


@login_required
def complaint_duzenle(request, pk):
    """Şikayet/uygunsuzluk düzenle"""
    set_request_user(request.user)
    
    complaint = get_object_or_404(Complaint, pk=pk)
    
    if request.method == 'POST':
        form = ComplaintForm(request.POST, instance=complaint)
        if form.is_valid():
            form.save()
            messages.success(request, 'Şikayet/Uygunsuzluk güncellendi.')
            return redirect('stokapp:complaint_detay', pk=complaint.pk)
    else:
        form = ComplaintForm(instance=complaint)
    
    return render(request, 'stokapp/kalite/complaint_duzenle.html', {'form': form, 'complaint': complaint})


@login_required
def complaint_sil(request, pk):
    """Şikayet/uygunsuzluk sil"""
    set_request_user(request.user)
    
    complaint = get_object_or_404(Complaint, pk=pk)
    
    if request.method == 'POST':
        complaint.delete()
        messages.success(request, 'Şikayet/Uygunsuzluk silindi.')
        return redirect('stokapp:complaint_listesi')
    
    return render(request, 'stokapp/kalite/complaint_sil.html', {'complaint': complaint})


@login_required
def complaint_ekle_attachment(request, complaint_id):
    """Şikayete dosya eki ekle"""
    complaint = get_object_or_404(Complaint, pk=complaint_id)
    
    if request.method == 'POST':
        form = ComplaintAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.complaint = complaint
            attachment.uploaded_by = request.user
            attachment.save()
            messages.success(request, 'Dosya eklendi.')
            return redirect('stokapp:complaint_detay', pk=complaint.pk)
    else:
        form = ComplaintAttachmentForm()
    
    return render(request, 'stokapp/kalite/complaint_ekle_attachment.html', {
        'form': form,
        'complaint': complaint
    })


# ============================================================================
# CAPA Action Views
# ============================================================================

@login_required
def capa_action_ekle(request, complaint_id):
    """CAPA aksiyonu ekle"""
    set_request_user(request.user)
    
    complaint = get_object_or_404(Complaint, pk=complaint_id)
    
    if request.method == 'POST':
        form = CapaActionForm(request.POST)
        if form.is_valid():
            capa = form.save(commit=False)
            capa.complaint = complaint
            capa.save()
            messages.success(request, 'CAPA aksiyonu eklendi.')
            return redirect('stokapp:complaint_detay', pk=complaint.pk)
    else:
        form = CapaActionForm()
    
    return render(request, 'stokapp/kalite/capa_action_ekle.html', {
        'form': form,
        'complaint': complaint
    })


@login_required
def capa_action_duzenle(request, pk):
    """CAPA aksiyonu düzenle"""
    set_request_user(request.user)
    
    capa = get_object_or_404(CapaAction, pk=pk)
    
    if request.method == 'POST':
        form = CapaActionForm(request.POST, instance=capa)
        if form.is_valid():
            form.save()
            messages.success(request, 'CAPA aksiyonu güncellendi.')
            return redirect('stokapp:complaint_detay', pk=capa.complaint.pk)
    else:
        form = CapaActionForm(instance=capa)
    
    return render(request, 'stokapp/kalite/capa_action_duzenle.html', {
        'form': form,
        'capa': capa
    })


@login_required
def capa_action_sil(request, pk):
    """CAPA aksiyonu sil"""
    set_request_user(request.user)
    
    capa = get_object_or_404(CapaAction, pk=pk)
    complaint_id = capa.complaint.pk
    
    if request.method == 'POST':
        capa.delete()
        messages.success(request, 'CAPA aksiyonu silindi.')
        return redirect('stokapp:complaint_detay', pk=complaint_id)
    
    return render(request, 'stokapp/kalite/capa_action_sil.html', {'capa': capa})


# ============================================================================
# ECO Change Views
# ============================================================================

@login_required
def eco_listesi(request):
    """ECO listesi"""
    ecos = EcoChange.objects.all().select_related('product', 'created_by', 'approved_by').order_by('-created_at')
    
    # Filtreleme
    product_id = request.GET.get('product')
    approval_status = request.GET.get('approval_status')
    
    if product_id:
        ecos = ecos.filter(product_id=product_id)
    if approval_status:
        ecos = ecos.filter(approval_status=approval_status)
    
    # Sayfalama
    paginator = Paginator(ecos, 20)
    page = request.GET.get('page')
    ecos = paginator.get_page(page)
    
    context = {
        'ecos': ecos,
        'products': StokItem.objects.filter(arsivli=False).order_by('ad'),
        'approval_statuses': EcoChange.APPROVAL_STATUS,
    }
    return render(request, 'stokapp/kalite/eco_listesi.html', context)


@login_required
def eco_detay(request, pk):
    """ECO detay"""
    eco = get_object_or_404(EcoChange.objects.select_related('product', 'created_by', 'approved_by', 'complaint'), pk=pk)
    audit_logs = AuditLog.objects.filter(content_type='EcoChange', object_id=pk).order_by('-timestamp')
    
    context = {
        'eco': eco,
        'audit_logs': audit_logs,
    }
    return render(request, 'stokapp/kalite/eco_detay.html', context)


@login_required
def eco_ekle(request):
    """Yeni ECO ekle"""
    set_request_user(request.user)
    
    complaint_id = request.GET.get('complaint')
    
    if request.method == 'POST':
        form = EcoChangeForm(request.POST)
        if form.is_valid():
            eco = form.save(commit=False)
            eco.created_by = request.user
            eco.save()
            messages.success(request, 'ECO başarıyla eklendi.')
            return redirect('stokapp:eco_detay', pk=eco.pk)
    else:
        form = EcoChangeForm()
        if complaint_id:
            try:
                complaint = Complaint.objects.get(pk=complaint_id)
                form.fields['complaint'].initial = complaint
                form.fields['product'].initial = complaint.product
            except Complaint.DoesNotExist:
                pass
    
    return render(request, 'stokapp/kalite/eco_ekle.html', {'form': form})


@login_required
def eco_duzenle(request, pk):
    """ECO düzenle"""
    set_request_user(request.user)
    
    eco = get_object_or_404(EcoChange, pk=pk)
    
    if request.method == 'POST':
        form = EcoChangeForm(request.POST, instance=eco)
        if form.is_valid():
            form.save()
            messages.success(request, 'ECO güncellendi.')
            return redirect('stokapp:eco_detay', pk=eco.pk)
    else:
        form = EcoChangeForm(instance=eco)
    
    return render(request, 'stokapp/kalite/eco_duzenle.html', {'form': form, 'eco': eco})


@login_required
def eco_onayla(request, pk):
    """ECO onayla"""
    set_request_user(request.user)
    
    eco = get_object_or_404(EcoChange, pk=pk)
    
    if request.method == 'POST':
        if eco.approval_status == 'PENDING':
            eco.approval_status = 'APPROVED'
            eco.approved_by = request.user
            eco.approved_at = timezone.now()
            eco.save()
            messages.success(request, 'ECO onaylandı.')
            
            # ECO onaylandığında AlertRule veya ControlPlan güncelleme yapılabilir
            # Burada özel mantık eklenebilir
            
            return redirect('stokapp:eco_detay', pk=eco.pk)
        else:
            messages.error(request, 'Sadece bekleyen ECO\'lar onaylanabilir.')
    
    return redirect('stokapp:eco_detay', pk=eco.pk)


@login_required
def eco_reddet(request, pk):
    """ECO reddet"""
    set_request_user(request.user)
    
    eco = get_object_or_404(EcoChange, pk=pk)
    
    if request.method == 'POST':
        rejection_reason = request.POST.get('rejection_reason', '')
        if eco.approval_status == 'PENDING':
            eco.approval_status = 'REJECTED'
            eco.rejection_reason = rejection_reason
            eco.save()
            messages.success(request, 'ECO reddedildi.')
            return redirect('stokapp:eco_detay', pk=eco.pk)
        else:
            messages.error(request, 'Sadece bekleyen ECO\'lar reddedilebilir.')
    
    return redirect('stokapp:eco_detay', pk=eco.pk)


@login_required
def eco_sil(request, pk):
    """ECO sil"""
    set_request_user(request.user)
    
    eco = get_object_or_404(EcoChange, pk=pk)
    
    if request.method == 'POST':
        eco.delete()
        messages.success(request, 'ECO silindi.')
        return redirect('stokapp:eco_listesi')
    
    return render(request, 'stokapp/kalite/eco_sil.html', {'eco': eco})


# ============================================================================
# AlertRule Views
# ============================================================================

@login_required
def alert_rule_listesi(request):
    """Uyarı kuralı listesi"""
    rules = AlertRule.objects.all().select_related('product', 'customer', 'created_by').order_by('-created_at')
    
    # Filtreleme
    scope = request.GET.get('scope')
    level = request.GET.get('level')
    active = request.GET.get('active')
    
    if scope:
        rules = rules.filter(scope=scope)
    if level:
        rules = rules.filter(level=level)
    if active is not None:
        rules = rules.filter(active=active == '1')
    
    # Sayfalama
    paginator = Paginator(rules, 20)
    page = request.GET.get('page')
    rules = paginator.get_page(page)
    
    context = {
        'rules': rules,
        'scopes': AlertRule.SCOPE_CHOICES,
        'levels': AlertRule.LEVEL_CHOICES,
    }
    return render(request, 'stokapp/kalite/alert_rule_listesi.html', context)


@login_required
def alert_rule_ekle(request):
    """Yeni uyarı kuralı ekle"""
    set_request_user(request.user)
    
    if request.method == 'POST':
        form = AlertRuleForm(request.POST)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.created_by = request.user
            rule.save()
            messages.success(request, 'Uyarı kuralı eklendi.')
            return redirect('stokapp:alert_rule_listesi')
    else:
        form = AlertRuleForm()
    
    return render(request, 'stokapp/kalite/alert_rule_ekle.html', {'form': form})


@login_required
def alert_rule_duzenle(request, pk):
    """Uyarı kuralı düzenle"""
    set_request_user(request.user)
    
    rule = get_object_or_404(AlertRule, pk=pk)
    
    if request.method == 'POST':
        form = AlertRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, 'Uyarı kuralı güncellendi.')
            return redirect('stokapp:alert_rule_listesi')
    else:
        form = AlertRuleForm(instance=rule)
    
    return render(request, 'stokapp/kalite/alert_rule_duzenle.html', {'form': form, 'rule': rule})


@login_required
def alert_rule_sil(request, pk):
    """Uyarı kuralı sil"""
    set_request_user(request.user)
    
    rule = get_object_or_404(AlertRule, pk=pk)
    
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Uyarı kuralı silindi.')
        return redirect('stokapp:alert_rule_listesi')
    
    return render(request, 'stokapp/kalite/alert_rule_sil.html', {'rule': rule})


# ============================================================================
# API Views - Üretim Entegrasyonu
# ============================================================================

@login_required
def api_get_alerts(request):
    """Üretim emri için aktif uyarıları getir (AJAX)"""
    product_id = request.GET.get('product_id')
    product_revision = request.GET.get('product_revision', '')
    customer_id = request.GET.get('customer_id')
    category = request.GET.get('category', '')
    
    product = None
    customer = None
    
    if product_id:
        try:
            product = StokItem.objects.get(pk=product_id)
        except StokItem.DoesNotExist:
            pass
    
    if customer_id:
        try:
            customer = Musteri.objects.get(pk=customer_id)
        except Musteri.DoesNotExist:
            pass
    
    alerts = get_matching_alerts(product, product_revision, customer, category)
    
    return JsonResponse({
        'alerts': [
            {
                'id': alert.pk,
                'level': alert.level,
                'message': alert.message,
                'scope': alert.get_scope_display(),
            }
            for alert in alerts
        ]
    })


# ============================================================================
# ControlPlan Views
# ============================================================================

@login_required
def control_plan_listesi(request):
    """Kontrol planı listesi"""
    plans = ControlPlan.objects.all().select_related('product', 'created_by').order_by('-created_at')
    
    # Filtreleme
    product_id = request.GET.get('product_id')
    if product_id:
        plans = plans.filter(product_id=product_id)
    
    context = {
        'plans': plans,
    }
    return render(request, 'stokapp/kalite/control_plan_listesi.html', context)


@login_required
def control_plan_detay(request, pk):
    """Kontrol planı detay"""
    plan = get_object_or_404(ControlPlan.objects.select_related('product'), pk=pk)
    items = plan.items.all()
    
    context = {
        'plan': plan,
        'items': items,
    }
    return render(request, 'stokapp/kalite/control_plan_detay.html', context)


@login_required
def control_plan_ekle(request):
    """Yeni kontrol planı ekle"""
    set_request_user(request.user)
    
    if request.method == 'POST':
        form = ControlPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.created_by = request.user
            plan.save()
            messages.success(request, 'Kontrol planı eklendi.')
            return redirect('stokapp:control_plan_detay', pk=plan.pk)
    else:
        form = ControlPlanForm()
    
    return render(request, 'stokapp/kalite/control_plan_ekle.html', {'form': form})


@login_required
def control_item_ekle(request, plan_id):
    """Kontrol planı maddesi ekle"""
    plan = get_object_or_404(ControlPlan, pk=plan_id)
    
    if request.method == 'POST':
        form = ControlItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.plan = plan
            item.save()
            messages.success(request, 'Kontrol planı maddesi eklendi.')
            return redirect('stokapp:control_plan_detay', pk=plan.pk)
    else:
        form = ControlItemForm()
    
    return render(request, 'stokapp/kalite/control_item_ekle.html', {
        'form': form,
        'plan': plan
    })

