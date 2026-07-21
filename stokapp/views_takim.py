import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Istasyon,
    ReceteOperasyon,
    ReceteOperasyonTakim,
    Tool,
    ToolBodyMaterialOption,
    ToolBrandOption,
    ToolChange,
    ToolCoatingOption,
    ToolMaterial,
    ToolModelOption,
    ToolTypeOption,
    ToolUsageLog,
    UretimAsamasi,
    UretimEmri,
)


def _to_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _ensure_default_tool_types():
    defaults = [
        ("Matkap", "DR"),
        ("Freze", "EM"),
        ("Rayba", "RM"),
        ("Kılavuz", "TP"),
        ("Diğer", "TL"),
    ]
    for name, prefix in defaults:
        ToolTypeOption.objects.get_or_create(name=name, defaults={"prefix": prefix, "aktif": True})


def _option_model_map():
    return {
        "tool_type": ToolTypeOption,
        "brand": ToolBrandOption,
        "coating": ToolCoatingOption,
        "model": ToolModelOption,
        "body_material": ToolBodyMaterialOption,
        "cutting_material": ToolMaterial,
    }


def _tool_payload(tool):
    active_life = tool.get_active_life()
    active_life_mm = active_life.cutting_mm if active_life else Decimal("0")
    active_life_no = active_life.life_no if active_life else None
    active_life_percent = 0
    if tool.max_cutting_mm and active_life:
        try:
            active_life_percent = round((Decimal(str(active_life_mm)) / Decimal(str(tool.max_cutting_mm))) * Decimal("100"), 2)
        except Exception:
            active_life_percent = 0
    return {
        "id": tool.id,
        "tool_code": tool.tool_code,
        "tool_type": tool.tool_type,
        "tool_type_label": tool.tool_type_label,
        "diameter": str(tool.diameter),
        "brand": tool.brand or "",
        "coating": tool.coating or "",
        "model_no": tool.model_no or "",
        "tool_material": tool.body_material_option.name if tool.body_material_option_id else "",
        "max_cutting_mm": str(tool.max_cutting_mm),
        "total_cutting_mm": str(tool.total_cutting_mm),
        "status": tool.status,
        "status_label": tool.get_status_display(),
        "usage_percent": tool.usage_percent,
        "warning_level": tool.warning_level,
        "active_life_no": active_life_no,
        "active_life_mm": str(active_life_mm),
        "active_life_percent": str(active_life_percent),
        "created_at": tool.created_at.isoformat() if tool.created_at else None,
    }


@login_required
def takim_listesi(request):
    _ensure_default_tool_types()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_tool":
            return _create_tool_from_form(request)
        if action == "add_recipe_tool":
            return _create_recipe_tool_link_from_form(request)
        if action == "update_recipe_tool":
            return _update_recipe_tool_link_from_form(request)
        if action == "delete_recipe_tool":
            return _delete_recipe_tool_link_from_form(request)
        if action == "create_option":
            return _create_option_from_form(request)

    status = request.GET.get("status", "").strip()
    tool_type = request.GET.get("tool_type", "").strip()
    qs = Tool.objects.all().order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    if tool_type:
        qs = qs.filter(tool_type_option_id=tool_type)

    recipe_operations = ReceteOperasyon.objects.select_related(
        "recete", "recete__urun", "operasyon", "istasyon"
    ).order_by("-id")[:500]

    link_qs = ReceteOperasyonTakim.objects.select_related(
        "recete_operasyon", "recete_operasyon__recete", "recete_operasyon__recete__urun",
        "recete_operasyon__operasyon", "recete_operasyon__istasyon", "tool", "material"
    )
    link_station = (request.GET.get("link_station") or "").strip()
    link_tool_type = (request.GET.get("link_tool_type") or "").strip()
    link_material = (request.GET.get("link_material") or "").strip()
    link_q = (request.GET.get("link_q") or "").strip()
    if link_station:
        link_qs = link_qs.filter(recete_operasyon__istasyon_id=link_station)
    if link_tool_type:
        link_qs = link_qs.filter(tool_type=link_tool_type)
    if link_material:
        link_qs = link_qs.filter(material_id=link_material)
    if link_q:
        link_qs = link_qs.filter(
            Q(recete_operasyon__recete__urun__stok_kodu__icontains=link_q)
            | Q(recete_operasyon__recete__urun__ad__icontains=link_q)
            | Q(recete_operasyon__operasyon__ad__icontains=link_q)
            | Q(tool__tool_code__icontains=link_q)
            | Q(tool_type__icontains=link_q)
        )

    edit_link = None
    edit_link_id = (request.GET.get("edit_link") or "").strip()
    if edit_link_id.isdigit():
        edit_link = ReceteOperasyonTakim.objects.select_related(
            "recete_operasyon", "recete_operasyon__istasyon", "tool", "material"
        ).filter(pk=int(edit_link_id)).first()

    context = {
        "tools": qs,
        "all_tools": Tool.objects.all().order_by("tool_code"),
        "tool_type_options": ToolTypeOption.objects.filter(aktif=True).order_by("name"),
        "brand_options": ToolBrandOption.objects.all().order_by("name"),
        "coating_options": ToolCoatingOption.objects.all().order_by("name"),
        "model_options": ToolModelOption.objects.all().order_by("name"),
        "body_material_options": ToolBodyMaterialOption.objects.all().order_by("name"),
        "status_choices": Tool.STATUS_CHOICES,
        "materials": ToolMaterial.objects.all(),
        "stations": Istasyon.objects.filter(aktif=True).order_by("ad"),
        "recipe_operations": recipe_operations,
        "recipe_tool_links": link_qs.order_by("-id")[:500],
        "selected_status": status,
        "selected_tool_type": tool_type,
        "link_station": link_station,
        "link_tool_type": link_tool_type,
        "link_material": link_material,
        "link_q": link_q,
        "edit_link": edit_link,
    }
    return render(request, "stokapp/takim_listesi.html", context)


