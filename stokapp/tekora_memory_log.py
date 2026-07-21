"""TEKORA AI memory — güvenli log yazımı (ana akışı bozmaz)."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def tekora_json_safe(obj: Any, _depth: int = 0) -> Any:
    """JSONField / ORM için güvenli serileştirme (Decimal, UUID, datetime, model örnekleri)."""
    if _depth > 24:
        return "<max_depth>"
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")[:5000]
        except Exception:
            return "<bytes>"
    if hasattr(obj, "isoformat") and callable(getattr(obj, "isoformat")):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            out[key] = tekora_json_safe(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [tekora_json_safe(x, _depth + 1) for x in obj]
    if hasattr(obj, "pk") and hasattr(obj, "_meta"):
        try:
            return {"_model": obj._meta.label, "pk": obj.pk}
        except Exception:
            return str(obj)
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def log_tekora_tool(
    *,
    user: Any | None,
    tool_name: str,
    payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
    dangerous: bool,
    approval_required: bool,
    success: bool,
    error_message: str | None = None,
) -> None:
    try:
        from .models import TekoraToolLog

        TekoraToolLog.objects.create(
            user=user if getattr(user, "pk", None) else None,
            tool_name=(tool_name or "")[:120],
            payload=tekora_json_safe(payload or {}),
            result=tekora_json_safe(result or {}),
            dangerous=dangerous,
            approval_required=approval_required,
            success=success,
            error_message=(error_message or "")[:8000] if error_message else None,
        )
    except Exception:
        logger.exception("[TEKORA MEMORY] TekoraToolLog yazılamadı: %s", tool_name)


def log_tekora_chat(
    *,
    user: Any | None,
    user_message: str,
    ai_response: str = "",
    source: str = "web_chat",
    session_key: str = "",
    raw_context: dict[str, Any] | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> Any | None:
    try:
        from .models import TekoraChatLog

        chat_log = TekoraChatLog.objects.create(
            user=user if getattr(user, "pk", None) else None,
            user_message=(user_message or "")[:500000],
            ai_response=(ai_response or "")[:500000],
            source=(source or "web_chat")[:40],
            session_key=(session_key or "")[:80],
            raw_context=tekora_json_safe(raw_context or {}),
            success=success,
            error_message=(error_message or "")[:8000] if error_message else None,
        )
        return chat_log
    except Exception:
        logger.exception("[TEKORA MEMORY] TekoraChatLog yazılamadı")
        return None


def log_tekora_decision(
    *,
    user: Any | None,
    decision_type: str,
    title: str,
    description: str = "",
    related_approval: Any | None = None,
    payload: dict[str, Any] | None = None,
    status: str = "recorded",
) -> None:
    try:
        from .models import TekoraDecisionLog

        TekoraDecisionLog.objects.create(
            user=user if getattr(user, "pk", None) else None,
            decision_type=(decision_type or "unknown")[:80],
            title=(title or "")[:255],
            description=(description or "")[:10000],
            related_approval=related_approval,
            payload=tekora_json_safe(payload or {}),
            status=(status or "recorded")[:40],
        )
    except Exception:
        logger.exception("[TEKORA MEMORY] TekoraDecisionLog yazılamadı: %s", decision_type)


def build_chat_raw_context_for_storage(
    erp_payload: dict[str, Any] | None,
    tool_result: dict[str, Any] | None,
    critical_analysis_result: dict[str, Any] | None,
    bulk_approval_result: dict[str, Any] | None,
    approval_action_result: dict[str, Any] | None,
    proactive_alerts: dict[str, Any] | None = None,
    production_intelligence_result: dict[str, Any] | None = None,
    tool_intelligence_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sohbet logu için bağlam; çok büyük listeler kısaltılır."""

    def _trim_tool_result(tr: dict[str, Any]) -> dict[str, Any]:
        out = dict(tr)
        rs = out.get("results")
        if isinstance(rs, list) and len(rs) > 25:
            out = {**out, "results": rs[:25], "_results_truncated": len(rs) - 25}
        return out

    def _trim_critical(cr: dict[str, Any]) -> dict[str, Any]:
        out = dict(cr)
        rs = out.get("results")
        if isinstance(rs, list) and len(rs) > 50:
            out = {**out, "results": rs[:50], "_results_truncated": len(rs) - 50}
        return out

    ctx: dict[str, Any] = {"erp": tekora_json_safe(erp_payload or {})}
    if tool_result:
        ctx["tool_result"] = tekora_json_safe(_trim_tool_result(tool_result))
    if critical_analysis_result:
        ctx["critical_analysis"] = tekora_json_safe(_trim_critical(critical_analysis_result))
    if bulk_approval_result:
        ctx["bulk_approval"] = tekora_json_safe(bulk_approval_result)
    if approval_action_result:
        ctx["approval_action"] = tekora_json_safe(approval_action_result)
    if proactive_alerts:
        ctx["proactive_alerts"] = tekora_json_safe(proactive_alerts)
    if production_intelligence_result:
        ctx["production_intelligence"] = tekora_json_safe(production_intelligence_result)
    if tool_intelligence_result:
        ctx["tool_intelligence"] = tekora_json_safe(tool_intelligence_result)
    return ctx


