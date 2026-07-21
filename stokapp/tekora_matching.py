"""TEKORA akıllı ürün eşleştirme — normalizasyon, token ve skor (salt okunur yardımcılar)."""

from __future__ import annotations

import re
from typing import Any

# Türkçe büyük harfler → ASCII küçük (önce çeviri, sonra .lower())
_TR_UPPER_TO_ASCII = (
    ("İ", "i"),
    ("I", "i"),
    ("Ş", "s"),
    ("Ğ", "g"),
    ("Ü", "u"),
    ("Ö", "o"),
    ("Ç", "c"),
)


def normalize_text(text: str) -> str:
    """
    Türkçe sadeleştirme, küçük harf, ayırıcı/boşluk düzeni, boyut ayırıcılarını 'x' ile birleştirme.
    """
    if not isinstance(text, str):
        return ""
    s = text.strip()
    if not s:
        return ""
    for src, dst in _TR_UPPER_TO_ASCII:
        s = s.replace(src, dst)
    s = s.lower()
    # Ölçü: 10 x 20, 10×20, 10X20 → 10x20
    s = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1x\2", s, flags=re.IGNORECASE)
    s = s.replace("×", "x")
    s = re.sub(r"[/\\_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compact_alnum(text: str) -> str:
    """Kıyaslama için yalnızca a-z0-9 birleşik dize (m1020, m10x20)."""
    n = normalize_text(text)
    return re.sub(r"[^a-z0-9]+", "", n)


def tokenize_query(query: str) -> list[str]:
    """
    Sorgudan anlamlı token listesi (sıra korunur, tekrarsız).
    Örn. 'M10x20 imbus' → m10, 20, m10x20, imbus ve kompakt varyantlar.
    """
    n = normalize_text(query)
    if not n:
        return []

    seen: set[str] = set()
    out: list[str] = []

    def add(tok: str) -> None:
        t = tok.strip().lower()
        if len(t) < 2:
            return
        if t not in seen:
            seen.add(t)
            out.append(t)

    for w in n.split():
        add(w)
        # m10x20 → m10, 20, m10x20
        m = re.match(r"^([a-z]{0,4})(\d+)\s*x\s*(\d+)$", w)
        if m:
            pfx, a, b = m.group(1), m.group(2), m.group(3)
            add(f"{pfx}{a}" if pfx else a)
            add(b)
            add(f"{pfx}{a}x{b}" if pfx else f"{a}x{b}")
        # m1020 gibi bitişik
        m2 = re.match(r"^([a-z]+)(\d{2,})$", w)
        if m2 and "x" not in w:
            pfx2, digits = m2.group(1), m2.group(2)
            if len(digits) >= 4 and len(digits) % 2 == 0:
                half = len(digits) // 2
                add(f"{pfx2}{digits[:half]}")
                add(digits[half:])
                add(f"{pfx2}{digits[:half]}x{digits[half:]}")

    c = compact_alnum(query)
    if len(c) >= 3:
        add(c)

    # rakam grupları (20, 10)
    for num in re.findall(r"\d{2,4}", n):
        add(num)

    return out[:24]


def _item_text_bundle(item: dict[str, Any]) -> tuple[str, str, str]:
    code = str(item.get("stok_kodu") or item.get("code") or item.get("kod") or "")
    name = str(item.get("ad") or item.get("name") or item.get("stok_adi") or "")
    desc = str(item.get("aciklama") or item.get("description") or "")
    return code, name, desc


def calculate_match_score(
    item: dict[str, Any],
    tokens: list[str],
    normalized_query: str,
) -> int:
    """
    0–100 arası skor. Tam/kısmi kod, ad, token kapsaması ve kompakt eşleşme.
    """
    code, name, desc = _item_text_bundle(item)
    n_code = normalize_text(code)
    n_name = normalize_text(name)
    n_desc = normalize_text(desc)
    bundle = normalize_text(f"{code} {name} {desc}")
    c_code = compact_alnum(code)
    c_name = compact_alnum(name)
    c_desc = compact_alnum(desc)
    c_bundle = compact_alnum(bundle)
    nq = normalized_query.strip()
    cq = compact_alnum(normalized_query)

    score = 0
    if not c_bundle and not bundle:
        return 0

    if nq and nq == n_code.strip():
        score += 100
    elif cq and cq == c_code:
        score += 98
    elif cq and len(cq) >= 4 and cq in c_code:
        score += 85
    elif cq and len(cq) >= 4 and cq in c_bundle:
        score += 55

    if nq and len(nq) >= 3 and nq in bundle:
        score += 35

    for t in tokens:
        if len(t) < 2:
            continue
        if t in c_code:
            score += 22
        elif t in c_name:
            score += 16
        elif t in c_desc:
            score += 10
        elif t in c_bundle:
            score += 12

    if tokens:
        strong = [t for t in tokens if len(t) >= 3]
        if strong:
            hit = sum(1 for t in strong if t in c_bundle)
            if hit == len(strong):
                score += 28
            elif hit >= max(1, len(strong) // 2):
                score += 14

    if n_name and any(t in n_name for t in tokens if len(t) >= 4):
        score += 8

    return int(min(100, max(0, score)))


def build_stock_candidate_q(tokens: list[str], original: str):
    """StokItem aday kümesi için geniş ORM Q (salt okunur filtre)."""
    from django.db.models import Q

    parts: list[Q] = []
    for t in tokens:
        if len(t) < 2:
            continue
        parts.append(
            Q(stok_kodu__icontains=t)
            | Q(ad__icontains=t)
            | Q(aciklama__icontains=t)
        )

    og = (original or "").strip()
    if len(og) >= 2:
        parts.append(
            Q(stok_kodu__icontains=og)
            | Q(ad__icontains=og)
            | Q(aciklama__icontains=og)
        )

    cq = compact_alnum(original)
    if len(cq) >= 3:
        parts.append(
            Q(stok_kodu__icontains=cq)
            | Q(ad__icontains=cq)
            | Q(aciklama__icontains=cq)
        )

    if not parts:
        if len(og) >= 1:
            return (
                Q(stok_kodu__icontains=og)
                | Q(ad__icontains=og)
                | Q(aciklama__icontains=og)
            )
        return Q(pk__in=[])

    qo = parts[0]
    for p in parts[1:]:
        qo |= p
    return qo
