"""TEKORA tool kayıtları — merkezi registry (açıklama, güvenlik bayrakları)."""

from __future__ import annotations

TOOL_SEARCH_STOCK_ITEM = "search_stock_item"
TOOL_CREATE_PURCHASE_REQUEST = "create_purchase_request"
TOOL_ANALYZE_CRITICAL_STOCK = "analyze_critical_stock"
TOOL_CREATE_BULK_PURCHASE_APPROVAL = "create_bulk_purchase_approval"
TOOL_SEMANTIC_SEARCH = "semantic_search"
TOOL_ANALYZE_PRODUCTION_INTELLIGENCE = "analyze_production_intelligence"
TOOL_ANALYZE_TOOL_INTELLIGENCE = "analyze_tool_intelligence"

# Stok arama tetikleyicileri (sohbet yönlendirmesi; views_tekora ile paylaşılır)
STOCK_SEARCH_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "stok",
    "var mı",
    "var mi",
    "ürün",
    "urun",
    "malzeme",
    "civata",
    "rulman",
    "somun",
)

# Satınalma onay talebi tetikleyicileri (mesaj + isteğe bağlı confirm bayrağı)
PURCHASE_APPROVAL_CONFIRM_KEYWORDS: tuple[str, ...] = (
    "evet",
    "tamam",
    "onaylıyorum",
    "onayliyorum",
    "oluştur",
    "olustur",
    "kaydet",
)

# Kritik stok toplu analiz tetikleyicileri (sohbet)
CRITICAL_STOCK_ANALYSIS_KEYWORDS: tuple[str, ...] = (
    "kritik stok",
    "kritik stoklar",
    "kritik ürün",
    "kritik ürünler",
    "kritik urun",
    "eksik stok",
    "satınalma önerisi",
    "satinalma onerisi",
    "toplu satınalma",
    "toplu satinalma",
    "stok analiz",
    "kritik analiz",
)

# Kritik stok + toplu onay kaydı oluşturma (sohbet; analyze + bulk approval)
# Proaktif risk / uyarı sohbet tetikleyicileri
PROACTIVE_RISK_QUERY_KEYWORDS: tuple[str, ...] = (
    "önemli risk",
    "onemli risk",
    "risk var mı",
    "risk var mi",
    "bugün risk",
    "tekora bugün",
    "tekora bugun",
    "operasyonel risk",
    "aktif uyarı",
    "aktif uyari",
    "bekleyen risk",
    "uyarı var mı",
    "uyari var mi",
    "acil durum",
    "kritik uyarı",
    "kritik uyari",
)

# Semantic memory search tetikleyicileri (sohbet içinde)
SEMANTIC_SEARCH_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "geçmişte ne konuşt",  # geçmişte ne konuşmuştuk / konuştu...
    "geçmiş konuş",
    "gecmiste ne konuşt",
    "gecmis konus",
    "benzer",
    "benzeri",
    "benzer kayıt",
    "daha önce bununla ilgili",
    "daha once bununla ilgili",
    "daha önce ne demiş",
    "daha once ne demis",
    "hafızadan ara",
    "hafizadan ara",
    "hafiza ara",
    "hatırla",
)

# Üretim zekâsı — sohbet tetikleyicileri (sıra: ilk eşleşen kazanır)
PRODUCTION_INTEL_KIND_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("riskli sipariş", "riskli siparis", "riskli siparişler", "riskli siparisler"), "risky_orders"),
    (("darboğaz", "darbogaz", "dar boğaz", "dar bogaz", "darboğaz analiz", "darbogaz analiz"), "bottlenecks"),
    (("üretim performans", "uretim performans", "operasyon performans"), "performance"),
    (("hangi istasyon", "istasyon yavaş", "istasyon yavas", "yavaş istasyon", "yavas istasyon"), "bottlenecks"),
    (
        (
            "geciken iş",
            "geciken is",
            "geciken işler",
            "geciken isler",
            "geciken emir",
            "geciken emirler",
            "problemli iş",
            "problemli is",
            "problemli işler",
            "g geciken",
        ),
        "delayed",
    ),
)


