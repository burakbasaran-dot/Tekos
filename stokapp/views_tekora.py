"""TEKORA API — harici entegrasyon ve şirket içi AI sohbet."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .tekora_alert_engine import get_proactive_alerts_snapshot_for_chat
from .tekora_approval_tools import extract_purchase_payload_from_message
from .tekora_memory_log import (
    build_chat_raw_context_for_storage,
    log_critical_stock_recommendation_decision,
    log_tekora_chat,
)
from .tekora_tool_executor import execute_tool
from .tekora_tools import (
    BULK_PURCHASE_FROM_CRITICAL_KEYWORDS,
    CRITICAL_STOCK_ANALYSIS_KEYWORDS,
    PROACTIVE_RISK_QUERY_KEYWORDS,
    PURCHASE_APPROVAL_CONFIRM_KEYWORDS,
    PURCHASE_APPROVAL_INTENT_KEYWORDS,
    SEMANTIC_SEARCH_TRIGGER_KEYWORDS,
    STOCK_SEARCH_TRIGGER_KEYWORDS,
    TOOL_ANALYZE_CRITICAL_STOCK,
    TOOL_ANALYZE_PRODUCTION_INTELLIGENCE,
    TOOL_ANALYZE_TOOL_INTELLIGENCE,
    TOOL_CREATE_BULK_PURCHASE_APPROVAL,
    TOOL_CREATE_PURCHASE_REQUEST,
    TOOL_SEMANTIC_SEARCH,
    match_production_intel_kind,
    match_tool_intel_kind,
)

logger = logging.getLogger(__name__)

# TEKORA sohbet oturum bağlamı (stok arama → satınalma onayı devamlılığı)
SESSION_LAST_STOCK_QUERY = "tekora_last_stock_query"
SESSION_LAST_STOCK_RESULT = "tekora_last_stock_result"
SESSION_LAST_SELECTED_PRODUCT = "tekora_last_selected_product"

TEKORA_PURCHASE_REASON_DEFAULT = (
    "Kullanıcı TEKORA üzerinden satınalma önerisi oluşturulmasını onayladı."
)

TEKORA_REPLY_NEED_PRODUCT = (
    "Satınalma önerisi oluşturabilmem için önce hangi ürün olduğunu netleştirmem gerekiyor."
)

TEKORA_API_VERSION = "1.0"


def _tekora_chat_memory_log(
    request,
    *,
    message: str,
    erp_payload: dict[str, Any] | None,
    tool_result: dict[str, Any] | None,
    critical_analysis_result: dict[str, Any] | None,
    bulk_approval_result: dict[str, Any] | None,
    approval_action_result: dict[str, Any] | None,
    ai_response: str,
    success: bool,
    error_message: str | None = None,
    proactive_alerts_snapshot: dict[str, Any] | None = None,
    production_intelligence_result: dict[str, Any] | None = None,
    tool_intelligence_result: dict[str, Any] | None = None,
) -> None:
    """Sohbet hafızası; hata olsa bile ana akışı etkilemez."""
    try:
        chat_log = log_tekora_chat(
            user=request.user,
            user_message=message,
            ai_response=ai_response,
            source="web_chat",
            session_key=getattr(request.session, "session_key", "") or "",
            raw_context=build_chat_raw_context_for_storage(
                erp_payload,
                tool_result,
                critical_analysis_result,
                bulk_approval_result,
                approval_action_result,
                proactive_alerts_snapshot,
                production_intelligence_result,
                tool_intelligence_result,
            ),
            success=success,
            error_message=error_message,
        )
        # Semantic memory embedding: hata olsa bile sohbet akışını bozma.
        if chat_log is not None and success and (ai_response or "").strip():
            try:
                from .tekora_embeddings import create_memory_embedding_for_chat

                create_memory_embedding_for_chat(chat_log)
            except Exception:
                logger.exception("TEKORA embedding: chat_log embedding failed (chat_log_id=%s)", getattr(chat_log, "pk", None))
    except Exception:
        logger.exception("TEKORA memory: chat log skipped")


_TEKORA_JSON = {
    "json_dumps_params": {"ensure_ascii": False},
    "content_type": "application/json; charset=utf-8",
}


def _tekora_json_response(payload: dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(payload, status=status, **_TEKORA_JSON)


def _tekora_semantic_search_remote_allowed(request) -> bool:
    """Yalnızca yerel makineden gelen istekler (curl / internal)."""
    addr = (request.META.get("REMOTE_ADDR") or "").strip()
    if addr in ("127.0.0.1", "::1", "localhost"):
        return True
    if addr.startswith("127."):
        return True
    if addr.startswith("::ffff:127."):
        return True
    return False


TEKORA_CHAT_SYSTEM_PROMPT = """Sen TEKORA isimli şirket içi ERP yapay zekasısın.
Kullanıcılara üretim, stok, satınalma ve operasyon süreçlerinde yardımcı olursun.
Yanıtların:
- kısa
- net
- profesyonel
- operasyon odaklı olsun.

Güvenlik: Sohbet üzerinden doğrudan satınalma kaydı veya sipariş oluşturamazsın.
Kritik veya düşük stok durumunda kullanıcı isterse satınalma önerisinin onay merkezine (ApprovalRequest) düşürülebileceğini kısaca belirtebilirsin; kullanıcı onay verirse sistem aracı bunu yapar, sen yapmazsın.
`analyze_critical_stock` çıktısı verildiğinde özet numaralı liste şeklinde olmalı; aynı istekte `create_bulk_purchase_approval` sonucu da varsa toplu onay kaydı oluşturulmuş veya hata vermiş olabilir — JSON'a göre bildir.
Aksi halde toplu onay henüz oluşturulmadıysa isterseniz oluşturulabileceğini söyleyebilirsin.
Proaktif uyarı JSON'u (`proactive_alerts`) verildiyse çözülmemiş riskleri özetle; yoksa veya alerts boşsa güncel ciddi uyarı olmadığını net söyle."""


def _ollama_generate_url() -> str:
    return getattr(
        settings,
        "TEKORA_OLLAMA_GENERATE_URL",
        os.environ.get("TEKORA_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate"),
    )


def _ollama_model() -> str:
    return getattr(
        settings,
        "TEKORA_OLLAMA_MODEL",
        os.environ.get("TEKORA_OLLAMA_MODEL", "deepseek-r1:8b"),
    )