@login_required
def takim_secenek_yonetimi(request):
    _ensure_default_tool_types()
    model_map = _option_model_map()
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        kind = (request.POST.get("kind") or "").strip()
        model_cls = model_map.get(kind)
        if not model_cls:
            messages.error(request, "Geçersiz seçenek türü.")
            return redirect("stokapp:takim_secenek_yonetimi")

        if action == "add":
            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, "Ad alanı zorunludur.")
                return redirect("stokapp:takim_secenek_yonetimi")
            if kind == "tool_type":
                prefix = (request.POST.get("prefix") or "").strip().upper()
                if not prefix:
                    messages.error(request, "Takım tipi için prefix zorunludur.")
                    return redirect("stokapp:takim_secenek_yonetimi")
                model_cls.objects.get_or_create(name=name, defaults={"prefix": prefix, "aktif": True})
            else:
                model_cls.objects.get_or_create(name=name)
            messages.success(request, "Seçenek eklendi.")
            return redirect("stokapp:takim_secenek_yonetimi")

        option_id = request.POST.get("id")
        option = get_object_or_404(model_cls, pk=option_id)
        if action == "update":
            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, "Ad alanı zorunludur.")
                return redirect("stokapp:takim_secenek_yonetimi")
            option.name = name
            if kind == "tool_type":
                prefix = (request.POST.get("prefix") or "").strip().upper()
                if not prefix:
                    messages.error(request, "Takım tipi için prefix zorunludur.")
                    return redirect("stokapp:takim_secenek_yonetimi")
                option.prefix = prefix
                option.aktif = request.POST.get("aktif") == "on"
                option.save(update_fields=["name", "prefix", "aktif"])
            else:
                option.save(update_fields=["name"])
            messages.success(request, "Seçenek güncellendi.")
            return redirect("stokapp:takim_secenek_yonetimi")

        if action == "delete":
            option.delete()
            messages.success(request, "Seçenek silindi.")
            return redirect("stokapp:takim_secenek_yonetimi")

    context = {
        "tool_types": ToolTypeOption.objects.all().order_by("name"),
        "brands": ToolBrandOption.objects.all().order_by("name"),
        "coatings": ToolCoatingOption.objects.all().order_by("name"),
        "models": ToolModelOption.objects.all().order_by("name"),
        "body_materials": ToolBodyMaterialOption.objects.all().order_by("name"),
        "cutting_materials": ToolMaterial.objects.all().order_by("name"),
    }
    return render(request, "stokapp/takim_secenek_yonetimi.html", context)


