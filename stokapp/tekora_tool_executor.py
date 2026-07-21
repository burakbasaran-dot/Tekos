"""TEKORA tool yürütme — salt okunur ve onay gerektiren araçlar ayrı kanallarda."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable

from django.db.models import Q

from .tekora_approval_tools import create_bulk_purchase_approval, create_purchase_request
from .tekora_matching import (
    build_stock_candidate_q,
    calculate_match_score,
    normalize_text,
    tokenize_query,
)
from .tekora_critical_stock import build_critical_stock_analysis_payload
from .tekora_tools import (
    TOOL_ANALYZE_CRITICAL_STOCK,
    TOOL_ANALYZE_PRODUCTION_INTELLIGENCE,
    TOOL_ANALYZE_TOOL_INTELLIGENCE,
    TOOL_CREATE_BULK_PURCHASE_APPROVAL,
    TOOL_SEMANTIC_SEARCH,
    TOOLS,
)

logger = logging.getLogger(__name__)

_MAX_QUERY_LEN = 500
_MAX_RESULTS = 10
_CANDIDATE_LIMIT = 280
_MIN_BEST_MATCH_SCORE = 18
_MATCH_UNCERTAIN_BELOW = 30


def _row_to_result_dict(row: Any, match_score: int) -> dict[str, Any]:
    stock_val = row.mevcut_miktar
    if isinstance(stock_val, Decimal):
        stock_num = float(stock_val)
    else:
        stock_num = float(stock_val or 0)
    return {
        "id": row.pk,
        "code": row.stok_kodu,
        "name": row.ad,
        "stock": stock_num,
        "match_score": int(match_score),
    }


def _run_search_stock_item(payload: dict[str, Any]) -> dict[str, Any]:
    """Akıllı eşleştirme ile stok kartı araması (salt okunur ORM)."""
    raw = payload.get("query")
    if not isinstance(raw, str) or not raw.strip():
        return {
            "status": "error",
            "error": "query alanı zorunludur.",
            "query": "",
            "best_match": None,
            "results": [],
            "match_uncertain": True,
        }
    q = raw.strip()[:_MAX_QUERY_LEN]

    try:
        from .models import StokItem

        nq = normalize_text(q)
        tokens = tokenize_query(q)
        q_filter = build_stock_candidate_q(tokens, q)

        candidates = list(
            StokItem.objects.filter(q_filter)
            .filter(arsivli=False)
            .distinct()[:_CANDIDATE_LIMIT]
        )

        if not candidates and len(q) >= 2:
            candidates = list(
                StokItem.objects.filter(arsivli=False)
                .filter(
                    Q(stok_kodu__icontains=q[:40]) | Q(ad__icontains=q[:40])
                )[:120]
            )

        scored: list[tuple[int, Any]] = []
        for row in candidates:
            item = {
                "stok_kodu": row.stok_kodu or "",
                "ad": row.ad or "",
                "aciklama": row.aciklama or "",
            }
            sc = calculate_match_score(item, tokens, nq)
            scored.append((sc, row))

        scored.sort(key=lambda x: -x[0])
        top_rows = scored[:_MAX_RESULTS]
        results = [_row_to_result_dict(row, sc) for sc, row in top_rows]

        best_match: dict[str, Any] | None = None
        if results and results[0].get("match_score", 0) >= _MIN_BEST_MATCH_SCORE:
            best_match = dict(results[0])

        top_score = results[0]["match_score"] if results else 0
        match_uncertain = (not results) or (top_score < _MATCH_UNCERTAIN_BELOW)

        logger.info(
            "[TEKORA TOOL]\nTool: search_stock_item\nQuery: %s\nResult count: %s\nTop score: %s",
            q,
            len(results),
            top_score,
        )

        return {
            "status": "ok",
            "query": q,
            "best_match": best_match,
            "results": results,
            "match_uncertain": match_uncertain,
        }
    except Exception:
        logger.exception("[TEKORA TOOL] search_stock_item başarısız (query=%r)", q)
        return {
            "status": "error",
            "error": "Stok araması sırasında hata oluştu.",
            "query": q,
            "best_match": None,
            "results": [],
            "match_uncertain": True,
        }


def _run_analyze_critical_stock(_payload: dict[str, Any]) -> dict[str, Any]:
    """Kritik stok listesi ve satınalma öneri miktarları (salt okunur)."""
    return build_critical_stock_analysis_payload()


def _run_analyze_tool_intelligence(_payload: dict[str, Any]) -> dict[str, Any]:
    """Takım / CNC istihbaratı."""
    raw = _payload.get("analysis") or _payload.get("kind") or "lifetimes"
    analysis = str(raw).strip().lower()
    mat = _payload.get("material_hint")
    material_hint = str(mat).strip() if isinstance(mat, str) and mat.strip() else None
    days_raw = _payload.get("days", 90)
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 90
    days = max(7, min(days, 180))
    try:
        from .tekora_tool_intelligence import run_tool_intelligence_analysis

        return run_tool_intelligence_analysis(
            analysis,
            material_hint=material_hint,
            days=days,
        )
    except Exception as exc:
        logger.exception("[TEKORA TOOL] analyze_tool_intelligence başarısız")
        return {
            "status": "error",
            "error": str(exc)[:500],
            "items": [],
        }


def _run_analyze_production_intelligence(_payload: dict[str, Any]) -> dict[str, Any]:
    """Üretim istihbaratı — gecikme, istasyon, performans, riskli sipariş."""
    raw = _payload.get("analysis") or _payload.get("kind") or "delayed"
    analysis = str(raw).strip().lower()
    if analysis in ("darboğaz", "dar bogaz"):
        analysis = "darbogaz"
    days_raw = _payload.get("days", 30)
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 90))
    try:
        from .tekora_production_intelligence import run_production_intelligence_analysis

        return run_production_intelligence_analysis(analysis, days=days)
    except Exception as exc:
        logger.exception("[TEKORA TOOL] analyze_production_intelligence başarısız")
        return {
            "status": "error",
            "error": str(exc)[:500],
            "items": [],
        }


def _run_semantic_search(_payload: dict[str, Any], *, user_id: int | None = None) -> dict[str, Any]:
    """
    Semantic search: TekoraMemoryEmbedding içinde cosine benzerliğe göre sonuçlar döner.

    Tool executor payload'u dışında user_id filtreleme için ayrı parametre alır.
    """
    query = _payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return {
            "status": "error",
            "error": "query alanı zorunludur.",
            "query": "",
            "results": [],
        }

    try:
        limit_raw = _payload.get("limit", 5)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        from .tekora_embeddings import semantic_search

        results = semantic_search(query.strip()[:5000], limit=limit, user_id=user_id)
        return {
            "status": "ok",
            "query": query.strip()[:5000],
            "results": results,
        }
    except Exception as exc:
        logger.exception("[TEKORA TOOL] semantic_search başarısız")
        return {
            "status": "error",
            "error": f"semantic_search başarısız: {exc}",
            "query": query.strip()[:5000],
            "results": [],
        }


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "search_stock_item": _run_search_stock_item,
    TOOL_ANALYZE_CRITICAL_STOCK: _run_analyze_critical_stock,
    TOOL_ANALYZE_TOOL_INTELLIGENCE: _run_analyze_tool_intelligence,
    TOOL_ANALYZE_PRODUCTION_INTELLIGENCE: _run_analyze_production_intelligence,
    TOOL_SEMANTIC_SEARCH: lambda payload: _run_semantic_search(
        payload, user_id=payload.get("user_id")
    ),
}

_APPROVAL_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "create_purchase_request": create_purchase_request,
    TOOL_CREATE_BULK_PURCHASE_APPROVAL: create_bulk_purchase_approval,
}


def _unknown_tool_response() -> dict[str, Any]:
    return {
        "status": "error",
        "error": "bilinmeyen_tool",
        "results": [],
    }


def _missing_handler_response() -> dict[str, Any]:
    return {
        "status": "error",
        "error": "handler_tanımsız",
        "results": [],
    }


def execute_tool(
    tool_name: str,
    payload: dict[str, Any],
    user: Any | None = None,
) -> dict[str, Any]:
    """
    Kayıtlı tool'u çalıştırır.
    approval_required=True olanlar yalnızca onay (ApprovalRequest) üretir; doğrudan işlem yapmaz.
    """
    from .tekora_memory_log import log_tekora_tool

    def _emit_log(
        out: dict[str, Any],
        *,
        dangerous: bool,
        approval_required: bool,
    ) -> dict[str, Any]:
        try:
            succ = isinstance(out, dict) and out.get("status") == "ok"
            em: str | None = None
            if not succ and isinstance(out, dict):
                em = out.get("error")
                if em is not None:
                    em = str(em)[:8000]
            log_tekora_tool(
                user=user,
                tool_name=tool_name,
                payload=payload,
                result=out,
                dangerous=dangerous,
                approval_required=approval_required,
                success=succ,
                error_message=em,
            )
        except Exception:
            logger.exception("[TEKORA MEMORY] tool log emit failed for %s", tool_name)
        return out

    if tool_name not in TOOLS:
        logger.warning(
            "[TEKORA TOOL]\nTool: %s\nRejected: not in registry",
            tool_name,
        )
        return _emit_log(_unknown_tool_response(), dangerous=False, approval_required=False)

    meta = TOOLS[tool_name]
    approval_required = bool(meta.get("approval_required"))
    dangerous = bool(meta.get("dangerous"))

    if approval_required:
        if not dangerous:
            logger.error(
                "[TEKORA TOOL] approval_required ancak dangerous değil: %s",
                tool_name,
            )
        handler = _APPROVAL_TOOL_HANDLERS.get(tool_name)
        if handler is None:
            logger.error(
                "[TEKORA TOOL]\nTool: %s\nRejected: no approval handler",
                tool_name,
            )
            return _emit_log(
                _missing_handler_response(),
                dangerous=dangerous,
                approval_required=approval_required,
            )
        try:
            out = handler(payload)
            return _emit_log(out, dangerous=dangerous, approval_required=approval_required)
        except Exception:
            logger.exception("[TEKORA TOOL] approval tool hatası: %s", tool_name)
            out = {
                "status": "error",
                "error": "tool_yürütme_hatası",
                "approval_tool": tool_name,
            }
            return _emit_log(out, dangerous=dangerous, approval_required=approval_required)

    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        logger.error(
            "[TEKORA TOOL]\nTool: %s\nRejected: no handler registered",
            tool_name,
        )
        return _emit_log(
            _missing_handler_response(),
            dangerous=dangerous,
            approval_required=approval_required,
        )

    try:
        out = handler(payload)
        return _emit_log(out, dangerous=dangerous, approval_required=approval_required)
    except Exception:
        logger.exception("[TEKORA TOOL] execute_tool beklenmeyen hata: %s", tool_name)
        out = {
            "status": "error",
            "error": "tool_yürütme_hatası",
            "results": [],
        }
        return _emit_log(out, dangerous=dangerous, approval_required=approval_required)
