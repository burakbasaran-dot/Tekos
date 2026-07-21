from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Prefetch, Count, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from urllib.parse import urlencode
from collections import defaultdict
import io
import re
import json
import pandas as pd
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .uretim_emri_service import get_aktif_recete_for_urun
from .bom_planlama import create_uretim_emri_with_alt_emirler
from .stok_search import stok_multi_term_filter
from .models import (
    UretimEmri, UretimAsamasi, Recete, ReceteDetay, StokHareketi, StokItem, Personel, Siparis,
    ControlPlan, ControlItem, WorkOrderInspection, QualityGate, ReceteOperasyon,
    ReceteTalimat, UretimAsamaDurusKaydi, UretimAsamaNot, UretimAsamaSorun, Istasyon, PersonelIzin,
    Tool, ToolUsageLog
)

PLANLAMA_MAX_PARALLEL_TASKS = 2

# Alert kontrolü için (döngüsel import'u önlemek için doğrudan import)
try:
    from .models import AlertRule
    def get_matching_alerts(product=None, product_revision=None, customer=None, category=None):
        """Verilen parametrelere göre eşleşen aktif uyarıları döndür"""
        alerts = AlertRule.objects.filter(active=True)
        matching = []
        
        for alert in alerts:
            if alert.is_valid() and alert.matches(product, product_revision, customer, category):
                matching.append(alert)
        
        return matching
except ImportError:
    def get_matching_alerts(*args, **kwargs):
        return []


def _siparis_no_emirden_bul(emir):
    if not emir.aciklama:
        return None
    match = re.search(r"Sipariş\s+([A-Za-z0-9\-_/]+)\s+için oluşturuldu", emir.aciklama, re.IGNORECASE)
    return match.group(1) if match else None


def _tool_usage_hesapla_ve_logla(emir):
    """Tamamlanan iş emri için reçete operasyon takım tüketimini mm bazında loglar."""
    miktar = Decimal(str(emir.miktar or 0))
    if miktar <= 0:
        return

    recete_op_qs = ReceteOperasyon.objects.filter(recete=emir.recete).prefetch_related(
        "takim_kullanimlari",
        "takim_kullanimlari__tool",
        "takim_kullanimlari__material",
    )
    recete_op_by_sira = {op.sira: op for op in recete_op_qs}

    for asama in emir.asamalar.all():
        recete_op = recete_op_by_sira.get(asama.sira)
        if not recete_op:
            recete_op = recete_op_qs.filter(operasyon__ad__iexact=asama.ad).first()
        if not recete_op:
            continue
        for recete_tool in recete_op.takim_kullanimlari.all():
            if not recete_tool.tool_id:
                continue
            cutting_mm = Decimal(str(recete_tool.hole_count or 0)) * Decimal(str(recete_tool.hole_depth_mm or 0)) * miktar
            if cutting_mm <= 0:
                continue
            active_life = recete_tool.tool.get_active_life()
            if not active_life:
                active_life = recete_tool.tool.start_new_life(reason="regrind", note="Sistem tarafından otomatik oluşturuldu")
            ToolUsageLog.objects.create(
                tool=recete_tool.tool,
                life_cycle=active_life,
                task=asama,
                work_order=emir,
                material=recete_tool.material,
                cutting_mm=cutting_mm,
            )
            Tool.objects.filter(pk=recete_tool.tool_id).update(total_cutting_mm=F("total_cutting_mm") + cutting_mm)
            active_life.cutting_mm = Decimal(str(active_life.cutting_mm or 0)) + cutting_mm
            active_life.save(update_fields=["cutting_mm"])


@login_required
def _uretim_emri_listesi_filtered_qs(request):
    tab = request.GET.get('tab', 'devam_eden')
    emirler = UretimEmri.objects.select_related('recete__urun').order_by('-created_at')
    if tab == 'tamamlanan':
        emirler = emirler.filter(durum='TAMAMLANDI')
    else:
        emirler = emirler.exclude(durum='TAMAMLANDI')

    durum = request.GET.get('durum', '')
    uretim_tipi = request.GET.get('uretim_tipi', '')
    if durum:
        emirler = emirler.filter(durum=durum)
    if uretim_tipi in ['ORDER', 'STOCK']:
        emirler = emirler.filter(production_type=uretim_tipi)
    return emirler


@login_required
def uretim_emri_listesi(request):
    """Üretim emirleri listesi"""
    tab = request.GET.get('tab', 'devam_eden')
    durum = request.GET.get('durum', '')
    uretim_tipi = request.GET.get('uretim_tipi', '')
    emirler = _uretim_emri_listesi_filtered_qs(request)

    counts = {
        'devam_eden': UretimEmri.objects.exclude(durum='TAMAMLANDI').count(),
        'tamamlanan': UretimEmri.objects.filter(durum='TAMAMLANDI').count(),
    }

    context = {
        'emirler': emirler,
        'durum': durum,
        'uretim_tipi': uretim_tipi,
        'tab': tab,
        'counts': counts,
    }
    return render(request, 'stokapp/uretim_emri_listesi.html', context)


@login_required
@never_cache
def uretim_emri_listesi_export_excel(request):
    try:
        emirler = _uretim_emri_listesi_filtered_qs(request)
        satirlar = []
        for emir in emirler:
            satirlar.append({
                'Emir No': emir.emir_no,
                'Ürün Kodu': emir.recete.urun.stok_kodu if emir.recete and emir.recete.urun else '',
                'Ürün Adı': emir.recete.urun.ad if emir.recete and emir.recete.urun else '',
                'Miktar': float(emir.miktar or 0),
                'Birim': (emir.recete.urun.birim if emir.recete and emir.recete.urun else ''),
                'Durum': emir.get_durum_display(),
                'Tip': 'Stok' if emir.production_type == 'STOCK' else 'Sipariş',
                'Planlanan Başlangıç': emir.planlanan_baslama.strftime('%d.%m.%Y %H:%M') if emir.planlanan_baslama else '',
                'Planlanan Bitiş': emir.planlanan_bitis.strftime('%d.%m.%Y %H:%M') if emir.planlanan_bitis else '',
            })
        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=['Emir No', 'Ürün Kodu', 'Ürün Adı', 'Miktar', 'Birim', 'Durum', 'Tip', 'Planlanan Başlangıç', 'Planlanan Bitiş'])
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="uretim_emri_listesi_{ts}.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Üretim Emirleri', index=False)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_emri_listesi')


