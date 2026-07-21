"""
Üretim Süreci Kontrol (In-Process Inspection) Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count
from datetime import date, timedelta
from decimal import Decimal

from .models import (
    ControlPlan, ControlItem, WorkOrderInspection, QualityGate, NonconformanceAutoRule,
    UretimEmri, ReceteOperasyon, OlcuAleti, Complaint
)
from .forms import (
    ControlPlanForm, ControlItemForm, WorkOrderInspectionForm,
    QualityGateForm, NonconformanceAutoRuleForm
)


# ============================================================================
# Inspection Dashboard
# ============================================================================

@login_required
def inspection_dashboard(request):
    """Üretim Süreci Kontrol Dashboard"""
    today = timezone.now().date()
    
    # HOLD durumundaki iş emirleri (quality gate nedeniyle)
    hold_work_orders = UretimEmri.objects.filter(durum='HOLD').select_related('recete__urun')
    
    # Bugün yapılması gereken kontroller
    # (Bu hesaplama için aktif control planlar ve iş emirlerini kontrol et)
    active_control_plans = ControlPlan.objects.filter(status='ACTIVE')
    
    # Bugünkü inspection kayıtları
    today_inspections = WorkOrderInspection.objects.filter(
        measured_at__date=today
    ).select_related('work_order', 'control_item', 'measured_by')
    
    # En çok başarısız olan kontrol maddeleri
    failed_inspections = WorkOrderInspection.objects.filter(
        pass_fail='FAIL'
    ).values('control_item__name', 'control_item__id').annotate(
        fail_count=Count('id')
    ).order_by('-fail_count')[:10]
    
    context = {
        'hold_work_orders': hold_work_orders,
        'active_control_plans': active_control_plans,
        'today_inspections': today_inspections,
        'failed_inspections': failed_inspections,
        'today': today,
    }
    return render(request, 'stokapp/kalite/inspection_dashboard.html', context)


# ============================================================================
# Control Plan Views
# ============================================================================

@login_required
def control_plan_listesi(request):
    """Kontrol planları listesi"""
    plans = ControlPlan.objects.select_related('product', 'created_by').all().order_by('-created_at')
    
    # Filtreleme
    product_id = request.GET.get('product')
    status = request.GET.get('status')
    
    if product_id:
        plans = plans.filter(product_id=product_id)
    if status:
        plans = plans.filter(status=status)
    
    context = {
        'plans': plans,
        'products': ControlPlan.objects.values_list('product', 'product__ad').distinct(),
    }
    return render(request, 'stokapp/kalite/control_plan_listesi.html', context)


@login_required
def control_plan_detay(request, pk):
    """Kontrol planı detay sayfası"""
    plan = get_object_or_404(ControlPlan.objects.select_related('product'), pk=pk)
    items = plan.items.select_related('operation_step').all().order_by('operation_step__sira', 'display_order')
    
    # Operasyon adımlarına göre grupla
    items_by_step = {}
    for item in items:
        step = item.operation_step
        if step:
            step_key = f"{step.sira}_{step.operasyon.ad}"
            if step_key not in items_by_step:
                items_by_step[step_key] = {'step': step, 'items': []}
            items_by_step[step_key]['items'].append(item)
        else:
            # Operasyon adımı yoksa "Diğer" grubuna ekle
            if 'other' not in items_by_step:
                items_by_step['other'] = {'step': None, 'items': []}
            items_by_step['other']['items'].append(item)
    
    context = {
        'plan': plan,
        'items': items,
        'items_by_step': items_by_step,
    }
    return render(request, 'stokapp/kalite/control_plan_detay.html', context)


@login_required
def control_item_ekle(request, plan_pk):
    """Kontrol maddesi ekle"""
    plan = get_object_or_404(ControlPlan, pk=plan_pk)
    
    if request.method == 'POST':
        form = ControlItemForm(request.POST, plan=plan)
        if form.is_valid():
            item = form.save(commit=False)
            item.plan = plan
            item.save()
            messages.success(request, 'Kontrol maddesi başarıyla eklendi.')
            return redirect('stokapp:control_plan_detay', pk=plan.pk)
    else:
        form = ControlItemForm(plan=plan)
    
    context = {
        'form': form,
        'plan': plan,
    }
    return render(request, 'stokapp/kalite/control_item_ekle.html', context)


# ============================================================================
# Work Order Inspection Views
# ============================================================================

@login_required
def work_order_inspection_listesi(request, work_order_pk):
    """İş emri için kontrol kayıtları listesi"""
    work_order = get_object_or_404(UretimEmri, pk=work_order_pk)
    inspections = WorkOrderInspection.objects.filter(
        work_order=work_order
    ).select_related('control_item', 'operation_step', 'measured_by', 'instrument').order_by('-measured_at')
    
    # Operasyon adımına göre grupla
    inspections_by_step = {}
    for inspection in inspections:
        step = inspection.operation_step
        step_key = f"{step.sira}_{step.operasyon.ad}" if step else 'other'
        if step_key not in inspections_by_step:
            inspections_by_step[step_key] = {'step': step, 'inspections': []}
        inspections_by_step[step_key]['inspections'].append(inspection)
    
    context = {
        'work_order': work_order,
        'inspections': inspections,
        'inspections_by_step': inspections_by_step,
    }
    return render(request, 'stokapp/kalite/work_order_inspection_listesi.html', context)


@login_required
def inspection_ekle_modal(request, work_order_pk, operation_step_pk):
    """Inspection ekle modal için AJAX endpoint"""
    work_order = get_object_or_404(UretimEmri, pk=work_order_pk)
    operation_step = get_object_or_404(ReceteOperasyon, pk=operation_step_pk)
    
    if request.method == 'POST':
        form = WorkOrderInspectionForm(
            request.POST, 
            request.FILES,
            work_order=work_order,
            operation_step=operation_step
        )
        
        if form.is_valid():
            # Kalibrasyon kontrolü
            instrument = form.cleaned_data.get('instrument')
            if instrument and form.cleaned_data.get('control_item').requires_instrument:
                if not is_instrument_calibration_valid(instrument, timezone.now().date()):
                    return JsonResponse({
                        'success': False,
                        'error': f'Seçilen ölçü aleti ({instrument.seri_no}) kalibrasyonu geçersiz veya süresi dolmuş.'
                    })
            
            inspection = form.save(commit=False)
            inspection.work_order = work_order
            inspection.operation_step = operation_step
            inspection.measured_by = request.user
            inspection.measured_at = timezone.now()
            
            # Otomatik pass/fail hesaplama
            if inspection.measured_value and inspection.control_item.inspection_type == 'NUMERIC':
                auto_result = inspection.auto_calculate_pass_fail()
                if auto_result:
                    inspection.pass_fail = auto_result
            
            inspection.save()
            
            # FAIL durumunda işlemler
            if inspection.pass_fail == 'FAIL':
                handle_inspection_fail(inspection, request.user)
            
            # Quality gate kontrolü
            check_quality_gates(work_order, operation_step)
            
            return JsonResponse({
                'success': True,
                'message': 'Kontrol kaydı başarıyla eklendi.',
                'inspection_id': inspection.pk
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })
    
    # GET: Form göster
    form = WorkOrderInspectionForm(work_order=work_order, operation_step=operation_step)
    
    # Bu operasyon adımı için gerekli kontrol maddelerini al
    recete = work_order.recete
    control_plan = ControlPlan.objects.filter(
        product=recete.urun,
        status='ACTIVE'
    ).first()
    
    required_items = []
    if control_plan:
        required_items = control_plan.items.filter(
            operation_step=operation_step
        ).order_by('display_order')
    
    context = {
        'form': form,
        'work_order': work_order,
        'operation_step': operation_step,
        'required_items': required_items,
    }
    return render(request, 'stokapp/kalite/inspection_ekle_modal.html', context)


# ============================================================================
# Helper Functions
# ============================================================================

def is_instrument_calibration_valid(instrument, check_date):
    """Ölçü aleti kalibrasyonunun geçerli olup olmadığını kontrol et"""
    if not instrument.sonraki_kalibrasyon_tarihi:
        return False
    return instrument.sonraki_kalibrasyon_tarihi >= check_date


def check_quality_gates(work_order, operation_step):
    """Kalite geçitlerini kontrol et ve gerekiyorsa engelle"""
    gates = QualityGate.objects.filter(
        operation_step=operation_step,
        active=True
    )
    
    for gate in gates:
        # Bu operasyon adımı için kontrol maddelerini al
        control_items = ControlItem.objects.filter(
            plan__product=work_order.recete.urun,
            plan__status='ACTIVE',
            operation_step=operation_step
        )
        
        if gate.gate_type == 'BLOCK_ON_INCOMPLETE':
            # Eksik kontrolleri kontrol et
            for item in control_items:
                # Frekans kurallarına göre gerekli kontrol sayısını hesapla
                required_count = calculate_required_inspections(work_order, item)
                actual_count = WorkOrderInspection.objects.filter(
                    work_order=work_order,
                    control_item=item,
                    operation_step=operation_step
                ).count()
                
                if actual_count < required_count:
                    # İş emrini HOLD durumuna geçir
                    work_order.durum = 'HOLD'
                    work_order.save()
                    return False
        
        elif gate.gate_type == 'BLOCK_ON_FAIL':
            # Başarısız kontrolleri kontrol et
            fails = WorkOrderInspection.objects.filter(
                work_order=work_order,
                operation_step=operation_step,
                pass_fail='FAIL'
            )
            
            if fails.exists():
                work_order.durum = 'HOLD'
                work_order.save()
                return False
        
        elif gate.gate_type == 'BLOCK_ON_CRITICAL_FAIL':
            # Sadece kritik başarısızları kontrol et
            if gate.applies_to_critical_only:
                critical_items = control_items.filter(criticality='CRITICAL')
                fails = WorkOrderInspection.objects.filter(
                    work_order=work_order,
                    operation_step=operation_step,
                    control_item__in=critical_items,
                    pass_fail='FAIL'
                )
                
                if fails.exists():
                    work_order.durum = 'HOLD'
                    work_order.save()
                    return False
    
    return True


def calculate_required_inspections(work_order, control_item):
    """Frekans kurallarına göre gerekli kontrol sayısını hesapla"""
    qty = int(work_order.miktar)
    
    if control_item.frequency_type == '100_PERCENT':
        return qty
    elif control_item.frequency_type == 'FIRST_PIECE':
        return 1
    elif control_item.frequency_type == 'EVERY_N':
        n = control_item.frequency_n or 1
        return max(1, qty // n)
    elif control_item.frequency_type == 'PER_LOT':
        return 1
    elif control_item.frequency_type == 'PER_SHIFT':
        return 1
    
    return 1


def handle_inspection_fail(inspection, user):
    """Başarısız kontrol için gerekli işlemleri yap"""
    # NCR/Complaint oluşturma kurallarını kontrol et
    rules = NonconformanceAutoRule.objects.filter(active=True)
    
    for rule in rules:
        # Kuralın koşullarını kontrol et
        if should_trigger_rule(rule, inspection):
            # Aksiyonu uygula
            if rule.action_type == 'CREATE_NCR':
                create_ncr_from_inspection(inspection, rule, user)
            elif rule.action_type == 'CREATE_COMPLAINT':
                create_complaint_from_inspection(inspection, rule, user)
            elif rule.action_type == 'HOLD_WORK_ORDER':
                inspection.work_order.durum = 'HOLD'
                inspection.work_order.save()


def should_trigger_rule(rule, inspection):
    """Kuralın tetiklenip tetiklenmeyeceğini kontrol et"""
    control_item = inspection.control_item
    
    # Kritiklik kontrolü
    if rule.trigger_type == 'CRITICAL_FAIL':
        if control_item.criticality != 'CRITICAL' or inspection.pass_fail != 'FAIL':
            return False
    elif rule.trigger_type == 'MAJOR_FAIL':
        if control_item.criticality != 'MAJOR' or inspection.pass_fail != 'FAIL':
            return False
    elif rule.trigger_type == 'ANY_FAIL':
        if inspection.pass_fail != 'FAIL':
            return False
    
    # Ürün/kategori filtresi
    if rule.product and inspection.work_order.recete.urun != rule.product:
        return False
    if rule.category and inspection.work_order.recete.urun.kategori != rule.category:
        return False
    
    # Sayı kontrolü (birden fazla başarısız)
    if rule.trigger_type == 'MULTIPLE_FAIL':
        fail_count = WorkOrderInspection.objects.filter(
            work_order=inspection.work_order,
            pass_fail='FAIL'
        ).count()
        if fail_count < rule.trigger_count:
            return False
    
    return True


def create_ncr_from_inspection(inspection, rule, user):
    """Inspection'dan NCR oluştur"""
    # Complaint modelini NCR olarak kullan
    Complaint.objects.create(
        type='NCR',
        customer=None,  # İç uygunsuzluk
        product=inspection.work_order.recete.urun,
        category=rule.default_category or 'Üretim Süreci Kontrol',
        severity=rule.default_severity,
        description=f"Otomatik oluşturulan NCR: {inspection.control_item.name} kontrolü başarısız.\n"
                   f"İş Emri: {inspection.work_order.emir_no}\n"
                   f"Ölçülen Değer: {inspection.measured_value}\n"
                   f"Notlar: {inspection.notes}",
        status='OPEN',
        created_by=user
    )