def _ollama_timeouts() -> tuple[float, float]:
    connect = float(
        os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_CONNECT", "10"),
    )
    read = float(
        os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_READ", "300"),
    )
    return connect, read


def _strip_reasoning_blocks(text: str) -> str:
    if not text:
        return text
    out = text
    for tag in ("think", "redacted_reasoning", "redacted_thinking"):
        out = re.sub(
            rf"<{tag}>.*?</{tag}>",
            "",
            out,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return out.strip()


def _should_query_proactive_risks(message: str) -> bool:
    """Örn. 'TEKORA bugün önemli risk var mı?' — TekoraAlert kayıtlarını modele ver."""
    t = (message or "").lower()
    return any(k in t for k in PROACTIVE_RISK_QUERY_KEYWORDS)


def _should_run_bulk_purchase_approval(message: str) -> bool:
    """
    Kritik stok bağlamında toplu satınalma onay kaydı oluşturma niyeti.
    Örn.: 'Kritik stoklar için satınalma önerilerini oluştur'
    """
    t = (message or "").lower()
    critical_ctx = any(
        x in t
        for x in (
            "kritik stok",
            "kritik ürün",
            "kritik urun",
            "eksik stok",
            "kritik analiz",
            "stok analiz",
        )
    )
    create_verb = any(
        x in t
        for x in (
            "oluştur",
            "olustur",
            "kaydet",
            "onaya gönder",
            "onaya gonder",
            "gönder",
        )
    )
    bulk_hint = any(k in t for k in BULK_PURCHASE_FROM_CRITICAL_KEYWORDS)
    return critical_ctx and create_verb and bulk_hint


def _critical_results_to_bulk_items(results: list[Any]) -> list[dict[str, Any]]:
    """analyze_critical_stock results -> create_bulk_purchase_approval items."""
    out: list[dict[str, Any]] = []
    if not isinstance(results, list):
        return out
    for row in results:
        if not isinstance(row, dict):
            continue
        try:
            pid_i = int(row.get("product_id"))
        except (TypeError, ValueError):
            continue
        if pid_i <= 0:
            continue
        try:
            sq_i = int(row.get("suggested_purchase_quantity"))
        except (TypeError, ValueError):
            continue
        if sq_i <= 0:
            continue
        sev = str(row.get("severity") or "medium").lower()
        if sev not in ("high", "medium", "low"):
            sev = "medium"
        out.append(
            {
                "product_id": pid_i,
                "product_code": str(row.get("code") or "").strip(),
                "product_name": str(row.get("name") or "").strip(),
                "current_stock": row.get("current_stock"),
                "critical_level": row.get("critical_level"),
                "suggested_quantity": sq_i,
                "severity": sev,
            }
        )
    return out


def _should_run_critical_stock_analysis(message: str) -> bool:
    """Toplu kritik stok analizi tetikleyicileri."""
    t = (message or "").lower()
    return any(k in t for k in CRITICAL_STOCK_ANALYSIS_KEYWORDS)


def _should_use_stock_search_tool(message: str) -> bool:
    """Stok arama tool'unun devreye girmesi için basit anahtar kelime eşleşmesi."""
    t = message.lower()
    if _should_run_critical_stock_analysis(message):
        return False
    return any(k in t for k in STOCK_SEARCH_TRIGGER_KEYWORDS)


SEMANTIC_MEMORY_INTENT_KEYWORDS_EXTRA: tuple[str, ...] = (
    "geçmişte",
    "gecmiste",
    "hafızadan",
    "hafizadan",
    "hafıza",
    "hafiza",
    "hafızada",
    "hafizada",
    "daha önce",
    "daha once",
    "ne konuşmuştuk",
    "ne konustum",
    "konuşmuştuk",
    "konustum",
    "benzer kayıt",
    "benzer kayit",
    "benzer kayıtlar",
    "benzer kayitlar",
    "önceki konuşma",
    "onceki konusma",
    "önceki konusma",
)


def _semantic_memory_intent(message: str) -> bool:
    """Geçmiş / hafıza / benzer kayıt sorgusu (kritik stok toplu onay yolunu ezmez)."""
    if _should_run_bulk_purchase_approval(message):
        return False
    t = (message or "").lower()
    if any(k in t for k in SEMANTIC_MEMORY_INTENT_KEYWORDS_EXTRA):
        return True
    return any(k in t for k in SEMANTIC_SEARCH_TRIGGER_KEYWORDS)


def _should_use_semantic_memory_search_tool(message: str) -> bool:
    """Hafıza/semantic arama (tek kaynak: _semantic_memory_intent)."""
    return _semantic_memory_intent(message)


def _is_short_purchase_continuation(message: str) -> bool:
    """Önceki stok bağlamı varken kısa onay ifadeleri."""
    t = (message or "").strip().lower()
    if not t:
        return False
    short_exact = {
        "evet",
        "tamam",
        "oluştur",
        "olustur",
        "onaylıyorum",
        "onayliyorum",
        "onayla",
        "kaydet",
    }
    if t in short_exact:
        return True
    return len(t) <= 40 and any(k in t for k in ("evet", "tamam", "oluştur", "olustur"))


def _should_run_create_purchase_request(
    message: str, body: dict[str, Any], request
) -> bool:
    """Onay kaydı oluşturma — onay bayrağı, niyet+cümle veya oturumdaki son ürün + kısa onay."""
    if _should_run_bulk_purchase_approval(message):
        return False
    if body.get("confirm_purchase_request") is True:
        return True
    t = (message or "").lower()
    has_confirm = any(k in t for k in PURCHASE_APPROVAL_CONFIRM_KEYWORDS)
    has_intent = any(k in t for k in PURCHASE_APPROVAL_INTENT_KEYWORDS)
    if has_confirm and has_intent:
        return True
    sel = request.session.get(SESSION_LAST_SELECTED_PRODUCT)
    if isinstance(sel, dict) and sel.get("product_id") and _is_short_purchase_continuation(message):
        return True
    return False


def _pick_best_stock_match(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Sonuç listesinden en yüksek match_score ile session alanlarını üretir."""
    if not results:
        return None
    best_row: dict[str, Any] | None = None
    best_ms = -1.0
    for row in results:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        try:
            ms = float(row.get("match_score") or 0)
        except (TypeError, ValueError):
            ms = 0.0
        if ms > best_ms:
            best_ms = ms
            best_row = row
    if not best_row:
        return None
    return {
        "product_id": int(best_row["id"]),
        "product_code": str(best_row.get("code") or ""),
        "product": str(best_row.get("name") or ""),
        "current_stock": best_row.get("stock"),
        "match_score": best_row.get("match_score"),
    }


def _session_save_stock_search(
    request,
    query: str,
    tool_result: dict[str, Any],
) -> None:
    """search_stock_item sonrası oturum bağlamını günceller (best_match öncelikli)."""
    request.session[SESSION_LAST_STOCK_QUERY] = query[:500]
    results = tool_result.get("results") if isinstance(tool_result.get("results"), list) else []
    request.session[SESSION_LAST_STOCK_RESULT] = results[:10]

    bm = tool_result.get("best_match")
    if isinstance(bm, dict) and bm.get("id") is not None:
        request.session[SESSION_LAST_SELECTED_PRODUCT] = {
            "product_id": int(bm["id"]),
            "product_code": str(bm.get("code") or ""),
            "product": str(bm.get("name") or ""),
            "current_stock": bm.get("stock"),
            "match_score": bm.get("match_score"),
        }
    else:
        fb = _pick_best_stock_match(query, results)
        top_ms = float(results[0].get("match_score") or 0) if results else 0.0
        if fb and top_ms >= 12:
            request.session[SESSION_LAST_SELECTED_PRODUCT] = fb
        else:
            request.session.pop(SESSION_LAST_SELECTED_PRODUCT, None)
    request.session.modified = True


def _purchase_payload_has_product(payload: dict[str, Any]) -> bool:
    p = payload.get("product")
    if isinstance(p, str) and p.strip():
        return True
    pid = payload.get("product_id")
    try:
        return pid is not None and int(pid) > 0
    except (TypeError, ValueError):
        return False


def _apply_session_to_purchase_payload(request, payload: dict[str, Any]) -> dict[str, Any]:
    """Session'daki last_selected_product ile eksik ürün alanlarını doldurur."""
    out = dict(payload)
    sel = request.session.get(SESSION_LAST_SELECTED_PRODUCT)
    if not isinstance(sel, dict):
        return out
    if not out.get("product") and sel.get("product"):
        out["product"] = sel["product"]
    if not out.get("product_code") and sel.get("product_code"):
        out["product_code"] = sel["product_code"]
    if out.get("product_id") in (None, "", 0) and sel.get("product_id") is not None:
        try:
            out["product_id"] = int(sel["product_id"])
        except (TypeError, ValueError):
            pass
    if out.get("current_stock") is None and sel.get("current_stock") is not None:
        out["current_stock"] = sel["current_stock"]
    return out


def _default_suggested_quantity(payload: dict[str, Any]) -> float | None:
    """Ürün kartından güvenli varsayılan öneri miktarı (ORM)."""
    pid = payload.get("product_id")
    try:
        pk = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pk = None
    if not pk:
        return 100.0
    try:
        from .models import StokItem

        item = StokItem.objects.only("minimum_stok", "mevcut_miktar").get(pk=pk)
        mn = float(item.minimum_stok or 0)
        cur = float(item.mevcut_miktar or 0)
        base = max(mn * 4.0, 50.0)
        sug = max(base, base - cur, mn * 2.0 if mn else 50.0)
        return float(min(sug, 1_000_000_000))
    except Exception:
        return 100.0


def _payload_suggested_quantity_positive(merged: dict[str, Any]) -> bool:
    v = merged.get("suggested_quantity")
    if v is None:
        return False
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if v is not None and v != "":
            out[k] = v
    return out


def _build_purchase_request_payload(
    body: dict[str, Any],
    message: str,
    request,
) -> dict[str, Any]:
    """approval_payload + mesaj sezgisini birleştirir; session ile tamamlanır; audit alanı ekler."""
    ap: dict[str, Any] = {}
    raw_ap = body.get("approval_payload")
    if isinstance(raw_ap, dict):
        ap = {k: v for k, v in raw_ap.items() if isinstance(k, str)}

    inferred = extract_purchase_payload_from_message(message)
    merged = _merge_dicts(inferred, ap)
    merged = _apply_session_to_purchase_payload(request, merged)

    merged.setdefault("reason", TEKORA_PURCHASE_REASON_DEFAULT)
    merged["tekora_triggered_by"] = request.user.get_username()

    if not _payload_suggested_quantity_positive(merged):
        dq = _default_suggested_quantity(merged)
        if dq is not None:
            merged["suggested_quantity"] = int(dq) if dq == int(dq) else dq

    return merged


def build_system_summary_payload() -> dict[str, Any]:
    """ERP system-summary gövdesi (tek kaynak; HTTP endpoint ile aynı veri)."""
    notes: list[str] = []
    generated_at = timezone.now().isoformat()
    summary = {
        "critical_stock_count": _count_critical_stock(notes),
        "open_order_count": _count_open_orders(notes),
        "pending_approval_count": _count_pending_approvals(notes),
        "today_production_count": _count_today_production(notes),
    }
    return {
        "status": "ok",
        "service": "TEKORA",
        "summary": summary,
        "notes": notes,
        "generated_at": generated_at,
    }


_SEMANTIC_MEMORY_MIN_SIMILARITY = 0.45


def _erp_payload_stub_semantic_memory() -> dict[str, Any]:
    """Semantic hafıza sorgusunda tam ERP özetini modeli meşgul etmemek için minimal bağlam."""
    return {
        "status": "ok",
        "service": "TEKORA",
        "semantic_memory_query": True,
        "summary": {
            "critical_stock_count": 0,
            "open_order_count": 0,
            "pending_approval_count": 0,
            "today_production_count": 0,
        },
        "notes": [
            "Semantic memory sorgusu: system-summary kasıtlı olarak kısaltıldı. "
            "Yanıtını SEMANTIC MEMORY RESULTS bölümüne dayandır; kritik stok analizi bu turda verilmemiştir."
        ],
        "generated_at": timezone.now().isoformat(),
    }


def _format_semantic_memory_prompt_block(results: list[dict[str, Any]]) -> str:
    lines = ["SEMANTIC MEMORY RESULTS:"]
    if not results:
        lines.append("(no rows at or above minimum similarity threshold)")
    else:
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. similarity: {r.get('similarity')}")
            lines.append(f"   created_at: {r.get('created_at')}")
            lines.append(f"   source_type: {r.get('source_type')}")
            txt = str(r.get("text") or "")
            if len(txt) > 2000:
                txt = txt[:2000] + "…"
            lines.append(f"   text: {txt}")
            lines.append("")
    return "\n".join(lines)


def _build_semantic_memory_for_chat(message: str, user) -> tuple[str, dict[str, Any]]:
    """semantic_search + similarity filtresi; prompt metni ve log için dict döner."""
    uid = getattr(user, "pk", None)
    try:
        from .tekora_embeddings import semantic_search

        raw = semantic_search(message[:4000], limit=40, user_id=uid)
    except Exception:
        logger.exception("TEKORA chat: semantic_search failed")
        raw = []

    filtered: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        try:
            sim = float(r.get("similarity") or 0.0)
        except (TypeError, ValueError):
            sim = 0.0
        if sim >= _SEMANTIC_MEMORY_MIN_SIMILARITY:
            filtered.append(r)
    filtered = filtered[:5]

    fmt = _format_semantic_memory_prompt_block(filtered)
    meta: dict[str, Any] = {
        "status": "ok",
        "query": message[:5000],
        "results": filtered,
        "min_similarity": _SEMANTIC_MEMORY_MIN_SIMILARITY,
    }
    return fmt, meta


def _call_ollama_chat(
    user_text: str,
    erp_json: dict[str, Any],
    tool_result: dict[str, Any] | None = None,
    semantic_memory_result: dict[str, Any] | None = None,
    semantic_memory_mode: bool = False,
    semantic_memory_formatted_block: str | None = None,
    approval_action_result: dict[str, Any] | None = None,
    critical_analysis_result: dict[str, Any] | None = None,
    bulk_approval_result: dict[str, Any] | None = None,
    proactive_alerts_snapshot: dict[str, Any] | None = None,
    production_intelligence_result: dict[str, Any] | None = None,
    tool_intelligence_result: dict[str, Any] | None = None,
) -> str:
    """Ollama generate; yanıt metnini döndürür veya istisna fırlatır."""
    payload_block = json.dumps(erp_json, ensure_ascii=False, indent=2)
    if semantic_memory_mode:
        blocks: list[str] = [
            "Kullanıcı SEMANTİK HAFIZA / geçmiş konuşma sorusu sordu.\n"
            "Aşağıdaki ERP JSON yalnızca minimal bağlamdır; yanıtını ÖNCELİKLE SEMANTIC MEMORY RESULTS bölümüne dayandır.\n"
            "Bu turda kritik stok analizi, toplu onay veya stok arama aracı çalıştırılmamıştır.\n\n"
            f"```json\n{payload_block}\n```",
        ]
    else:
        blocks = [
            "Aşağıda TEKORA ERP system-summary (JSON) verilmiştir. "
            "Bu verileri bağlam olarak kullan ve kullanıcı sorusuna yanıt ver.\n\n"
            f"```json\n{payload_block}\n```",
        ]

    summary = erp_json.get("summary") or {}
    crit = summary.get("critical_stock_count")
    try:
        crit_n = int(crit) if crit is not None else 0
    except (TypeError, ValueError):
        crit_n = 0
    if not semantic_memory_mode and crit_n > 0:
        blocks.append(
            "Not: Özet verisinde kritik stok kalemi sayısı sıfırdan büyük. "
            "Uygunsa kullanıcıya bu ürün veya stok için satınalma önerisinin "
            "onay merkezine gönderilebileceğini (doğrudan satınalma açılmayacağını) kısaca önerebilirsin; "
            "kullanıcı onay verir ve gerekli bilgileri sağlarsa sistem aracı `create_purchase_request` devreye girer."
        )

    if tool_result is not None:
        tool_block = json.dumps(tool_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda `search_stock_item` (akıllı eşleştirme) çıktısı yer almaktadır. "
            "`match_score` eşleşme gücüdür (0–100). `best_match` öncelikli üründür; yoksa veya "
            "`match_uncertain` true ise kullanıcıdan stok kodu, DIN/ölçü veya tam ürün adıyla netleştirmesini iste; "
            "tahminî eşleşmeyle kesin yanıt verme. Ürün netse `best_match` veya ilk sonuçlardaki code ve name ile "
            "kritik stok gibi soruları yanıtla.\n\n"
            f"```json\n{tool_block}\n```"
        )

    if semantic_memory_formatted_block:
        blocks.append(
            "=== SEMANTİK HAFIZA TALİMATLARI ===\n"
            "- SEMANTIC MEMORY RESULTS altında numaralı kayıt yoksa veya yalnızca '(no rows...)' yazıyorsa: "
            "kullanıcıya tam olarak şunu söyle: 'Bu konuda hafızada kayıt bulamadım.'\n"
            "- Kayıtlar varsa: önce 'Hafızada şu kayıtları buldum' de; similarity, tarih ve metinlere dayanarak kısa özet ver.\n"
            "- Bu kayıtlar similarity >= 0.45 filtresinden geçmiştir; var olan sonuçları inkâr etme, 'geçmişte yok' deme.\n"
            "- Metinleri uydurma; yalnızca verilen satırlardaki içerikleri kullan.\n\n"
            + semantic_memory_formatted_block
        )
    elif semantic_memory_result is not None:
        sm_block = json.dumps(semantic_memory_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda `semantic_search` (hafıza / benzer geçmiş konuşmalar) çıktısı yer almaktadır. "
            "Kullanıcının niyetine göre benzer konuşmalardan kısa bir özet çıkar ve ilgili noktaları belirt. "
            "JSON içindeki değerlerden (text, similarity, source_type, created_at) sapma yapma.\n\n"
            f"```json\n{sm_block}\n```"
        )

    if approval_action_result is not None:
        ap_block = json.dumps(approval_action_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda `create_purchase_request` (onay merkezi) aracının çıktısı yer almaktadır. "
            "Bu araç yalnızca ApprovalRequest oluşturur; satınalma fişi açmaz. "
            "Kullanıcıya sonucu net şekilde bildir.\n\n"
            f"```json\n{ap_block}\n```"
        )

    if critical_analysis_result is not None:
        ca_block = json.dumps(critical_analysis_result, ensure_ascii=False, indent=2)
        tail_bulk = (
            "Sonraki blokta `create_bulk_purchase_approval` sonucu var; onu da özetle (başarılıysa item_count ve onay merkezi)."
            if bulk_approval_result is not None
            else "Listenin sonunda: İsterseniz bu ürünler için toplu satınalma onay kayıtları "
            "oluşturabileceğinizi belirt (şu an bu mesajda toplu onay oluşturulmadı)."
        )
        blocks.append(
            "Aşağıda `analyze_critical_stock` (kritik stok analizi) çıktısı yer almaktadır; salt okunur. "
            "Kullanıcıya Türkçe yanıt ver:\n"
            "- Önce tek cümle: örn. 'Kritik stokta N ürün bulundu.' (N = critical_count; status error ise hatayı kısaca söyle).\n"
            "- Her ürün için numaralı madde: ürün adı (name), alt satırlarda Mevcut: current_stock, "
            "Kritik Seviye: critical_level, Önerilen Satınalma: suggested_purchase_quantity. "
            "Sayıları yalnızca JSON'daki alanlarla ver; tahmin veya uydurma yapma.\n"
            f"- {tail_bulk}\n\n"
            f"```json\n{ca_block}\n```"
        )

    if bulk_approval_result is not None:
        blk = json.dumps(bulk_approval_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda `create_bulk_purchase_approval` (toplu onay kaydı) çıktısı yer almaktadır. "
            "Doğrudan satınalma veya talep oluşturulmaz; yalnızca onay merkezi kaydı. "
            "status ok ise kullanıcıya item_count veya message ile özet ver (örn. '25 ürün için toplu satınalma approval kaydı oluşturuldu. "
            "Onay merkezinden inceleyebilirsiniz.'); hata ise error alanını kısaca ilet.\n\n"
            f"```json\n{blk}\n```"
        )

    if production_intelligence_result is not None:
        pi_block = json.dumps(production_intelligence_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda TEKORA üretim istihbaratı (`analyze_production_intelligence`) çıktısı yer almaktadır. "
            "Önce `executive_summary` ile kısa, işletme dilinde yorum yap (ör. darboğaz, gecikme, termin riski). "
            "Ardından `items` içinden en önemli 3-5 kaydı özetle; sayıları JSON ile tutarlı tut. "
            "Ham JSON'u kullanıcıya satır satır okutma; `guidance` alanını içsel talimat olarak kullan.\n\n"
            f"```json\n{pi_block}\n```"
        )

    if tool_intelligence_result is not None:
        ti_block = json.dumps(tool_intelligence_result, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda TEKORA CNC / takım istihbaratı (`analyze_tool_intelligence`) çıktısı yer almaktadır. "
            "Önce `executive_summary` ile kısa yorum (ör. ömür, bileme sonrası düşüş, malzeme, kırılma riski). "
            "`items` içinden en kritik birkaç kaydı özetle; örnek cümleler: '2379 operasyonlarında takım ömrü düşük görünüyor.', "
            "'Takım kırılmaları yüksek olabilir.' — veri yoksa JSON’daki boş durumu dürüstçe belirt.\n\n"
            f"```json\n{ti_block}\n```"
        )

    if proactive_alerts_snapshot is not None:
        pa_block = json.dumps(proactive_alerts_snapshot, ensure_ascii=False, indent=2)
        blocks.append(
            "Aşağıda TEKORA proaktif uyarı özeti (`proactive_alerts`) yer almaktadır; veritabanındaki TekoraAlert kayıtlarından okunur. "
            "Kullanıcıya Türkçe yanıt ver: önem derecesi (severity), başlık ve kısa mesajları özetle; "
            "uyarı yoksa veya unresolved_count 0 ise bugün kayıtlı önemli açık uyarı olmadığını söyle. "
            "Sayıları ve metinleri JSON ile uyumlu tut; uydurma.\n\n"
            f"```json\n{pa_block}\n```"
        )

    blocks.append(f"Kullanıcı mesajı:\n{user_text}")
    prompt = "\n\n".join(blocks)
    system_prompt = TEKORA_CHAT_SYSTEM_PROMPT
    if semantic_memory_mode:
        system_prompt += (
            "\n\nSEMANTİK HAFIZA: Kullanıcı geçmiş / hafıza soruyorsa SEMANTIC MEMORY RESULTS bölümü "
            "birincil kaynaktır; boşsa 'Bu konuda hafızada kayıt bulamadım.' de."
        )
    body = {
        "model": _ollama_model(),
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
    }
    url = _ollama_generate_url()
    connect, read = _ollama_timeouts()
    r = requests.post(url, json=body, timeout=(connect, read))
    r.raise_for_status()
    data = r.json()
    text = data.get("response")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Ollama yanıtında geçerli 'response' yok.")
    return _strip_reasoning_blocks(text)


@csrf_exempt
@require_GET
def tekora_ping(request):
    """Sağlık kontrolü; yalnızca GET kabul edilir."""
    return _tekora_json_response(
        {
            "status": "ok",
            "service": "TEKORA",
            "version": TEKORA_API_VERSION,
        }
    )


def _count_critical_stock(notes: list[str]) -> int:
    try:
        from stokapp.models import StokItem

        return int(
            StokItem.objects.filter(
                stok_takip=True,
                mevcut_miktar__lte=F("minimum_stok"),
            ).count()
        )
    except Exception:
        logger.exception("TEKORA system-summary: critical stock count failed")
        notes.append(
            "Kritik stok sayımı yapılamadı (veritabanı veya model); değer 0 kullanıldı."
        )
        return 0


def _count_open_orders(notes: list[str]) -> int:
    try:
        from stokapp.models import Siparis

        return int(
            Siparis.objects.filter(
                siparis_durumu__in=("ONAY_BEKLIYOR", "ONAYLANDI"),
            ).count()
        )
    except Exception:
        logger.exception("TEKORA system-summary: open order count failed")
        notes.append(
            "Açık sipariş sayımı yapılamadı (veritabanı veya model); değer 0 kullanıldı."
        )
        return 0


def _count_pending_approvals(notes: list[str]) -> int:
    try:
        from stokapp.models import ApprovalRequest

        return int(
            ApprovalRequest.objects.filter(
                status=ApprovalRequest.STATUS_PENDING,
            ).count()
        )
    except Exception:
        logger.exception("TEKORA system-summary: pending approval count failed")
        notes.append(
            "Bekleyen onay sayımı yapılamadı (ApprovalRequest veya şema); değer 0 kullanıldı."
        )
        return 0


def _count_today_production(notes: list[str]) -> int:
    try:
        from stokapp.models import UretimEmri

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
        logger.exception("TEKORA system-summary: today production count failed")
        notes.append(
            "Bugünkü üretim emri sayımı yapılamadı (veritabanı veya model); değer 0 kullanıldı."
        )
        return 0


@csrf_exempt
@require_GET
def tekora_system_summary(request):
    """
    ERP genel durumu — salt okunur özet. Veritabanı kısmen hata verse bile JSON döner.
    """
    return _tekora_json_response(build_system_summary_payload())


@login_required
def tekora_chat_page(request):
    """Şirket içi TEKORA AI sohbet arayüzü."""
    return render(request, "stokapp/tekora_chat.html")


@login_required
@require_POST
def tekora_chat_api(request):
    """
    Sohbet: ERP özeti + kullanıcı mesajı ile Ollama üzerinden yanıt üretir.
    Salt okunur ERP verisi; Ollama dış çağrı.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "error": "Geçersiz JSON gövdesi."},
            status=400,
        )

    if not isinstance(body, dict):
        return _tekora_json_response(
            {"status": "error", "error": "JSON gövdesi nesne olmalıdır."},
            status=400,
        )

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return _tekora_json_response(
            {"status": "error", "error": "Mesaj alanı zorunludur ve boş olamaz."},
            status=400,
        )
    message = message.strip()
    if len(message) > 12000:
        return _tekora_json_response(
            {"status": "error", "error": "Mesaj çok uzun (en fazla 12000 karakter)."},
            status=400,
        )

    semantic_memory_mode = _semantic_memory_intent(message)
    semantic_memory_formatted_block: str | None = None
    production_intelligence_result: dict[str, Any] | None = None
    tool_intelligence_result: dict[str, Any] | None = None

    if semantic_memory_mode:
        erp_payload = _erp_payload_stub_semantic_memory()
        proactive_alerts_for_chat: dict[str, Any] | None = None
        tool_result: dict[str, Any] | None = None
        critical_analysis_result: dict[str, Any] | None = None
        bulk_approval_result: dict[str, Any] | None = None
        semantic_memory_formatted_block, semantic_memory_result = _build_semantic_memory_for_chat(
            message, request.user
        )
        logger.info(
            "TEKORA chat: semantic memory mode (results=%s)",
            len((semantic_memory_result or {}).get("results") or []),
        )
    else:
        try:
            erp_payload = build_system_summary_payload()
        except Exception:
            logger.exception("TEKORA chat: ERP özeti oluşturulamadı")
            _tekora_chat_memory_log(
                request,
                message=message,
                erp_payload=None,
                tool_result=None,
                critical_analysis_result=None,
                bulk_approval_result=None,
                approval_action_result=None,
                ai_response="",
                success=False,
                error_message="ERP özeti oluşturulamadı.",
                proactive_alerts_snapshot=None,
                production_intelligence_result=None,
                tool_intelligence_result=None,
            )
            return _tekora_json_response(
                {
                    "status": "error",
                    "error": "ERP özeti oluşturulamadı. Lütfen daha sonra tekrar deneyin.",
                },
                status=500,
            )

        proactive_alerts_for_chat = None
        if _should_query_proactive_risks(message):
            try:
                proactive_alerts_for_chat = get_proactive_alerts_snapshot_for_chat(limit=40)
            except Exception:
                logger.exception("TEKORA chat: proactive alerts snapshot failed")
                proactive_alerts_for_chat = None

        tool_result = None
        semantic_memory_result = None
        critical_analysis_result = None
        bulk_approval_result = None
        production_intel_kind = match_production_intel_kind(message)
        tool_intel_match = match_tool_intel_kind(message)

        if _should_run_bulk_purchase_approval(message):
            critical_analysis_result = execute_tool(
                TOOL_ANALYZE_CRITICAL_STOCK, {}, user=request.user
            )
            logger.info(
                "TEKORA chat: bulk path analyze_critical_stock (status=%s, critical_count=%s)",
                critical_analysis_result.get("status"),
                critical_analysis_result.get("critical_count"),
            )
            if (
                isinstance(critical_analysis_result, dict)
                and critical_analysis_result.get("status") == "ok"
                and int(critical_analysis_result.get("critical_count") or 0) > 0
            ):
                bulk_items = _critical_results_to_bulk_items(
                    critical_analysis_result.get("results") or []
                )
                if bulk_items:
                    bulk_approval_result = execute_tool(
                        TOOL_CREATE_BULK_PURCHASE_APPROVAL,
                        {
                            "type": "bulk_purchase_request",
                            "generated_by": "TEKORA",
                            "items": bulk_items,
                            "tekora_triggered_by": request.user.get_username(),
                        },
                        user=request.user,
                    )
                    logger.info(
                        "TEKORA chat: create_bulk_purchase_approval (status=%s)",
                        bulk_approval_result.get("status"),
                    )
                else:
                    bulk_approval_result = {
                        "status": "error",
                        "error": "Kritik ürünlerde pozitif önerilen miktar yok.",
                        "approval_tool": "create_bulk_purchase_approval",
                    }
        elif _should_run_critical_stock_analysis(message):
            critical_analysis_result = execute_tool(
                TOOL_ANALYZE_CRITICAL_STOCK, {}, user=request.user
            )
            logger.info(
                "TEKORA chat: analyze_critical_stock tetiklendi (status=%s, critical_count=%s)",
                critical_analysis_result.get("status"),
                critical_analysis_result.get("critical_count"),
            )
        elif production_intel_kind:
            production_intelligence_result = execute_tool(
                TOOL_ANALYZE_PRODUCTION_INTELLIGENCE,
                {"analysis": production_intel_kind, "days": 30},
                user=request.user,
            )
            logger.info(
                "TEKORA chat: production intelligence kind=%s status=%s",
                production_intel_kind,
                production_intelligence_result.get("status"),
            )
        elif tool_intel_match:
            t_kind, mat_hint = tool_intel_match
            tool_intelligence_result = execute_tool(
                TOOL_ANALYZE_TOOL_INTELLIGENCE,
                {"analysis": t_kind, "material_hint": mat_hint, "days": 90},
                user=request.user,
            )
            logger.info(
                "TEKORA chat: tool intelligence kind=%s status=%s",
                t_kind,
                tool_intelligence_result.get("status"),
            )
        elif _should_use_stock_search_tool(message):
            tool_result = execute_tool(
                "search_stock_item",
                {"query": message[:500]},
                user=request.user,
            )
            logger.info(
                "TEKORA chat: search_stock_item tetiklendi (status=%s)",
                tool_result.get("status"),
            )
            if (
                isinstance(tool_result, dict)
                and tool_result.get("status") == "ok"
                and tool_result.get("results")
            ):
                _session_save_stock_search(request, message[:500], tool_result)

    approval_action_result: dict[str, Any] | None = None
    if _should_run_create_purchase_request(message, body, request):
        pr_payload = _build_purchase_request_payload(body, message, request)
        if not _purchase_payload_has_product(pr_payload):
            _tekora_chat_memory_log(
                request,
                message=message,
                erp_payload=erp_payload,
                tool_result=tool_result,
                critical_analysis_result=critical_analysis_result,
                bulk_approval_result=bulk_approval_result,
                approval_action_result=None,
                ai_response=TEKORA_REPLY_NEED_PRODUCT,
                success=True,
                error_message=None,
                proactive_alerts_snapshot=proactive_alerts_for_chat,
                production_intelligence_result=production_intelligence_result,
                tool_intelligence_result=tool_intelligence_result,
            )
            return _tekora_json_response(
                {"status": "ok", "reply": TEKORA_REPLY_NEED_PRODUCT}
            )
        approval_action_result = execute_tool(
            TOOL_CREATE_PURCHASE_REQUEST, pr_payload, user=request.user
        )
        logger.info(
            "TEKORA chat: create_purchase_request tetiklendi (status=%s)",
            approval_action_result.get("status"),
        )

    try:
        log_critical_stock_recommendation_decision(request.user, critical_analysis_result)
    except Exception:
        logger.exception("TEKORA memory: critical decision log skipped")

    try:
        reply = _call_ollama_chat(
            message,
            erp_payload,
            tool_result=tool_result,
            semantic_memory_result=semantic_memory_result,
            semantic_memory_mode=semantic_memory_mode,
            semantic_memory_formatted_block=semantic_memory_formatted_block,
            approval_action_result=approval_action_result,
            critical_analysis_result=critical_analysis_result,
            bulk_approval_result=bulk_approval_result,
            proactive_alerts_snapshot=proactive_alerts_for_chat,
            production_intelligence_result=production_intelligence_result,
            tool_intelligence_result=tool_intelligence_result,
        )
    except requests.exceptions.Timeout:
        logger.warning("TEKORA chat: Ollama zaman aşımı")
        _tekora_chat_memory_log(
            request,
            message=message,
            erp_payload=erp_payload,
            tool_result=tool_result,
            critical_analysis_result=critical_analysis_result,
            bulk_approval_result=bulk_approval_result,
            approval_action_result=approval_action_result,
            ai_response="",
            success=False,
            error_message="Yapay zekâ sunucusu yanıt vermedi (zaman aşımı).",
            proactive_alerts_snapshot=proactive_alerts_for_chat,
            production_intelligence_result=production_intelligence_result,
            tool_intelligence_result=tool_intelligence_result,
        )
        return _tekora_json_response(
            {"status": "error", "error": "Yapay zekâ sunucusu yanıt vermedi (zaman aşımı)."},
            status=504,
        )
    except requests.exceptions.ConnectionError:
        logger.warning("TEKORA chat: Ollama bağlantı hatası")
        _tekora_chat_memory_log(
            request,
            message=message,
            erp_payload=erp_payload,
            tool_result=tool_result,
            critical_analysis_result=critical_analysis_result,
            bulk_approval_result=bulk_approval_result,
            approval_action_result=approval_action_result,
            ai_response="",
            success=False,
            error_message="Yapay zekâ sunucusuna bağlanılamadı.",
            proactive_alerts_snapshot=proactive_alerts_for_chat,
            production_intelligence_result=production_intelligence_result,
            tool_intelligence_result=tool_intelligence_result,
        )
        return _tekora_json_response(
            {
                "status": "error",
                "error": "Yapay zekâ sunucusuna bağlanılamadı (Ollama çalışıyor mu?).",
            },
            status=502,
        )
    except requests.exceptions.RequestException as exc:
        logger.exception("TEKORA chat: Ollama istek hatası: %s", exc)
        _tekora_chat_memory_log(
            request,
            message=message,
            erp_payload=erp_payload,
            tool_result=tool_result,
            critical_analysis_result=critical_analysis_result,
            bulk_approval_result=bulk_approval_result,
            approval_action_result=approval_action_result,
            ai_response="",
            success=False,
            error_message="Yapay zekâ isteği başarısız oldu.",
            proactive_alerts_snapshot=proactive_alerts_for_chat,
            production_intelligence_result=production_intelligence_result,
            tool_intelligence_result=tool_intelligence_result,
        )
        return _tekora_json_response(
            {"status": "error", "error": "Yapay zekâ isteği başarısız oldu."},
            status=502,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        logger.exception("TEKORA chat: Ollama yanıt işleme hatası: %s", exc)
        _tekora_chat_memory_log(
            request,
            message=message,
            erp_payload=erp_payload,
            tool_result=tool_result,
            critical_analysis_result=critical_analysis_result,
            bulk_approval_result=bulk_approval_result,
            approval_action_result=approval_action_result,
            ai_response="",
            success=False,
            error_message="Yapay zekâ yanıtı işlenemedi.",
            proactive_alerts_snapshot=proactive_alerts_for_chat,
            production_intelligence_result=production_intelligence_result,
            tool_intelligence_result=tool_intelligence_result,
        )
        return _tekora_json_response(
            {"status": "error", "error": "Yapay zekâ yanıtı işlenemedi."},
            status=502,
        )

    _tekora_chat_memory_log(
        request,
        message=message,
        erp_payload=erp_payload,
        tool_result=tool_result,
        critical_analysis_result=critical_analysis_result,
        bulk_approval_result=bulk_approval_result,
        approval_action_result=approval_action_result,
        ai_response=reply,
        success=True,
        error_message=None,
        proactive_alerts_snapshot=proactive_alerts_for_chat,
        production_intelligence_result=production_intelligence_result,
        tool_intelligence_result=tool_intelligence_result,
    )
    return _tekora_json_response({"status": "ok", "reply": reply})


@csrf_exempt
@login_required
@require_POST
def tekora_tool_search_stock(request):
    """
    TEKORA tool API: stok kartı araması (salt okunur).
    POST body: {"query": "..."}
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "error": "Geçersiz JSON gövdesi.", "results": []},
            status=400,
        )

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        return _tekora_json_response(
            {"status": "error", "error": "query alanı zorunludur.", "results": []},
            status=400,
        )

    out = execute_tool("search_stock_item", {"query": query.strip()}, user=request.user)
    return _tekora_json_response(out)