@login_required
@never_cache
def uretim_emri_listesi_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:uretim_emri_listesi')

    emirler = list(_uretim_emri_listesi_filtered_qs(request)[:1200])
    olusturma_tarihi = timezone.localtime(timezone.now())
    rows = []
    for emir in emirler:
        rows.append(
            f"""
            <tr>
                <td>{emir.emir_no}</td>
                <td>{emir.recete.urun.stok_kodu if emir.recete and emir.recete.urun else '-'}</td>
                <td>{emir.recete.urun.ad if emir.recete and emir.recete.urun else '-'}</td>
                <td class="num">{emir.miktar or 0}</td>
                <td>{emir.get_durum_display()}</td>
                <td>{'Stok' if emir.production_type == 'STOCK' else 'Sipariş'}</td>
            </tr>
            """
        )
    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Üretim Emri Listesi</h1>
      <div class="meta">Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(emirler)}</div>
      <table>
        <thead><tr><th>Emir No</th><th>Ürün Kodu</th><th>Ürün</th><th>Miktar</th><th>Durum</th><th>Tip</th></tr></thead>
        <tbody>{''.join(rows) if rows else '<tr><td colspan="6" class="empty">Kayıt yok.</td></tr>'}</tbody>
      </table>
    </body></html>
    """
    css = CSS(string="""
        @page { size: A4 landscape; margin: 10mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8pt; color: #111827; }
        h1 { font-size: 14pt; margin: 0 0 4px 0; }
        .meta { color: #6b7280; font-size: 8pt; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f3f4f6; border: 1px solid #d1d5db; padding: 5px 4px; text-align: left; font-size: 7.5pt; }
        td { border: 1px solid #e5e7eb; padding: 4px; vertical-align: top; font-size: 7.5pt; }
        .num { text-align: right; white-space: nowrap; }
        .empty { text-align: center; color: #6b7280; padding: 24px; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_emri_listesi')

    filename = f'uretim_emri_listesi_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _parse_datetime_local(value):
    if not value or not str(value).strip():
        return None
    dt = parse_datetime(str(value).strip())
    if dt is None:
        try:
            dt = datetime.strptime(str(value).strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@login_required
@require_http_methods(["GET"])
def api_uretim_emri_urun_ara(request):
    """AJAX: Aktif reçetesi olan ürün arama (operasyon zorunlu değil)."""
    search_query = request.GET.get("q", "").strip()
    urun_ids = (
        Recete.objects.filter(aktif=True)
        .values_list("urun_id", flat=True)
        .distinct()
    )
    stok_items = StokItem.objects.filter(pk__in=urun_ids).select_related("kategori")
    if search_query:
        stok_items = stok_multi_term_filter(stok_items, search_query)
    stok_items = list(stok_items.order_by("stok_kodu")[:20])

    op_map = {}
    if stok_items:
        for urun_id, op_count in (
            Recete.objects.filter(aktif=True, urun_id__in=[i.pk for i in stok_items])
            .annotate(op_count=Count("operasyonlar"))
            .values_list("urun_id", "op_count")
        ):
            op_map[urun_id] = max(op_map.get(urun_id, 0), op_count or 0)

    results = [
        {
            "id": item.pk,
            "stok_kodu": item.stok_kodu,
            "ad": item.ad,
            "has_operations": op_map.get(item.pk, 0) > 0,
        }
        for item in stok_items
    ]

    empty_hint = ""
    if search_query and not results:
        any_stok = stok_multi_term_filter(StokItem.objects.all(), search_query).exists()
        if any_stok:
            empty_hint = (
                "Bu aramaya uyan ürün var ancak aktif reçetesi tanımlı değil. "
                "Önce reçete ekleyin."
            )
        else:
            empty_hint = "Sonuç bulunamadı"

    return JsonResponse({"results": results, "empty_hint": empty_hint})


@login_required
def uretim_emri_ekle(request):
    """Manuel üretim emri oluşturma — birden fazla satır destekler."""
    now = timezone.now()
    default_baslama = now.strftime("%Y-%m-%dT%H:%M")
    default_bitis = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")
    uretim_tipleri = UretimEmri.URETIM_TIPLERI

    def _base_context(**extra):
        ctx = {
            "uretim_tipleri": uretim_tipleri,
            "default_baslama": default_baslama,
            "default_bitis": default_bitis,
            "satirlar": [],
            "aciklama": "",
        }
        ctx.update(extra)
        return ctx

    if request.method == "POST":
        urun_ids = request.POST.getlist("urun")
        miktarlar = request.POST.getlist("miktar")
        production_types = request.POST.getlist("production_type")
        baslamalar = request.POST.getlist("planlanan_baslama")
        bitisler = request.POST.getlist("planlanan_bitis")
        urun_kodlari = request.POST.getlist("urun_kod")
        urun_adlari = request.POST.getlist("urun_ad")
        aciklama = (request.POST.get("aciklama") or "").strip()

        n = max(
            len(urun_ids),
            len(miktarlar),
            len(production_types),
            len(baslamalar),
            len(bitisler),
            1,
        )

        def _at(lst, i, default=""):
            return lst[i] if i < len(lst) else default

        # Form yeniden gösterimi için satırları sakla
        form_satirlar = []
        for i in range(n):
            form_satirlar.append(
                {
                    "urun": (_at(urun_ids, i) or "").strip(),
                    "urun_kod": (_at(urun_kodlari, i) or "").strip(),
                    "urun_ad": (_at(urun_adlari, i) or "").strip(),
                    "miktar": (_at(miktarlar, i) or "").strip(),
                    "production_type": (_at(production_types, i) or "STOCK").strip(),
                    "planlanan_baslama": (_at(baslamalar, i) or "").strip(),
                    "planlanan_bitis": (_at(bitisler, i) or "").strip(),
                }
            )

        # Boş satırları (ürün seçilmemiş) ele
        dolu_satirlar = [s for s in form_satirlar if s["urun"]]
        if not dolu_satirlar:
            messages.error(request, "En az bir ürün satırı ekleyin.")
            return render(
                request,
                "stokapp/uretim_emri_ekle.html",
                _base_context(satirlar=form_satirlar or [{}], aciklama=aciklama),
            )

        prepared = []
        errors = []
        for idx, sat in enumerate(dolu_satirlar, start=1):
            prefix = f"Satır {idx}"
            urun = StokItem.objects.filter(pk=sat["urun"]).first()
            if not urun:
                errors.append(f"{prefix}: ürün bulunamadı.")
                continue

            recete = get_aktif_recete_for_urun(urun)
            if not recete:
                errors.append(
                    f"{prefix} ({urun.stok_kodu}): aktif reçete bulunamadı."
                )
                continue

            try:
                miktar = Decimal((sat["miktar"] or "").replace(",", "."))
                if miktar <= 0:
                    raise ValueError
            except Exception:
                errors.append(f"{prefix} ({urun.stok_kodu}): geçerli miktar girin.")
                continue

            production_type = sat["production_type"]
            if production_type not in ("ORDER", "STOCK"):
                production_type = "STOCK"

            planlanan_baslama = _parse_datetime_local(sat["planlanan_baslama"])
            planlanan_bitis = _parse_datetime_local(sat["planlanan_bitis"])
            if not planlanan_baslama:
                errors.append(f"{prefix} ({urun.stok_kodu}): planlanan başlama geçersiz.")
                continue
            if not planlanan_bitis:
                errors.append(f"{prefix} ({urun.stok_kodu}): planlanan bitiş geçersiz.")
                continue
            if planlanan_bitis <= planlanan_baslama:
                errors.append(
                    f"{prefix} ({urun.stok_kodu}): bitiş, başlamadan sonra olmalıdır."
                )
                continue

            prepared.append(
                {
                    "urun": urun,
                    "recete": recete,
                    "miktar": miktar,
                    "production_type": production_type,
                    "planlanan_baslama": planlanan_baslama,
                    "planlanan_bitis": planlanan_bitis,
                }
            )

        if errors:
            for msg in errors:
                messages.error(request, msg)
            return render(
                request,
                "stokapp/uretim_emri_ekle.html",
                _base_context(satirlar=form_satirlar, aciklama=aciklama),
            )

        olusturulan = []
        try:
            with transaction.atomic():
                for item in prepared:
                    emir, alt_emirler = create_uretim_emri_with_alt_emirler(
                        recete=item["recete"],
                        miktar=item["miktar"],
                        planlanan_baslama=item["planlanan_baslama"],
                        planlanan_bitis=item["planlanan_bitis"],
                        aciklama=aciklama,
                        production_type=item["production_type"],
                    )
                    olusturulan.append((emir, alt_emirler))
        except Exception as exc:
            messages.error(request, f"Emirler oluşturulurken hata: {exc}")
            return render(
                request,
                "stokapp/uretim_emri_ekle.html",
                _base_context(satirlar=form_satirlar, aciklama=aciklama),
            )

        emir_nolar = []
        for emir, alt_emirler in olusturulan:
            emir_nolar.append(emir.emir_no)
            if alt_emirler:
                emir_nolar.extend(ae.emir_no for ae in alt_emirler)

        if len(olusturulan) == 1 and not olusturulan[0][1]:
            messages.success(request, f"Üretim emri {olusturulan[0][0].emir_no} oluşturuldu.")
            return redirect("stokapp:uretim_emri_detay", pk=olusturulan[0][0].pk)

        messages.success(
            request,
            f"{len(olusturulan)} üretim emri oluşturuldu: {', '.join(e.emir_no for e, _ in olusturulan)}.",
        )
        return redirect("stokapp:uretim_emri_listesi")

    return render(
        request,
        "stokapp/uretim_emri_ekle.html",
        _base_context(satirlar=[{}]),
    )


@login_required
def uretim_emri_detay(request, pk):
    """Üretim emri detay sayfası"""
    emir = get_object_or_404(
        UretimEmri.objects.select_related("recete__urun", "ust_uretim_emri", "ust_uretim_emri__recete__urun")
        .prefetch_related(
            Prefetch(
                "alt_emirler",
                queryset=UretimEmri.objects.select_related("recete__urun").order_by("id"),
            )
        ),
        pk=pk,
    )
    asamalar = emir.asamalar.all().order_by('sira')
    recete_detaylar = emir.recete.detaylar.all()
    
    # Recete operasyonlarını al (inspection için)
    recete_operasyonlar = emir.recete.operasyonlar.select_related('operasyon').all().order_by('sira')
    
    # Control plan'ı kontrol et
    product = emir.recete.urun
    control_plan = ControlPlan.objects.filter(
        product=product,
        status='ACTIVE'
    ).first()
    
    # Her operasyon adımı için gerekli kontrolleri hesapla
    operation_inspections = {}
    if control_plan:
        for operation_step in recete_operasyonlar:
            control_items = control_plan.items.filter(operation_step=operation_step)
            required_inspections = []
            
            for item in control_items:
                # Gerekli kontrol sayısını hesapla
                from .views_inspection import calculate_required_inspections
                required_count = calculate_required_inspections(emir, item)
                actual_count = WorkOrderInspection.objects.filter(
                    work_order=emir,
                    control_item=item,
                    operation_step=operation_step
                ).count()
                
                # Quality gate durumunu kontrol et
                has_fail = WorkOrderInspection.objects.filter(
                    work_order=emir,
                    control_item=item,
                    operation_step=operation_step,
                    pass_fail='FAIL'
                ).exists()
                
                required_inspections.append({
                    'item': item,
                    'required_count': required_count,
                    'actual_count': actual_count,
                    'remaining': max(0, required_count - actual_count),
                    'has_fail': has_fail,
                })
            
            if required_inspections:
                operation_inspections[operation_step.pk] = {
                    'operation_step': operation_step,
                    'inspections': required_inspections,
                    'all_completed': all(ri['remaining'] == 0 for ri in required_inspections),
                    'has_fail': any(ri['has_fail'] for ri in required_inspections),
                }
    
    # Her detay için gerekli miktarı hesapla (recete miktarı * emir miktarı)
    cikis_by_stok = {}
    for row in (
        StokHareketi.objects.filter(uretim_emri=emir, hareket_tipi="URETIM_CIKIS")
        .values("stok_item_id")
        .annotate(total=Sum("miktar"))
    ):
        cikis_by_stok[row["stok_item_id"]] = Decimal(str(row["total"] or 0))

    recete_detaylar_list = []
    for detay in recete_detaylar:
        gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
        mevcut_miktar = Decimal(str(detay.stok_item.mevcut_miktar or 0))
        uretim_cikis_miktar = cikis_by_stok.get(detay.stok_item_id, Decimal("0"))
        # Stok üretiminde veya başlatılmış emirde depodan çıkan miktar ihtiyacın karşılandığı sayılır
        if emir.production_type == "STOCK" or uretim_cikis_miktar > 0:
            karsilastirma_stok = mevcut_miktar + uretim_cikis_miktar
        else:
            karsilastirma_stok = mevcut_miktar
        recete_detaylar_list.append({
            "detay": detay,
            "gerekli_miktar": gerekli_miktar,
            "mevcut_miktar": mevcut_miktar,
            "uretim_cikis_miktar": uretim_cikis_miktar,
            "karsilastirma_stok": karsilastirma_stok,
            "yeterli": karsilastirma_stok >= gerekli_miktar,
        })
    
    # Üretim uyarılarını kontrol et
    product_revision = emir.recete.versiyon if hasattr(emir.recete, 'versiyon') else ''
    alerts = get_matching_alerts(product=product, product_revision=product_revision)
    
    context = {
        'emir': emir,
        'asamalar': asamalar,
        'recete_detaylar': recete_detaylar,
        'recete_detaylar_list': recete_detaylar_list,
        'alerts': alerts,
        'recete_operasyonlar': recete_operasyonlar,
        'control_plan': control_plan,
        'operation_inspections': operation_inspections,
    }
    return render(request, 'stokapp/uretim_emri_detay.html', context)


def uretim_emri_baslat_execute(emir, username):
    """
    PLANLANDI emri için hammadde URETIM_CIKIS ve durum BASLADI.
    Çağıran kod transaction.atomic() içinde olmalıdır (siparişten toplu oluşturma vb.).
    Dönüş: {"ok": bool, "error": str | None, "warnings": list[str], "block_messages": list[str]}
    """
    if emir.durum != "PLANLANDI":
        return {"ok": False, "error": "Sadece planlanmış emirler başlatılabilir.", "warnings": [], "block_messages": []}

    product = emir.recete.urun
    product_revision = emir.recete.versiyon if hasattr(emir.recete, "versiyon") else ""
    alerts = get_matching_alerts(product=product, product_revision=product_revision)
    block_alerts = [a for a in alerts if a.level == "BLOCK"]
    if block_alerts:
        return {
            "ok": False,
            "error": "Bu ürün için engelleme seviyesinde uyarılar bulunmaktadır. Üretim başlatılamaz.",
            "warnings": [],
            "block_messages": [a.message for a in block_alerts],
        }

    recete_detaylar = emir.recete.detaylar.all()
    eksik_stoklar = []
    warnings = []

    mevcut_cikis_hareketleri = StokHareketi.objects.filter(
        uretim_emri=emir,
        hareket_tipi="URETIM_CIKIS",
    ).values_list("stok_item_id", "miktar")
    cikis_dict = {}
    for stok_item_id, miktar in mevcut_cikis_hareketleri:
        cikis_dict[stok_item_id] = cikis_dict.get(stok_item_id, Decimal("0")) + Decimal(str(miktar))

    for detay in recete_detaylar:
        gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
        cikis_yapilan = cikis_dict.get(detay.stok_item_id, Decimal("0"))
        kalan_cikis = gerekli_miktar - cikis_yapilan
        if kalan_cikis <= 0:
            continue
        mevcut_stok = Decimal(str(detay.stok_item.mevcut_miktar))
        if mevcut_stok < kalan_cikis:
            eksik_miktar = kalan_cikis - mevcut_stok
            eksik_stoklar.append(
                {
                    "stok": detay.stok_item,
                    "gerekli": kalan_cikis,
                    "mevcut": mevcut_stok,
                    "eksik": eksik_miktar,
                }
            )

    for detay in recete_detaylar:
        gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
        cikis_yapilan = cikis_dict.get(detay.stok_item_id, Decimal("0"))
        kalan_cikis = gerekli_miktar - cikis_yapilan
        if kalan_cikis <= 0:
            continue
        mevcut_stok = Decimal(str(detay.stok_item.mevcut_miktar))
        cikis_miktari = min(mevcut_stok, kalan_cikis)
        if cikis_miktari > 0:
            StokHareketi.objects.create(
                stok_item=detay.stok_item,
                hareket_tipi="URETIM_CIKIS",
                miktar=cikis_miktari,
                birim=detay.birim,
                referans_no=emir.emir_no,
                uretim_emri=emir,
                aciklama=(
                    f"Üretim emri {emir.emir_no} için hammadde çıkışı "
                    f"(Mevcut stok: {cikis_miktari}, Gerekli: {gerekli_miktar})"
                ),
                user=username,
            )

    if eksik_stoklar:
        warnings.append("Bazı malzemeler eksik, ancak mevcut malzemelerle üretim başlatılıyor:")
        for eksik in eksik_stoklar:
            warnings.append(
                f"{eksik['stok'].stok_kodu}: Gerekli: {eksik['gerekli']}, "
                f"Mevcut: {eksik['mevcut']}, Eksik: {eksik['eksik']}"
            )

    emir.durum = "BASLADI"
    emir.gerceklesen_baslama = timezone.now()
    emir.save()

    ilk_asama = emir.asamalar.first()
    if ilk_asama:
        ilk_asama.durum = "DEVAM_EDIYOR"
        ilk_asama.baslama_zamani = timezone.now()
        ilk_asama.save()
        try:
            from .uretim_dis_sync import sync_dis_on_devam

            sync_dis_on_devam(ilk_asama, username)
        except ValueError as e:
            return {"ok": False, "error": str(e), "warnings": warnings, "block_messages": []}

    return {"ok": True, "error": None, "warnings": warnings, "block_messages": []}


@login_required
def uretim_emri_baslat(request, pk):
    """Üretim emrini başlat (stok üretimi emirleri; sipariş emirleri Siparişler ekranından başlar)"""
    emir = get_object_or_404(UretimEmri, pk=pk)

    if emir.production_type == "ORDER":
        messages.info(
            request,
            "Siparişe bağlı iş emirleri yalnızca Satış → Siparişler üzerinden “Üretimi Başlat” ile "
            "oluşturulur ve tek seferde başlatılır. İş emri sayfasından tekrar başlatmayın.",
        )
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    if emir.durum != "PLANLANDI":
        messages.error(request, "Sadece planlanmış emirler başlatılabilir.")
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    with transaction.atomic():
        result = uretim_emri_baslat_execute(emir, request.user.username)

    if not result["ok"]:
        messages.error(request, result["error"])
        for msg in result.get("block_messages") or []:
            messages.error(request, f"🔴 {msg}")
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    for w in result.get("warnings") or []:
        messages.warning(request, w)

    messages.success(request, f"Üretim emri {emir.emir_no} başlatıldı.")
    return redirect("stokapp:uretim_emri_detay", pk=pk)


def uretim_emri_tamamla_execute(emir, username, allow_negative=False):
    """
    BASLADI emri tamamlar: eksik hammadde çıkışı + üretilen ürün girişi.
    Dönüş: {
      ok, error, requires_confirmation, items (negatif risk),
    }
    """
    if emir.durum != "BASLADI":
        return {
            "ok": False,
            "error": "Sadece başlatılmış emirler tamamlanabilir.",
            "requires_confirmation": False,
            "items": [],
        }

    recete_detaylar = list(emir.recete.detaylar.select_related("stok_item"))
    mevcut_cikis_hareketleri = StokHareketi.objects.filter(
        uretim_emri=emir,
        hareket_tipi="URETIM_CIKIS",
    ).values_list("stok_item_id", "miktar")

    cikis_dict = {}
    for stok_item_id, miktar in mevcut_cikis_hareketleri:
        cikis_dict[stok_item_id] = cikis_dict.get(stok_item_id, Decimal("0")) + Decimal(str(miktar))

    negative_risk_items = []
    for detay in recete_detaylar:
        gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
        cikis_yapilan_miktar = cikis_dict.get(detay.stok_item_id, Decimal("0"))
        eksik_miktar = gerekli_miktar - cikis_yapilan_miktar
        if eksik_miktar <= 0:
            continue
        mevcut_stok = Decimal(str(detay.stok_item.mevcut_miktar))
        kalan_stok = mevcut_stok - eksik_miktar
        if kalan_stok < 0:
            negative_risk_items.append(
                {
                    "stok_kodu": detay.stok_item.stok_kodu,
                    "stok_adi": detay.stok_item.ad,
                    "mevcut": mevcut_stok,
                    "dusecek": eksik_miktar,
                    "kalan": kalan_stok,
                }
            )

    if negative_risk_items and not allow_negative:
        return {
            "ok": False,
            "error": None,
            "requires_confirmation": True,
            "items": negative_risk_items,
        }

    for detay in recete_detaylar:
        gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
        cikis_yapilan_miktar = cikis_dict.get(detay.stok_item_id, Decimal("0"))
        eksik_miktar = gerekli_miktar - cikis_yapilan_miktar
        if eksik_miktar > 0:
            StokHareketi.objects.create(
                stok_item=detay.stok_item,
                hareket_tipi="URETIM_CIKIS",
                miktar=eksik_miktar,
                birim=detay.birim,
                referans_no=emir.emir_no,
                uretim_emri=emir,
                aciklama=(
                    f"Üretim emri {emir.emir_no} tamamlandı - hammadde çıkışı "
                    f"(Gerekli: {gerekli_miktar}, Daha önce düşülen: {cikis_yapilan_miktar}, "
                    f"Şimdi düşülen: {eksik_miktar})"
                ),
                user=username,
            )

    urun = emir.recete.urun
    StokHareketi.objects.create(
        stok_item=urun,
        hareket_tipi="URETIM_GIRIS",
        miktar=emir.miktar,
        birim=urun.birim,
        referans_no=emir.emir_no,
        uretim_emri=emir,
        aciklama=f"Üretim emri {emir.emir_no} tamamlandı",
        user=username,
    )

    emir.durum = "TAMAMLANDI"
    emir.gerceklesen_bitis = timezone.now()
    emir.save()

    for asama in emir.asamalar.all():
        if asama.durum != "TAMAMLANDI":
            asama.durum = "TAMAMLANDI"
            asama.bitis_zamani = timezone.now()
            if not asama.baslama_zamani:
                asama.baslama_zamani = timezone.now()
            if asama.baslama_zamani and asama.bitis_zamani:
                gecen_sure = (asama.bitis_zamani - asama.baslama_zamani).total_seconds() / 60
                asama.gerceklesen_sure = int(gecen_sure)
            asama.save()

    _tool_usage_hesapla_ve_logla(emir)

    siparis_no = _siparis_no_emirden_bul(emir)
    if siparis_no:
        siparis = Siparis.objects.filter(siparis_numarasi=siparis_no).first()
        if siparis:
            ilgili_emirler = UretimEmri.objects.filter(
                aciklama__icontains=f"Sipariş {siparis_no} için oluşturuldu"
            )
            if ilgili_emirler.exists() and not ilgili_emirler.exclude(durum="TAMAMLANDI").exists():
                siparis.uretim_durumu = "TAMAMLANDI"
                siparis.save(update_fields=["uretim_durumu"])

    return {
        "ok": True,
        "error": None,
        "requires_confirmation": False,
        "items": [],
    }


@login_required
def uretim_emri_tamamla(request, pk):
    """Üretim emrini tamamla ve stok girişi yap"""
    emir = get_object_or_404(UretimEmri, pk=pk)

    if emir.durum != "BASLADI":
        messages.error(request, "Sadece başlatılmış emirler tamamlanabilir.")
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    allow_negative = request.GET.get("allow_negative") == "1"
    preview = request.GET.get("preview") == "1"

    if preview:
        # Sadece risk kontrolü (yazma yok)
        recete_detaylar = list(emir.recete.detaylar.select_related("stok_item"))
        mevcut_cikis_hareketleri = StokHareketi.objects.filter(
            uretim_emri=emir, hareket_tipi="URETIM_CIKIS"
        ).values_list("stok_item_id", "miktar")
        cikis_dict = {}
        for stok_item_id, miktar in mevcut_cikis_hareketleri:
            cikis_dict[stok_item_id] = cikis_dict.get(stok_item_id, Decimal("0")) + Decimal(str(miktar))
        negative_risk_items = []
        for detay in recete_detaylar:
            gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
            cikis_yapilan_miktar = cikis_dict.get(detay.stok_item_id, Decimal("0"))
            eksik_miktar = gerekli_miktar - cikis_yapilan_miktar
            if eksik_miktar <= 0:
                continue
            mevcut_stok = Decimal(str(detay.stok_item.mevcut_miktar))
            kalan_stok = mevcut_stok - eksik_miktar
            if kalan_stok < 0:
                negative_risk_items.append(
                    {
                        "stok_kodu": detay.stok_item.stok_kodu,
                        "stok_adi": detay.stok_item.ad,
                        "mevcut": mevcut_stok,
                        "dusecek": eksik_miktar,
                        "kalan": kalan_stok,
                    }
                )
        if negative_risk_items and not allow_negative:
            return JsonResponse(
                {
                    "success": True,
                    "requires_confirmation": True,
                    "message": "Stok eksi değere düşecektir. Onaylıyor musunuz?",
                    "items": negative_risk_items,
                }
            )
        return JsonResponse(
            {
                "success": True,
                "requires_confirmation": False,
                "message": "Tamamlama için stok kontrolü uygun.",
            }
        )

    with transaction.atomic():
        result = uretim_emri_tamamla_execute(
            emir, request.user.username, allow_negative=allow_negative
        )

    if result.get("requires_confirmation"):
        messages.warning(request, "Stok eksi değere düşecektir. Onaylıyor musunuz?")
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    if not result["ok"]:
        messages.error(request, result.get("error") or "Tamamlama başarısız.")
        return redirect("stokapp:uretim_emri_detay", pk=pk)

    messages.success(request, f"Üretim emri {emir.emir_no} tamamlandı ve stok girişi yapıldı.")
    return redirect("stokapp:uretim_emri_detay", pk=pk)


@login_required
@require_http_methods(["POST"])
def uretim_emri_toplu_islem(request):
    """Listeden seçilen emirleri toplu başlat veya tamamla."""
    action = (request.POST.get("action") or "").strip()
    allow_negative = request.POST.get("allow_negative") == "1"
    raw_ids = request.POST.getlist("emir_ids")
    redirect_to = request.POST.get("next") or reverse("stokapp:uretim_emri_listesi")

    try:
        emir_ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]
    except (TypeError, ValueError):
        emir_ids = []

    if action not in ("baslat", "tamamla"):
        messages.error(request, "Geçersiz toplu işlem.")
        return redirect(redirect_to)
    if not emir_ids:
        messages.error(request, "Lütfen en az bir üretim emri seçin.")
        return redirect(redirect_to)

    emirler = list(
        UretimEmri.objects.filter(pk__in=emir_ids)
        .select_related("recete__urun")
        .order_by("id")
    )
    if not emirler:
        messages.error(request, "Seçilen emirler bulunamadı.")
        return redirect(redirect_to)

    basarili = []
    atlanan = []
    hatalar = []
    uyarilar = []

    if action == "baslat":
        for emir in emirler:
            if emir.production_type == "ORDER":
                atlanan.append(f"{emir.emir_no}: sipariş emri (Siparişler ekranından başlatılır)")
                continue
            if emir.durum != "PLANLANDI":
                atlanan.append(f"{emir.emir_no}: durum {emir.get_durum_display()}")
                continue
            try:
                with transaction.atomic():
                    result = uretim_emri_baslat_execute(emir, request.user.username)
                if not result["ok"]:
                    hatalar.append(f"{emir.emir_no}: {result.get('error') or 'Başlatılamadı'}")
                    for msg in result.get("block_messages") or []:
                        hatalar.append(f"{emir.emir_no}: {msg}")
                    continue
                for w in result.get("warnings") or []:
                    uyarilar.append(f"{emir.emir_no}: {w}")
                basarili.append(emir.emir_no)
            except Exception as exc:
                hatalar.append(f"{emir.emir_no}: {exc}")

        if basarili:
            messages.success(
                request,
                f"{len(basarili)} emir başlatıldı: {', '.join(basarili)}.",
            )
    else:
        for emir in emirler:
            if emir.durum != "BASLADI":
                atlanan.append(f"{emir.emir_no}: durum {emir.get_durum_display()}")
                continue
            try:
                with transaction.atomic():
                    result = uretim_emri_tamamla_execute(
                        emir, request.user.username, allow_negative=allow_negative
                    )
                if result.get("requires_confirmation"):
                    atlanan.append(f"{emir.emir_no}: stok eksi riski (onay gerekli)")
                    continue
                if not result["ok"]:
                    hatalar.append(f"{emir.emir_no}: {result.get('error') or 'Tamamlanamadı'}")
                    continue
                basarili.append(emir.emir_no)
            except Exception as exc:
                hatalar.append(f"{emir.emir_no}: {exc}")

        if basarili:
            messages.success(
                request,
                f"{len(basarili)} emir tamamlandı: {', '.join(basarili)}.",
            )

    for msg in atlanan:
        messages.warning(request, f"Atlandı — {msg}")
    for msg in hatalar:
        messages.error(request, msg)
    for msg in uyarilar:
        messages.warning(request, msg)

    if not basarili and not atlanan and not hatalar:
        messages.info(request, "İşlenecek uygun emir bulunamadı.")

    return redirect(redirect_to)


def _uretim_emri_malzeme_iade_olustur(emir, kullanici, islem='iptal', bagla_emir=True):
    """
    Başlatılmış üretim emrinde fiilen yapılmış URETIM_CIKIS kadar stoğu iade et.
    Reçete ihtiyacının tamamı değil, gerçek tüketim miktarı esas alınır.
    """
    cikisler = (
        StokHareketi.objects.filter(
            uretim_emri=emir,
            hareket_tipi='URETIM_CIKIS',
        )
        .values('stok_item_id', 'birim')
        .annotate(toplam=Sum('miktar'))
    )
    islem_metni = 'iptal edildi' if islem == 'iptal' else 'silindi'
    for row in cikisler:
        miktar = Decimal(str(row['toplam'] or 0))
        if miktar <= 0:
            continue
        stok_item = StokItem.objects.get(pk=row['stok_item_id'])
        StokHareketi.objects.create(
            stok_item=stok_item,
            hareket_tipi='URETIM_IADE',
            miktar=miktar,
            birim=row['birim'] or stok_item.birim or 'Adet',
            referans_no=emir.emir_no,
            uretim_emri=emir if bagla_emir else None,
            aciklama=(
                f'Üretim emri {emir.emir_no} {islem_metni} — '
                f'tüketilen malzeme stoğa iade edildi'
            ),
            user=kullanici or 'Sistem',
        )


@login_required
def uretim_emri_iptal(request, pk):
    """Üretim emrini iptal et"""
    emir = get_object_or_404(UretimEmri, pk=pk)
    
    if emir.durum == 'TAMAMLANDI':
        messages.error(request, 'Tamamlanmış emirler iptal edilemez.')
        return redirect('stokapp:uretim_emri_detay', pk=pk)
    
    if request.method == 'POST':
        aciklama = request.POST.get('aciklama', '')
        
        # Eğer başlatılmışsa, fiilen tüketilen malzemeyi iade et
        if emir.durum == 'BASLADI':
            with transaction.atomic():
                _uretim_emri_malzeme_iade_olustur(
                    emir,
                    request.user.username,
                    islem='iptal',
                )
                StokHareketi.objects.filter(
                    uretim_emri=emir,
                    hareket_tipi='URETIM_CIKIS',
                ).delete()
        
        emir.durum = 'IPTAL'
        if aciklama:
            emir.aciklama = f"{emir.aciklama}\n[İPTAL] {aciklama}" if emir.aciklama else f"[İPTAL] {aciklama}"
        emir.save()
        
        messages.success(request, f'Üretim emri {emir.emir_no} iptal edildi.')
        return redirect('stokapp:uretim_emri_listesi')
    
    return render(request, 'stokapp/uretim_emri_iptal.html', {'emir': emir})


@login_required
def uretim_emri_sil(request, pk):
    """Üretim emrini sil"""
    emir = get_object_or_404(UretimEmri, pk=pk)
    
    # Tamamlanmış emirler silinemez (stok girişi yapılmış)
    if emir.durum == 'TAMAMLANDI':
        messages.error(request, 'Tamamlanmış üretim emirleri silinemez. Önce stok hareketlerini kontrol edin.')
        return redirect('stokapp:uretim_emri_detay', pk=pk)
    
    if request.method == 'POST':
        emir_no = emir.emir_no
        
        with transaction.atomic():
            # Başlatılmış emirler için fiilen tüketilen malzemeyi iade et
            if emir.durum == 'BASLADI':
                _uretim_emri_malzeme_iade_olustur(
                    emir,
                    request.user.username,
                    islem='sil',
                    bagla_emir=False,
                )
            
            # İlişkili üretim hareket kayıtlarını temizle (iade kaydı referans_no ile kalır)
            StokHareketi.objects.filter(uretim_emri=emir).delete()
            
            # Üretim aşamalarını sil
            emir.asamalar.all().delete()
            
            # Emri sil
            emir.delete()
        
        messages.success(request, f'Üretim emri "{emir_no}" başarıyla silindi.')
        return redirect('stokapp:uretim_emri_listesi')
    
    # GET isteği için onay sayfası göster
    # İlişkili stok hareketlerini kontrol et
    stok_hareketleri = StokHareketi.objects.filter(uretim_emri=emir)
    
    context = {
        'emir': emir,
        'stok_hareketleri': stok_hareketleri,
        'stok_hareket_sayisi': stok_hareketleri.count(),
    }
    return render(request, 'stokapp/uretim_emri_sil.html', context)


def _planlama_format_duration(minutes):
    if minutes is None:
        return "-"
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return "-"
    if total < 0:
        total = 0
    saat = total // 60
    dakika = total % 60
    return f"{saat:02d}:{dakika:02d}"


def _planlama_status_meta(durum):
    status_map = {
        "BEKLIYOR": {"label": "Bekliyor", "color": "status-waiting"},
        "DEVAM_EDIYOR": {"label": "Devam Ediyor", "color": "status-active"},
        "BEKLEMEDE": {"label": "Beklemede", "color": "status-paused"},
        "TAMAMLANDI": {"label": "Tamamlandı", "color": "status-done"},
        "SORUNLU": {"label": "Sorunlu / Durduruldu", "color": "status-problem"},
    }
    return status_map.get(durum, {"label": durum or "-", "color": "status-waiting"})


def _planlama_kapat_acik_durus(asama, now=None):
    if not now:
        now = timezone.now()
    acik_durus = asama.durus_kayitlari.filter(bitis_zamani__isnull=True).order_by("-baslama_zamani").first()
    if not acik_durus:
        return 0
    sure = int(max(0, (now - acik_durus.baslama_zamani).total_seconds()))
    acik_durus.bitis_zamani = now
    acik_durus.sure_saniye = sure
    acik_durus.save(update_fields=["bitis_zamani", "sure_saniye"])
    asama.duraklatma_toplam_saniye = int(asama.duraklatma_toplam_saniye or 0) + sure
    asama.save(update_fields=["duraklatma_toplam_saniye"])
    return sure


def _planlama_gerceklesen_sure_hesapla(asama):
    if not asama.baslama_zamani:
        return None
    bitis = asama.bitis_zamani or timezone.now()
    toplam_sn = int(max(0, (bitis - asama.baslama_zamani).total_seconds()))
    durus_sn = int(asama.duraklatma_toplam_saniye or 0)
    calisma_sn = max(0, toplam_sn - durus_sn)
    return int(calisma_sn / 60)


def _planlama_apply_status_change(asama, yeni_durum, user=None):
    now = timezone.now()
    onceki_durum = asama.durum

    if yeni_durum == "DEVAM_EDIYOR":
        if not asama.baslama_zamani:
            asama.baslama_zamani = now
        if onceki_durum in ["BEKLEMEDE", "SORUNLU"]:
            _planlama_kapat_acik_durus(asama, now)
        asama.durum = "DEVAM_EDIYOR"
        asama.save(update_fields=["durum", "baslama_zamani"])
        from .uretim_dis_sync import sync_dis_on_devam

        sync_dis_on_devam(asama, user)
        return

    if yeni_durum in ["BEKLEMEDE", "SORUNLU"]:
        if onceki_durum == "DEVAM_EDIYOR":
            UretimAsamaDurusKaydi.objects.create(
                asama=asama,
                baslama_zamani=now,
                aciklama=f"{yeni_durum} durumuna alındı",
            )
        asama.durum = yeni_durum
        asama.save(update_fields=["durum"])
        return

    if yeni_durum == "TAMAMLANDI":
        _planlama_kapat_acik_durus(asama, now)
        asama.durum = "TAMAMLANDI"
        asama.bitis_zamani = now
        asama.gerceklesen_sure = _planlama_gerceklesen_sure_hesapla(asama)
        asama.save(update_fields=["durum", "bitis_zamani", "gerceklesen_sure"])

        sonraki_asama = asama.uretim_emri.asamalar.filter(sira__gt=asama.sira).order_by("sira").first()
        sonraki_basladi = None
        if sonraki_asama and sonraki_asama.durum == "BEKLIYOR":
            sonraki_asama.durum = "DEVAM_EDIYOR"
            if not sonraki_asama.baslama_zamani:
                sonraki_asama.baslama_zamani = now
            sonraki_asama.save(update_fields=["durum", "baslama_zamani"])
            sonraki_basladi = sonraki_asama
        from .uretim_dis_sync import sync_dis_on_devam, sync_dis_on_tamamlandi

        sync_dis_on_tamamlandi(asama, user)
        if sonraki_basladi is not None:
            sync_dis_on_devam(sonraki_basladi, user)
        return

    if yeni_durum == "BEKLIYOR":
        asama.durum = "BEKLIYOR"
        asama.save(update_fields=["durum"])


@login_required
def asama_durum_guncelle(request, asama_id):
    """Üretim aşaması durumunu güncelle (AJAX)"""
    asama = get_object_or_404(UretimAsamasi, pk=asama_id)

    if request.method == 'POST':
        yeni_durum = request.POST.get('durum')

        if yeni_durum in ['BEKLIYOR', 'DEVAM_EDIYOR', 'BEKLEMEDE', 'TAMAMLANDI', 'SORUNLU']:
            try:
                with transaction.atomic():
                    _planlama_apply_status_change(asama, yeni_durum, request.user)
            except ValueError as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
            return JsonResponse({'success': True, 'durum': yeni_durum})

    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})


def _planlama_add_months(base_dt, months):
    year = base_dt.year + (base_dt.month - 1 + months) // 12
    month = (base_dt.month - 1 + months) % 12 + 1
    day = min(base_dt.day, monthrange(year, month)[1])
    return base_dt.replace(year=year, month=month, day=day)


def _planlama_slots(scale, base_date, count):
    slots = []
    if scale == "hour":
        start_dt = timezone.make_aware(datetime.combine(base_date, datetime.min.time())).replace(hour=8)
        delta = timedelta(minutes=15)
        total_slots = count * 4
        for i in range(total_slots):
            slot_start = start_dt + (delta * i)
            slot_end = slot_start + delta
            is_hour_start = slot_start.minute == 0
            label = slot_start.strftime("%H:%M") if is_hour_start else ""
            slots.append({
                "label": label,
                "start": slot_start,
                "end": slot_end,
                "key": slot_start.isoformat(),
                "is_hour_start": is_hour_start,
            })
        return slots

    if scale == "day":
        start_dt = timezone.make_aware(datetime.combine(base_date, datetime.min.time()))
        for i in range(count):
            slot_start = start_dt + timedelta(days=i)
            slot_end = slot_start + timedelta(days=1)
            label = slot_start.strftime("%d.%m")
            slots.append({
                "label": label,
                "start": slot_start,
                "end": slot_end,
                "key": slot_start.isoformat(),
            })
        return slots

    if scale == "week":
        week_start = base_date - timedelta(days=base_date.weekday())
        start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
        for i in range(count):
            slot_start = start_dt + timedelta(weeks=i)
            slot_end = slot_start + timedelta(weeks=1)
            label = f"{slot_start.strftime('%d.%m')} - {(slot_end - timedelta(days=1)).strftime('%d.%m')}"
            slots.append({
                "label": label,
                "start": slot_start,
                "end": slot_end,
                "key": slot_start.isoformat(),
            })
        return slots

    if scale == "month":
        month_start = base_date.replace(day=1)
        start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))
        for i in range(count):
            slot_start = _planlama_add_months(start_dt, i)
            slot_end = _planlama_add_months(start_dt, i + 1)
            label = slot_start.strftime("%m.%Y")
            slots.append({
                "label": label,
                "start": slot_start,
                "end": slot_end,
                "key": slot_start.isoformat(),
            })
        return slots

    if scale == "year":
        year_start = base_date.replace(month=1, day=1)
        start_dt = timezone.make_aware(datetime.combine(year_start, datetime.min.time()))
        for i in range(count):
            slot_start = start_dt.replace(year=start_dt.year + i)
            slot_end = slot_start.replace(year=slot_start.year + 1)
            label = slot_start.strftime("%Y")
            slots.append({
                "label": label,
                "start": slot_start,
                "end": slot_end,
                "key": slot_start.isoformat(),
            })
        return slots

    return []