def create_complaint_from_inspection(inspection, rule, user):
    """Inspection'dan Complaint oluştur"""
    create_ncr_from_inspection(inspection, rule, user)  # Aynı işlevi kullan


# ============================================================================
# API Endpoints
# ============================================================================

@login_required
def api_get_required_inspections(request, work_order_pk, operation_step_pk):
    """Belirli bir operasyon adımı için gerekli kontrolleri döndür"""
    work_order = get_object_or_404(UretimEmri, pk=work_order_pk)
    operation_step = get_object_or_404(ReceteOperasyon, pk=operation_step_pk)
    
    # Control plan'ı bul
    recete = work_order.recete
    control_plan = ControlPlan.objects.filter(
        product=recete.urun,
        status='ACTIVE'
    ).first()
    
    if not control_plan:
        return JsonResponse({'items': []})
    
    # Bu operasyon adımı için kontrol maddeleri
    items = control_plan.items.filter(operation_step=operation_step).order_by('display_order')
    
    result = []
    for item in items:
        required_count = calculate_required_inspections(work_order, item)
        actual_count = WorkOrderInspection.objects.filter(
            work_order=work_order,
            control_item=item,
            operation_step=operation_step
        ).count()
        
        # Son kontrolleri al
        recent_inspections = WorkOrderInspection.objects.filter(
            work_order=work_order,
            control_item=item,
            operation_step=operation_step
        ).order_by('-measured_at')[:5]
        
        result.append({
            'id': item.pk,
            'name': item.name,
            'inspection_type': item.inspection_type,
            'criticality': item.criticality,
            'required_count': required_count,
            'actual_count': actual_count,
            'remaining': max(0, required_count - actual_count),
            'requires_instrument': item.requires_instrument,
            'requires_attachment': item.requires_attachment,
            'min_value': float(item.min_value) if item.min_value else None,
            'max_value': float(item.max_value) if item.max_value else None,
            'unit': item.unit,
            'recent_inspections': [
                {
                    'sample_no': insp.sample_no,
                    'measured_value': float(insp.measured_value) if insp.measured_value else None,
                    'pass_fail': insp.pass_fail,
                    'measured_at': insp.measured_at.isoformat(),
                }
                for insp in recent_inspections
            ]
        })
    
    return JsonResponse({'items': result})