@csrf_exempt
@login_required
@require_POST
def tekora_tool_create_purchase_request(request):
    """
    TEKORA onay aracı API: satınalma önerisi için ApprovalRequest (pending).
    POST body: {"product": "...", "suggested_quantity": 500, "current_stock": 12, "notes": "..."}
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "error": "Geçersiz JSON gövdesi."},
            status=400,
        )

    if not isinstance(body, dict):
        return _tekora_json_response(
            {"status": "error", "error": "Gövde nesne olmalıdır."},
            status=400,
        )

    payload = dict(body)
    payload["tekora_triggered_by"] = request.user.get_username()
    payload.setdefault("reason", TEKORA_PURCHASE_REASON_DEFAULT)
    payload = _apply_session_to_purchase_payload(request, payload)
    if not _payload_suggested_quantity_positive(payload):
        dq = _default_suggested_quantity(payload)
        if dq is not None:
            payload["suggested_quantity"] = int(dq) if dq == int(dq) else dq
    if not _purchase_payload_has_product(payload):
        return _tekora_json_response(
            {"status": "error", "error": TEKORA_REPLY_NEED_PRODUCT},
            status=400,
        )
    out = execute_tool(TOOL_CREATE_PURCHASE_REQUEST, payload, user=request.user)
    if out.get("status") != "ok":
        return _tekora_json_response(out, status=400)
    return _tekora_json_response(out)


@login_required
@require_GET
def tekora_tool_analyze_critical_stock(request):
    """
    TEKORA tool API: kritik stok analizi ve önerilen satınalma miktarları (salt okunur, GET).
    """
    out = execute_tool(TOOL_ANALYZE_CRITICAL_STOCK, {}, user=request.user)
    return _tekora_json_response(out)


@login_required
@require_POST
def tekora_tool_production_intelligence(request):
    """
    TEKORA üretim istihbaratı API (salt okunur).
    POST body: {"analysis": "delayed"|"bottlenecks"|"performance"|"risky_orders", "days": 30}
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "error": "Geçersiz JSON gövdesi."},
            status=400,
        )
    if not isinstance(body, dict):
        return _tekora_json_response(
            {"status": "error", "error": "JSON gövdesi nesne olmalıdır."},
            status=400,
        )
    analysis = body.get("analysis") or body.get("kind") or "delayed"
    days_raw = body.get("days", 30)
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 30
    out = execute_tool(
        TOOL_ANALYZE_PRODUCTION_INTELLIGENCE,
        {"analysis": str(analysis).strip(), "days": days},
        user=request.user,
    )
    return _tekora_json_response(out)


