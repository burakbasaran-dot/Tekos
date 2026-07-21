"""TEKORA kritik stok analizi — merkezi liste: tekora_stock_intelligence.analyze_critical_stock_items."""

from __future__ import annotations

import logging
from typing import Any

from .tekora_stock_intelligence import analyze_critical_stock_items

# Tool dışı kullanım için merkezi API (alert engine ile aynı liste)
__all__ = ["analyze_critical_stock_items", "build_critical_stock_analysis_payload"]

logger = logging.getLogger(__name__)


def build_critical_stock_analysis_payload() -> dict[str, Any]:
    """
    Kritik stok kalemlerini listeler (stok_takip=True, arsivli=False).
    Kaynak: analyze_critical_stock_items() ile alert engine ve tool birebir aynı veriyi kullanır.
    """
    try:
        results = analyze_critical_stock_items()
        count = len(results)
        logger.info(
            "[TEKORA TOOL]\nTool: analyze_critical_stock\nCritical count: %s",
            count,
        )
        return {
            "status": "ok",
            "critical_count": count,
            "results": results,
        }
    except Exception:
        logger.exception("[TEKORA TOOL] analyze_critical_stock başarısız")
        return {
            "status": "error",
            "error": "Kritik stok analizi sırasında hata oluştu.",
            "critical_count": 0,
            "results": [],
        }
