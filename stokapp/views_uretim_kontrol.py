"""
Üretim Kontrol — kontrol planı tanımı ve ölçüm oturumları.
"""
import json
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms_uretim_kontrol import (
    MeasurementEntryForm,
    ProductionControlPlanForm,
    ProductionControlSessionStartForm,
    ProductionControlStepForm,
    ResultEditForm,
    RevisionNoteForm,
)
from .models import Recete, ReceteDetay, Siparis, StokItem, UretimEmri
from .nav_visibility import NAV_KEY_URETIM_KONTROL, hidden_nav_access_required
from .models_uretim_kontrol import (
    ProductionControlPlan,
    ProductionControlResult,
    ProductionControlResultChangeLog,
    ProductionControlRevisionArchive,
    ProductionControlSession,
    ProductionControlStep,
    next_revision_no,
)

WEASYPRINT_AVAILABLE = None

_uk_nav_guard = hidden_nav_access_required(NAV_KEY_URETIM_KONTROL)


def _weasyprint_html_pdf(html_string):
    global WEASYPRINT_AVAILABLE
    if WEASYPRINT_AVAILABLE is None:
        try:
            from weasyprint import HTML  # noqa: F401
            WEASYPRINT_AVAILABLE = True
        except ImportError:
            WEASYPRINT_AVAILABLE = False
    if not WEASYPRINT_AVAILABLE:
        return None
    from weasyprint import HTML
    return HTML(string=html_string).write_pdf()


def _uretim_urunleri_qs():
    return StokItem.objects.filter(
        Q(stok_tipi__in=['URUN', 'YARI_MAMUL']) |
        Q(urun_tipi='URETIM') |
        Q(urun_rolu='NIHAI_URUN')
    ).order_by('stok_kodu')


def _alt_parca_listesi(product_id):
    recete = (
        Recete.objects.filter(urun_id=product_id, aktif=True)
        .order_by('-id')
        .first()
    )
    if not recete:
        recete = Recete.objects.filter(urun_id=product_id).order_by('-id').first()
    if not recete:
        return []
    detaylar = (
        ReceteDetay.objects.filter(recete=recete)
        .select_related('stok_item')
        .order_by('sira', 'id')
    )
    return [
        {'id': d.stok_item_id, 'kod': d.stok_item.stok_kodu, 'ad': d.stok_item.ad}
        for d in detaylar
    ]


def _deactivate_sibling_plans(plan):
    qs = ProductionControlPlan.objects.filter(
        product_id=plan.product_id,
        is_active=True,
    ).exclude(pk=plan.pk)
    if plan.sub_part_id:
        qs = qs.filter(sub_part_id=plan.sub_part_id)
    else:
        qs = qs.filter(sub_part__isnull=True)
    qs.update(is_active=False, archived_at=timezone.now())


def _get_active_plan(product_id, sub_part_id=None):
    qs = ProductionControlPlan.objects.filter(product_id=product_id, is_active=True)
    if sub_part_id:
        qs = qs.filter(sub_part_id=sub_part_id)
    else:
        qs = qs.filter(sub_part__isnull=True)
    return qs.order_by('-revision_no').first()


def _get_active_plan_by_pk(plan_pk):
    return (
        ProductionControlPlan.objects.filter(pk=plan_pk, is_active=True)
        .select_related('product', 'sub_part')
        .first()
    )


def _products_with_templates_qs(search_q=None, aktif_emir_only=False):
    """En az bir aktif bileşen kontrol şablonu olan ürünler."""
    product_ids = (
        ProductionControlPlan.objects.filter(is_active=True, sub_part__isnull=False)
        .values_list('product_id', flat=True)
        .distinct()
    )
    qs = StokItem.objects.filter(pk__in=product_ids)
    if search_q:
        qs = qs.filter(Q(stok_kodu__icontains=search_q) | Q(ad__icontains=search_q))
    if aktif_emir_only:
        aktif_emir = UretimEmri.objects.exclude(durum='IPTAL').filter(recete__urun_id=OuterRef('pk'))
        qs = qs.filter(Exists(aktif_emir))
    return qs.annotate(
        bilesen_sablon_sayisi=Count(
            'uretim_kontrol_planlari',
            filter=Q(uretim_kontrol_planlari__is_active=True, uretim_kontrol_planlari__sub_part__isnull=False),
        )
    ).order_by('stok_kodu')


def _siparisler_for_plan(plan):
    """Ana ürün veya bileşen sipariş kalemlerinde geçen siparişler."""
    stok_ids = [plan.product_id]
    if plan.sub_part_id:
        stok_ids.append(plan.sub_part_id)
    return (
        Siparis.objects.filter(kalemler__stok_item_id__in=stok_ids)
        .distinct()
        .order_by('-olusturulma_tarihi')[:200]
    )