def _create_tool_from_form(request):
    tool_type_option_id = request.POST.get("tool_type_option_id")
    tool_type_option = ToolTypeOption.objects.filter(pk=tool_type_option_id, aktif=True).first()
    tool_type = tool_type_option.name if tool_type_option else ""
    diameter = _to_decimal(request.POST.get("diameter"))
    max_cutting_mm = _to_decimal(request.POST.get("max_cutting_mm"))
    if not tool_type or diameter <= 0:
        messages.error(request, "Takım tipi ve geçerli çap zorunludur.")
        return redirect("stokapp:takim_listesi")
    brand_option = ToolBrandOption.objects.filter(pk=request.POST.get("brand_option_id")).first()
    coating_option = ToolCoatingOption.objects.filter(pk=request.POST.get("coating_option_id")).first()
    model_option = ToolModelOption.objects.filter(pk=request.POST.get("model_option_id")).first()
    body_material_option = ToolBodyMaterialOption.objects.filter(pk=request.POST.get("body_material_option_id")).first()
    tool = Tool.objects.create(
        tool_type=tool_type,
        tool_type_option=tool_type_option,
        diameter=diameter,
        brand=brand_option.name if brand_option else "",
        brand_option=brand_option,
        coating=coating_option.name if coating_option else "",
        coating_option=coating_option,
        model_no=model_option.name if model_option else "",
        model_option=model_option,
        body_material_option=body_material_option,
        max_cutting_mm=max_cutting_mm if max_cutting_mm > 0 else Decimal("0"),
    )
    messages.success(request, f"Takım oluşturuldu: {tool.tool_code}")
    return redirect("stokapp:takim_listesi")


def _create_option_from_form(request):
    option_kind = (request.POST.get("option_kind") or "").strip()
    option_name = (request.POST.get("option_name") or "").strip()
    option_prefix = (request.POST.get("option_prefix") or "").strip().upper()
    if not option_name:
        messages.error(request, "Yeni seçenek adı zorunludur.")
        return redirect("stokapp:takim_listesi")

    if option_kind == "tool_type":
        if not option_prefix:
            messages.error(request, "Takım tipi için prefix zorunludur.")
            return redirect("stokapp:takim_listesi")
        ToolTypeOption.objects.get_or_create(name=option_name, defaults={"prefix": option_prefix, "aktif": True})
        messages.success(request, "Yeni takım tipi eklendi.")
        return redirect("stokapp:takim_listesi")

    model_map = _option_model_map()
    model_cls = model_map.get(option_kind)
    if not model_cls:
        messages.error(request, "Geçersiz seçenek türü.")
        return redirect("stokapp:takim_listesi")
    model_cls.objects.get_or_create(name=option_name)
    messages.success(request, "Yeni seçenek eklendi.")
    return redirect("stokapp:takim_listesi")


def _create_recipe_tool_link_from_form(request):
    station_id = request.POST.get("station_id")
    recete_operasyon_id = request.POST.get("recete_operasyon_id")
    recete_operasyon = get_object_or_404(ReceteOperasyon.objects.select_related("istasyon"), pk=recete_operasyon_id)
    if station_id:
        try:
            if int(station_id) != int(recete_operasyon.istasyon_id or 0):
                messages.error(request, "Seçilen operasyon, seçtiğiniz istasyona ait değil.")
                return redirect("stokapp:takim_listesi")
        except ValueError:
            messages.error(request, "Geçersiz istasyon seçimi.")
            return redirect("stokapp:takim_listesi")
    tool_id = request.POST.get("tool_id")
    tool = Tool.objects.filter(pk=tool_id).first() if tool_id else None
    tool_type = request.POST.get("tool_type", "").strip()
    hole_count = int(request.POST.get("hole_count", "0") or 0)
    hole_depth_mm = _to_decimal(request.POST.get("hole_depth_mm"))
    material_id = request.POST.get("material_id")
    material = ToolMaterial.objects.filter(pk=material_id).first() if material_id else None

    if not tool and not tool_type:
        messages.error(request, "Takım veya takım tipi seçmelisiniz.")
        return redirect("stokapp:takim_listesi")
    if hole_count <= 0 or hole_depth_mm <= 0:
        messages.error(request, "Delik sayısı ve delik boyu sıfırdan büyük olmalıdır.")
        return redirect("stokapp:takim_listesi")

    ReceteOperasyonTakim.objects.create(
        recete_operasyon=recete_operasyon,
        tool=tool,
        tool_type=tool_type if not tool else tool.tool_type,
        hole_count=hole_count,
        hole_depth_mm=hole_depth_mm,
        material=material,
    )
    messages.success(request, "Operasyon takım eşleştirmesi kaydedildi.")
    return redirect("stokapp:takim_listesi")