def match_production_intel_kind(message: str) -> str | None:
    """Üretim analizi türü; eşleşme yoksa None."""
    m = (message or "").lower()
    for keys, kind in PRODUCTION_INTEL_KIND_RULES:
        if any(k in m for k in keys):
            return kind
    return None


def match_tool_intel_kind(message: str) -> tuple[str, str | None] | None:
    """
    Takım / CNC istihbaratı. Dönüş: (analysis_kind, material_hint) veya None.
    analysis_kind: lifetimes | material | operations | brands
    """
    from .tekora_tool_intelligence import extract_tool_material_hint

    m = (message or "").lower()
    hint = extract_tool_material_hint(message or "")

    if any(
        k in m
        for k in (
            "problemli operasyon",
            "problemli operasyonlar",
            "problem operasyon",
        )
    ):
        return ("operations", None)

    if any(
        k in m
        for k in (
            "marka karşılaştır",
            "marka karsilastir",
            "takım marka",
            "takim marka",
            "en verimli takım",
            "en verimli takim",
            "verimli takım hangisi",
            "verimli takim hangisi",
        )
    ):
        return ("brands", None)

    if any(
        k in m
        for k in (
            "takım ömrü",
            "takim omru",
            "takım ömrü analiz",
            "takim omru analiz",
            "hangi takım hızlı bitiyor",
            "hangi takim hizli bitiyor",
            "hızlı biten takım",
            "hizli biten takim",
            "hangi takım sorunlu",
            "hangi takim sorunlu",
            "sorunlu takım",
            "sorunlu takim",
        )
    ):
        return ("lifetimes", None)

    if hint and (
        "takım" in m
        or "takim" in m
        or "performans" in m
        or "malzeme" in m
        or "analiz" in m
    ):
        return ("material", hint)

    return None


BULK_PURCHASE_FROM_CRITICAL_KEYWORDS: tuple[str, ...] = (
    "önerilerini",
    "onerilerini",
    "satınalma önerileri",
    "satinalma onerileri",
    "toplu satınalma",
    "toplu satinalma",
    "toplu onay",
    "toplu satınalma onay",
    "toplu satinalma onay",
)

PURCHASE_APPROVAL_INTENT_KEYWORDS: tuple[str, ...] = (
    "satınalma önerisi",
    "satinalma onerisi",
    "satınalma talebi",
    "satinalma talebi",
    "talep oluştur",
    "talep olustur",
    "onaya gönder",
    "onaya gonder",
)

TOOLS: dict[str, dict[str, object]] = {
    TOOL_SEARCH_STOCK_ITEM: {
        "description": "ERP içinde stok ürünü arar",
        "dangerous": False,
        "approval_required": False,
    },
    TOOL_CREATE_PURCHASE_REQUEST: {
        "description": "Satınalma talebi için onay kaydı oluşturur (doğrudan satınalma açmaz)",
        "dangerous": True,
        "approval_required": True,
    },
    TOOL_ANALYZE_CRITICAL_STOCK: {
        "description": "Kritik stok kalemlerini analiz eder ve toplu satınalma önerisi üretir (salt okunur)",
        "dangerous": False,
        "approval_required": False,
    },
    TOOL_CREATE_BULK_PURCHASE_APPROVAL: {
        "description": "Kritik stok analizine göre tek toplu satınalma onay kaydı oluşturur (satınalma fişi açmaz)",
        "dangerous": True,
        "approval_required": True,
    },
    TOOL_SEMANTIC_SEARCH: {
        "description": "Geçmiş konuşmalar ve hafıza kayıtları üzerinde anlam bazlı arama yapar.",
        "dangerous": False,
        "approval_required": False,
    },
    TOOL_ANALYZE_PRODUCTION_INTELLIGENCE: {
        "description": "Üretim emirleri, istasyon darboğazları, operasyon performansı ve riskli siparişleri analiz eder (salt okunur).",
        "dangerous": False,
        "approval_required": False,
    },
    TOOL_ANALYZE_TOOL_INTELLIGENCE: {
        "description": "CNC takım ömrü, malzeme performansı, operasyon yoğunluğu ve marka karşılaştırması (salt okunur).",
        "dangerous": False,
        "approval_required": False,
    },
}