def _is_emirleri_for_product(product_id):
    return (
        UretimEmri.objects.filter(recete__urun_id=product_id)
        .exclude(durum='IPTAL')
        .select_related('recete', 'recete__urun')
        .order_by('-created_at')[:200]
    )


def _sablon_yonetim_url_context():
    try:
        urun_ara_url = reverse('stokapp:api_uretim_kontrol_urun_ara')
    except Exception:
        urun_ara_url = '/stok/api/uretim-kontrol/urun-ara/'
    try:
        urun_kontrol_base = reverse('stokapp:uretim_kontrol_urun', kwargs={'product_pk': 0}).replace('/0/', '/')
    except Exception:
        urun_kontrol_base = '/stok/uretim/kontrol/urun/'
    return {'urun_ara_url': urun_ara_url, 'urun_kontrol_base': urun_kontrol_base}


def _completed_sessions_qs(gecmis_q=None, sonuc_filter=None, archived=False):
    qs = (
        ProductionControlSession.objects.filter(status='COMPLETED', is_archived=archived)
        .select_related('product', 'sub_part', 'order', 'work_order', 'inspector', 'archived_by')
        .order_by('-archived_at' if archived else '-finished_at', '-control_date', '-created_at')
    )
    if gecmis_q:
        qs = qs.filter(
            Q(product__stok_kodu__icontains=gecmis_q)
            | Q(product__ad__icontains=gecmis_q)
            | Q(sub_part__stok_kodu__icontains=gecmis_q)
            | Q(sub_part__ad__icontains=gecmis_q)
            | Q(lot_no__icontains=gecmis_q)
            | Q(order__siparis_numarasi__icontains=gecmis_q)
            | Q(work_order__emir_no__icontains=gecmis_q)
        )
    if sonuc_filter in ('KABUL', 'RED', 'SARTLI'):
        qs = qs.filter(final_result=sonuc_filter)
    return qs[:200]


def _product_bilesen_sablonlari(product_id):
    """Reçete bileşenleri + şablon durumu."""
    product = get_object_or_404(StokItem, pk=product_id)
    plans = (
        ProductionControlPlan.objects.filter(product_id=product_id, is_active=True, sub_part__isnull=False)
        .select_related('sub_part')
        .annotate(step_count=Count('steps'))
    )
    plans_by_sub = {p.sub_part_id: p for p in plans}
    items = []
    seen = set()
    for c in _alt_parca_listesi(product_id):
        sid = c['id']
        seen.add(sid)
        plan = plans_by_sub.get(sid)
        items.append({
            **c,
            'plan': plan,
            'has_template': plan is not None,
            'step_count': plan.step_count if plan else 0,
            'revision_no': plan.revision_no if plan else None,
            'has_sessions': plan.sessions.exists() if plan else False,
        })
    for sid, plan in plans_by_sub.items():
        if sid in seen:
            continue
        sp = plan.sub_part
        items.append({
            'id': sid,
            'kod': sp.stok_kodu,
            'ad': sp.ad,
            'plan': plan,
            'has_template': True,
            'step_count': plan.step_count,
            'revision_no': plan.revision_no,
            'has_sessions': plan.sessions.exists(),
        })
    return product, items


def _redirect_urun(product_id):
    return redirect('stokapp:uretim_kontrol_urun', product_pk=product_id)


def _redirect_sablon(plan):
    return redirect('stokapp:uretim_kontrol_sablon', plan_pk=plan.pk)


def _clone_plan_with_revision(old_plan, user, change_note, step_updates=None):
    """Aktif planı arşivleyip yeni revizyon oluşturur."""
    new_rev = next_revision_no(old_plan.revision_no)
    archive_data = {
        'plan': {
            'revision_no': old_plan.revision_no,
            'description': old_plan.description,
        },
        'steps': [s.snapshot_dict() for s in old_plan.steps.all()],
    }
    with transaction.atomic():
        new_plan = ProductionControlPlan.objects.create(
            product=old_plan.product,
            sub_part=old_plan.sub_part,
            revision_no=new_rev,
            description=old_plan.description,
            is_active=True,
            created_by=user,
        )
        for step in old_plan.steps.all().order_by('sort_order', 'step_no'):
            ProductionControlStep.objects.create(
                control_plan=new_plan,
                step_no=step.step_no,
                title=step.title,
                description=step.description,
                photo=step.photo,
                nominal_value=step.nominal_value,
                nominal_unit=step.nominal_unit,
                plus_tolerance=step.plus_tolerance,
                plus_tolerance_unit=step.plus_tolerance_unit,
                minus_tolerance=step.minus_tolerance,
                minus_tolerance_unit=step.minus_tolerance_unit,
                measurement_method=step.measurement_method,
                measurement_method_other=step.measurement_method_other,
                is_required=step.is_required,
                is_critical=step.is_critical,
                note=step.note,
                sort_order=step.sort_order,
                photo_annotation_json=step.photo_annotation_json,
            )
        old_plan.superseded_by = new_plan
        old_plan.deactivate()
        ProductionControlRevisionArchive.objects.create(
            product=old_plan.product,
            sub_part=old_plan.sub_part,
            old_revision_no=old_plan.revision_no,
            new_revision_no=new_rev,
            change_note=change_note,
            archived_data_json=archive_data,
            old_plan=old_plan,
            new_plan=new_plan,
            changed_by=user,
        )
    return new_plan