@login_required
def api_get_valid_instruments(request):
    """Kalibrasyon geçerli ölçü aletlerini döndür"""
    instruments = OlcuAleti.objects.filter(
        aktif=True,
        durum='AKTIF'
    ).exclude(
        sonraki_kalibrasyon_tarihi__lt=date.today()
    ).order_by('seri_no')
    
    result = [
        {
            'id': inst.pk,
            'seri_no': inst.seri_no,
            'alet_turu': inst.alet_turu.ad,
            'marka': inst.marka,
            'model': inst.model,
        }
        for inst in instruments
    ]
    
    return JsonResponse({'instruments': result})


@login_required
def api_get_control_item(request, item_pk):
    """Kontrol maddesi detaylarını döndür"""
    item = get_object_or_404(ControlItem, pk=item_pk)
    
    result = {
        'item': {
            'id': item.pk,
            'name': item.name,
            'inspection_type': item.inspection_type,
            'unit': item.unit,
            'nominal': float(item.nominal) if item.nominal else None,
            'min_value': float(item.min_value) if item.min_value else None,
            'max_value': float(item.max_value) if item.max_value else None,
            'requires_instrument': item.requires_instrument,
            'requires_attachment': item.requires_attachment,
            'requires_ack': item.requires_ack,
            'criticality': item.criticality,
        }
    }
    
    return JsonResponse(result)

