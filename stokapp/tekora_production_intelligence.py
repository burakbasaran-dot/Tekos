"""
TEKORA Production Intelligence — üretim emirleri, istasyonlar ve sipariş riskleri (salt okunur, ORM).
Ağır sorgulardan kaçınmak için sınırlar ve basit toplulaştırmalar kullanılır.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

_MAX_OPEN_WORK_ORDERS = 120
_MAX_DURUS_GROUPS = 500
_MAX_ACTIVE_ASAMALAR = 400
_MAX_SIPARIS_RISK_SCAN = 45
_LONG_OP_FACTOR = 3.0
_DURUS_WINDOW_DAYS = 14


def _now():
    return timezone.now()


def _risk_tier_from_hours(hours: float) -> str:
    if hours >= 48:
        return "high"
    if hours >= 6:
        return "medium"
    return "medium"


def _recete_operasyon_istasyon_map(recete_ids: set[int]) -> dict[tuple[int, int], str | None]:
    """(recete_id, sira) -> istasyon adı."""
    if not recete_ids:
        return {}
    from .models import ReceteOperasyon

    out: dict[tuple[int, int], str | None] = {}
    qs = (
        ReceteOperasyon.objects.filter(recete_id__in=recete_ids)
        .select_related("istasyon")
        .only("recete_id", "sira", "istasyon__ad")
    )
    for ro in qs[:2000]:
        key = (int(ro.recete_id), int(ro.sira or 0))
        name = ro.istasyon.ad if ro.istasyon_id else None
        out[key] = name
    return out


def _istasyon_name_for_asama(asama, ro_map: dict[tuple[int, int], str | None]) -> str:
    rid = int(asama.uretim_emri.recete_id)
    sira = int(asama.sira or 0)
    name = ro_map.get((rid, sira))
    if name:
        return name
    return "İstasyon atanmamış"


def get_delayed_work_orders() -> list[dict[str, Any]]:
    """
    Tamamlanmamış iş emirleri: planlanan bitiş geçmiş veya aktif operasyon planlanan süreyi aşmış.
    """
    try:
        from .models import UretimEmri

        now = _now()
        qs = (
            UretimEmri.objects.filter(durum__in=("PLANLANDI", "BASLADI"))
            .select_related("recete")
            .prefetch_related("asamalar")
            .order_by("planlanan_bitis")[:_MAX_OPEN_WORK_ORDERS]
        )
        rows: list[dict[str, Any]] = []
        for emir in qs:
            delay_hours = 0.0
            reasons: list[str] = []

            if emir.planlanan_bitis and emir.planlanan_bitis < now:
                dh = (now - emir.planlanan_bitis).total_seconds() / 3600.0
                delay_hours = max(delay_hours, dh)
                reasons.append("planlanan_bitis_gecmis")

            active = None
            for a in emir.asamalar.all():
                if a.durum == "DEVAM_EDIYOR" and a.baslama_zamani:
                    active = a
                    break
            if active and active.baslama_zamani and (active.planlanan_sure or 0) > 0:
                elapsed_m = (now - active.baslama_zamani).total_seconds() / 60.0
                planned_m = float(active.planlanan_sure)
                if elapsed_m > planned_m * _LONG_OP_FACTOR:
                    overrun_h = max(0.0, (elapsed_m - planned_m) / 60.0)
                    delay_hours = max(delay_hours, overrun_h)
                    reasons.append("aktif_operasyon_asiri_uzun")

            if delay_hours < 0.01 and not reasons:
                continue

            risk = _risk_tier_from_hours(delay_hours)
            rows.append(
                {
                    "work_order_id": emir.pk,
                    "order_no": emir.emir_no,
                    "delay_hours": round(delay_hours, 2),
                    "status": emir.durum,
                    "risk": risk,
                    "reasons": reasons or ["planlama_uyumsuzlugu"],
                }
            )
        rows.sort(key=lambda x: -float(x.get("delay_hours") or 0))
        return rows[:40]
    except Exception:
        logger.exception("get_delayed_work_orders failed")
        return []


def get_station_bottlenecks() -> list[dict[str, Any]]:
    """
    Son _DURUS_WINDOW_DAYS gün duruş toplamı + açık işlerde istasyon başına bekleyen/aktif aşama sayısı.
    """
    try:
        from .models import UretimAsamaDurusKaydi, UretimAsamasi

        now = _now()
        cutoff = now - timedelta(days=_DURUS_WINDOW_DAYS)

        durus_agg = list(
            UretimAsamaDurusKaydi.objects.filter(baslama_zamani__gte=cutoff)
            .values("asama_id")
            .annotate(downtime_s=Sum("sure_saniye"))
            .order_by("-downtime_s")[:_MAX_DURUS_GROUPS]
        )
        asama_ids = [r["asama_id"] for r in durus_agg if r.get("asama_id")]
        downtime_by_station: dict[str, float] = defaultdict(float)

        if asama_ids:
            asamas = {
                a.pk: a
                for a in UretimAsamasi.objects.filter(pk__in=asama_ids[:800]).select_related(
                    "uretim_emri__recete"
                )
            }
            recete_ids = {int(a.uretim_emri.recete_id) for a in asamas.values()}
            ro_map = _recete_operasyon_istasyon_map(recete_ids)
            by_id = {r["asama_id"]: int(r.get("downtime_s") or 0) for r in durus_agg}
            for aid, sec in by_id.items():
                asama = asamas.get(aid)
                if not asama:
                    continue
                st = _istasyon_name_for_asama(asama, ro_map)
                downtime_by_station[st] += float(sec or 0) / 60.0
            for k in list(downtime_by_station.keys()):
                downtime_by_station[k] = round(downtime_by_station[k], 1)

        active_counts: Counter[str] = Counter()
        active_qs = (
            UretimAsamasi.objects.filter(
                durum__in=("BEKLIYOR", "DEVAM_EDIYOR", "BEKLEMEDE"),
                uretim_emri__durum__in=("PLANLANDI", "BASLADI"),
            )
            .select_related("uretim_emri__recete")[:_MAX_ACTIVE_ASAMALAR]
        )
        rec_ids2 = {int(a.uretim_emri.recete_id) for a in active_qs}
        ro_map2 = _recete_operasyon_istasyon_map(rec_ids2)
        for asama in active_qs:
            active_counts[_istasyon_name_for_asama(asama, ro_map2)] += 1

        stations: set[str] = set(downtime_by_station) | set(active_counts)
        out: list[dict[str, Any]] = []
        for st in stations:
            dm = float(downtime_by_station.get(st, 0.0))
            aj = int(active_counts.get(st, 0))
            if dm < 1 and aj < 2:
                continue
            risk = "low"
            if dm >= 360 or aj >= 6:
                risk = "high"
            elif dm >= 120 or aj >= 3:
                risk = "medium"
            out.append(
                {
                    "station": st,
                    "downtime_minutes": round(dm, 1),
                    "active_jobs": aj,
                    "risk": risk,
                }
            )
        out.sort(key=lambda x: (-x["downtime_minutes"], -x["active_jobs"]))
        return out[:25]
    except Exception:
        logger.exception("get_station_bottlenecks failed")
        return []


def analyze_operation_performance(days: int = 30) -> list[dict[str, Any]]:
    """Tamamlanmış aşamalarda hedef (planlanan_sure) vs gerçek (gerceklesen_sure)."""
    try:
        from .models import UretimAsamasi

        days = max(1, min(int(days), 90))
        cutoff = _now() - timedelta(days=days)
        rows = (
            UretimAsamasi.objects.filter(
                durum="TAMAMLANDI",
                bitis_zamani__gte=cutoff,
                planlanan_sure__gt=0,
                gerceklesen_sure__isnull=False,
            )
            .values("ad")
            .annotate(
                target_minutes=Avg("planlanan_sure"),
                actual_minutes=Avg("gerceklesen_sure"),
                n=Count("id"),
            )
            .filter(n__gte=2)
            .order_by("-n")[:40]
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            t = float(r["target_minutes"] or 0)
            a = float(r["actual_minutes"] or 0)
            if t <= 0:
                continue
            ratio = round(a / t, 4) if t else 0.0
            status = "ok"
            if a > t * 1.25:
                status = "slow"
            elif a < t * 0.85:
                status = "fast"
            out.append(
                {
                    "operation": r["ad"] or "?",
                    "target_minutes": round(t, 2),
                    "actual_minutes": round(a, 2),
                    "performance_ratio": ratio,
                    "status": status,
                    "sample_count": int(r["n"] or 0),
                }
            )
        out.sort(key=lambda x: -x["performance_ratio"])
        return [x for x in out if x["status"] == "slow"][:20]
    except Exception:
        logger.exception("analyze_operation_performance failed")
        return []


def _bom_critical_for_recete(recete_id: int) -> bool:
    from .models import ReceteDetay, StokItem

    det_ids = list(
        ReceteDetay.objects.filter(recete_id=recete_id).values_list("stok_item_id", flat=True)[:80]
    )
    if not det_ids:
        return False
    return StokItem.objects.filter(
        pk__in=det_ids,
        stok_takip=True,
    ).filter(mevcut_miktar__lte=F("minimum_stok")).exists()


def predict_risky_orders() -> list[dict[str, Any]]:
    """
    Kural tabanlı risk: termin yakınlığı, geciken iş emri, BOM kritik stok, darboğaz istasyonu.
    """
    try:
        from .models import Recete, Siparis, SiparisKalemi, UretimAsamasi, UretimEmri

        today = timezone.localdate()
        horizon = today + timedelta(days=7)

        delayed_nos = {r["order_no"] for r in get_delayed_work_orders()}
        bneck = get_station_bottlenecks()
        hot_stations = {b["station"] for b in bneck[:8] if b.get("risk") in ("high", "medium")}

        sip_qs = (
            Siparis.objects.filter(siparis_durumu="ONAYLANDI")
            .exclude(teslimat_durumu="TESLIM_EDILDI")
            .order_by(F("tamamlanma_tarihi").asc(nulls_last=True))[:_MAX_SIPARIS_RISK_SCAN]
        )

        ro_map_cache: dict[int, dict[tuple[int, int], str | None]] = {}

        def station_of_current_stage(emir: UretimEmri) -> str | None:
            rid = int(emir.recete_id)
            if rid not in ro_map_cache:
                ro_map_cache[rid] = _recete_operasyon_istasyon_map({rid})
            ro_map = ro_map_cache[rid]
            asama = (
                UretimAsamasi.objects.filter(uretim_emri=emir)
                .exclude(durum="TAMAMLANDI")
                .order_by("sira", "id")
                .select_related("uretim_emri__recete")
                .first()
            )
            if not asama:
                return None
            return _istasyon_name_for_asama(asama, ro_map)

        out: list[dict[str, Any]] = []
        for sp in sip_qs:
            reasons: list[str] = []
            score = 0
            frag = f"Sipariş {sp.siparis_numarasi} için"
            emir = (
                UretimEmri.objects.filter(
                    aciklama__icontains=frag,
                    production_type="ORDER",
                )
                .exclude(durum__in=("TAMAMLANDI", "IPTAL"))
                .order_by("-id")
                .first()
            )

            if sp.tamamlanma_tarihi and sp.tamamlanma_tarihi <= horizon:
                score += 28
                reasons.append("Termin tarihi 7 gün içinde veya geçmiş.")

            if emir and emir.emir_no in delayed_nos:
                score += 32
                reasons.append("Bağlı iş emri gecikme analizinde öne çıkıyor.")

            if emir:
                st = station_of_current_stage(emir)
                if st and st in hot_stations:
                    score += 22
                    reasons.append(f"Aktif aşama darboğaz gözlenen istasyonda: {st}.")

                rid = int(emir.recete_id)
                if _bom_critical_for_recete(rid):
                    score += 26
                    reasons.append("Reçete bileşenlerinde kritik stok seviyesi var.")

            if not reasons:
                kalem = (
                    SiparisKalemi.objects.filter(siparis=sp, stok_item__isnull=False)
                    .select_related("stok_item")
                    .first()
                )
                if kalem and kalem.stok_item_id:
                    rc = Recete.objects.filter(urun_id=kalem.stok_item_id, aktif=True).first()
                    if rc and _bom_critical_for_recete(int(rc.pk)):
                        score += 20
                        reasons.append("Ürün reçetesinde kritik malzeme riski.")

            if score < 18:
                continue

            score = min(100, score)
            out.append(
                {
                    "order_no": sp.siparis_numarasi,
                    "risk_score": score,
                    "reasons": reasons[:6],
                    "delivery_date": sp.tamamlanma_tarihi.isoformat() if sp.tamamlanma_tarihi else None,
                    "production_status": sp.uretim_durumu,
                }
            )
        out.sort(key=lambda x: -int(x.get("risk_score") or 0))
        return out[:25]
    except Exception:
        logger.exception("predict_risky_orders failed")
        return []


def _narrative_delayed(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Şu an planlanan bitişini aşmış veya operasyon süresi belirgin şekilde uzamış açık iş emri bulunmuyor."
    top = items[0]
    return (
        f"{len(items)} adet gecikmeli veya riskli iş emri listeleniyor; en yüksek gecikme "
        f"{top.get('order_no')} için yaklaşık {top.get('delay_hours')} saat. "
        "Plan dışı süreler teslim ve kapasite planını etkileyebilir."
    )


def _narrative_bottlenecks(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Son dönemde istasyon bazlı anlamlı duruş veya iş yığılması sinyali görülmüyor."
    b = items[0]
    return (
        f"{b.get('station')} istasyonunda son {_DURUS_WINDOW_DAYS} günde yaklaşık "
        f"{b.get('downtime_minutes')} dakika duruş ve {b.get('active_jobs')} açık iş/aşama birikimi var. "
        "Bu tip yoğunluk teslim sürelerini aşağı çekebilir."
    )


def _narrative_performance(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Seçilen dönemde hedef süreye göre anlamlı şekilde yavaşladığı görülen operasyon tipi yok."
    op = items[0]
    return (
        f"'{op.get('operation')}' operasyonunda gerçek süre hedefin üzerinde (oran {op.get('performance_ratio')}). "
        "Kapasite, kurulum veya bekletme kaynaklı olabilir; detay için üretim kayıtlarına bakılmalı."
    )


def _narrative_risky(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Kural setine göre öncelikli risk skoru yüksek sipariş tespit edilmedi."
    r = items[0]
    return (
        f"En yüksek risk {r.get('order_no')} (skor {r.get('risk_score')}). "
        "Termin, üretim gecikmesi veya malzeme/istasyon riskleri bir araya gelmiş olabilir."
    )


def run_production_intelligence_analysis(
    analysis: str,
    days: int = 30,
) -> dict[str, Any]:
    """
    TEKORA tool çıktısı: ham liste + model için kısa yönetici özeti (Türkçe).
    analysis: delayed | bottlenecks | performance | risky_orders (ve Türkçe eş anlamlılar)
    """
    raw = (analysis or "").strip().lower()
    try:
        if (
            raw in ("delayed", "geciken")
            or "geciken" in raw
            or "problemli iş" in raw
            or "problemli is" in raw
        ):
            items = get_delayed_work_orders()
            narrative = _narrative_delayed(items)
            return {
                "status": "ok",
                "analysis_type": "delayed_work_orders",
                "executive_summary": narrative,
                "guidance": (
                    "Kullanıcıya önce executive_summary ile bir cümlelik yorum ver; "
                    "ardından tablo/liste halinde önemli 3-5 kalemi özetle. Ham JSON'u satır satır okuma."
                ),
                "items": items,
            }
        if raw in ("bottlenecks", "stations", "darbogaz") or "darbo" in raw:
            items = get_station_bottlenecks()
            narrative = _narrative_bottlenecks(items)
            return {
                "status": "ok",
                "analysis_type": "station_bottlenecks",
                "executive_summary": narrative,
                "guidance": (
                    "İstasyon yoğunluğu ve duruşları yorumla; kullanıcıya aksiyon önermeden önce veriye dayan."
                ),
                "items": items,
            }
        if raw in ("risky_orders", "risky") or ("riskli" in raw and "sipari" in raw):
            items = predict_risky_orders()
            narrative = _narrative_risky(items)
            return {
                "status": "ok",
                "analysis_type": "risky_orders",
                "executive_summary": narrative,
                "guidance": "Risk skorunu ve reasons alanlarını kullanarak net, kısa bir özet ver.",
                "items": items,
            }
        if raw == "performance" or "performans" in raw:
            items = analyze_operation_performance(days=days)
            narrative = _narrative_performance(items)
            return {
                "status": "ok",
                "analysis_type": "operation_performance",
                "executive_summary": narrative,
                "guidance": (
                    "Hedef ve gerçek süre farkını açıkla; yavaş operasyonları önceliklendir."
                ),
                "items": items,
                "days": int(days),
            }
        return {
            "status": "error",
            "error": "Geçersiz analysis. delayed | bottlenecks | performance | risky_orders",
            "items": [],
        }
    except Exception as exc:
        logger.exception("run_production_intelligence_analysis failed")
        return {
            "status": "error",
            "error": str(exc)[:500],
            "items": [],
        }
