"""
TEKORA CNC / Tool Intelligence — takım ömrü, malzeme, operasyon ve marka analizi (salt okunur ORM).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

_MAX_FINISHED_LIVES = 450
_MAX_TOOLS_AGG = 200
_MAX_USAGE_TASK_GROUPS = 80
_MAX_BRANDS = 20
_DEFAULT_MATERIALS = ("2379", "4140", "1040", "ST", "paslanmaz", "316", "304")


def _now():
    return timezone.now()


def _float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _life_duration_minutes(lc) -> float | None:
    if not lc.start_date or not lc.end_date:
        return None
    return max(0.0, (lc.end_date - lc.start_date).total_seconds() / 60.0)


def analyze_tool_lifetimes() -> list[dict[str, Any]]:
    """
    Bitmiş ömürlerden ortalama süre, bileme sayısı, kullanım kaydı sayısı; kısa ömür → critical/warning.
    """
    try:
        from .models import Tool, ToolLifeCycle, ToolUsageLog

        qs = (
            ToolLifeCycle.objects.filter(status="finished", end_date__isnull=False)
            .select_related("tool")
            .order_by("-end_date")[:_MAX_FINISHED_LIVES]
        )
        by_tool: dict[int, dict[str, Any]] = {}
        for lc in qs:
            tid = int(lc.tool_id)
            if tid not in by_tool:
                by_tool[tid] = {
                    "tool": lc.tool.tool_code,
                    "brand": (lc.tool.brand or "").strip() or None,
                    "durations": [],
                    "regrind_finishes": 0,
                    "broken_finishes": 0,
                }
            mins = _life_duration_minutes(lc)
            if mins is not None:
                by_tool[tid]["durations"].append(mins)
            if lc.change_reason == "regrind":
                by_tool[tid]["regrind_finishes"] += 1
            if lc.change_reason == "broken":
                by_tool[tid]["broken_finishes"] += 1

        usage_counts = dict(
            ToolUsageLog.objects.filter(tool_id__in=list(by_tool.keys())[:_MAX_TOOLS_AGG])
            .values("tool_id")
            .annotate(n=Count("id"))
            .values_list("tool_id", "n")[:500]
        )

        regrind_totals = dict(
            ToolLifeCycle.objects.filter(tool_id__in=list(by_tool.keys()), change_reason="regrind")
            .values("tool_id")
            .annotate(n=Count("id"))
            .values_list("tool_id", "n")[:500]
        )

        global_avgs: list[float] = []
        for d in by_tool.values():
            for x in d["durations"]:
                global_avgs.append(x)
        median_floor = sorted(global_avgs)[len(global_avgs) // 2] if global_avgs else 0.0

        rows: list[dict[str, Any]] = []
        for tid, data in by_tool.items():
            durs = data["durations"]
            if not durs:
                continue
            avg_m = sum(durs) / len(durs)
            short = min(durs)
            uc = int(usage_counts.get(tid, 0))
            rg = int(regrind_totals.get(tid, data["regrind_finishes"]))
            status = "ok"
            if avg_m < max(30.0, median_floor * 0.35) or short < max(15.0, median_floor * 0.2):
                status = "critical"
            elif avg_m < median_floor * 0.55 or data["broken_finishes"] > 0:
                status = "warning"

            post_regrind_drop = None
            if len(durs) >= 4 and rg >= 2:
                first = sum(durs[:2]) / 2
                last = sum(durs[-2:]) / 2
                if first > 1 and last < first * 0.75:
                    post_regrind_drop = round(last / first, 3)

            rows.append(
                {
                    "tool": data["tool"],
                    "brand": data["brand"],
                    "avg_lifetime_minutes": round(avg_m, 2),
                    "shortest_lifetime_minutes": round(short, 2),
                    "usage_count": uc,
                    "regrind_count": rg,
                    "post_regrind_performance_ratio": post_regrind_drop,
                    "status": status,
                }
            )
        rows.sort(key=lambda x: (0 if x["status"] == "critical" else 1 if x["status"] == "warning" else 2, x["avg_lifetime_minutes"]))
        return rows[:35]
    except Exception:
        logger.exception("analyze_tool_lifetimes failed")
        return []


def analyze_material_tool_performance(material_hint: str | None = None) -> list[dict[str, Any]]:
    """Malzeme (ToolUsageLog.material) bazında kullanım ve ömür özeti."""
    try:
        from .models import ToolLifeCycle, ToolMaterial, ToolUsageLog

        mats = list(
            ToolMaterial.objects.filter(name__isnull=False).values_list("id", "name")[:200]
        )
        target_names: set[str] = set()
        if material_hint:
            hint = material_hint.strip().lower()
            for _pk, name in mats:
                if name and hint in name.lower():
                    target_names.add(name)
            if not target_names:
                target_names.add(material_hint.strip())
        else:
            for _pk, name in mats:
                if not name:
                    continue
                up = name.upper()
                for token in _DEFAULT_MATERIALS:
                    if token.upper() in up or up in token.upper():
                        target_names.add(name)
                        break

        if not target_names:
            for token in _DEFAULT_MATERIALS:
                tm = ToolMaterial.objects.filter(name__icontains=token).first()
                if tm:
                    target_names.add(tm.name)

        rows: list[dict[str, Any]] = []
        for mat_name in sorted(target_names)[:12]:
            logs = ToolUsageLog.objects.filter(material__name=mat_name)
            agg = logs.aggregate(
                usage_n=Count("id"),
                tool_count=Count("tool_id", distinct=True),
            )
            usage_n = min(int(agg.get("usage_n") or 0), 5000)
            tool_count = int(agg.get("tool_count") or 0)
            if usage_n == 0:
                continue
            tool_ids = list(logs.values_list("tool_id", flat=True).distinct()[:120])

            life_qs = ToolLifeCycle.objects.filter(
                tool_id__in=tool_ids,
                status="finished",
                end_date__isnull=False,
            ).order_by("-end_date")[:200]
            durs: list[float] = []
            for lc in life_qs:
                m = _life_duration_minutes(lc)
                if m is not None:
                    durs.append(m)
            avg_life = round(sum(durs) / len(durs), 2) if durs else None

            risk = "low"
            if avg_life is not None and avg_life < 180:
                risk = "high"
            elif avg_life is not None and avg_life < 400:
                risk = "medium"
            elif tool_count >= 8 and usage_n >= 200:
                risk = "medium"

            rows.append(
                {
                    "material": mat_name,
                    "tool_count": tool_count,
                    "usage_log_count": min(usage_n, 5000),
                    "avg_lifetime": avg_life,
                    "risk": risk,
                }
            )
        rows.sort(key=lambda x: (0 if x["risk"] == "high" else 1 if x["risk"] == "medium" else 2, -(x.get("avg_lifetime") or 0)))
        return rows[:20]
    except Exception:
        logger.exception("analyze_material_tool_performance failed")
        return []


def detect_problematic_operations(days: int = 90) -> list[dict[str, Any]]:
    """Aşama bazında yoğun takım kullanımı / çoklu takım değişimi (proxy: usage log sayısı)."""
    try:
        from .models import ToolUsageLog

        days = max(7, min(int(days), 180))
        cutoff = _now() - timedelta(days=days)
        grouped = (
            ToolUsageLog.objects.filter(created_at__gte=cutoff)
            .values("task_id", "task__ad")
            .annotate(
                log_count=Count("id"),
                distinct_tools=Count("tool_id", distinct=True),
                total_cut=Sum("cutting_mm"),
            )
            .order_by("-log_count")[:_MAX_USAGE_TASK_GROUPS]
        )
        task_ids = [r["task_id"] for r in grouped if r.get("task_id")]
        broken_by_task: dict[int, int] = defaultdict(int)
        if task_ids:
            for row in (
                ToolUsageLog.objects.filter(task_id__in=task_ids, tool__status="broken")
                .values("task_id")
                .annotate(n=Count("id"))
            ):
                broken_by_task[int(row["task_id"])] = int(row["n"])

        rows: list[dict[str, Any]] = []
        for r in grouped:
            tid = r.get("task_id")
            if not tid:
                continue
            op_name = r.get("task__ad") or f"task_{tid}"
            lc = int(r.get("log_count") or 0)
            dt = int(r.get("distinct_tools") or 0)
            br = int(broken_by_task.get(int(tid), 0))
            avg_cut = _float(r.get("total_cut")) / lc if lc else 0.0

            risk = "low"
            if lc >= 45 or dt >= 10 or br >= 2:
                risk = "high"
            elif lc >= 25 or dt >= 6 or br >= 1:
                risk = "medium"

            rows.append(
                {
                    "operation": op_name,
                    "task_id": int(tid),
                    "tool_changes": lc,
                    "distinct_tools": dt,
                    "broken_usage_events": br,
                    "avg_cutting_mm_per_log": round(avg_cut, 4),
                    "avg_lifetime": None,
                    "risk": risk,
                }
            )
        rows.sort(key=lambda x: (0 if x["risk"] == "high" else 1 if x["risk"] == "medium" else 2, -x["tool_changes"]))
        return rows[:25]
    except Exception:
        logger.exception("detect_problematic_operations failed")
        return []


def compare_tool_brands() -> list[dict[str, Any]]:
    """Marka bazlı bitmiş ömür ortalaması ve basit verim / başarısızlık skoru."""
    try:
        from .models import Tool, ToolLifeCycle

        brand_rows = (
            Tool.objects.exclude(brand="")
            .values("brand")
            .annotate(tool_n=Count("id"))
            .order_by("-tool_n")[:_MAX_BRANDS]
        )
        out: list[dict[str, Any]] = []
        for br in brand_rows:
            brand = (br.get("brand") or "").strip()
            if not brand:
                continue
            tool_ids = list(
                Tool.objects.filter(brand=brand).values_list("pk", flat=True)[:80]
            )
            if not tool_ids:
                continue
            lives = ToolLifeCycle.objects.filter(
                tool_id__in=tool_ids,
                status="finished",
                end_date__isnull=False,
            ).order_by("-end_date")[:250]
            durs: list[float] = []
            fail = 0
            total = 0
            for lc in lives:
                total += 1
                m = _life_duration_minutes(lc)
                if m is not None:
                    durs.append(m)
                if lc.change_reason in ("broken", "worn"):
                    fail += 1
            avg_life = round(sum(durs) / len(durs), 2) if durs else None
            fail_rate = fail / total if total else 0.0
            eff = 50.0
            if avg_life:
                eff += min(40.0, avg_life / 30.0)
            eff -= min(45.0, fail_rate * 100)
            eff = max(5.0, min(100.0, round(eff, 1)))
            status = "good"
            if eff < 40 or fail_rate > 0.35:
                status = "poor"
            elif eff < 60 or fail_rate > 0.2:
                status = "mixed"

            out.append(
                {
                    "brand": brand,
                    "tool_count": int(br.get("tool_n") or 0),
                    "finished_lives_sampled": total,
                    "avg_lifetime": avg_life,
                    "failure_rate": round(fail_rate, 4),
                    "efficiency_score": eff,
                    "status": status,
                }
            )
        out.sort(key=lambda x: -float(x.get("efficiency_score") or 0))
        return out[:20]
    except Exception:
        logger.exception("compare_tool_brands failed")
        return []


def _narrative_lifetimes(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Yeterli takım ömrü kapanış kaydı yok; önce üretimde kullanım ve ömür kapanışı birikmeli."
    c = sum(1 for x in items if x.get("status") == "critical")
    has_drop = any(x.get("post_regrind_performance_ratio") is not None for x in items)
    parts = [
        f"{len(items)} takım için özet ömür verisi üretildi; {c} adet kritik/çok kısa ömür sinyali var."
    ]
    if has_drop:
        parts.append(
            "Bazı takımlarda bileme sonrası ömür kısalması (performans düşüşü) izleniyor; kesme yükü veya bileme kalitesi gözden geçirilebilir."
        )
    else:
        parts.append("Kırılma veya aşırı aşınma paterni için değişim kayıtları ve takım statüsü ile birlikte değerlendirin.")
    return " ".join(parts)


def _narrative_material(items: list[dict[str, Any]], hint: str | None) -> str:
    if not items:
        h = f" ({hint})" if hint else ""
        return f"Seçilen malzemeler için kullanım kaydı bulunamadı{h}."
    hi = [x for x in items if x.get("risk") == "high"]
    if hi:
        return (
            f"{hi[0].get('material')} malzemesinde takım ömrü düşük görünüyor; "
            "yüksek kesme hacmi veya sert malzeme kombinasyonu aşınmayı artırmış olabilir."
        )
    return "Malzeme grupları arasında belirgin risk farkı yok; yine de en yoğun kullanılan malzemeleri izlemeye devam edin."


def _narrative_operations(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Son dönemde anlamlı takım kullanım yoğunluğu görülen operasyon yok."
    top = items[0]
    if top.get("risk") == "high":
        return (
            f"{top.get('operation')} operasyonunda sık takım kullanım kaydı var; "
            "takım kırılmaları veya erken değişimler yüksek olabilir. Program, ısıl veya takım seçimi gözden geçirilebilir."
        )
    return "Bazı operasyonlarda kullanım yoğunluğu artmış; önleyici bakım ve takım standardizasyonu faydalı olabilir."


def _narrative_brands(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Marka karşılaştırması için yeterli kapanmış ömür verisi yok."
    best = items[0]
    worst = items[-1] if len(items) > 1 else None
    msg = f"Özet skora göre en iyi performans {best.get('brand')} (skor {best.get('efficiency_score')})."
    if worst and worst.get("efficiency_score", 100) < best.get("efficiency_score", 0) - 15:
        msg += f" {worst.get('brand')} markasında başarısızlık oranı veya kısa ömür daha yüksek görünebilir."
    return msg


def extract_tool_material_hint(message: str) -> str | None:
    t = message or ""
    low = t.lower()
    m = re.search(r"\b(2379|4140|1040|316|304)\b", t, re.I)
    if m:
        return m.group(1)
    if "paslanmaz" in low:
        return "paslanmaz"
    if re.search(r"\bST\b", t):
        return "ST"
    return None


def run_tool_intelligence_analysis(
    analysis: str,
    *,
    material_hint: str | None = None,
    days: int = 90,
) -> dict[str, Any]:
    """
    analysis: lifetimes | material | operations | brands
    """
    raw = (analysis or "").strip().lower()
    try:
        if raw in ("lifetimes", "lifetime", "omur", "ömür", "tool_lifetime"):
            items = analyze_tool_lifetimes()
            return {
                "status": "ok",
                "analysis_type": "tool_lifetimes",
                "executive_summary": _narrative_lifetimes(items),
                "guidance": (
                    "Önce executive_summary ile kısa yorum; ardından kritik/uyarı takımları 3-5 madde ile özetle. "
                    "Takım kırılması veya bileme sonrası düşüş için post_regrind_performance_ratio alanına değin."
                ),
                "items": items,
            }
        if raw in ("material", "malzeme", "material_performance"):
            items = analyze_material_tool_performance(material_hint)
            return {
                "status": "ok",
                "analysis_type": "material_tool_performance",
                "executive_summary": _narrative_material(items, material_hint),
                "guidance": "Malzeme bazlı risk ve avg_lifetime değerlerini kullanıcı dilinde özetle.",
                "items": items,
                "material_hint": material_hint,
            }
        if raw in ("operations", "operation", "problemli_operasyon"):
            items = detect_problematic_operations(days=days)
            return {
                "status": "ok",
                "analysis_type": "problematic_operations",
                "executive_summary": _narrative_operations(items),
                "guidance": "tool_changes ve distinct_tools ile sık değişim hikâyesini anlat; abartılı kesin iddia kullanma.",
                "items": items,
                "days": int(days),
            }
        if raw in ("brands", "brand", "marka", "markalar"):
            items = compare_tool_brands()
            return {
                "status": "ok",
                "analysis_type": "tool_brands",
                "executive_summary": _narrative_brands(items),
                "guidance": "efficiency_score ve failure_rate ile marka karşılaştırması yap; ham tablo okutma.",
                "items": items,
            }
        return {
            "status": "error",
            "error": "Geçersiz analysis: lifetimes | material | operations | brands",
            "items": [],
        }
    except Exception as exc:
        logger.exception("run_tool_intelligence_analysis failed")
        return {"status": "error", "error": str(exc)[:500], "items": []}