def _planlama_toplam_sure_dakika(asama):
    birim_sure = Decimal(str(asama.planlanan_sure or 0))
    emir_miktari = Decimal(str(asama.uretim_emri.miktar or 0))
    toplam = birim_sure * emir_miktari
    if toplam <= 0:
        return 0
    return int(toplam)


def _planlama_planlanan_sure_dakika(asama):
    if asama.planlanan_baslama and asama.planlanan_bitis and asama.planlanan_bitis > asama.planlanan_baslama:
        return int((asama.planlanan_bitis - asama.planlanan_baslama).total_seconds() / 60)
    return _planlama_toplam_sure_dakika(asama)


def _planlama_round_to_slot(dt, slot_minutes=15):
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    total_minutes = dt.hour * 60 + dt.minute
    rounded_total = int(round(total_minutes / slot_minutes) * slot_minutes)
    rounded_total = max(0, min(23 * 60 + 59, rounded_total))
    hour = rounded_total // 60
    minute = rounded_total % 60
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _planlama_overlap_count(personel_id, start_dt, end_dt, exclude_asama_id=None):
    qs = UretimAsamasi.objects.filter(
        atanan_personel_id=personel_id,
        planlanan_baslama__lt=end_dt,
        planlanan_bitis__gt=start_dt,
    )
    if exclude_asama_id:
        qs = qs.exclude(pk=exclude_asama_id)
    return qs.count()


