"""
Merkezi stok zekâsı — TEKORA `analyze_critical_stock` tool ve alert engine aynı listeyi kullanır.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db.models import F, Q

logger = logging.getLogger(__name__)

_MAX_CRITICAL_ITEMS = 500


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _critical_threshold(minimum_stok: float, guvenlik_stoku: float) -> float:
    return max(minimum_stok, guvenlik_stoku)


def _suggested_quantity(critical_level: float, current: float) -> int:
    raw = critical_level * 3.0 - current
    return int(max(0, round(raw)))


def _severity(current: float, threshold: float) -> str:
    if threshold <= 0:
        if current <= 0:
            return "high"
        return "low"
    ratio = current / threshold if threshold else 0.0
    if current <= 0 or ratio < 0.25:
        return "high"
    if ratio < 0.6:
        return "medium"
    return "low"


def analyze_critical_stock_items() -> list[dict[str, Any]]:
    """
    Kritik stok kalemleri (stok_takip=True, arsivli=False).
    Kural: mevcut_miktar <= minimum_stok veya (guvenlik_stoku>0 ve mevcut <= guvenlik_stoku).
    Dönüş: analyze_critical_stock tool ile aynı yapıdaki `results` satırları.
    """
    from .models import StokItem

    qs = (
        StokItem.objects.filter(stok_takip=True, arsivli=False)
        .filter(
            Q(mevcut_miktar__lte=F("minimum_stok"))
            | (Q(guvenlik_stoku__gt=0) & Q(mevcut_miktar__lte=F("guvenlik_stoku")))
        )
        .order_by("mevcut_miktar", "stok_kodu")[:_MAX_CRITICAL_ITEMS]
    )

    results: list[dict[str, Any]] = []
    for row in qs:
        cur = _to_float(row.mevcut_miktar)
        mn = _to_float(row.minimum_stok)
        gs = _to_float(row.guvenlik_stoku)
        crit_level = _critical_threshold(mn, gs)
        sug = _suggested_quantity(crit_level, cur)
        sev = _severity(cur, crit_level if crit_level > 0 else mn)
        results.append(
            {
                "product_id": row.pk,
                "code": row.stok_kodu,
                "name": row.ad,
                "current_stock": cur,
                "critical_level": round(crit_level, 3),
                "suggested_purchase_quantity": sug,
                "severity": sev,
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: (order.get(r.get("severity"), 3), r["current_stock"]))
    return results