def _plan_has_sessions(plan):
    return plan.sessions.filter(status__in=('COMPLETED', 'IN_PROGRESS', 'PAUSED')).exists()


# ---------------------------------------------------------------------------
# Sayfalar
# ---------------------------------------------------------------------------

@login_required
@_uk_nav_guard
def uretim_kontrol_ana(request):
    """Üretim kontrol ana sayfası — şablon, tamamlanan ve arşiv sekmeleri."""
    tab = request.GET.get('tab', 'sablonlar')
    if tab not in ('sablonlar', 'gecmis', 'arsiv'):
        tab = 'sablonlar'
    completed_base = ProductionControlSession.objects.filter(status='COMPLETED')
    ctx = {
        'tab': tab,
        'gecmis_count': completed_base.filter(is_archived=False).count(),
        'arsiv_count': completed_base.filter(is_archived=True).count(),
        **_sablon_yonetim_url_context(),
    }
    if tab in ('gecmis', 'arsiv'):
        gecmis_q = (request.GET.get('q') or '').strip()
        sonuc_filter = (request.GET.get('sonuc') or '').strip()
        ctx.update({
            'gecmis_q': gecmis_q,
            'sonuc_filter': sonuc_filter,
            'oturumlar': _completed_sessions_qs(
                gecmis_q or None,
                sonuc_filter or None,
                archived=(tab == 'arsiv'),
            ),
            'list_tab': tab,
            'search_q': '',
            'aktif_emir': False,
        })
    else:
        search_q = (request.GET.get('q') or '').strip()
        aktif_emir = request.GET.get('aktif_emir') == '1'
        ctx.update({
            'search_q': search_q,
            'aktif_emir': aktif_emir,
            'gecmis_q': '',
            'sonuc_filter': '',
            'urunler': _products_with_templates_qs(search_q=search_q or None, aktif_emir_only=aktif_emir),
        })
    return render(request, 'stokapp/uretim_kontrol/ana.html', ctx)


@login_required
@_uk_nav_guard
def uretim_kontrol_urun(request, product_pk):
    """Ürünün bileşenleri ve her biri için kontrol şablonu."""
    product, bilesenler = _product_bilesen_sablonlari(product_pk)
    sablonlu = sum(1 for b in bilesenler if b['has_template'])
    return render(
        request,
        'stokapp/uretim_kontrol/urun.html',
        {
            'product': product,
            'bilesenler': bilesenler,
            'sablonlu_sayisi': sablonlu,
            'toplam_bilesen': len(bilesenler),
        },
    )


@login_required
@_uk_nav_guard
def uretim_kontrol_sablon_yonetim(request):
    """Eski URL — ana sayfa şablon sekmesine yönlendirir."""
    return redirect(reverse('stokapp:uretim_kontrol_ana') + '?tab=sablonlar')


@login_required
@_uk_nav_guard
@require_POST
def uretim_kontrol_oturum_arsivle(request, session_pk):
    session = get_object_or_404(ProductionControlSession, pk=session_pk, status='COMPLETED')
    if session.is_archived:
        messages.info(request, 'Bu kontrol zaten arşivde.')
    else:
        session.is_archived = True
        session.archived_at = timezone.now()
        session.archived_by = request.user
        session.save(update_fields=['is_archived', 'archived_at', 'archived_by'])
        messages.success(request, 'Kontrol arşive taşındı.')
    next_url = request.POST.get('next') or (reverse('stokapp:uretim_kontrol_ana') + '?tab=gecmis')
    return redirect(next_url)


@login_required
@_uk_nav_guard
@require_POST
def uretim_kontrol_oturum_arsivden_cikar(request, session_pk):
    session = get_object_or_404(ProductionControlSession, pk=session_pk, status='COMPLETED')
    if not session.is_archived:
        messages.info(request, 'Bu kontrol zaten arşivde değil.')
    else:
        session.is_archived = False
        session.archived_at = None
        session.archived_by = None
        session.save(update_fields=['is_archived', 'archived_at', 'archived_by'])
        messages.success(request, 'Kontrol tamamlananlar listesine geri alındı.')
    next_url = request.POST.get('next') or (reverse('stokapp:uretim_kontrol_ana') + '?tab=arsiv')
    return redirect(next_url)


