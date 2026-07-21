import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from stokapp.constants import SYSTEM_AI_NAME
from stokapp.nav_visibility import NAV_KEY_URETIM_TEKORA_ONAY, hidden_nav_access_required
from stokapp.models import ApprovalRequest
from stokapp.services.approval_service import approve_request, serialize_approval_request
from stokapp.services.tekora_approval_refresh import (
    refresh_all_pending_email_orders,
    refresh_email_approval_analysis,
)


def _get_json_payload(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@login_required
@hidden_nav_access_required(NAV_KEY_URETIM_TEKORA_ONAY)
def ai_approval_center(request):
    filters = {
        "status": request.GET.get("status", "").strip(),
        "action_type": request.GET.get("action_type", "").strip(),
        "risk_level": request.GET.get("risk_level", "").strip(),
        "source": request.GET.get("source", "").strip(),
    }

    qs = ApprovalRequest.objects.all()
    if filters["status"]:
        qs = qs.filter(status=filters["status"])
    if filters["action_type"]:
        qs = qs.filter(action_type=filters["action_type"])
    if filters["risk_level"]:
        qs = qs.filter(risk_level=filters["risk_level"])
    if filters["source"]:
        qs = qs.filter(source=filters["source"])

    status_counts = {
        row["status"]: row["total"]
        for row in ApprovalRequest.objects.values("status").annotate(total=Count("id"))
    }
    for key in ["pending", "approved", "rejected", "executed", "failed"]:
        status_counts.setdefault(key, 0)

    return render(
        request,
        "stokapp/ai_approval_center.html",
        {
            "requests": qs[:200],
            "status_counts": status_counts,
            "filters": filters,
            "action_types": ApprovalRequest.ACTION_TYPES,
            "risk_levels": ApprovalRequest.RISK_LEVELS,
            "sources": ApprovalRequest.SOURCE_CHOICES,
            "statuses": ApprovalRequest.STATUS_CHOICES,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def approval_requests_collection_api(request):
    if request.method == "GET":
        qs = ApprovalRequest.objects.all()
        for f in ["status", "action_type", "risk_level", "source"]:
            val = request.GET.get(f)
            if val:
                qs = qs.filter(**{f: val})
        data = [serialize_approval_request(x) for x in qs[:500]]
        return JsonResponse({"count": len(data), "results": data})

    payload = _get_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Geçersiz JSON")

    required = ["action_type", "title", "description", "ai_summary", "payload", "source"]
    for f in required:
        if f not in payload:
            return JsonResponse({"error": f"{f} zorunludur."}, status=400)

    obj = ApprovalRequest.objects.create(
        action_type=payload["action_type"],
        title=payload["title"],
        description=payload.get("description", ""),
        ai_summary=payload.get("ai_summary", ""),
        payload=payload.get("payload", {}),
        risk_level=payload.get("risk_level", ApprovalRequest.RISK_MEDIUM),
        source=payload.get("source", ApprovalRequest.SOURCE_MANUAL),
        status=ApprovalRequest.STATUS_PENDING,
    )
    return JsonResponse(serialize_approval_request(obj), status=201)


@login_required
@require_http_methods(["GET", "PATCH"])
def approval_request_detail_api(request, pk):
    obj = get_object_or_404(ApprovalRequest, pk=pk)
    if request.method == "GET":
        return JsonResponse(serialize_approval_request(obj))

    payload = _get_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Geçersiz JSON")

    allowed = {"title", "description", "ai_summary", "payload", "risk_level", "source"}
    changed = False
    for key in allowed:
        if key in payload:
            setattr(obj, key, payload[key])
            changed = True

    if "payload" in payload:
        obj.status = ApprovalRequest.STATUS_PENDING
        obj.error_message = None
        changed = True

    if changed:
        obj.save()
    return JsonResponse(serialize_approval_request(obj))


@login_required
@require_POST
def approval_request_approve_api(request, pk):
    obj = get_object_or_404(ApprovalRequest, pk=pk)
    if obj.status not in [ApprovalRequest.STATUS_PENDING, ApprovalRequest.STATUS_FAILED]:
        return JsonResponse({"error": "Sadece pending/failed kayıtlar onaylanabilir."}, status=400)

    result = approve_request(obj, request.user.username)
    response = serialize_approval_request(obj)
    response["execution"] = result
    return JsonResponse(response, status=200 if result["ok"] else 500)


@login_required
@require_POST
def approval_request_reject_api(request, pk):
    obj = get_object_or_404(ApprovalRequest, pk=pk)
    if obj.status not in [ApprovalRequest.STATUS_PENDING, ApprovalRequest.STATUS_FAILED]:
        return JsonResponse({"error": "Sadece pending/failed kayıtlar reddedilebilir."}, status=400)

    payload = _get_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Geçersiz JSON")
    reject_reason = (payload.get("reject_reason") or "").strip()
    if not reject_reason:
        return JsonResponse({"error": "reject_reason zorunludur."}, status=400)

    from django.utils import timezone

    obj.status = ApprovalRequest.STATUS_REJECTED
    obj.rejected_by = request.user.username
    obj.rejected_at = timezone.now()
    obj.reject_reason = reject_reason
    obj.save(update_fields=["status", "rejected_by", "rejected_at", "reject_reason", "updated_at"])
    return JsonResponse(serialize_approval_request(obj))


@login_required
@require_POST
def approval_requests_bulk_approve_api(request):
    payload = _get_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Geçersiz JSON")

    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return JsonResponse({"error": "ids listesi zorunludur."}, status=400)

    results = []
    for obj in ApprovalRequest.objects.filter(id__in=ids):
        if obj.status not in [ApprovalRequest.STATUS_PENDING, ApprovalRequest.STATUS_FAILED]:
            results.append({"id": str(obj.id), "ok": False, "error": "Durum uygun değil"})
            continue
        result = approve_request(obj, request.user.username)
        results.append({"id": str(obj.id), **result})

    return JsonResponse({"results": results})


@login_required
@require_POST
def approval_requests_bulk_reject_api(request):
    payload = _get_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Geçersiz JSON")

    ids = payload.get("ids") or []
    reject_reason = (payload.get("reject_reason") or "").strip()
    if not isinstance(ids, list) or not ids:
        return JsonResponse({"error": "ids listesi zorunludur."}, status=400)
    if not reject_reason:
        return JsonResponse({"error": "reject_reason zorunludur."}, status=400)

    from django.utils import timezone

    results = []
    for obj in ApprovalRequest.objects.filter(id__in=ids):
        if obj.status not in [ApprovalRequest.STATUS_PENDING, ApprovalRequest.STATUS_FAILED]:
            results.append({"id": str(obj.id), "ok": False, "error": "Durum uygun değil"})
            continue
        obj.status = ApprovalRequest.STATUS_REJECTED
        obj.rejected_by = request.user.username
        obj.rejected_at = timezone.now()
        obj.reject_reason = reject_reason
        obj.save(update_fields=["status", "rejected_by", "rejected_at", "reject_reason", "updated_at"])
        results.append({"id": str(obj.id), "ok": True})

    return JsonResponse({"results": results})


@login_required
@require_POST
def approval_request_seed_demo_api(request):
    sample_payload = {
        "customer_name": "ABC Firma",
        "order_source": "email",
        "items": [{"product_code": "TMW-DSB-30-HM-G", "quantity": 12, "unit": "adet"}],
        "requested_delivery_date": None,
        "email_subject": "Yeni sipariş talebi",
        "email_sender": "satinalma@abcfirma.com",
    }

    obj = ApprovalRequest.objects.create(
        action_type=ApprovalRequest.ACTION_CREATE_SALES_ORDER,
        title=f"Yeni müşteri siparişi {SYSTEM_AI_NAME} tarafından algılandı",
        description="ABC firmasından gelen mail sipariş olarak algılandı.",
        ai_summary=(
            f"{SYSTEM_AI_NAME} analizi: Müşteri ABC firması 12 adet TMW-DSB-30-HM-G ürünü için sipariş geçmiş görünüyor. "
            "Termin talebi 15 gün."
        ),
        payload=sample_payload,
        risk_level=ApprovalRequest.RISK_MEDIUM,
        source=ApprovalRequest.SOURCE_EMAIL,
        status=ApprovalRequest.STATUS_PENDING,
    )
    return JsonResponse(serialize_approval_request(obj), status=201)


@login_required
@require_POST
def approval_requests_refresh_pending_email_api(request):
    """Onay bekleyen ve hatalı e-posta sipariş kayıtlarının analizini güncel kurallarla yeniden hesaplar (hatalılar tekrar bekliyor olur)."""
    try:
        limit = int(request.GET.get("limit") or "500")
    except ValueError:
        limit = 500
    limit = max(1, min(limit, 1000))
    stats = refresh_all_pending_email_orders(limit=limit)
    return JsonResponse(stats)


@login_required
@require_POST
def approval_request_refresh_analysis_api(request, pk):
    """Tek bir e-posta onay kaydının analizini yeniler (bekleyen veya hatalı)."""
    obj = get_object_or_404(ApprovalRequest, pk=pk)
    out = refresh_email_approval_analysis(obj)
    return JsonResponse(out)


@login_required
@require_POST
def cleanup_approval_email_texts_api(request):
    # Geçici bakım endpointi: mevcut kayıtların metin alanlarını yeniden sanitize eder.
    from stokapp.views_mail import clean_email_body

    qs = ApprovalRequest.objects.all().order_by("-created_at")
    cleaned = 0
    for record in qs:
        payload = record.payload or {}
        old_summary = record.ai_summary or ""
        old_description = record.description or ""
        old_raw_body = payload.get("raw_body", "")

        new_summary = clean_email_body(old_summary)
        new_description = clean_email_body(old_description)
        new_raw_body = clean_email_body(old_raw_body)

        changed = False
        if new_summary != old_summary:
            record.ai_summary = new_summary
            changed = True
        if new_description != old_description:
            record.description = new_description
            changed = True
        if new_raw_body != old_raw_body:
            payload["raw_body"] = new_raw_body
            record.payload = payload
            changed = True

        if changed:
            record.save(update_fields=["ai_summary", "description", "payload", "updated_at"])
            cleaned += 1

    return JsonResponse({"cleaned_count": cleaned})


@login_required
@require_POST
def simulate_email_order_api(request):
    obj = ApprovalRequest.objects.create(
        action_type=ApprovalRequest.ACTION_CREATE_SALES_ORDER,
        title=f"Mailden sipariş {SYSTEM_AI_NAME} tarafından algılandı",
        description="ABC firmasından gelen mail sipariş olarak yorumlandı.",
        ai_summary=f"{SYSTEM_AI_NAME} önerisi: Müşteri ABC firması 10 adet TMW-DSB-30-HM-G sipariş etmiş görünüyor.",
        payload={
            "customer_name": "ABC Firma",
            "order_source": "email",
            "items": [
                {
                    "product_code": "TMW-DSB-30-HM-G",
                    "quantity": 10,
                    "unit": "adet",
                }
            ],
        },
        status=ApprovalRequest.STATUS_PENDING,
        risk_level=ApprovalRequest.RISK_MEDIUM,
        source=ApprovalRequest.SOURCE_EMAIL,
    )
    return JsonResponse(serialize_approval_request(obj), status=201)