def _update_recipe_tool_link_from_form(request):
    link_id = request.POST.get("link_id")
    link = get_object_or_404(ReceteOperasyonTakim, pk=link_id)
    station_id = request.POST.get("station_id")
    recete_operasyon_id = request.POST.get("recete_operasyon_id")
    recete_operasyon = get_object_or_404(ReceteOperasyon.objects.select_related("istasyon"), pk=recete_operasyon_id)
    if station_id:
        try:
            if int(station_id) != int(recete_operasyon.istasyon_id or 0):
                messages.error(request, "Seçilen operasyon, seçtiğiniz istasyona ait değil.")
                return redirect("stokapp:takim_listesi")
        except ValueError:
            messages.error(request, "Geçersiz istasyon seçimi.")
            return redirect("stokapp:takim_listesi")

    tool_id = request.POST.get("tool_id")
    tool = Tool.objects.filter(pk=tool_id).first() if tool_id else None
    tool_type = (request.POST.get("tool_type") or "").strip()
    hole_count = int(request.POST.get("hole_count", "0") or 0)
    hole_depth_mm = _to_decimal(request.POST.get("hole_depth_mm"))
    material_id = request.POST.get("material_id")
    material = ToolMaterial.objects.filter(pk=material_id).first() if material_id else None
    if not tool and not tool_type:
        messages.error(request, "Takım veya takım tipi seçmelisiniz.")
        return redirect("stokapp:takim_listesi")
    if hole_count <= 0 or hole_depth_mm <= 0:
        messages.error(request, "Delik sayısı ve delik boyu sıfırdan büyük olmalıdır.")
        return redirect("stokapp:takim_listesi")

    link.recete_operasyon = recete_operasyon
    link.tool = tool
    link.tool_type = tool.tool_type if tool else tool_type
    link.hole_count = hole_count
    link.hole_depth_mm = hole_depth_mm
    link.material = material
    link.save()
    messages.success(request, "Eşleştirme kaydı güncellendi.")
    return redirect("stokapp:takim_listesi")


def _delete_recipe_tool_link_from_form(request):
    link_id = request.POST.get("link_id")
    link = get_object_or_404(ReceteOperasyonTakim, pk=link_id)
    link.delete()
    messages.success(request, "Eşleştirme kaydı silindi.")
    return redirect("stokapp:takim_listesi")


@login_required
def takim_detay(request, pk):
    tool = get_object_or_404(Tool, pk=pk)
    if request.method == "POST":
        return _create_tool_change_from_form(request, tool)

    usage_qs = tool.usage_logs.select_related("task", "work_order", "material", "life_cycle").order_by("-created_at")[:100]
    changes = tool.changes.select_related("created_by").order_by("-change_date")[:100]
    life_cycles = tool.life_cycles.order_by("-life_no")
    active_life = tool.get_active_life()
    son_kullanim = tool.usage_logs.aggregate(last=Max("created_at")).get("last")
    context = {
        "tool": tool,
        "usage_logs": usage_qs,
        "changes": changes,
        "life_cycles": life_cycles,
        "active_life": active_life,
        "change_reason_choices": ToolChange.CHANGE_REASONS,
        "son_kullanim": son_kullanim,
    }
    return render(request, "stokapp/takim_detay.html", context)


def _create_tool_change_from_form(request, tool):
    reason = request.POST.get("change_reason", "").strip()
    if reason not in {"broken", "worn", "regrind"}:
        messages.error(request, "Geçerli bir değişim nedeni seçin.")
        return redirect("stokapp:takim_detay", pk=tool.id)
    change_date_raw = request.POST.get("change_date", "").strip()
    change_date = timezone.now()
    if change_date_raw:
        parsed = datetime.fromisoformat(change_date_raw)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        change_date = parsed
    cutting_mm = _to_decimal(request.POST.get("cutting_mm_at_change"), tool.total_cutting_mm)
    active_life = tool.get_active_life()
    ToolChange.objects.create(
        tool=tool,
        life_cycle=active_life,
        change_date=change_date,
        change_reason=reason,
        cutting_mm_at_change=cutting_mm,
        note=request.POST.get("note", "").strip(),
        created_by=request.user if request.user.is_authenticated else None,
    )
    tool.apply_life_change(reason=reason, note=request.POST.get("note", "").strip(), end_date=change_date)
    messages.success(request, "Takım değişim kaydı oluşturuldu ve takım durumu güncellendi.")
    return redirect("stokapp:takim_detay", pk=tool.id)


