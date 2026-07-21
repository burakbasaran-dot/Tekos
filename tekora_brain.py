#!/usr/bin/env python3
"""
TEKORA AI köprüsü: Django ERP system-summary → Ollama (DeepSeek-R1) → yönetici özeti.

Çalıştırma:
  python tekora_brain.py

Ortam değişkenleri (isteğe bağlı):
  TEKORA_ERP_SUMMARY_URL  — varsayılan: http://127.0.0.1:8000/stok/api/tekora/system-summary/
  OLLAMA_GENERATE_URL     — varsayılan: http://127.0.0.1:11434/api/generate
  OLLAMA_MODEL            — varsayılan: deepseek-r1:8b
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

# --- Yapılandırma ---
ERP_SUMMARY_URL = os.environ.get(
    "TEKORA_ERP_SUMMARY_URL",
    "http://127.0.0.1:8000/stok/api/tekora/system-summary/",
)
OLLAMA_GENERATE_URL = os.environ.get(
    "OLLAMA_GENERATE_URL",
    "http://127.0.0.1:11434/api/generate",
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-r1:8b")

# (bağlantı saniyesi, okuma saniyesi)
TIMEOUT_ERP = float(os.environ.get("TEKORA_BRAIN_TIMEOUT_ERP", "15"))
TIMEOUT_OLLAMA_CONNECT = float(os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_CONNECT", "10"))
TIMEOUT_OLLAMA_READ = float(os.environ.get("TEKORA_BRAIN_TIMEOUT_OLLAMA_READ", "300"))

SYSTEM_PROMPT = """Sen TEKORA isimli şirket içi ERP yapay zekasısın.
Görevin üretim, stok, satınalma ve operasyon verilerini analiz ederek yönetime kısa ve net değerlendirme sunmaktır.
Yanıtların:
- kısa
- teknik
- yönetici özeti şeklinde olsun.
Gereksiz konuşma yapma."""


def _strip_reasoning_blocks(text: str) -> str:
    """DeepSeek-R1 vb. modellerde görülen düşünce bloklarını kaldırır (terminal özeti için)."""
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


def fetch_erp_summary() -> dict[str, Any]:
    """Django TEKORA system-summary JSON'unu çeker."""
    try:
        r = requests.get(ERP_SUMMARY_URL, timeout=TIMEOUT_ERP)
        r.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"ERP API zaman aşımı ({ERP_SUMMARY_URL}): {exc}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"ERP API bağlantı hatası (Django çalışıyor mu?): {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"ERP API isteği başarısız: {exc}") from exc

    try:
        return r.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"ERP yanıtı geçerli JSON değil (ilk 200 karakter): {r.text[:200]!r}"
        ) from exc


def generate_analysis(erp_payload: dict[str, Any]) -> str:
    """Ollama üzerinden DeepSeek ile ERP analizi üretir."""
    user_prompt = (
        "Aşağıda TEKORA system-summary API çıktısı (JSON) verilmiştir. "
        "Bu verilere dayanarak yönetici özeti yaz (Türkçe, madde imi veya kısa paragraflar).\n\n"
        f"```json\n{json.dumps(erp_payload, ensure_ascii=False, indent=2)}\n```"
    )

    body = {
        "model": OLLAMA_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
    }

    try:
        r = requests.post(
            OLLAMA_GENERATE_URL,
            json=body,
            timeout=(TIMEOUT_OLLAMA_CONNECT, TIMEOUT_OLLAMA_READ),
        )
        r.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            f"Ollama zaman aşımı ({OLLAMA_GENERATE_URL}). Model yanıtı çok uzun sürdü veya servis yanıt vermiyor: {exc}"
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Ollama bağlantı hatası (Ollama çalışıyor mu?): {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Ollama isteği başarısız: {exc}") from exc

    try:
        data = r.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Ollama yanıtı geçerli JSON değil (ilk 200 karakter): {r.text[:200]!r}"
        ) from exc

    text = data.get("response")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(
            f"Ollama yanıtında 'response' alanı yok veya boş: {json.dumps(data, ensure_ascii=False)[:500]}"
        )

    return _strip_reasoning_blocks(text)


def print_banner(title: str = "TEKORA ERP ANALİZİ") -> None:
    line = "=" * 30
    print(line)
    print(title)
    print(line)


def main() -> int:
    try:
        summary = fetch_erp_summary()
        analysis = generate_analysis(summary)
    except RuntimeError as exc:
        print_banner("TEKORA ERP ANALİZİ — HATA")
        print(str(exc))
        print()
        print("=" * 30)
        return 1

    print_banner("TEKORA ERP ANALİZİ")
    print()
    print(analysis if analysis else "(Boş yanıt)")
    print()
    print("=" * 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