@login_required
@_uk_nav_guard
def uretim_kontrol_sablon(request, plan_pk):
    """Bileşen kontrol şablonu — adım listesi ve düzenleme."""
    plan = get_object_or_404(
        ProductionControlPlan.objects.select_related('product', 'sub_part'),
        pk=plan_pk,
    )
    steps = plan.steps.all()
    revisions = ProductionControlPlan.objects.filter(
        product_id=plan.product_id,
        sub_part_id=plan.sub_part_id,
    ).order_by('-revision_no')
    has_sessions = plan.sessions.exists() or ProductionControlSession.objects.filter(
        control_plan__product_id=plan.product_id,
        control_plan__sub_part_id=plan.sub_part_id,
    ).exists()
    return render(
        request,
        'stokapp/uretim_kontrol/sablon.html',
        {
            'plan': plan,
            'steps': steps,
            'revisions': revisions,
            'product': plan.product,
            'bilesen': plan.sub_part,
            'has_sessions': has_sessions,
        },
    )


@login_required
@_uk_nav_guard
@require_POST
def uretim_kontrol_plan_sil(request, pk):
    """Aktif kontrol şablonunu siler veya kontrol kaydı varsa arşivler."""
    plan = get_object_or_404(
        ProductionControlPlan.objects.select_related('product', 'sub_part'),
        pk=pk,
    )
    product_id = plan.product_id
    sub_part_id = plan.sub_part_id
    sp_label = plan.sub_part.stok_kodu if plan.sub_part else plan.product.stok_kodu

    related = ProductionControlPlan.objects.filter(product_id=product_id, sub_part_id=sub_part_id)
    any_sessions = ProductionControlSession.objects.filter(
        control_plan__product_id=product_id,
        control_plan__sub_part_id=sub_part_id,
    ).exists()

    if any_sessions:
        related.filter(is_active=True).update(is_active=False, archived_at=timezone.now())
        messages.warning(
            request,
            f'"{sp_label}" için kayıtlı kontrol geçmişi olduğundan şablon arşivlendi; ölçüm kayıtları korunur. '
            'Yeni şablon tanımlayabilirsiniz.',
        )
    else:
        count, _ = related.delete()
        messages.success(request, f'"{sp_label}" kontrol şablonu silindi ({count} kayıt).')

    return _redirect_urun(product_id)


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_plan_olustur(request):
    product_id = request.GET.get('product') or request.POST.get('product')
    sub_part_id = request.GET.get('sub_part') or request.POST.get('sub_part')
    if request.method == 'POST':
        form = ProductionControlPlanForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            sub_part = form.cleaned_data.get('sub_part')
            if not sub_part:
                messages.error(request, 'Kontrol şablonu bir reçete bileşeni (alt parça) için tanımlanmalıdır.')
            elif ProductionControlPlan.objects.filter(
                product=product, sub_part=sub_part, is_active=True
            ).exists():
                messages.error(request, 'Bu bileşen için zaten aktif bir kontrol şablonu var.')
            else:
                plan = form.save(commit=False)
                plan.revision_no = 'R00'
                plan.created_by = request.user
                plan.save()
                _deactivate_sibling_plans(plan)
                messages.success(request, f'Kontrol şablonu {plan.revision_no} oluşturuldu.')
                return _redirect_sablon(plan)
        messages.error(request, 'Plan kaydedilemedi. Alanları kontrol edin.')
    else:
        initial = {}
        if product_id:
            initial['product'] = product_id
        if sub_part_id:
            initial['sub_part'] = sub_part_id
        form = ProductionControlPlanForm(initial=initial)
    form.fields['product'].queryset = _uretim_urunleri_qs()
    if product_id:
        component_ids = [c['id'] for c in _alt_parca_listesi(int(product_id))]
        form.fields['sub_part'].queryset = StokItem.objects.filter(pk__in=component_ids).order_by('stok_kodu')
        form.fields['sub_part'].required = True
    else:
        form.fields['sub_part'].queryset = StokItem.objects.none()
    cancel_url = reverse('stokapp:uretim_kontrol_urun', kwargs={'product_pk': product_id}) if product_id else reverse('stokapp:uretim_kontrol_sablon_yonetim')
    return render(
        request,
        'stokapp/uretim_kontrol/plan_form.html',
        {'form': form, 'title': 'Kontrol Şablonu Oluştur', 'cancel_url': cancel_url},
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_plan_duzenle(request, pk):
    plan = get_object_or_404(ProductionControlPlan, pk=pk)
    if request.method == 'POST':
        form = ProductionControlPlanForm(request.POST, instance=plan)
        if form.is_valid():
            desc_changed = form.cleaned_data['description'] != plan.description
            active_changed = form.cleaned_data['is_active'] != plan.is_active
            if desc_changed and _plan_has_sessions(plan):
                rev_form = RevisionNoteForm(request.POST)
                if not rev_form.is_valid():
                    return render(
                        request,
                        'stokapp/uretim_kontrol/plan_form.html',
                        {
                            'form': form,
                            'plan': plan,
                            'revision_form': rev_form,
                            'require_revision': True,
                            'title': 'Plan Düzenle',
                        },
                    )
                new_plan = _clone_plan_with_revision(
                    plan, request.user, rev_form.cleaned_data['change_note']
                )
                new_plan.description = form.cleaned_data['description']
                new_plan.is_active = form.cleaned_data['is_active']
                new_plan.save()
                messages.success(request, f'Yeni revizyon {new_plan.revision_no} oluşturuldu.')
                return _redirect_sablon(new_plan)
            updated = form.save(commit=False)
            updated.product = plan.product
            updated.sub_part = plan.sub_part
            updated.save()
            messages.success(request, 'Şablon güncellendi.')
            return _redirect_urun(plan.product_id)
    else:
        form = ProductionControlPlanForm(instance=plan)
    form.fields['product'].queryset = _uretim_urunleri_qs()
    form.fields['sub_part'].queryset = StokItem.objects.filter(pk=plan.sub_part_id) if plan.sub_part_id else StokItem.objects.none()
    form.fields['product'].disabled = True
    form.fields['sub_part'].disabled = True
    return render(
        request,
        'stokapp/uretim_kontrol/plan_form.html',
        {
            'form': form,
            'plan': plan,
            'title': 'Şablonu Değiştir',
            'cancel_url': reverse('stokapp:uretim_kontrol_urun', kwargs={'product_pk': plan.product_id}),
        },
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_adim_ekle(request, plan_pk):
    from django.db.models import Max

    plan = get_object_or_404(ProductionControlPlan, pk=plan_pk, is_active=True)
    next_no = (plan.steps.aggregate(m=Max('step_no'))['m'] or 0) + 1
    if request.method == 'POST':
        form = ProductionControlStepForm(request.POST, request.FILES)
        if form.is_valid():
            step = form.save(commit=False)
            step.control_plan = plan
            if not step.step_no:
                step.step_no = next_no
            step.sort_order = step.step_no
            if _plan_has_sessions(plan):
                rev_form = RevisionNoteForm(request.POST)
                if not rev_form.is_valid():
                    return render(
                        request,
                        'stokapp/uretim_kontrol/adim_form.html',
                        {
                            'form': form,
                            'plan': plan,
                            'revision_form': rev_form,
                            'require_revision': True,
                            'title': 'Kontrol Adımı Ekle',
                        },
                    )
                new_plan = _clone_plan_with_revision(
                    plan, request.user, rev_form.cleaned_data['change_note']
                )
                step.control_plan = new_plan
            step.save()
            messages.success(request, 'Kontrol adımı kaydedildi.')
            return _redirect_sablon(step.control_plan)
    else:
        form = ProductionControlStepForm(initial={'step_no': next_no})
    return render(
        request,
        'stokapp/uretim_kontrol/adim_form.html',
        {'form': form, 'plan': plan, 'title': 'Kontrol Adımı Ekle'},
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_adim_duzenle(request, step_pk):
    step = get_object_or_404(ProductionControlStep.objects.select_related('control_plan'), pk=step_pk)
    plan = step.control_plan
    revision_fields = (
        'nominal_value', 'plus_tolerance', 'minus_tolerance', 'photo', 'description', 'title'
    )
    if request.method == 'POST':
        form = ProductionControlStepForm(request.POST, request.FILES, instance=step)
        if form.is_valid():
            needs_rev = _plan_has_sessions(plan)
            if needs_rev:
                rev_form = RevisionNoteForm(request.POST)
                if not rev_form.is_valid():
                    return render(
                        request,
                        'stokapp/uretim_kontrol/adim_form.html',
                        {
                            'form': form,
                            'plan': plan,
                            'step': step,
                            'revision_form': rev_form,
                            'require_revision': True,
                            'title': 'Kontrol Adımı Düzenle',
                        },
                    )
                new_plan = _clone_plan_with_revision(
                    plan, request.user, rev_form.cleaned_data['change_note']
                )
                new_step = new_plan.steps.filter(step_no=step.step_no).first()
                if not new_step:
                    new_step = ProductionControlStep(control_plan=new_plan, step_no=step.step_no)
                for f in form.Meta.fields:
                    setattr(new_step, f, form.cleaned_data.get(f, getattr(step, f)))
                if request.FILES.get('photo'):
                    new_step.photo = request.FILES['photo']
                new_step.save()
            else:
                form.save()
            messages.success(request, 'Adım güncellendi.')
            return _redirect_sablon(new_plan if needs_rev else plan)
    else:
        form = ProductionControlStepForm(instance=step)
    return render(
        request,
        'stokapp/uretim_kontrol/adim_form.html',
        {'form': form, 'plan': plan, 'step': step, 'title': 'Kontrol Adımı Düzenle'},
    )


@login_required
@_uk_nav_guard
@require_POST
def uretim_kontrol_adim_sil(request, step_pk):
    step = get_object_or_404(ProductionControlStep, pk=step_pk)
    plan = step.control_plan
    pid, spid = plan.product_id, plan.sub_part_id
    if _plan_has_sessions(plan):
        rev_note = request.POST.get('change_note', 'Adım silindi')
        new_plan = _clone_plan_with_revision(plan, request.user, rev_note)
        new_plan.steps.filter(step_no=step.step_no).delete()
    else:
        step.delete()
    messages.success(request, 'Adım silindi.')
    if spid:
        plan = _get_active_plan(pid, spid)
        if plan:
            return _redirect_sablon(plan)
    return _redirect_urun(pid)


@login_required
@_uk_nav_guard
@require_POST
def uretim_kontrol_adim_sira(request, plan_pk):
    plan = get_object_or_404(ProductionControlPlan, pk=plan_pk)
    try:
        data = json.loads(request.body.decode())
        order = data.get('order', [])
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': 'Geçersiz veri'}, status=400)
    for idx, step_id in enumerate(order, start=1):
        ProductionControlStep.objects.filter(pk=step_id, control_plan=plan).update(
            sort_order=idx, step_no=idx
        )
    return JsonResponse({'success': True})


@login_required
@_uk_nav_guard
def uretim_kontrol_revizyon_detay(request, archive_pk):
    archive = get_object_or_404(ProductionControlRevisionArchive, pk=archive_pk)
    return render(
        request,
        'stokapp/uretim_kontrol/revizyon_detay.html',
        {'archive': archive, 'data': archive.archived_data_json},
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_baslat(request):
    plan_pk = request.GET.get('plan') or request.POST.get('plan') or request.GET.get('control_plan')
    product_id = request.GET.get('product')
    sub_part_id = request.GET.get('sub_part')
    locked_plan = None
    initial = {'control_date': timezone.localdate(), 'inspector': request.user.id, 'quantity': 1}
    if plan_pk:
        locked_plan = _get_active_plan_by_pk(int(plan_pk))
    elif product_id:
        locked_plan = _get_active_plan(int(product_id), int(sub_part_id) if sub_part_id else None)
    if locked_plan:
        if not locked_plan.steps.exists():
            messages.error(request, 'Bu bileşen için kontrol adımı tanımlı değil. Önce şablonu tamamlayın.')
            return _redirect_urun(locked_plan.product_id)
        initial['control_plan'] = locked_plan.pk
        product_id = locked_plan.product_id
        sub_part_id = locked_plan.sub_part_id
    if request.method == 'POST':
        form = ProductionControlSessionStartForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            if form.cleaned_data.get('bagimsiz_kontrol'):
                session.order = None
            session.control_plan_revision_no = session.control_plan.revision_no
            session.product = session.control_plan.product
            session.sub_part = session.control_plan.sub_part
            session.inspector = form.cleaned_data['inspector']
            session.status = 'IN_PROGRESS'
            session.started_at = timezone.now()
            session.save()
            for step in session.control_plan.steps.all():
                snap = step.snapshot_dict()
                lo, hi = step.lower_limit(), step.upper_limit()
                ProductionControlResult.objects.create(
                    session=session,
                    step=step,
                    step_snapshot_json=snap,
                    lower_limit=lo,
                    upper_limit=hi,
                    measured_unit=step.nominal_unit,
                )
            return redirect('stokapp:uretim_kontrol_olcum', session_pk=session.pk, step_index=0)
        messages.error(request, 'Kontrol başlatılamadı.')
    else:
        form = ProductionControlSessionStartForm(initial=initial)
    if locked_plan:
        form.fields['order'].queryset = _siparisler_for_plan(locked_plan)
        form.fields['work_order'].queryset = _is_emirleri_for_product(locked_plan.product_id)
    else:
        form.fields['order'].queryset = Siparis.objects.all().order_by('-olusturulma_tarihi')[:200]
        form.fields['work_order'].queryset = UretimEmri.objects.exclude(durum='IPTAL').order_by('-created_at')[:200]
    form.fields['control_plan'].queryset = ProductionControlPlan.objects.filter(is_active=True)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    form.fields['inspector'].queryset = User.objects.filter(is_active=True).order_by('username')
    if locked_plan:
        form.fields['control_plan'].widget = forms.HiddenInput()
    return render(
        request,
        'stokapp/uretim_kontrol/baslat.html',
        {
            'form': form,
            'locked_plan': locked_plan,
            'product_id': product_id,
            'sub_part_id': sub_part_id,
        },
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_olcum(request, session_pk, step_index=0):
    session = get_object_or_404(
        ProductionControlSession.objects.select_related('control_plan', 'product', 'sub_part'),
        pk=session_pk,
    )
    if session.status == 'CANCELLED':
        messages.warning(request, 'Bu kontrol iptal edilmiş.')
        return redirect('stokapp:uretim_kontrol_ana')
    results = list(session.results.select_related('step').order_by('step__sort_order', 'step__step_no'))
    total = len(results)
    if total == 0:
        messages.error(request, 'Bu planda kontrol adımı yok.')
        return redirect('stokapp:uretim_kontrol_ana')
    step_index = max(0, min(int(step_index), total - 1))
    result = results[step_index]
    step = result.step

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action == 'cancel':
            session.status = 'CANCELLED'
            session.save(update_fields=['status'])
            messages.info(request, 'Kontrol iptal edildi.')
            return redirect('stokapp:uretim_kontrol_ana')
        if action == 'pause':
            session.status = 'PAUSED'
            session.current_step_index = step_index
            session.save(update_fields=['status', 'current_step_index'])
            messages.info(request, 'Kontrol duraklatıldı.')
            return redirect('stokapp:uretim_kontrol_ana')
        form = MeasurementEntryForm(request.POST)
        if form.is_valid():
            mv = form.cleaned_data.get('measured_value')
            result.measured_value = mv
            result.measured_unit = form.cleaned_data.get('measured_unit') or step.nominal_unit
            result.measurement_note = form.cleaned_data.get('measurement_note', '')
            result.measured_at = timezone.now()
            result.refresh_from_measurement()
            result.save()
            session.status = 'IN_PROGRESS'
            session.current_step_index = step_index
            session.save(update_fields=['status', 'current_step_index'])
            if action == 'finish' or step_index >= total - 1:
                session.status = 'COMPLETED'
                session.finished_at = timezone.now()
                session.final_result = session.compute_final_result()
                session.save()
                return redirect('stokapp:uretim_kontrol_sonuc', session_pk=session.pk)
            if action == 'prev':
                return redirect('stokapp:uretim_kontrol_olcum', session_pk=session.pk, step_index=step_index - 1)
            return redirect('stokapp:uretim_kontrol_olcum', session_pk=session.pk, step_index=step_index + 1)
    else:
        form = MeasurementEntryForm(
            initial={
                'measured_value': result.measured_value,
                'measured_unit': result.measured_unit or step.nominal_unit,
                'measurement_note': result.measurement_note,
            }
        )
    lo = result.lower_limit if result.lower_limit is not None else step.lower_limit()
    hi = result.upper_limit if result.upper_limit is not None else step.upper_limit()
    preview_status = result.status
    if step.nominal_value is not None and result.measured_value is not None:
        preview_status, _ = step.evaluate_measurement(result.measured_value)
    return render(
        request,
        'stokapp/uretim_kontrol/olcum.html',
        {
            'session': session,
            'result': result,
            'step': step,
            'form': form,
            'step_index': step_index,
            'total_steps': total,
            'lower_limit': lo,
            'upper_limit': hi,
            'preview_status': preview_status,
        },
    )


@login_required
@_uk_nav_guard
def uretim_kontrol_sonuc(request, session_pk):
    session = get_object_or_404(
        ProductionControlSession.objects.select_related(
            'control_plan', 'product', 'sub_part', 'order', 'work_order', 'inspector'
        ),
        pk=session_pk,
    )
    results = session.results.select_related('step').order_by('step__sort_order', 'step__step_no')
    ok_count = results.filter(status='OK').count()
    nok_count = results.filter(status='NOK').count()
    critical_nok = results.filter(status='NOK', step__is_critical=True).count()
    return render(
        request,
        'stokapp/uretim_kontrol/sonuc.html',
        {
            'session': session,
            'results': results,
            'ok_count': ok_count,
            'nok_count': nok_count,
            'critical_nok': critical_nok,
            'total': results.count(),
        },
    )


@login_required
@_uk_nav_guard
@require_http_methods(['GET', 'POST'])
def uretim_kontrol_sonuc_duzenle(request, result_pk):
    result = get_object_or_404(
        ProductionControlResult.objects.select_related('session', 'step'), pk=result_pk
    )
    if request.method == 'POST':
        form = ResultEditForm(request.POST)
        if form.is_valid():
            old = str(result.measured_value) if result.measured_value is not None else ''
            new_val = form.cleaned_data.get('measured_value')
            new = str(new_val) if new_val is not None else ''
            if old != new:
                ProductionControlResultChangeLog.objects.create(
                    result=result,
                    old_value=old,
                    new_value=new,
                    change_note=form.cleaned_data.get('change_note', ''),
                    changed_by=request.user,
                )
            result.measured_value = new_val
            result.measurement_note = form.cleaned_data.get('measurement_note', '')
            result.refresh_from_measurement()
            result.save()
            session = result.session
            session.final_result = session.compute_final_result()
            session.save(update_fields=['final_result'])
            messages.success(request, 'Ölçüm güncellendi.')
            return redirect('stokapp:uretim_kontrol_sonuc', session_pk=session.pk)
    else:
        form = ResultEditForm(
            initial={
                'measured_value': result.measured_value,
                'measurement_note': result.measurement_note,
            }
        )
    logs = result.change_logs.select_related('changed_by').all()
    return render(
        request,
        'stokapp/uretim_kontrol/sonuc_duzenle.html',
        {'result': result, 'form': form, 'logs': logs},
    )


@login_required
@_uk_nav_guard
def uretim_kontrol_pdf(request, session_pk):
    session = get_object_or_404(
        ProductionControlSession.objects.select_related(
            'control_plan', 'product', 'sub_part', 'order', 'work_order', 'inspector'
        ),
        pk=session_pk,
    )
    results = session.results.select_related('step').order_by('step__sort_order', 'step__step_no')
    html = render_to_string(
        'stokapp/uretim_kontrol/pdf_rapor.html',
        {'session': session, 'results': results},
        request=request,
    )
    pdf = _weasyprint_html_pdf(html)
    if pdf:
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="uretim_kontrol_{session.pk}.pdf"'
        return resp
    return HttpResponse(html)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@login_required
@_uk_nav_guard
@require_GET
def api_uretim_kontrol_urun_ara(request):
    """Üretim kontrol şablonu için ürün arama (stok kodu / ad)."""
    q = (request.GET.get('q') or '').strip()
    qs = _uretim_urunleri_qs()
    if q:
        qs = qs.filter(Q(stok_kodu__icontains=q) | Q(ad__icontains=q))
    results = [
        {
            'id': u.pk,
            'kod': u.stok_kodu,
            'ad': u.ad,
            'label': f'{u.stok_kodu} — {u.ad}',
        }
        for u in qs[:50]
    ]
    return JsonResponse({'results': results})


@login_required
@_uk_nav_guard
@require_GET
def api_uretim_kontrol_alt_parca(request):
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'results': []})
    return JsonResponse({'results': _alt_parca_listesi(int(product_id))})


@login_required
@_uk_nav_guard
@require_GET
def api_uretim_kontrol_planlar(request):
    product_id = request.GET.get('product_id')
    sub_part_id = request.GET.get('sub_part_id')
    qs = ProductionControlPlan.objects.filter(is_active=True).select_related('product', 'sub_part')
    if product_id:
        qs = qs.filter(product_id=product_id)
    if sub_part_id:
        qs = qs.filter(sub_part_id=sub_part_id)
    else:
        qs = qs.filter(sub_part__isnull=True)
    data = [
        {
            'id': p.pk,
            'revision_no': p.revision_no,
            'product': p.product.stok_kodu,
            'sub_part': p.sub_part.stok_kodu if p.sub_part else None,
            'step_count': p.steps.count(),
        }
        for p in qs[:50]
    ]
    return JsonResponse({'results': data})


@login_required
@_uk_nav_guard
@require_GET
def api_uretim_kontrol_plan_detay(request, pk):
    plan = get_object_or_404(ProductionControlPlan.objects.prefetch_related('steps'), pk=pk)
    steps = [
        {
            'id': s.pk,
            'step_no': s.step_no,
            'title': s.title,
            'nominal_value': str(s.nominal_value) if s.nominal_value is not None else None,
            'nominal_unit': s.nominal_unit,
            'is_critical': s.is_critical,
            'photo_url': s.photo.url if s.photo else None,
        }
        for s in plan.steps.all()
    ]
    return JsonResponse(
        {
            'id': plan.pk,
            'revision_no': plan.revision_no,
            'description': plan.description,
            'is_active': plan.is_active,
            'steps': steps,
        }
    )


@login_required
@_uk_nav_guard
@require_POST
def api_uretim_kontrol_session_result(request, session_pk):
    session = get_object_or_404(ProductionControlSession, pk=session_pk)
    try:
        payload = json.loads(request.body.decode())
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON gerekli'}, status=400)
    result_id = payload.get('result_id')
    result = get_object_or_404(ProductionControlResult, pk=result_id, session=session)
    mv = payload.get('measured_value')
    if mv is not None and mv != '':
        try:
            result.measured_value = Decimal(str(mv))
        except InvalidOperation:
            return JsonResponse({'success': False, 'error': 'Geçersiz sayı'}, status=400)
    result.measurement_note = payload.get('measurement_note', '')
    result.measured_at = timezone.now()
    result.refresh_from_measurement()
    result.save()
    return JsonResponse(
        {
            'success': True,
            'status': result.status,
            'deviation': str(result.deviation) if result.deviation is not None else None,
        }
    )


@login_required
@_uk_nav_guard
@require_POST
def api_uretim_kontrol_session_finish(request, session_pk):
    session = get_object_or_404(ProductionControlSession, pk=session_pk)
    session.status = 'COMPLETED'
    session.finished_at = timezone.now()
    session.final_result = session.compute_final_result()
    session.save()
    return JsonResponse({'success': True, 'final_result': session.final_result})