@login_required
def takim_raporlari(request):
    context = {
        "tools": Tool.objects.all().order_by("tool_code"),
        "materials": ToolMaterial.objects.all(),
    }
    return render(request, "stokapp/takim_raporlari.html", context)


@login_required
@require_POST
def create_tool(request):
    payload = json.loads(request.body.decode("utf-8"))
    _ensure_default_tool_types()
    diameter = _to_decimal(payload.get("diameter"))
    if diameter <= 0:
        return JsonResponse({"success": False, "error": "Geçerli diameter zorunludur."}, status=400)
    tool_type_option = ToolTypeOption.objects.filter(pk=payload.get("tool_type_option_id"), aktif=True).first()
    if not tool_type_option:
        return JsonResponse({"success": False, "error": "Geçerli takım tipi seçin."}, status=400)
    brand_option = ToolBrandOption.objects.filter(pk=payload.get("brand_option_id")).first()
    coating_option = ToolCoatingOption.objects.filter(pk=payload.get("coating_option_id")).first()
    model_option = ToolModelOption.objects.filter(pk=payload.get("model_option_id")).first()
    body_material_option = ToolBodyMaterialOption.objects.filter(pk=payload.get("body_material_option_id")).first()
    tool = Tool.objects.create(
        tool_type=tool_type_option.name,
        tool_type_option=tool_type_option,
        diameter=diameter,
        brand=brand_option.name if brand_option else "",
        brand_option=brand_option,
        coating=coating_option.name if coating_option else "",
        coating_option=coating_option,
        model_no=model_option.name if model_option else "",
        model_option=model_option,
        body_material_option=body_material_option,
        max_cutting_mm=_to_decimal(payload.get("max_cutting_mm")),
    )
    return JsonResponse({"success": True, "tool": _tool_payload(tool)})


@login_required
@require_POST
def create_tool_option(request):
    payload = json.loads(request.body.decode("utf-8"))
    option_kind = (payload.get("option_kind") or "").strip()
    option_name = (payload.get("option_name") or "").strip()
    option_prefix = (payload.get("option_prefix") or "").strip().upper()
    if not option_name:
        return JsonResponse({"success": False, "error": "option_name zorunludur."}, status=400)
    if option_kind == "tool_type":
        if not option_prefix:
            return JsonResponse({"success": False, "error": "option_prefix zorunludur."}, status=400)
        option, _ = ToolTypeOption.objects.get_or_create(
            name=option_name,
            defaults={"prefix": option_prefix, "aktif": True},
        )
        return JsonResponse({"success": True, "id": option.id, "name": option.name, "prefix": option.prefix})
    model_map = _option_model_map()
    model_cls = model_map.get(option_kind)
    if not model_cls:
        return JsonResponse({"success": False, "error": "Geçersiz option_kind."}, status=400)
    option, _ = model_cls.objects.get_or_create(name=option_name)
    return JsonResponse({"success": True, "id": option.id, "name": option.name})


@login_required
def get_tools(request):
    qs = Tool.objects.all().order_by("-created_at")
    return JsonResponse({"success": True, "items": [_tool_payload(t) for t in qs]})


@login_required
def get_tool_detail(request, pk):
    tool = get_object_or_404(Tool, pk=pk)
    usage = list(
        tool.usage_logs.select_related("material", "task", "work_order", "life_cycle")
        .order_by("-created_at")
        .values(
            "id",
            "created_at",
            "cutting_mm",
            "life_cycle__life_no",
            "material__name",
            "task_id",
            "work_order__emir_no",
        )[:100]
    )
    changes = list(
        tool.changes.select_related("created_by")
        .order_by("-change_date")
        .values("id", "change_date", "change_reason", "cutting_mm_at_change", "note", "created_by__username")[:100]
    )
    return JsonResponse({"success": True, "tool": _tool_payload(tool), "usage_logs": usage, "changes": changes})


