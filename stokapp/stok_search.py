"""Stok arama yardımcıları — çok kelimeli (AND) filtre."""
from django.db.models import Q


def stok_multi_term_filter(qs, search_query, *, kod_field='stok_kodu', ad_field='ad'):
    """
    Çok kelimeli arama: her kelime kod veya ad alanında geçmeli (AND).
    Örn. "M8 somun" → hem M8 hem somun içeren kayıtlar.
    """
    terms = [t.strip() for t in (search_query or '').split() if t.strip()]
    if not terms:
        return qs
    for term in terms:
        qs = qs.filter(
            Q(**{f'{kod_field}__icontains': term}) | Q(**{f'{ad_field}__icontains': term})
        )
    return qs


def row_matches_multi_term(text, query):
    """İstemci tarafı satır filtresi — tüm kelimeler metinde geçmeli."""
    if not query or not str(query).strip():
        return True
    haystack = (text or '').lower()
    for term in str(query).lower().split():
        t = term.strip()
        if t and t not in haystack:
            return False
    return True
