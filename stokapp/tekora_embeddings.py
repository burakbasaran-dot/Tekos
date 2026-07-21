"""
TEKORA semantic memory (pgvector) yardımcıları.

- Ollama embeddings üretir (nomic-embed-text / 768 dim)
- TekoraChatLog / TekoraMemory içeriklerinden embedding üretir
- Query ile pgvector üzerinden benzerlik araması yapar
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from django.db.models import Q
from django.utils import timezone

from .models import TekoraChatLog, TekoraMemory, TekoraMemoryEmbedding

logger = logging.getLogger(__name__)

_OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
_EMBED_MODEL = "nomic-embed-text"

_MAX_EMBED_TEXT_CHARS = 4000
_DEFAULT_LIMIT = 5


def _ollama_timeouts() -> tuple[float, float]:
    """
    views_tekora.py ile aynı timeout env isimlerini kullanır.
    """
    connect = float(os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_CONNECT", "10"))
    read = float(os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_READ", "300"))
    return connect, read


def get_embedding(text: str) -> list[float]:
    """
    Ollama embeddings üretir.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    t = text.strip()
    if not t:
        raise ValueError("text empty")

    t = t[:_MAX_EMBED_TEXT_CHARS]

    connect, read = _ollama_timeouts()
    payload = {"model": _EMBED_MODEL, "prompt": t}
    r = requests.post(_OLLAMA_EMBED_URL, json=payload, timeout=(connect, read))
    r.raise_for_status()
    data = r.json()

    emb = data.get("embedding")
    if emb is None:
        emb_list = data.get("embeddings")
        if isinstance(emb_list, list) and emb_list:
            emb = emb_list[0]
    if not isinstance(emb, list):
        raise ValueError(f"Ollama embeddings response format error: keys={list(data.keys())}")

    # pgvector VektorField boyutu ile uyum sağlamak için kontrol
    if len(emb) != 768:
        raise ValueError(f"Unexpected embedding dim: {len(emb)} (expected 768)")

    return [float(x) for x in emb]


def create_memory_embedding_for_chat(chat_log: TekoraChatLog) -> TekoraMemoryEmbedding:
    """
    TekoraChatLog için TekoraMemoryEmbedding oluşturur.
    Embedding zaten varsa yeni kayıt oluşturmaz.
    """
    if chat_log is None:
        raise ValueError("chat_log is required")

    existing = TekoraMemoryEmbedding.objects.filter(chat_log=chat_log).first()
    if existing is not None:
        return existing

    user_msg = chat_log.user_message or ""
    ai_resp = chat_log.ai_response or ""
    combined = (user_msg + "\n" + ai_resp).strip()
    if not combined:
        raise ValueError("chat_log has no text to embed")

    combined_for_embedding = combined[:_MAX_EMBED_TEXT_CHARS]
    embedding = get_embedding(combined_for_embedding)

    return TekoraMemoryEmbedding.objects.create(
        memory=None,
        chat_log=chat_log,
        source_type="chat_log",
        source_id=str(chat_log.pk),
        text=combined_for_embedding,
        embedding=embedding,
        metadata={
            "user_id": getattr(chat_log.user, "pk", None),
            "session_key": chat_log.session_key or "",
            "created_at": chat_log.created_at.isoformat() if getattr(chat_log, "created_at", None) else None,
        },
    )


def create_memory_embedding_for_memory(memory: TekoraMemory) -> TekoraMemoryEmbedding:
    """
    TekoraMemory için TekoraMemoryEmbedding oluşturur.
    Embedding zaten varsa yeni kayıt oluşturmaz.
    """
    if memory is None:
        raise ValueError("memory is required")

    existing = TekoraMemoryEmbedding.objects.filter(memory=memory).first()
    if existing is not None:
        return existing

    text = (memory.content or "").strip()
    if not text:
        raise ValueError("memory content empty")

    text_for_embedding = text[:_MAX_EMBED_TEXT_CHARS]
    embedding = get_embedding(text_for_embedding)

    return TekoraMemoryEmbedding.objects.create(
        memory=memory,
        chat_log=None,
        source_type="memory",
        source_id=str(memory.pk),
        text=text_for_embedding,
        embedding=embedding,
        metadata={
            "memory_type": memory.memory_type,
            "importance": memory.importance,
            "is_active": memory.is_active,
            "created_at": memory.created_at.isoformat() if getattr(memory, "created_at", None) else None,
        },
    )


def semantic_search(query: str, *, limit: int = _DEFAULT_LIMIT, user_id: int | None = None) -> list[dict[str, Any]]:
    """
    Query ile hem chat_log hem de memory embeddingleri arasında semantic arama yapar.

    PostgreSQL/pgvector yoksa (veya pgvector query API import edilemezse) exception fırlatır.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")

    try:
        from pgvector.django import CosineDistance  # type: ignore
    except Exception as exc:
        raise RuntimeError("pgvector not available: CosineDistance import failed") from exc

    q = query.strip()[:_MAX_EMBED_TEXT_CHARS]
    query_embedding = get_embedding(q)

    # Kullanıcıya ait chat_log + global memory birlikte aranır.
    qs = TekoraMemoryEmbedding.objects.all()
    if user_id is not None:
        qs = qs.filter(Q(source_type="memory") | Q(chat_log__user_id=user_id))

    limit = max(1, int(limit or _DEFAULT_LIMIT))

    rows = (
        qs.annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:limit]
    )

    results: list[dict[str, Any]] = []
    for r in rows:
        try:
            distance_val = float(getattr(r, "distance", 0.0) or 0.0)
        except Exception:
            distance_val = 0.0
        similarity = 1.0 - distance_val

        created_at = getattr(r, "created_at", None)
        results.append(
            {
                "text": r.text,
                "similarity": round(float(similarity), 4),
                "source_type": r.source_type,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )

    return results