@login_required
@require_POST
def log_tool_usage(request):
    payload = json.loads(request.body.decode("utf-8"))
    tool = get_object_or_404(Tool, pk=payload.get("tool_id"))
    task = get_object_or_404(UretimAsamasi, pk=payload.get("task_id"))
    work_order = get_object_or_404(UretimEmri, pk=payload.get("work_order_id"))
    cutting_mm = _to_decimal(payload.get("cutting_mm"))
    if cutting_mm <= 0:
        return JsonResponse({"success": False, "error": "cutting_mm sıfırdan büyük olmalıdır."}, status=400)
    material_id = payload.get("material_id")
    material = ToolMaterial.objects.filter(pk=material_id).first() if material_id else None
    with transaction.atomic():
        ToolUsageLog.objects.create(
            tool=tool,
            task=task,
            work_order=work_order,
            material=material,
            cutting_mm=cutting_mm,
        )
        tool.total_cutting_mm = _to_decimal(tool.total_cutting_mm) + cutting_mm
        tool.save(update_fields=["total_cutting_mm"])
    return JsonResponse({"success": True, "tool": _tool_payload(tool)})


@login_required
@require_POST
def create_tool_change(request):
    payload = json.loads(request.body.decode("utf-8"))
    tool = get_object_or_404(Tool, pk=payload.get("tool_id"))
    reason = payload.get("change_reason")
    if reason not in {"broken", "worn", "regrind"}:
        return JsonResponse({"success": False, "error": "Geçersiz change_reason."}, status=400)
    active_life = tool.get_active_life()
    change = ToolChange.objects.create(
        tool=tool,
        life_cycle=active_life,
        change_reason=reason,
        cutting_mm_at_change=_to_decimal(payload.get("cutting_mm_at_change"), tool.total_cutting_mm),
        note=(payload.get("note") or "").strip(),
        created_by=request.user if request.user.is_authenticated else None,
    )
    tool.apply_life_change(reason=reason, note=(payload.get("note") or "").strip())
    return JsonResponse({"success": True, "change_id": change.id, "tool": _tool_payload(tool)})


@login_required
def get_tool_reports(request):
    qs = ToolUsageLog.objects.select_related("tool", "material")
    tool_id = request.GET.get("tool")
    material_id = request.GET.get("material")
    date_start = request.GET.get("date_start")
    date_end = request.GET.get("date_end")
    if tool_id:
        qs = qs.filter(tool_id=tool_id)
    if material_id:
        qs = qs.filter(material_id=material_id)
    if date_start:
        qs = qs.filter(created_at__date__gte=date_start)
    if date_end:
        qs = qs.filter(created_at__date__lte=date_end)

    total_cutting = qs.aggregate(total=Sum("cutting_mm")).get("total") or Decimal("0")
    by_material = list(
        qs.values("material__name")
        .annotate(total=Sum("cutting_mm"))
        .order_by("-total")
    )
    by_tool = list(
        qs.values("tool__tool_code")
        .annotate(total=Sum("cutting_mm"))
        .order_by("-total")
    )
    by_day = list(
        qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("cutting_mm"))
        .order_by("day")
    )
    life_qs = ToolUsageLog.objects.select_related("life_cycle", "tool")
    if tool_id:
        life_qs = life_qs.filter(tool_id=tool_id)
    if material_id:
        life_qs = life_qs.filter(material_id=material_id)
    if date_start:
        life_qs = life_qs.filter(created_at__date__gte=date_start)
    if date_end:
        life_qs = life_qs.filter(created_at__date__lte=date_end)
    by_life = list(
        life_qs.values("tool__tool_code", "life_cycle__life_no")
        .annotate(total=Sum("cutting_mm"))
        .order_by("tool__tool_code", "life_cycle__life_no")
    )
    life_avg = Decimal("0")
    if by_life:
        life_avg = (sum(Decimal(str(row.get("total") or 0)) for row in by_life) / Decimal(str(len(by_life)))).quantize(Decimal("0.001"))
    return JsonResponse(
        {
            "success": True,
            "summary": {"total_cutting_mm": str(total_cutting)},
            "by_material": by_material,
            "by_tool": by_tool,
            "by_day": by_day,
            "by_life": by_life,
            "avg_life_mm": str(life_avg),
        }
    )
