"""TEKORA onay merkezi araçları — yalnızca ApprovalRequest üretir; satınalma fişi oluşturmaz."""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)

_MAX_PRODUCT_LEN = 500
_MAX_QTY = 1_000_000_000
_MAX_REASON_LEN = 2000
_MAX_BULK_ITEMS = 500
_MAX_ITEM_CODE_LEN = 120
_MAX_ITEM_NAME_LEN = 500


def _to_number(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def create_purchase_request(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Satınalma satırı oluşturmaz; ApprovalRequest (pending) üretir.
    Zorunlu: product (veya product_id ile çözülebilir ad), suggested_quantity.
    İsteğe bağlı: product_id, product_code, current_stock, notes, reason, tekora_triggered_by
    """
    work: dict[str, Any] = dict(payload)

    product = work.get("product") or work.get("product_name")
    product_id = work.get("product_id")
    pk: int | None = None
    try:
        if product_id is not None and str(product_id).strip() != "":
            pk = int(product_id)
    except (TypeError, ValueError):
        pk = None

    if (not isinstance(product, str) or not product.strip()) and pk:
        try:
            from .models import StokItem

            item = StokItem.objects.only("ad", "stok_kodu", "mevcut_miktar").get(pk=pk)
            product = item.ad
            if not work.get("product_code"):
                work["product_code"] = item.stok_kodu
            if work.get("current_stock") is None:
                work["current_stock"] = float(item.mevcut_miktar or 0)
        except Exception:
            logger.exception("create_purchase_request: product_id çözülemedi (%s)", pk)
            return {
                "status": "error",
                "error": "product veya geçerli product_id zorunludur.",
                "approval_tool": "create_purchase_request",
            }

    if not isinstance(product, str) or not product.strip():
        return {
            "status": "error",
            "error": "product alanı zorunludur.",
            "approval_tool": "create_purchase_request",
        }

    product = product.strip()[:_MAX_PRODUCT_LEN]
    sq = _to_number(work.get("suggested_quantity"))
    if sq is None or sq <= 0 or sq > _MAX_QTY:
        return {
            "status": "error",
            "error": "suggested_quantity pozitif bir sayı olmalıdır.",
            "approval_tool": "create_purchase_request",
        }

    cur = _to_number(work.get("current_stock"))
    notes = work.get("notes")
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)
    if isinstance(notes, str):
        notes = notes.strip()[:2000] or None

    reason = work.get("reason")
    if reason is not None and not isinstance(reason, str):
        reason = str(reason)
    if isinstance(reason, str):
        reason = reason.strip()[:_MAX_REASON_LEN] or None

    triggered_by = work.get("tekora_triggered_by")
    if triggered_by is not None and not isinstance(triggered_by, str):
        triggered_by = str(triggered_by)[:150]

    product_code = work.get("product_code")
    if product_code is not None and not isinstance(product_code, str):
        product_code = str(product_code)
    if isinstance(product_code, str):
        product_code = product_code.strip()[:120] or None

    out_payload: dict[str, Any] = {
        "product": product,
        "suggested_quantity": int(sq) if sq == int(sq) else sq,
    }
    if pk:
        out_payload["product_id"] = pk
    if product_code:
        out_payload["product_code"] = product_code
    if cur is not None:
        out_payload["current_stock"] = cur
    if reason:
        out_payload["reason"] = reason
    if notes:
        out_payload["notes"] = notes
    if triggered_by:
        out_payload["tekora_triggered_by"] = triggered_by

    from .models import ApprovalRequest

    title = "TEKORA Satınalma Önerisi"
    description = (
        "Kritik stok tespit edildi.\n"
        "AI satınalma önerisi oluşturdu.\n"
        "Bu kayıt yalnızca onay kuyruğundadır; otomatik satınalma oluşturulmaz."
    )
    if reason:
        description += f"\n\nGerekçe:\n{reason}"
    if notes:
        description += f"\n\nEk not:\n{notes}"

    code_disp = product_code or "—"
    ai_summary = (
        f"Ürün kodu: {code_disp}. Ürün: {product}. "
        f"Güncel stok: {cur if cur is not None else 'bilinmiyor'}. "
        f"Önerilen satınalma miktarı: {out_payload['suggested_quantity']}. "
        "TEKORA AI — onay merkezinde değerlendirme bekliyor."
    )

    risk = ApprovalRequest.RISK_HIGH if (cur is not None and cur <= 0) else ApprovalRequest.RISK_MEDIUM

    try:
        with transaction.atomic():
            ar = ApprovalRequest(
                action_type=ApprovalRequest.ACTION_CREATE_PURCHASE_REQUEST,
                title=title[:255],
                description=description,
                ai_summary=ai_summary,
                payload=out_payload,
                risk_level=risk,
                status=ApprovalRequest.STATUS_PENDING,
                source=ApprovalRequest.SOURCE_STOCK,
            )
            ar.save()
    except Exception:
        logger.exception("[TEKORA APPROVAL] create_purchase_request DB hatası")
        return {
            "status": "error",
            "error": "Onay kaydı oluşturulamadı.",
            "approval_tool": "create_purchase_request",
        }

    logger.info(
        "[TEKORA APPROVAL]\nTool: create_purchase_request\nStatus: pending_approval\nApproval id: %s",
        ar.pk,
    )

    try:
        from .tekora_memory_log import log_tekora_decision, resolve_tekora_user

        log_tekora_decision(
            user=resolve_tekora_user(triggered_by if isinstance(triggered_by, str) else None),
            decision_type="purchase_request",
            title=title[:255],
            description=(description or "")[:8000],
            related_approval=ar,
            payload={
                "approval_id": str(ar.pk),
                "product": product,
                "suggested_quantity": out_payload.get("suggested_quantity"),
            },
            status="recorded",
        )
    except Exception:
        logger.exception("[TEKORA MEMORY] TekoraDecisionLog (purchase_request) atlandı")

    return {
        "status": "ok",
        "approval_tool": "create_purchase_request",
        "approval_id": str(ar.pk),
        "approval_status": "pending",
        "message": "Satınalma önerisi onay merkezine kaydedildi. Doğrudan satınalma oluşturulmadı.",
    }


def _normalize_bulk_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        pid = int(raw.get("product_id"))
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    sq = _to_number(raw.get("suggested_quantity"))
    if sq is None or sq <= 0 or sq > _MAX_QTY:
        return None
    code = raw.get("product_code")
    if code is not None and not isinstance(code, str):
        code = str(code)
    code = (code or "").strip()[:_MAX_ITEM_CODE_LEN] or f"ID:{pid}"
    name = raw.get("product_name") or raw.get("product")
    if name is not None and not isinstance(name, str):
        name = str(name)
    name = (name or "").strip()[:_MAX_ITEM_NAME_LEN] or code
    cur = _to_number(raw.get("current_stock"))
    cl = _to_number(raw.get("critical_level"))
    sev = raw.get("severity")
    if sev is not None and not isinstance(sev, str):
        sev = str(sev)
    sev = (sev or "medium").strip().lower()[:20]
    if sev not in ("high", "medium", "low"):
        sev = "medium"
    return {
        "product_id": pid,
        "product_code": code,
        "product_name": name,
        "current_stock": cur if cur is not None else 0.0,
        "critical_level": cl if cl is not None else 0.0,
        "suggested_quantity": int(sq) if sq == int(sq) else sq,
        "severity": sev,
    }


def create_bulk_purchase_approval(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Kritik stok analiz satırlarından tek ApprovalRequest (pending) üretir.
    Payload: type=bulk_purchase_request, generated_by, items[] (product_id, product_code, ...).
    Satınalma fişi / talep oluşturmaz; yalnızca onay kuyruğu.
    """
    work = dict(payload) if isinstance(payload, dict) else {}
    ptype = work.get("type")
    if ptype is not None and str(ptype).strip() and str(ptype).strip() != "bulk_purchase_request":
        return {
            "status": "error",
            "error": "type alanı bulk_purchase_request olmalıdır.",
            "approval_tool": "create_bulk_purchase_approval",
        }

    items_raw = work.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        return {
            "status": "error",
            "error": "items boş olamaz.",
            "approval_tool": "create_bulk_purchase_approval",
        }

    normalized: list[dict[str, Any]] = []
    for raw in items_raw[:_MAX_BULK_ITEMS]:
        row = _normalize_bulk_item(raw)
        if row:
            normalized.append(row)

    if not normalized:
        return {
            "status": "error",
            "error": "Geçerli satır bulunamadı (product_id ve pozitif suggested_quantity gerekli).",
            "approval_tool": "create_bulk_purchase_approval",
        }

    ids = list({r["product_id"] for r in normalized})
    try:
        from .models import ApprovalRequest, StokItem

        found = set(
            StokItem.objects.filter(pk__in=ids, arsivli=False).values_list("pk", flat=True)
        )
    except Exception:
        logger.exception("create_bulk_purchase_approval: stok doğrulama hatası")
        return {
            "status": "error",
            "error": "Ürün doğrulaması yapılamadı.",
            "approval_tool": "create_bulk_purchase_approval",
        }

    missing = [i for i in ids if i not in found]
    if missing:
        return {
            "status": "error",
            "error": f"Bazı ürünler bulunamadı veya arşivli: {missing[:10]}",
            "approval_tool": "create_bulk_purchase_approval",
        }

    triggered_by = work.get("tekora_triggered_by")
    if triggered_by is not None and not isinstance(triggered_by, str):
        triggered_by = str(triggered_by)[:150]

    gen = work.get("generated_by")
    if gen is not None and not isinstance(gen, str):
        gen = str(gen)[:80]
    gen = (gen or "TEKORA").strip()[:80]

    out_items = [
        {
            "product_id": r["product_id"],
            "product_code": r["product_code"],
            "product_name": r["product_name"],
            "current_stock": r["current_stock"],
            "critical_level": r["critical_level"],
            "suggested_quantity": r["suggested_quantity"],
            "severity": r["severity"],
        }
        for r in normalized
    ]

    stored_payload: dict[str, Any] = {
        "type": "bulk_purchase_request",
        "generated_by": gen,
        "items": out_items,
    }
    if triggered_by:
        stored_payload["tekora_triggered_by"] = triggered_by

    title = "TEKORA Toplu Satınalma Önerisi"
    description = (
        "AI tarafından kritik stok analizi sonucu oluşturulan toplu satınalma önerisi.\n"
        "Bu kayıt yalnızca onay kuyruğundadır; otomatik satınalma veya talep oluşturulmaz."
    )

    n = len(out_items)
    ai_summary = (
        f"Toplu öneri: {n} kalem. Kritik stok analizi sonrası TEKORA — onay merkezinde değerlendirme bekliyor."
    )

    any_high = any(
        r["severity"] == "high" or (isinstance(r["current_stock"], (int, float)) and r["current_stock"] <= 0)
        for r in out_items
    )
    risk = ApprovalRequest.RISK_HIGH if any_high else ApprovalRequest.RISK_MEDIUM

    try:
        with transaction.atomic():
            ar = ApprovalRequest(
                action_type=ApprovalRequest.ACTION_BULK_CREATE_PURCHASE_REQUEST,
                title=title[:255],
                description=description,
                ai_summary=ai_summary,
                payload=stored_payload,
                risk_level=risk,
                status=ApprovalRequest.STATUS_PENDING,
                source=ApprovalRequest.SOURCE_STOCK,
            )
            ar.save()
    except Exception:
        logger.exception("[TEKORA APPROVAL] create_bulk_purchase_approval DB hatası")
        return {
            "status": "error",
            "error": "Toplu onay kaydı oluşturulamadı.",
            "approval_tool": "create_bulk_purchase_approval",
        }

    logger.info(
        "[TEKORA APPROVAL]\nType: bulk_purchase_request\nItem count: %s\nApproval id: %s",
        n,
        ar.pk,
    )

    try:
        from .tekora_memory_log import log_tekora_decision, resolve_tekora_user

        log_tekora_decision(
            user=resolve_tekora_user(triggered_by if isinstance(triggered_by, str) else None),
            decision_type="bulk_purchase_request",
            title=title[:255],
            description=(description or "")[:8000],
            related_approval=ar,
            payload={
                "approval_id": str(ar.pk),
                "item_count": n,
                "type": "bulk_purchase_request",
            },
            status="recorded",
        )
    except Exception:
        logger.exception("[TEKORA MEMORY] TekoraDecisionLog (bulk_purchase_request) atlandı")

    return {
        "status": "ok",
        "approval_tool": "create_bulk_purchase_approval",
        "approval_id": str(ar.pk),
        "approval_status": "pending",
        "item_count": n,
        "message": f"{n} ürün için toplu satınalma onay kaydı oluşturuldu. Onay merkezinden inceleyebilirsiniz.",
    }


def extract_purchase_payload_from_message(message: str) -> dict[str, Any]:
    """
    Basit sezgisel çıkarım (onay paneli yoksa). Güvenilir değildir; tercihen approval_payload kullanılır.
    """
    out: dict[str, Any] = {}
    t = message.strip()
    if not t:
        return out

    mq = re.search(
        r"(?:miktar|adet|qty)\s*[:.]?\s*([\d.,]+)",
        t,
        flags=re.IGNORECASE,
    )
    if mq:
        sq = _to_number(mq.group(1))
        if sq and sq > 0:
            out["suggested_quantity"] = sq

    cq = re.search(
        r"(?:güncel\s*stok|mevcut\s*stok|stok)\s*[:.]?\s*([\d.,]+)",
        t,
        flags=re.IGNORECASE,
    )
    if cq:
        cv = _to_number(cq.group(1))
        if cv is not None:
            out["current_stock"] = cv

    pm = re.search(
        r"(?:ürün|urun|malzeme)\s*[:]\s*(.+?)(?:\.|,|miktar|güncel|$)",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if pm:
        cand = pm.group(1).strip()
        if len(cand) >= 2:
            out["product"] = cand[:_MAX_PRODUCT_LEN]

    return out