def _planlama_personel_izin_cakisma(personel_id, start_dt, end_dt):
    if not personel_id or not start_dt or not end_dt:
        return None
    return PersonelIzin.objects.filter(
        personel_id=personel_id,
        baslangic_zamani__lt=end_dt,
        bitis_zamani__gt=start_dt,
    ).order_by("baslangic_zamani").first()


def _planlama_unassigned_tree(unassigned_qs):
    """Atanmamış görevleri iş emri → bileşen → operasyon ağacına dönüştürür."""
    from collections import OrderedDict

    emir_map = OrderedDict()
    for asama in unassigned_qs:
        emir = asama.uretim_emri
        urun = emir.recete.urun
        eid = emir.pk
        if eid not in emir_map:
            emir_map[eid] = {
                "emir_id": eid,
                "emir_no": emir.emir_no,
                "urun_kod": urun.stok_kodu,
                "urun_ad": urun.ad,
                "bilesenler": OrderedDict(),
            }
        detay_key = asama.recete_detay_id or 0
        bilesenler = emir_map[eid]["bilesenler"]
        if detay_key not in bilesenler:
            if asama.recete_detay_id and asama.recete_detay:
                stok = asama.recete_detay.stok_item
                label = f"{stok.stok_kodu} — {stok.ad}"
            else:
                label = "Genel Operasyon"
            bilesenler[detay_key] = {
                "detay_id": detay_key,
                "label": label,
                "asamalar": [],
            }
        bilesenler[detay_key]["asamalar"].append(asama)

    tree = []
    for emir in emir_map.values():
        emir["bilesenler"] = list(emir["bilesenler"].values())
        tree.append(emir)
    return tree