def log_proactive_alert_side_effects(alert: Any) -> None:
    """Yeni TekoraAlert için TekoraDecisionLog + TekoraMemory (başarısızlıkta sessiz)."""
    try:
        from .models import TekoraMemory

        pk = getattr(alert, "pk", None)
        sev = getattr(alert, "severity", "") or ""
        imp = {"critical": 10, "high": 7, "medium": 4, "low": 2}.get(str(sev), 3)

        log_tekora_decision(
            user=None,
            decision_type="proactive_alert",
            title=str(getattr(alert, "title", "") or "")[:255],
            description=str(getattr(alert, "message", "") or "")[:10000],
            related_approval=None,
            payload=tekora_json_safe(
                {
                    "alert_id": pk,
                    "alert_type": getattr(alert, "alert_type", None),
                    "severity": sev,
                    "source": getattr(alert, "source", None),
                }
            ),
            status="recorded",
        )

        TekoraMemory.objects.create(
            memory_type="proactive_alert",
            title=str(getattr(alert, "title", "") or "")[:255],
            content=str(getattr(alert, "message", "") or "")[:50000],
            source=str(getattr(alert, "source", "") or "tekora_alert_engine")[:80],
            importance=int(imp),
            is_active=True,
            metadata=tekora_json_safe(
                {
                    "alert_id": pk,
                    "alert_type": getattr(alert, "alert_type", None),
                    "severity": sev,
                    "payload": getattr(alert, "payload", None) or {},
                }
            ),
        )
    except Exception:
        logger.exception("[TEKORA MEMORY] proactive alert yan etkileri yazılamadı")


def log_critical_stock_recommendation_decision(
    user: Any | None, critical_result: dict[str, Any] | None
) -> None:
    """Kritik stok analizi başarılı ve en az bir kalem varsa karar logu."""
    if not isinstance(critical_result, dict) or critical_result.get("status") != "ok":
        return
    try:
        n = int(critical_result.get("critical_count") or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return
    log_tekora_decision(
        user=user,
        decision_type="critical_stock_recommendation",
        title="Kritik stok analiz özeti",
        description=f"TEKORA analizi: {n} kritik kalem.",
        payload={"critical_count": n},
        status="recorded",
    )


def resolve_tekora_user(username: str | None) -> Any | None:
    if not username or not isinstance(username, str) or not username.strip():
        return None
    try:
        from django.contrib.auth.models import User

        return User.objects.filter(username=username.strip()[:150]).first()
    except Exception:
        logger.exception("[TEKORA MEMORY] kullanıcı çözümü başarısız")
        return None
