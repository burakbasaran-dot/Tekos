"""
TEKORA e-posta kaynaklı onayların ürün / stok analizini güncel kurallarla yeniden üretir.
"""

from stokapp.constants import SYSTEM_AI_NAME
from stokapp.models import ApprovalRequest
from stokapp.views_mail import (
    _extract_tf_order_number,
    _run_stock_check,
    analyze_email,
    clean_email_body,
    make_json_serializable,
)


_REFRESHABLE_STATUSES = frozenset(
    {
        ApprovalRequest.STATUS_PENDING,
        ApprovalRequest.STATUS_FAILED,
    }
)


def refresh_email_approval_analysis(ar):
    """
    E-posta kaynaklı; durumu onay bekliyor veya hatalı olan kayıtlar.
    Payload içinden gövde: önce html_body_snapshot (HTML), yoksa raw_body (düz metin).
    Hatalı kayıtlar yeniden analiz sonrası tekrar onay bekliyor durumuna alınır.
    """
    if ar.source != ApprovalRequest.SOURCE_EMAIL:
        return {"ok": False, "skipped": True, "reason": "not_email"}
    if ar.status not in _REFRESHABLE_STATUSES:
        return {"ok": False, "skipped": True, "reason": "status_not_refreshable"}

    pl = dict(ar.payload or {})
    subject = (pl.get("subject") or "").strip()
    sender = (pl.get("sender") or "").strip()
    body_src = (pl.get("html_body_snapshot") or pl.get("raw_body") or "").strip()
    if not body_src and not subject:
        return {"ok": False, "skipped": True, "reason": "no_body"}

    mail = {"subject": subject, "body": body_src, "sender": sender}
    analysis = analyze_email(mail)
    detected_items = analysis.get("detected_items") or []
    stock_checks, _has_insufficient = _run_stock_check(detected_items)

    cleaned_for_tf = clean_email_body(body_src, max_chars=16000)
    preferred_no = _extract_tf_order_number(subject, cleaned_for_tf)

    first_insufficient = next((x for x in stock_checks if x.get("status") == "insufficient"), None)

    pl["detected_items"] = make_json_serializable(detected_items)
    pl["stock_checks"] = make_json_serializable(stock_checks)
    pl["stock_check"] = make_json_serializable(stock_checks[0]) if stock_checks else None

    if preferred_no:
        pl["preferred_siparis_numarasi"] = preferred_no

    if first_insufficient:
        pl["purchase_recommendation"] = make_json_serializable(
            {
                "product_code": first_insufficient.get("product_code"),
                "required_quantity": first_insufficient.get("missing_quantity"),
                "unit": first_insufficient.get("unit") or "adet",
                "reason": "Stok yetersiz; sipariş kalemleri oluşturulur, satın alma ihtiyacı sipariş notlarında görülebilir.",
            }
        )
    else:
        pl.pop("purchase_recommendation", None)

    summary_base = analysis.get("summary") or "Mail içeriği kısa veya boş."
    new_ai_summary = clean_email_body(f"{SYSTEM_AI_NAME} özeti: {summary_base}")

    ar.payload = pl
    ar.ai_summary = new_ai_summary

    update_fields = ["payload", "ai_summary", "updated_at"]
    reset_to_pending = ar.status == ApprovalRequest.STATUS_FAILED
    if reset_to_pending:
        ar.status = ApprovalRequest.STATUS_PENDING
        ar.error_message = None
        update_fields.extend(["status", "error_message"])

    ar.save(update_fields=update_fields)

    return {
        "ok": True,
        "id": str(ar.id),
        "detected_items_count": len(detected_items),
        "stock_checks_count": len(stock_checks),
        "reset_to_pending": reset_to_pending,
    }


def refresh_all_pending_email_orders(limit=500):
    qs = ApprovalRequest.objects.filter(
        status__in=list(_REFRESHABLE_STATUSES),
        source=ApprovalRequest.SOURCE_EMAIL,
        action_type__in=[
            ApprovalRequest.ACTION_CREATE_SALES_ORDER,
            ApprovalRequest.ACTION_CREATE_PURCHASE_REQUEST,
        ],
    ).order_by("-created_at")[:limit]

    stats = {"updated": 0, "skipped": 0, "failed_reset_to_pending": 0, "errors": []}
    for ar in qs:
        try:
            out = refresh_email_approval_analysis(ar)
            if out.get("ok"):
                stats["updated"] += 1
                if out.get("reset_to_pending"):
                    stats["failed_reset_to_pending"] += 1
            elif out.get("skipped"):
                stats["skipped"] += 1
        except Exception as exc:
            stats["errors"].append({"id": str(ar.id), "error": str(exc)})
    return stats