@login_required
def uretim_planlama(request):
    scale_map = {
        "saat": "hour",
        "gun": "day",
        "hafta": "week",
        "ay": "month",
        "yil": "year",
    }
    raw_scale = request.GET.get("scale", "hour")
    scale = scale_map.get(raw_scale, raw_scale)
    if scale not in ["hour", "day", "week", "month", "year"]:
        scale = "hour"

    start_str = request.GET.get("start")
    if start_str:
        try:
            base_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            base_date = timezone.localdate()
    else:
        base_date = timezone.localdate()

    default_counts = {
        "hour": 12,
        "day": 14,
        "week": 8,
        "month": 6,
        "year": 5,
    }
    try:
        count = int(request.GET.get("count", default_counts.get(scale, 14)))
    except ValueError:
        count = default_counts.get(scale, 14)
    count = max(3, min(count, 24))

    slots = _planlama_slots(scale, base_date, count)
    if not slots:
        slots = _planlama_slots("day", base_date, default_counts["day"])

    range_start = slots[0]["start"]
    range_end = slots[-1]["end"]

    personeller = Personel.objects.filter(aktif=True).order_by("ad", "soyad")

    # Sistemsel tutarsızlık nedeniyle personeli geçersiz kalan görevleri
    # (pasif personel veya veritabanında karşılığı olmayan personel id)
    # yeniden atanabilmesi için atanmamış havuza geri al.
    valid_personel_ids = Personel.objects.values("id")
    UretimAsamasi.objects.filter(
        atanan_personel_id__isnull=False,
    ).exclude(
        durum="TAMAMLANDI",
    ).filter(
        Q(atanan_personel__aktif=False) | ~Q(atanan_personel_id__in=valid_personel_ids)
    ).update(
        atanan_personel=None,
        planlanan_baslama=None,
        planlanan_bitis=None,
    )

    # Personelsiz kalan aktif görevlerin durumu "Devam ediyor/Beklemede/Sorunlu" ise
    # tutarlı olması için yeniden "Bekliyor"a çek.
    UretimAsamasi.objects.filter(
        atanan_personel_id__isnull=True,
        durum__in=["DEVAM_EDIYOR", "BEKLEMEDE", "SORUNLU"],
    ).update(
        durum="BEKLIYOR",
        baslama_zamani=None,
        bitis_zamani=None,
        planlanan_baslama=None,
        planlanan_bitis=None,
    )

    unassigned = UretimAsamasi.objects.select_related(
        "uretim_emri", "uretim_emri__recete", "uretim_emri__recete__urun",
        "recete_detay", "recete_detay__stok_item",
    ).filter(
        atanan_personel__isnull=True,
    ).exclude(
        durum="TAMAMLANDI",
    ).order_by("uretim_emri__planlanan_baslama", "recete_detay__sira", "sira")

    unassigned_tree = _planlama_unassigned_tree(unassigned)

    assigned = UretimAsamasi.objects.select_related(
        "atanan_personel", "uretim_emri", "uretim_emri__recete", "uretim_emri__recete__urun",
        "recete_detay", "recete_detay__stok_item",
    ).filter(
        atanan_personel__isnull=False,
        planlanan_baslama__isnull=False,
        planlanan_bitis__isnull=False,
        planlanan_baslama__lt=range_end,
        planlanan_bitis__gt=range_start,
    ).order_by("planlanan_baslama")

    assignments = []
    for asama in assigned:
        total_minutes = _planlama_planlanan_sure_dakika(asama)
        status_meta = _planlama_status_meta(asama.durum)
        urun = asama.uretim_emri.recete.urun
        assignments.append({
            "id": asama.id,
            "personel_id": asama.atanan_personel_id,
            "slot_key": asama.planlanan_baslama.isoformat(),
            "start": asama.planlanan_baslama.isoformat() if asama.planlanan_baslama else None,
            "end": asama.planlanan_bitis.isoformat() if asama.planlanan_bitis else None,
            "emir_id": asama.uretim_emri_id,
            "detay_id": asama.recete_detay_id or 0,
            "emir_no": asama.uretim_emri.emir_no,
            "asama_ad": asama.ad,
            "urun": urun.ad,
            "urun_kod": urun.stok_kodu,
            "sure": asama.planlanan_sure,
            "total_minutes": total_minutes,
            "status": asama.durum,
            "status_label": status_meta["label"],
            "status_class": status_meta["color"],
            "personel_ad": f"{asama.atanan_personel.ad} {asama.atanan_personel.soyad}" if asama.atanan_personel else "",
        })

    context = {
        "scale": scale,
        "start_date": base_date.strftime("%Y-%m-%d"),
        "count": count,
        "slots": slots,
        "personeller": personeller,
        "unassigned": unassigned,
        "unassigned_tree": unassigned_tree,
        "assignments_json": json.dumps(assignments, default=str),
    }
    return render(request, "stokapp/uretim_planlama.html", context)