@login_required
@require_POST
def tekora_tool_tool_intelligence(request):
    """
    TEKORA CNC / takım istihbaratı API (salt okunur).
    POST body: {"analysis": "lifetimes"|"material"|"operations"|"brands", "days": 90, "material_hint": "2379"}
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "error": "Geçersiz JSON gövdesi."},
            status=400,
        )
    if not isinstance(body, dict):
        return _tekora_json_response(
            {"status": "error", "error": "JSON gövdesi nesne olmalıdır."},
            status=400,
        )
    analysis = body.get("analysis") or body.get("kind") or "lifetimes"
    days_raw = body.get("days", 90)
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 90
    mat = body.get("material_hint")
    material_hint = str(mat).strip() if isinstance(mat, str) and mat.strip() else None
    out = execute_tool(
        TOOL_ANALYZE_TOOL_INTELLIGENCE,
        {
            "analysis": str(analysis).strip(),
            "days": days,
            "material_hint": material_hint,
        },
        user=request.user,
    )
    return _tekora_json_response(out)


@csrf_exempt
@require_POST
def tekora_semantic_search(request):
    """
    TEKORA semantic-search internal JSON API (oturum gerektirmez; yalnızca yerel IP).

    POST body: {"query": "...", "limit": 5 (opsiyonel), "user_id": <int> (opsiyonel)}
    """
    if not _tekora_semantic_search_remote_allowed(request):
        return _tekora_json_response(
            {"status": "error", "message": "Bu endpoint yalnızca yerel isteklere açıktır."},
            status=403,
        )

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tekora_json_response(
            {"status": "error", "message": "Geçersiz JSON gövdesi."},
            status=400,
        )

    if not isinstance(body, dict):
        return _tekora_json_response(
            {"status": "error", "message": "JSON gövdesi nesne olmalıdır."},
            status=400,
        )

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        return _tekora_json_response(
            {"status": "error", "message": "query alanı zorunludur."},
            status=400,
        )

    limit = body.get("limit", 5)
    user_id_raw = body.get("user_id")
    user_id: int | None
    if user_id_raw is None or user_id_raw == "":
        user_id = None
    else:
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            return _tekora_json_response(
                {"status": "error", "message": "user_id sayısal olmalıdır."},
                status=400,
            )

    out = execute_tool(
        TOOL_SEMANTIC_SEARCH,
        {"query": query.strip(), "limit": limit, "user_id": user_id},
        user=None,
    )
    if out.get("status") != "ok":
        msg = out.get("error") or out.get("message") or "Semantic arama başarısız."
        return _tekora_json_response({"status": "error", "message": str(msg)}, status=400)

    results = out.get("results")
    if not isinstance(results, list):
        results = []
    return _tekora_json_response({"status": "ok", "results": results})
