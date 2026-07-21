"""
TEKORA proaktif uyarı motoru — ERP verisini tarar, TekoraAlert üretir.
Duplicate / kısa süreli tekrar için ORM kontrolleri; hatalar ana akışı düşürmez.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db.models import F, Q
from django.utils import timezone

from stokapp.tekora_stock_intelligence import analyze_critical_stock_items

from .tekora_memory_log import log_proactive_alert_side_effects, tekora_json_safe

logger = logging.getLogger(__name__)

DEDUPE_HOURS_PENDING_APPROVAL = 24
DEDUPE_HOURS_PRODUCTION = 24
DEDUPE_HOURS_SEVERITY_BATCH = 6

STALE_APPROVAL_DAYS = 3


def _map_analysis_severity_to_alert_severity(analysis_sev: str, current: float) -> str:
    from .models import TekoraAlert

    s = (analysis_sev or "medium").lower()
    if current <= 0:
        return TekoraAlert.SEVERITY_CRITICAL
    if s == "high":
        return TekoraAlert.SEVERITY_HIGH
    if s == "medium":
        return TekoraAlert.SEVERITY_MEDIUM
    return TekoraAlert.SEVERITY_LOW


def _recent_alert_exists(
    *,
    alert_type: str,
    related_object_type: str,
    related_object_id: str,
    hours: int,
) -> bool:
    try:
        from .models import TekoraAlert

        if not related_object_id:
            return False
        cutoff = timezone.now() - timedelta(hours=hours)
        return TekoraAlert.objects.filter(
            alert_type=alert_type,
            related_object_type=related_object_type,
            related_object_id=related_object_id[:64],
            is_resolved=False,
            created_at__gte=cutoff,
        ).exists()
    except Exception:
        logger.exception("[TEKORA ALERT] duplicate kontrolü başarısız (yeni tablo yoksa migrate gerekir)")
        return False


def _persist_alert(
    *,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    payload: dict[str, Any],
    source: str,
    related_object_type: str,
    related_object_id: str,
) -> bool:
    """True if yeni kayıt oluşturuldu."""
    try:
        from .models import TekoraAlert

        alert = TekoraAlert.objects.create(
            alert_type=alert_type[:80],
            severity=severity,
            title=title[:255],
            message=message[:20000],
            payload=tekora_json_safe(payload or {}),
            source=(source or "tekora_alert_engine")[:80],
            related_object_type=(related_object_type or "")[:120],
            related_object_id=(related_object_id or "")[:64],
        )
        log_proactive_alert_side_effects(alert)
        return True
    except Exception:
        logger.exception("[TEKORA ALERT] kayıt oluşturulamadı: %s", alert_type)
        return False


def _analyze_critical_stock_alerts() -> dict[str, int]:
    """
    analyze_critical_stock_items() listesindeki her kalem için TekoraAlert.
    Açık (is_resolved=False) kayıt varsa atlanır; aksi halde create.
    Dönüş: created, skipped, errors, items_found
    """
    from .models import TekoraAlert

    stats = {"created": 0, "skipped": 0, "errors": 0, "items_found": 0}
    try:
        critical_items = analyze_critical_stock_items()
    except Exception:
        logger.exception("[TEKORA ALERT] analyze_critical_stock_items başarısız")
        return stats

    stats["items_found"] = len(critical_items)

    title = "Kritik Stok Riski"
    rel_type = "stok_item"

    for item in critical_items:
        pid = item.get("product_id")
        if pid is None:
            print(
                f"[DEBUG] product_id=None skip item={item!r}",
                flush=True,
            )
            continue
        rel_id = str(pid)[:64]

        existing = TekoraAlert.objects.filter(
            alert_type="critical_stock",
            related_object_type=rel_type,
            related_object_id=rel_id[:64],
            is_resolved=False,
        ).first()

        print(
            f"[DEBUG] product_id={rel_id} existing_open={existing is not None} "
            f"existing_alert_id={getattr(existing, 'pk', None)}",
            flush=True,
        )

        if existing:
            stats["skipped"] += 1
            print(
                f"[DEBUG] product_id={rel_id} -> skipped (open alert exists)",
                flush=True,
            )
            continue

        name = (str(item.get("name") or "").strip()) or (str(item.get("code") or "").strip()) or "Ürün"
        cur = item.get("current_stock")
        crit_level = item.get("critical_level")
        sug = item.get("suggested_purchase_quantity")
        analysis_sev = str(item.get("severity") or "medium").lower()
        try:
            cur_f = float(cur or 0)
        except (TypeError, ValueError):
            cur_f = 0.0
        sev = _map_analysis_severity_to_alert_severity(analysis_sev, cur_f)

        message = (
            f"{name} kritik stok seviyesinde. "
            f"Mevcut: {cur}, Kritik: {crit_level}, Önerilen Satınalma: {sug}"
        )

        try:
            alert = TekoraAlert.objects.create(
                alert_type="critical_stock",
                related_object_type=rel_type,
                related_object_id=rel_id[:64],
                is_resolved=False,
                severity=sev,
                title=title,
                message=message[:20000],
                payload=tekora_json_safe(dict(item)),
                source="tekora_analyze",
                is_read=False,
            )
        except Exception as e:
            print("[ERROR] Alert create failed:", item, str(e), flush=True)
            logger.exception(
                "[TEKORA ALERT] critical_stock create hatası (product_id=%s)",
                rel_id,
            )
            stats["errors"] += 1
            print(
                f"[DEBUG] product_id={rel_id} -> error (create failed)",
                flush=True,
            )
            continue

        try:
            log_proactive_alert_side_effects(alert)
        except Exception as mem_exc:
            logger.exception("[TEKORA ALERT] proactive memory log hatası (alert id=%s)", alert.pk)
            print(
                f"[DEBUG] product_id={rel_id} created_alert_id={alert.pk} "
                f"memory_log_error={mem_exc!r}",
                flush=True,
            )
        else:
            print(
                f"[DEBUG] product_id={rel_id} created_alert_id={alert.pk} created=True",
                flush=True,
            )

        stats["created"] += 1

    return stats


def _analyze_pending_approval_alerts() -> int:
    from .models import ApprovalRequest

    created = 0
    try:
        cutoff = timezone.now() - timedelta(days=STALE_APPROVAL_DAYS)
        qs = ApprovalRequest.objects.filter(
            status=ApprovalRequest.STATUS_PENDING,
            created_at__lt=cutoff,
        ).order_by("created_at")[:200]
        for ar in qs:
            rel_id = str(ar.pk)
            rel_type = "approval_request"
            if _recent_alert_exists(
                alert_type="pending_approval_stale",
                related_object_type=rel_type,
                related_object_id=rel_id,
                hours=DEDUPE_HOURS_PENDING_APPROVAL,
            ):
                continue
            title = "Uzun Süre Bekleyen Onay"
            message = (
                f"Onay kaydı '{ar.title[:120]}' {STALE_APPROVAL_DAYS} günden uzun süredir bekliyor. "
                f"İşlem tipi: {ar.action_type}."
            )
            payload = {
                "approval_id": str(ar.pk),
                "action_type": ar.action_type,
                "created_at": ar.created_at.isoformat() if ar.created_at else None,
            }
            if _persist_alert(
                alert_type="pending_approval_stale",
                severity="high",
                title=title,
                message=message,
                payload=payload,
                source="tekora_alert_engine",
                related_object_type=rel_type,
                related_object_id=rel_id,
            ):
                created += 1
    except Exception:
        logger.exception("[TEKORA ALERT] bekleyen onay taraması başarısız")
    return created


def _count_today_production() -> int:
    try:
        from .models import UretimEmri

        today = timezone.localdate()
        return int(
            UretimEmri.objects.filter(
                Q(created_at__date=today)
                | Q(planlanan_baslama__date=today)
                | Q(gerceklesen_baslama__date=today)
            )
            .distinct()
            .count()
        )
    except Exception:
        logger.exception("[TEKORA ALERT] üretim sayımı başarısız")
        return -1


def _analyze_low_production_alerts() -> int:
    created = 0
    n = _count_today_production()
    if n < 0:
        return 0
    if n > 0:
        return 0
    rel_type = "system"
    rel_id = "low_production_daily"
    if _recent_alert_exists(
        alert_type="low_production_activity",
        related_object_type=rel_type,
        related_object_id=rel_id,
        hours=DEDUPE_HOURS_PRODUCTION,
    ):
        return 0
    title = "Düşük Üretim Aktivitesi"
    message = (
        "Bugün için kayıtlı üretim emri aktivitesi bulunamadı veya sayım sıfır. "
        "Operasyon takvimini kontrol edin."
    )
    if _persist_alert(
        alert_type="low_production_activity",
        severity="medium",
        title=title,
        message=message,
        payload={"today_production_count": n},
        source="tekora_alert_engine",
        related_object_type=rel_type,
        related_object_id=rel_id,
    ):
        created += 1
    return created


def _analyze_critical_severity_batch() -> int:
    """Ortak kritik liste üzerinden 'yüksek önem' kalemleri için özet uyarı."""
    created = 0
    try:
        items = analyze_critical_stock_items()
        high_items: list[dict[str, Any]] = []
        for row in items:
            if str(row.get("severity") or "").lower() != "high":
                continue
            high_items.append(
                {
                    "product_id": row.get("product_id"),
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "current_stock": row.get("current_stock"),
                }
            )
        if not high_items:
            return 0
        rel_type = "system"
        rel_id = "critical_high_severity_batch"
        if _recent_alert_exists(
            alert_type="critical_severity_product",
            related_object_type=rel_type,
            related_object_id=rel_id,
            hours=DEDUPE_HOURS_SEVERITY_BATCH,
        ):
            return 0
        title = "Kritik Önemde Stok Kalemleri"
        message = f"{len(high_items)} ürün yüksek operasyonel risk (stok / seviye) sınıfında."
        payload = {
            "high_severity_count": len(high_items),
            "samples": high_items[:15],
        }
        if _persist_alert(
            alert_type="critical_severity_product",
            severity="critical",
            title=title,
            message=message,
            payload=payload,
            source="tekora_alert_engine",
            related_object_type=rel_type,
            related_object_id=rel_id,
        ):
            created += 1
    except Exception:
        logger.exception("[TEKORA ALERT] kritik önem batch başarısız")
    return created


def run_proactive_tekora_analysis() -> dict[str, int]:
    """Tüm analizleri çalıştırır; oluşturulan yeni uyarı sayılarını döndürür."""
    out: dict[str, int] = {
        "critical_stock_alerts": 0,
        "critical_stock_skipped": 0,
        "critical_stock_errors": 0,
        "critical_items_found": 0,
        "pending_approval_alerts": 0,
        "production_alerts": 0,
        "critical_severity_alerts": 0,
        "total_created": 0,
    }
    try:
        crit = _analyze_critical_stock_alerts()
        out["critical_stock_alerts"] = int(crit.get("created", 0))
        out["critical_stock_skipped"] = int(crit.get("skipped", 0))
        out["critical_stock_errors"] = int(crit.get("errors", 0))
        out["critical_items_found"] = int(crit.get("items_found", 0))
        out["pending_approval_alerts"] = _analyze_pending_approval_alerts()
        out["production_alerts"] = _analyze_low_production_alerts()
        out["critical_severity_alerts"] = _analyze_critical_severity_batch()
        out["total_created"] = sum(
            [
                out["critical_stock_alerts"],
                out["pending_approval_alerts"],
                out["production_alerts"],
                out["critical_severity_alerts"],
            ]
        )
    except Exception:
        logger.exception("[TEKORA ALERT] run_proactive_tekora_analysis genel hata")
    return out


def get_proactive_alerts_snapshot_for_chat(limit: int = 40) -> dict[str, Any]:
    """Sohbet bağlamı için çözülmemiş uyarıların özeti."""
    try:
        from .models import TekoraAlert

        qs = (
            TekoraAlert.objects.filter(is_resolved=False)
            .order_by("-created_at")[: max(1, min(limit, 100))]
        )
        rows = list(qs)
        sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

        def _key(a):
            return (-sev_rank.get(a.severity, 0), a.created_at or timezone.now())

        rows.sort(key=_key, reverse=True)
        alerts = []
        for a in rows:
            alerts.append(
                {
                    "id": a.pk,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "title": a.title,
                    "message": a.message,
                    "is_read": a.is_read,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "payload": tekora_json_safe(a.payload or {}),
                }
            )
        return {
            "status": "ok",
            "unresolved_count": len(alerts),
            "alerts": alerts,
        }
    except Exception:
        logger.exception("[TEKORA ALERT] snapshot okunamadı")
        return {"status": "error", "unresolved_count": 0, "alerts": [], "error": "snapshot_failed"}