@login_required
@never_cache
def uretim_planlama_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:uretim_planlama')

    scale_map = {
        "saat": "hour",
        "gun": "day",
        "hafta": "week",
        "ay": "month",
        "yil": "year",
    }
    raw_scale = request.GET.get("scale", "hour")
    scale = scale_map.get(raw_scale, raw_scale)
    if scale not in ["hour", "day", "week", "month", "year"]:
        scale = "hour"

    start_str = request.GET.get("start")
    if start_str:
        try:
            base_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            base_date = timezone.localdate()
    else:
        base_date = timezone.localdate()

    default_counts = {"hour": 12, "day": 14, "week": 8, "month": 6, "year": 5}
    try:
        count = int(request.GET.get("count", default_counts.get(scale, 14)))
    except ValueError:
        count = default_counts.get(scale, 14)
    count = max(3, min(count, 24))

    slots = _planlama_slots(scale, base_date, count)
    if not slots:
        slots = _planlama_slots("day", base_date, default_counts["day"])
    range_start = slots[0]["start"]
    range_end = slots[-1]["end"]

    assigned = UretimAsamasi.objects.select_related(
        "atanan_personel", "uretim_emri", "uretim_emri__recete", "uretim_emri__recete__urun",
    ).filter(
        atanan_personel__isnull=False,
        planlanan_baslama__isnull=False,
        planlanan_bitis__isnull=False,
        planlanan_baslama__lt=range_end,
        planlanan_bitis__gt=range_start,
    ).order_by("planlanan_baslama")

    olusturma_tarihi = timezone.localtime(timezone.now())
    template = render(
        request,
        "stokapp/uretim_planlama_pdf.html",
        {
            "asamalar": assigned,
            "scale": scale,
            "start_date": base_date,
            "count": count,
            "olusturma_tarihi": olusturma_tarihi,
        },
    )
    css = CSS(string="""
        @page { size: A4 landscape; margin: 10mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8pt; color: #111827; }
        h1 { font-size: 14pt; margin: 0 0 4px 0; }
        .meta { color: #6b7280; font-size: 8pt; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f3f4f6; border: 1px solid #d1d5db; padding: 5px 4px; text-align: left; font-size: 7.5pt; }
        td { border: 1px solid #e5e7eb; padding: 4px; vertical-align: top; font-size: 7.5pt; }
        .num { text-align: right; white-space: nowrap; }
        .empty { text-align: center; color: #6b7280; padding: 24px; }
    """)

    try:
        pdf_bytes = HTML(string=template.content.decode("utf-8"), base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_planlama')

    filename = f'uretim_planlama_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def uretim_planlama_atama(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Geçersiz veri"}, status=400)

    asama_id = payload.get("asama_id")
    personel_id = payload.get("personel_id")
    slot_start_raw = payload.get("slot_start")
    slot_end_raw = payload.get("slot_end")

    if not asama_id:
        return JsonResponse({"success": False, "error": "Aşama bulunamadı"}, status=400)

    asama = get_object_or_404(UretimAsamasi, pk=asama_id)

    if not personel_id:
        asama.atanan_personel = None
        asama.planlanan_baslama = None
        asama.planlanan_bitis = None
        asama.save(update_fields=["atanan_personel", "planlanan_baslama", "planlanan_bitis"])
        return JsonResponse({"success": True})

    personel = get_object_or_404(Personel, pk=personel_id)
    slot_start = parse_datetime(slot_start_raw) if slot_start_raw else None
    slot_end = parse_datetime(slot_end_raw) if slot_end_raw else None

    if not slot_start or not slot_end:
        return JsonResponse({"success": False, "error": "Zaman aralığı gerekli"}, status=400)

    if timezone.is_naive(slot_start):
        slot_start = timezone.make_aware(slot_start)
    if timezone.is_naive(slot_end):
        slot_end = timezone.make_aware(slot_end)

    toplam_dakika = _planlama_toplam_sure_dakika(asama)
    if toplam_dakika <= 0:
        return JsonResponse({"success": False, "error": "Görev süresi 0 olamaz."}, status=400)

    slot_start = _planlama_round_to_slot(slot_start, slot_minutes=15)
    planlanan_bitis = slot_start + timedelta(minutes=toplam_dakika)

    izin_kaydi = _planlama_personel_izin_cakisma(personel.id, slot_start, planlanan_bitis)
    if izin_kaydi:
        return JsonResponse({
            "success": False,
            "error": (
                f"{personel.ad} {personel.soyad} bu zaman aralığında izinli "
                f"({izin_kaydi.baslangic_zamani:%d.%m.%Y %H:%M} - {izin_kaydi.bitis_zamani:%d.%m.%Y %H:%M})."
            ),
        }, status=400)

    overlap_count = _planlama_overlap_count(personel.id, slot_start, planlanan_bitis, exclude_asama_id=asama.id)
    if overlap_count >= PLANLAMA_MAX_PARALLEL_TASKS:
        return JsonResponse({
            "success": False,
            "error": f"Bu personel için seçilen zaman aralığında maksimum eşzamanlı görev sayısına ulaşıldı (max: {PLANLAMA_MAX_PARALLEL_TASKS}).",
        }, status=400)

    asama.atanan_personel = personel
    asama.planlanan_baslama = slot_start
    asama.planlanan_bitis = planlanan_bitis
    asama.save(update_fields=["atanan_personel", "planlanan_baslama", "planlanan_bitis"])

    return JsonResponse({
        "success": True,
        "planlanan_baslama": asama.planlanan_baslama.isoformat() if asama.planlanan_baslama else None,
        "planlanan_bitis": asama.planlanan_bitis.isoformat() if asama.planlanan_bitis else None,
        "total_minutes": toplam_dakika,
        "personel_id": asama.atanan_personel_id,
        "status": asama.durum,
        "status_label": _planlama_status_meta(asama.durum)["label"],
        "status_class": _planlama_status_meta(asama.durum)["color"],
    })


def _planlama_asama_detay_dict(asama):
    urun = asama.uretim_emri.recete.urun
    status_meta = _planlama_status_meta(asama.durum)
    planned_minutes = _planlama_planlanan_sure_dakika(asama)
    actual_minutes = _planlama_gerceklesen_sure_hesapla(asama) if asama.baslama_zamani else asama.gerceklesen_sure
    gecikme = None
    if actual_minutes is not None:
        gecikme = int(actual_minutes) - int(planned_minutes or 0)

    notes = asama.not_kayitlari.select_related("olusturan").all()[:20]
    issues = asama.sorun_kayitlari.select_related("olusturan").all()[:20]

    return {
        "id": asama.id,
        "emir_no": asama.uretim_emri.emir_no,
        "urun_kodu": urun.stok_kodu,
        "urun_adi": urun.ad,
        "operasyon_adi": asama.ad,
        "personel_id": asama.atanan_personel_id,
        "atanan_personel": f"{asama.atanan_personel.ad} {asama.atanan_personel.soyad}" if asama.atanan_personel else "-",
        "planlanan_sure_dk": planned_minutes,
        "planlanan_sure_text": _planlama_format_duration(planned_minutes),
        "planlanan_baslangic": asama.planlanan_baslama.isoformat() if asama.planlanan_baslama else None,
        "planlanan_bitis": asama.planlanan_bitis.isoformat() if asama.planlanan_bitis else None,
        "gercek_baslangic": asama.baslama_zamani.isoformat() if asama.baslama_zamani else None,
        "gercek_bitis": asama.bitis_zamani.isoformat() if asama.bitis_zamani else None,
        "gerceklesen_sure_dk": actual_minutes,
        "gerceklesen_sure_text": _planlama_format_duration(actual_minutes),
        "gecikme_dk": gecikme,
        "gecikme_text": f"{gecikme:+d} dk" if gecikme is not None else "-",
        "durum": asama.durum,
        "durum_label": status_meta["label"],
        "durum_class": status_meta["color"],
        "notlar": [
            {
                "id": note.id,
                "metin": note.not_metni,
                "kullanici": note.olusturan.get_full_name() or note.olusturan.username if note.olusturan else "Sistem",
                "created_at": note.created_at.isoformat(),
            }
            for note in notes
        ],
        "sorunlar": [
            {
                "id": issue.id,
                "tip": issue.sorun_tipi,
                "tip_label": issue.get_sorun_tipi_display(),
                "aciklama": issue.aciklama,
                "durum": issue.durum,
                "durum_label": issue.get_durum_display(),
                "gorsel_url": issue.gorsel.url if issue.gorsel else "",
                "kullanici": issue.olusturan.get_full_name() or issue.olusturan.username if issue.olusturan else "Sistem",
                "created_at": issue.created_at.isoformat(),
            }
            for issue in issues
        ],
    }


@login_required
def uretim_planlama_gorev_detay(request, asama_id):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(
        UretimAsamasi.objects.select_related("uretim_emri", "uretim_emri__recete", "uretim_emri__recete__urun", "atanan_personel"),
        pk=asama_id,
    )
    return JsonResponse({"success": True, "task": _planlama_asama_detay_dict(asama)})


@login_required
def uretim_planlama_gorev_plan_guncelle(request, asama_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(UretimAsamasi, pk=asama_id)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    start_raw = payload.get("planlanan_baslangic")
    duration_raw = payload.get("planlanan_sure_dk")
    personel_raw = payload.get("personel_id")

    try:
        personel_id = int(personel_raw)
    except (TypeError, ValueError):
        personel_id = asama.atanan_personel_id
    if not personel_id:
        return JsonResponse({"success": False, "error": "Atanan personel seçilmeli."}, status=400)
    personel = get_object_or_404(Personel, pk=personel_id, aktif=True)

    slot_start = parse_datetime(start_raw) if start_raw else None
    if not slot_start:
        return JsonResponse({"success": False, "error": "Planlanan başlangıç gerekli."}, status=400)
    if timezone.is_naive(slot_start):
        slot_start = timezone.make_aware(slot_start)
    slot_start = _planlama_round_to_slot(slot_start, slot_minutes=15)

    try:
        duration_minutes = int(duration_raw)
    except (TypeError, ValueError):
        duration_minutes = _planlama_toplam_sure_dakika(asama)
    if duration_minutes <= 0:
        return JsonResponse({"success": False, "error": "Süre 0'dan büyük olmalı."}, status=400)

    planlanan_bitis = slot_start + timedelta(minutes=duration_minutes)
    if slot_start >= planlanan_bitis:
        return JsonResponse({"success": False, "error": "Başlangıç zamanı bitişten küçük olmalı."}, status=400)

    izin_kaydi = _planlama_personel_izin_cakisma(personel.id, slot_start, planlanan_bitis)
    if izin_kaydi:
        return JsonResponse({
            "success": False,
            "error": (
                f"{personel.ad} {personel.soyad} bu zaman aralığında izinli "
                f"({izin_kaydi.baslangic_zamani:%d.%m.%Y %H:%M} - {izin_kaydi.bitis_zamani:%d.%m.%Y %H:%M})."
            ),
        }, status=400)

    overlap_count = _planlama_overlap_count(personel.id, slot_start, planlanan_bitis, exclude_asama_id=asama.id)
    if overlap_count >= PLANLAMA_MAX_PARALLEL_TASKS:
        return JsonResponse({
            "success": False,
            "error": f"Bu personel için seçilen zaman aralığında maksimum eşzamanlı görev sayısına ulaşıldı (max: {PLANLAMA_MAX_PARALLEL_TASKS}).",
        }, status=400)

    asama.atanan_personel = personel
    asama.planlanan_baslama = slot_start
    asama.planlanan_bitis = planlanan_bitis
    asama.save(update_fields=["atanan_personel", "planlanan_baslama", "planlanan_bitis"])
    asama.refresh_from_db()

    return JsonResponse({
        "success": True,
        "task": _planlama_asama_detay_dict(asama),
    })


@login_required
def uretim_planlama_gorev_aksiyon(request, asama_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(UretimAsamasi, pk=asama_id)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    aksiyon = (payload.get("aksiyon") or "").upper()
    aksiyon_to_durum = {
        "BASLAT": "DEVAM_EDIYOR",
        "DURAKLAT": "BEKLEMEDE",
        "DEVAM": "DEVAM_EDIYOR",
        "TAMAMLA": "TAMAMLANDI",
        "SORUNLU_YAP": "SORUNLU",
    }
    yeni_durum = aksiyon_to_durum.get(aksiyon)
    if not yeni_durum:
        return JsonResponse({"success": False, "error": "Geçersiz aksiyon"}, status=400)

    valid_transitions = {
        "BEKLIYOR": {"BASLAT", "SORUNLU_YAP"},
        "DEVAM_EDIYOR": {"DURAKLAT", "TAMAMLA", "SORUNLU_YAP"},
        "BEKLEMEDE": {"DEVAM", "SORUNLU_YAP"},
        "SORUNLU": {"DEVAM"},
        "TAMAMLANDI": set(),
    }
    if aksiyon not in valid_transitions.get(asama.durum, set()):
        return JsonResponse({"success": False, "error": "Bu durum için aksiyon uygun değil."}, status=400)

    try:
        with transaction.atomic():
            _planlama_apply_status_change(asama, yeni_durum, request.user)
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    asama.refresh_from_db()
    return JsonResponse({"success": True, "task": _planlama_asama_detay_dict(asama)})


@login_required
def uretim_planlama_gorev_not_ekle(request, asama_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    asama = get_object_or_404(UretimAsamasi, pk=asama_id)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    note_text = (payload.get("not") or "").strip()
    if not note_text:
        return JsonResponse({"success": False, "error": "Not boş olamaz."}, status=400)

    UretimAsamaNot.objects.create(
        asama=asama,
        not_metni=note_text,
        olusturan=request.user,
    )
    asama.refresh_from_db()
    return JsonResponse({"success": True, "task": _planlama_asama_detay_dict(asama)})


@login_required
def uretim_planlama_gorev_sorun_bildir(request, asama_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(UretimAsamasi, pk=asama_id)
    sorun_tipi = (request.POST.get("sorun_tipi") or "").strip()
    aciklama = (request.POST.get("aciklama") or "").strip()
    sorunlu_yap = (request.POST.get("sorunlu_yap") or "1") in ["1", "true", "True", "on"]
    gorsel = request.FILES.get("gorsel")

    if not sorun_tipi:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        sorun_tipi = (payload.get("sorun_tipi") or "").strip()
        aciklama = aciklama or (payload.get("aciklama") or "").strip()
        sorunlu_yap = payload.get("sorunlu_yap", True)

    valid_types = {choice[0] for choice in UretimAsamaSorun.SORUN_TIPLERI}
    if sorun_tipi not in valid_types:
        return JsonResponse({"success": False, "error": "Geçersiz sorun tipi."}, status=400)
    if not aciklama:
        return JsonResponse({"success": False, "error": "Açıklama gerekli."}, status=400)

    with transaction.atomic():
        UretimAsamaSorun.objects.create(
            asama=asama,
            sorun_tipi=sorun_tipi,
            aciklama=aciklama,
            gorsel=gorsel,
            olusturan=request.user,
        )
        if sorunlu_yap and asama.durum in ["BEKLIYOR", "DEVAM_EDIYOR", "BEKLEMEDE"]:
            _planlama_apply_status_change(asama, "SORUNLU", request.user)

    asama.refresh_from_db()
    return JsonResponse({"success": True, "task": _planlama_asama_detay_dict(asama)})


@login_required
def uretim_planlama_gorev_talimat(request, asama_id):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(UretimAsamasi.objects.select_related("uretim_emri", "uretim_emri__recete"), pk=asama_id)
    talimatlar = ReceteTalimat.objects.filter(recete=asama.uretim_emri.recete).prefetch_related(
        "olculer",
        "ek_aciklamalar",
        "programlar",
        "ekipmanlar__ekipman",
        "fiksturler__fikstur",
        "olcu_aletleri__olcu_aleti",
        "kurulum_dosyalari__kurulum_dosyasi",
        "dosyalar",
    )

    result = []
    for talimat in talimatlar:
        files = []
        for dosya in talimat.dosyalar.all():
            lower_name = (dosya.dosya_adi or dosya.dosya.name or "").lower()
            lower_ext = lower_name.split(".")[-1] if "." in lower_name else ""
            is_image = lower_ext in ["png", "jpg", "jpeg", "gif", "webp", "bmp"]
            files.append({
                "id": dosya.id,
                "ad": dosya.dosya_adi or dosya.dosya.name.split("/")[-1],
                "aciklama": dosya.aciklama or "",
                "url": dosya.dosya.url,
                "is_image": is_image,
                "is_pdf": lower_ext == "pdf",
            })

        result.append({
            "id": talimat.id,
            "sira": talimat.sira,
            "aciklama": talimat.aciklama,
            "islem_adimlari": [item.aciklama for item in talimat.ek_aciklamalar.all() if item.aciklama],
            "kontrol_noktalari": [item.aciklama for item in talimat.olculer.all() if item.aciklama],
            "ekipmanlar": [item.ekipman.ad for item in talimat.ekipmanlar.all() if item.ekipman],
            "fiksturler": [item.fikstur.ad for item in talimat.fiksturler.all() if item.fikstur],
            "programlar": [item.program_adi for item in talimat.programlar.all() if item.program_adi],
            "olcu_aletleri": [item.olcu_aleti.seri_no for item in talimat.olcu_aletleri.all() if item.olcu_aleti],
            "dosyalar": files,
            "kurulum_dosyalari": [
                {
                    "id": item.kurulum_dosyasi.id,
                    "ad": str(item.kurulum_dosyasi),
                }
                for item in talimat.kurulum_dosyalari.all()
            ],
        })

    return JsonResponse({"success": True, "instructions": result})


def _uretim_rapor_filtered_qs(request):
    qs = UretimAsamasi.objects.select_related(
        "uretim_emri",
        "uretim_emri__recete",
        "uretim_emri__recete__urun",
        "atanan_personel",
    ).prefetch_related(
        "not_kayitlari",
        "sorun_kayitlari",
        "durus_kayitlari",
    )

    date_start = (request.GET.get("date_start") or "").strip()
    date_end = (request.GET.get("date_end") or "").strip()
    personel_id = (request.GET.get("personel") or "").strip()
    emir_no = (request.GET.get("emir_no") or "").strip()
    urun_kodu = (request.GET.get("urun_kodu") or "").strip()
    urun_adi = (request.GET.get("urun_adi") or "").strip()
    operasyon = (request.GET.get("operasyon") or "").strip()
    durum = (request.GET.get("durum") or "").strip()

    if date_start:
        try:
            start_date = datetime.strptime(date_start, "%Y-%m-%d").date()
            qs = qs.filter(
                Q(planlanan_baslama__date__gte=start_date) |
                Q(baslama_zamani__date__gte=start_date)
            )
        except ValueError:
            pass
    if date_end:
        try:
            end_date = datetime.strptime(date_end, "%Y-%m-%d").date()
            qs = qs.filter(
                Q(planlanan_baslama__date__lte=end_date) |
                Q(baslama_zamani__date__lte=end_date)
            )
        except ValueError:
            pass
    if personel_id:
        try:
            qs = qs.filter(atanan_personel_id=int(personel_id))
        except ValueError:
            pass
    if emir_no:
        qs = qs.filter(uretim_emri__emir_no__icontains=emir_no)
    if urun_kodu:
        qs = qs.filter(uretim_emri__recete__urun__stok_kodu__icontains=urun_kodu)
    if urun_adi:
        qs = qs.filter(uretim_emri__recete__urun__ad__icontains=urun_adi)
    if operasyon:
        qs = qs.filter(ad__icontains=operasyon)
    if durum:
        qs = qs.filter(durum=durum)

    return qs.order_by("-planlanan_baslama", "-id")


def _uretim_rapor_row_dict(asama):
    urun = asama.uretim_emri.recete.urun
    status_meta = _planlama_status_meta(asama.durum)
    planned_minutes = _planlama_planlanan_sure_dakika(asama)
    actual_minutes = asama.gerceklesen_sure
    if actual_minutes is None and asama.baslama_zamani:
        actual_minutes = _planlama_gerceklesen_sure_hesapla(asama)

    pause_minutes = int((asama.duraklatma_toplam_saniye or 0) / 60)
    net_minutes = actual_minutes if actual_minutes is not None else 0
    row_date = asama.planlanan_baslama or asama.baslama_zamani or asama.uretim_emri.created_at

    return {
        "id": asama.id,
        "tarih": row_date.isoformat() if row_date else None,
        "emir_no": asama.uretim_emri.emir_no,
        "urun_kodu": urun.stok_kodu,
        "urun_adi": urun.ad,
        "operasyon_adi": asama.ad,
        "personel": f"{asama.atanan_personel.ad} {asama.atanan_personel.soyad}" if asama.atanan_personel else "-",
        "planlanan_sure_dk": planned_minutes,
        "planlanan_sure_text": _planlama_format_duration(planned_minutes),
        "gerceklesen_sure_dk": actual_minutes,
        "gerceklesen_sure_text": _planlama_format_duration(actual_minutes),
        "durus_sure_dk": pause_minutes,
        "durus_sure_text": _planlama_format_duration(pause_minutes),
        "net_calisma_sure_dk": net_minutes,
        "net_calisma_sure_text": _planlama_format_duration(net_minutes),
        "durum": asama.durum,
        "durum_label": status_meta["label"],
        "durum_class": status_meta["color"],
        "not_var": len(asama.not_kayitlari.all()) > 0,
        "sorun_var": len(asama.sorun_kayitlari.all()) > 0,
    }


@login_required
def uretim_raporlari(request):
    personeller = Personel.objects.filter(aktif=True).order_by("ad", "soyad")
    durumlar = UretimAsamasi.DURUMLAR
    context = {
        "personeller": personeller,
        "durumlar": durumlar,
    }
    return render(request, "stokapp/uretim_raporlari.html", context)


@login_required
def uretim_raporlari_api_liste(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    qs = _uretim_rapor_filtered_qs(request)
    rows = [_uretim_rapor_row_dict(asama) for asama in qs[:500]]
    return JsonResponse({
        "success": True,
        "rows": rows,
        "count": len(rows),
    })


@login_required
def uretim_raporlari_api_ozet(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    qs = _uretim_rapor_filtered_qs(request)
    toplam_tamamlanan = qs.filter(durum="TAMAMLANDI").count()

    toplam_gerceklesen = 0
    toplam_durus = 0
    toplam_planlanan = 0
    operasyon_durus = {}
    personel_tamamlanan = {}

    for asama in qs:
        planned = _planlama_toplam_sure_dakika(asama)
        actual = asama.gerceklesen_sure
        if actual is None and asama.baslama_zamani:
            actual = _planlama_gerceklesen_sure_hesapla(asama)
        pause = int((asama.duraklatma_toplam_saniye or 0) / 60)

        toplam_planlanan += int(planned or 0)
        toplam_gerceklesen += int(actual or 0)
        toplam_durus += int(pause)

        operasyon_durus[asama.ad] = operasyon_durus.get(asama.ad, 0) + int(pause)
        if asama.durum == "TAMAMLANDI" and asama.atanan_personel:
            p_name = f"{asama.atanan_personel.ad} {asama.atanan_personel.soyad}"
            personel_tamamlanan[p_name] = personel_tamamlanan.get(p_name, 0) + 1

    en_cok_durus_operasyon = "-"
    if operasyon_durus:
        en_cok_durus_operasyon = max(operasyon_durus.items(), key=lambda item: item[1])[0]

    en_cok_tamamlayan_personel = "-"
    if personel_tamamlanan:
        en_cok_tamamlayan_personel = max(personel_tamamlanan.items(), key=lambda item: item[1])[0]

    return JsonResponse({
        "success": True,
        "summary": {
            "toplam_tamamlanan_is": toplam_tamamlanan,
            "toplam_gerceklesen_sure_dk": toplam_gerceklesen,
            "toplam_gerceklesen_sure_text": _planlama_format_duration(toplam_gerceklesen),
            "toplam_durus_sure_dk": toplam_durus,
            "toplam_durus_sure_text": _planlama_format_duration(toplam_durus),
            "en_cok_durus_operasyon": en_cok_durus_operasyon,
            "en_cok_tamamlayan_personel": en_cok_tamamlayan_personel,
            "sure_sapmasi_dk": toplam_gerceklesen - toplam_planlanan,
            "sure_sapmasi_text": f"{(toplam_gerceklesen - toplam_planlanan):+d} dk",
        }
    })


@login_required
@never_cache
def uretim_raporlari_export_excel(request):
    try:
        qs = _uretim_rapor_filtered_qs(request)
        rows = [_uretim_rapor_row_dict(asama) for asama in qs[:5000]]
        df = pd.DataFrame([{
            "Tarih": (datetime.fromisoformat(r["tarih"]).strftime("%d.%m.%Y %H:%M") if r["tarih"] else "-"),
            "İş Emri No": r["emir_no"],
            "Ürün Kodu": r["urun_kodu"],
            "Ürün Adı": r["urun_adi"],
            "Operasyon": r["operasyon_adi"],
            "Personel": r["personel"],
            "Planlanan Süre (dk)": r["planlanan_sure_dk"],
            "Gerçekleşen Süre (dk)": r["gerceklesen_sure_dk"],
            "Duruş Süresi (dk)": r["durus_sure_dk"],
            "Net Çalışma (dk)": r["net_calisma_sure_dk"],
            "Durum": r["durum_label"],
            "Not Var": "Evet" if r["not_var"] else "Hayır",
            "Sorun Var": "Evet" if r["sorun_var"] else "Hayır",
        } for r in rows])
        if df.empty:
            df = pd.DataFrame(columns=[
                "Tarih", "İş Emri No", "Ürün Kodu", "Ürün Adı", "Operasyon", "Personel",
                "Planlanan Süre (dk)", "Gerçekleşen Süre (dk)", "Duruş Süresi (dk)",
                "Net Çalışma (dk)", "Durum", "Not Var", "Sorun Var",
            ])

        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="uretim_raporlari_{ts}.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Üretim Raporları', index=False)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_raporlari')


@login_required
@never_cache
def uretim_raporlari_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:uretim_raporlari')

    qs = _uretim_rapor_filtered_qs(request)
    rows = [_uretim_rapor_row_dict(asama) for asama in qs[:1200]]
    olusturma_tarihi = timezone.localtime(timezone.now())

    html_rows = []
    for r in rows:
        html_rows.append(
            f"""
            <tr>
                <td>{datetime.fromisoformat(r["tarih"]).strftime("%d.%m.%Y %H:%M") if r["tarih"] else '-'}</td>
                <td>{r["emir_no"]}</td>
                <td>{r["urun_kodu"]}</td>
                <td>{r["urun_adi"]}</td>
                <td>{r["operasyon_adi"]}</td>
                <td>{r["personel"]}</td>
                <td class="num">{r["planlanan_sure_text"]}</td>
                <td class="num">{r["gerceklesen_sure_text"]}</td>
                <td class="num">{r["durus_sure_text"]}</td>
                <td>{r["durum_label"]}</td>
            </tr>
            """
        )
    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Üretim Raporları</h1>
      <div class="meta">Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(rows)}</div>
      <table>
        <thead><tr><th>Tarih</th><th>İş Emri</th><th>Ürün Kodu</th><th>Ürün</th><th>Operasyon</th><th>Personel</th><th>Planlanan</th><th>Gerçekleşen</th><th>Duruş</th><th>Durum</th></tr></thead>
        <tbody>{''.join(html_rows) if html_rows else '<tr><td colspan="10" class="empty">Kayıt bulunamadı.</td></tr>'}</tbody>
      </table>
    </body></html>
    """
    css = CSS(string="""
        @page { size: A4 landscape; margin: 10mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8pt; color: #111827; }
        h1 { font-size: 14pt; margin: 0 0 4px 0; }
        .meta { color: #6b7280; font-size: 8pt; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f3f4f6; border: 1px solid #d1d5db; padding: 5px 4px; text-align: left; font-size: 7.5pt; }
        td { border: 1px solid #e5e7eb; padding: 4px; vertical-align: top; font-size: 7.5pt; }
        .num { text-align: right; white-space: nowrap; }
        .empty { text-align: center; color: #6b7280; padding: 24px; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_raporlari')

    filename = f'uretim_raporlari_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def uretim_raporlari_api_detay(request, asama_id):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    asama = get_object_or_404(
        UretimAsamasi.objects.select_related(
            "uretim_emri",
            "uretim_emri__recete",
            "uretim_emri__recete__urun",
            "atanan_personel",
        ).prefetch_related(
            "not_kayitlari__olusturan",
            "sorun_kayitlari__olusturan",
            "durus_kayitlari",
        ),
        pk=asama_id,
    )

    task = _planlama_asama_detay_dict(asama)
    planlama_url = ""
    duzenle_url = ""
    if asama.planlanan_baslama:
        query_data = {
            "scale": "hour",
            "start": asama.planlanan_baslama.date().isoformat(),
            "focus_task": asama.id,
        }
        query = urlencode(query_data)
        planlama_url = f"{reverse('stokapp:uretim_planlama')}?{query}"
        query_data["open_edit"] = 1
        duzenle_url = f"{reverse('stokapp:uretim_planlama')}?{urlencode(query_data)}"
    else:
        query = urlencode({
            "scale": "hour",
            "start": timezone.localdate().isoformat(),
            "focus_task": asama.id,
            "open_edit": 1,
        })
        duzenle_url = f"{reverse('stokapp:uretim_planlama')}?{query}"
    task["planlama_url"] = planlama_url
    task["duzenle_url"] = duzenle_url
    task["duruslar"] = [
        {
            "id": durus.id,
            "baslama": durus.baslama_zamani.isoformat() if durus.baslama_zamani else None,
            "bitis": durus.bitis_zamani.isoformat() if durus.bitis_zamani else None,
            "sure_saniye": durus.sure_saniye,
            "sure_dk": int((durus.sure_saniye or 0) / 60),
            "aciklama": durus.aciklama or "",
        }
        for durus in asama.durus_kayitlari.all()
    ]

    return JsonResponse({
        "success": True,
        "task": task,
    })


def _durus_nedeni_from_text(text):
    raw = (text or "").strip()
    if not raw:
        return "Belirtilmemiş"
    for sep in [":", "-", "|"]:
        if sep in raw:
            left = raw.split(sep, 1)[0].strip()
            if left:
                return left
    return raw[:80]


def _durus_machine_for_asama(asama, cache):
    key = (asama.uretim_emri.recete_id, (asama.ad or "").strip().lower())
    if key not in cache:
        recete_op = ReceteOperasyon.objects.select_related("istasyon", "operasyon").filter(
            recete_id=asama.uretim_emri.recete_id,
            operasyon__ad__iexact=asama.ad or "",
        ).order_by("sira", "id").first()
        if recete_op and recete_op.istasyon:
            cache[key] = {"id": recete_op.istasyon_id, "ad": recete_op.istasyon.ad}
        else:
            cache[key] = {"id": None, "ad": "-"}
    return cache[key]


def _durus_filtered_base_qs(request):
    qs = UretimAsamaDurusKaydi.objects.select_related(
        "asama",
        "asama__atanan_personel",
        "asama__uretim_emri",
        "asama__uretim_emri__recete",
        "asama__uretim_emri__recete__urun",
    ).filter(asama__isnull=False)

    date_start = (request.GET.get("date_start") or "").strip()
    date_end = (request.GET.get("date_end") or "").strip()
    personel_id = (request.GET.get("personel") or "").strip()
    urun_id = (request.GET.get("urun") or "").strip()
    operasyon = (request.GET.get("operasyon") or "").strip()
    uretim_tipi = (request.GET.get("uretim_tipi") or "").strip().upper()

    if date_start:
        try:
            start_date = datetime.strptime(date_start, "%Y-%m-%d").date()
            qs = qs.filter(baslama_zamani__date__gte=start_date)
        except ValueError:
            pass
    if date_end:
        try:
            end_date = datetime.strptime(date_end, "%Y-%m-%d").date()
            qs = qs.filter(baslama_zamani__date__lte=end_date)
        except ValueError:
            pass
    if personel_id:
        try:
            qs = qs.filter(asama__atanan_personel_id=int(personel_id))
        except ValueError:
            pass
    if urun_id:
        try:
            qs = qs.filter(asama__uretim_emri__recete__urun_id=int(urun_id))
        except ValueError:
            pass
    if operasyon:
        qs = qs.filter(asama__ad__icontains=operasyon)
    if uretim_tipi in ["ORDER", "STOCK"]:
        qs = qs.filter(asama__uretim_emri__production_type=uretim_tipi)
    return qs.order_by("-baslama_zamani", "-id")


def _durus_filtered_rows(request):
    qs = _durus_filtered_base_qs(request)
    makine_id_raw = (request.GET.get("makine") or "").strip()
    neden_filter = (request.GET.get("durus_nedeni") or "").strip()

    try:
        makine_id = int(makine_id_raw) if makine_id_raw else None
    except ValueError:
        makine_id = None

    machine_cache = {}
    now = timezone.now()
    rows = []
    for durus in qs:
        asama = durus.asama
        machine = _durus_machine_for_asama(asama, machine_cache)
        reason = _durus_nedeni_from_text(durus.aciklama)
        if makine_id and machine["id"] != makine_id:
            continue
        if neden_filter and reason != neden_filter:
            continue

        baslama = durus.baslama_zamani
        bitis = durus.bitis_zamani
        if durus.sure_saniye:
            sure_dk = int((durus.sure_saniye or 0) / 60)
        elif baslama:
            sure_dk = int(((bitis or now) - baslama).total_seconds() / 60)
        else:
            sure_dk = 0
        if sure_dk < 0:
            sure_dk = 0

        urun = asama.uretim_emri.recete.urun
        personel_ad = f"{asama.atanan_personel.ad} {asama.atanan_personel.soyad}" if asama.atanan_personel else "-"
        rows.append({
            "id": durus.id,
            "tarih": baslama.isoformat() if baslama else None,
            "is_emri": asama.uretim_emri.emir_no,
            "urun": f"{urun.stok_kodu} - {urun.ad}",
            "operasyon": asama.ad,
            "personel": personel_ad,
            "personel_id": asama.atanan_personel_id,
            "makine": machine["ad"],
            "makine_id": machine["id"],
            "durus_nedeni": reason,
            "baslangic": baslama.isoformat() if baslama else None,
            "bitis": bitis.isoformat() if bitis else None,
            "sure_dk": sure_dk,
            "sure_text": _planlama_format_duration(sure_dk),
            "aciklama": durus.aciklama or "",
            "uretim_tipi": asama.uretim_emri.production_type,
            "uretim_tipi_label": "Stok" if asama.uretim_emri.production_type == "STOCK" else "Sipariş",
        })
    return rows


@login_required
def uretim_durus_raporlari(request):
    personeller = Personel.objects.filter(aktif=True).order_by("ad", "soyad")
    makineler = Istasyon.objects.filter(aktif=True).order_by("sira", "ad")
    urunler = StokItem.objects.filter(ana_urun__aktif=True).distinct().order_by("stok_kodu")
    nedenler = sorted({
        _durus_nedeni_from_text(item.aciklama)
        for item in UretimAsamaDurusKaydi.objects.all()[:1000]
    })
    return render(request, "stokapp/uretim_durus_raporlari.html", {
        "personeller": personeller,
        "makineler": makineler,
        "urunler": urunler,
        "nedenler": nedenler,
    })


@login_required
def uretim_durus_raporlari_api_liste(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per_page = max(10, min(200, int(request.GET.get("per_page", 50))))
    except ValueError:
        per_page = 50

    rows = _durus_filtered_rows(request)
    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page
    return JsonResponse({
        "success": True,
        "rows": rows[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }
    })


@login_required
def uretim_durus_raporlari_api_ozet(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    rows = _durus_filtered_rows(request)
    toplam_sure = sum(r["sure_dk"] for r in rows)
    durus_sayisi = len(rows)
    ortalama = int(toplam_sure / durus_sayisi) if durus_sayisi else 0
    en_uzun = max((r["sure_dk"] for r in rows), default=0)

    makine_agg = defaultdict(int)
    personel_agg = defaultdict(int)
    for row in rows:
        makine_agg[row["makine"]] += row["sure_dk"]
        personel_agg[row["personel"]] += row["sure_dk"]

    en_cok_makine = max(makine_agg.items(), key=lambda x: x[1])[0] if makine_agg else "-"
    en_cok_personel = max(personel_agg.items(), key=lambda x: x[1])[0] if personel_agg else "-"

    return JsonResponse({
        "success": True,
        "summary": {
            "toplam_durus_suresi_dk": toplam_sure,
            "toplam_durus_suresi_text": _planlama_format_duration(toplam_sure),
            "durus_sayisi": durus_sayisi,
            "ortalama_durus_suresi_dk": ortalama,
            "ortalama_durus_suresi_text": _planlama_format_duration(ortalama),
            "en_uzun_durus_dk": en_uzun,
            "en_uzun_durus_text": _planlama_format_duration(en_uzun),
            "en_cok_durus_makine": en_cok_makine,
            "en_cok_durus_personel": en_cok_personel,
        }
    })


@login_required
def uretim_durus_raporlari_api_grafikler(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    rows = _durus_filtered_rows(request)

    reason_agg = defaultdict(int)
    machine_agg = defaultdict(int)
    personnel_agg = defaultdict(int)
    daily_agg = defaultdict(int)
    for row in rows:
        reason_agg[row["durus_nedeni"]] += row["sure_dk"]
        machine_agg[row["makine"]] += row["sure_dk"]
        personnel_agg[row["personel"]] += row["sure_dk"]
        day_label = "-"
        if row["tarih"]:
            try:
                day_label = datetime.fromisoformat(row["tarih"]).strftime("%d.%m.%Y")
            except ValueError:
                day_label = row["tarih"][:10]
        daily_agg[day_label] += row["sure_dk"]

    def sorted_series(data_dict, limit=12):
        items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)[:limit]
        return {"labels": [i[0] for i in items], "values": [i[1] for i in items]}

    daily_items = sorted(
        daily_agg.items(),
        key=lambda x: datetime.strptime(x[0], "%d.%m.%Y") if x[0] != "-" else datetime.min
    )

    return JsonResponse({
        "success": True,
        "charts": {
            "reason_pie": sorted_series(reason_agg, limit=20),
            "machine_bar": sorted_series(machine_agg, limit=20),
            "personnel_bar": sorted_series(personnel_agg, limit=20),
            "daily_line": {
                "labels": [i[0] for i in daily_items],
                "values": [i[1] for i in daily_items],
            },
        }
    })


def _durus_export_dataframe(rows):
    return pd.DataFrame([{
        "Tarih": (datetime.fromisoformat(r["tarih"]).strftime("%d.%m.%Y %H:%M") if r["tarih"] else "-"),
        "İş Emri": r["is_emri"],
        "Ürün": r["urun"],
        "Operasyon": r["operasyon"],
        "Personel": r["personel"],
        "Makine": r["makine"],
        "Duruş Nedeni": r["durus_nedeni"],
        "Başlangıç": (datetime.fromisoformat(r["baslangic"]).strftime("%d.%m.%Y %H:%M") if r["baslangic"] else "-"),
        "Bitiş": (datetime.fromisoformat(r["bitis"]).strftime("%d.%m.%Y %H:%M") if r["bitis"] else "-"),
        "Süre (dk)": r["sure_dk"],
        "Süre (HH:MM)": r["sure_text"],
        "Açıklama": r["aciklama"],
        "İş Emri Tipi": r["uretim_tipi_label"],
    } for r in rows])


@login_required
@never_cache
def uretim_durus_raporlari_export_excel(request):
    rows = _durus_filtered_rows(request)
    df = _durus_export_dataframe(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Duruş Ham Veri", index=False)
    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    response["Content-Disposition"] = f'attachment; filename="uretim_durus_raporu_{ts}.xlsx"'
    return response


@login_required
@never_cache
def uretim_durus_raporlari_export_pdf(request):
    rows = _durus_filtered_rows(request)
    toplam_sure = sum(r["sure_dk"] for r in rows)
    durus_sayisi = len(rows)
    ortalama = int(toplam_sure / durus_sayisi) if durus_sayisi else 0
    en_uzun = max((r["sure_dk"] for r in rows), default=0)

    reason_agg = defaultdict(int)
    machine_agg = defaultdict(int)
    personnel_agg = defaultdict(int)
    for row in rows:
        reason_agg[row["durus_nedeni"]] += row["sure_dk"]
        machine_agg[row["makine"]] += row["sure_dk"]
        personnel_agg[row["personel"]] += row["sure_dk"]

    try:
        from weasyprint import HTML
    except ImportError:
        messages.error(request, "PDF oluşturma için WeasyPrint kütüphanesi gerekli.")
        return redirect('stokapp:uretim_durus_raporlari')

    summary_html = f"""
    <h1>Üretim Duruş Raporu</h1>
    <p>Toplam Duruş Süresi: {_planlama_format_duration(toplam_sure)} | Duruş Sayısı: {durus_sayisi} | Ortalama: {_planlama_format_duration(ortalama)} | En Uzun: {_planlama_format_duration(en_uzun)}</p>
    """
    def simple_table(title, data_dict):
        rows_html = "".join([f"<tr><td>{k}</td><td>{v} dk</td></tr>" for k, v in sorted(data_dict.items(), key=lambda x: x[1], reverse=True)[:10]])
        return f"<h3>{title}</h3><table><tr><th>Başlık</th><th>Süre</th></tr>{rows_html}</table>"

    detail_rows = "".join([
        f"<tr><td>{datetime.fromisoformat(r['tarih']).strftime('%d.%m.%Y %H:%M') if r['tarih'] else '-'}</td><td>{r['is_emri']}</td><td>{r['urun']}</td><td>{r['operasyon']}</td><td>{r['personel']}</td><td>{r['makine']}</td><td>{r['durus_nedeni']}</td><td>{r['sure_text']}</td></tr>"
        for r in rows[:300]
    ])
    html = f"""
    <html><head><meta charset="utf-8"><style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; }}
    th {{ background: #f4f4f4; }}
    </style></head><body>
    {summary_html}
    {simple_table("Duruş Sebepleri (grafik verisi)", reason_agg)}
    {simple_table("Makine Bazlı Duruş (grafik verisi)", machine_agg)}
    {simple_table("Personel Bazlı Duruş (grafik verisi)", personnel_agg)}
    <h3>Detay Tablo</h3>
    <table>
      <tr><th>Tarih</th><th>İş Emri</th><th>Ürün</th><th>Operasyon</th><th>Personel</th><th>Makine</th><th>Duruş Nedeni</th><th>Süre</th></tr>
      {detail_rows}
    </table>
    </body></html>
    """
    try:
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_durus_raporlari')
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    response["Content-Disposition"] = f'attachment; filename="uretim_durus_raporu_{ts}.pdf"'
    return response