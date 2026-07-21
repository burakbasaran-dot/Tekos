"""
Enerji Yönetim Paneli — demo özet API ve dashboard.

İlk faz: gerçek cihaz yok; JSON demo veri + hafif zaman bazlı titreşim (yenilemede canlılık).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from .nav_visibility import NAV_KEY_ENERJI_YONETIM, hidden_nav_access_required

# Enerji transfer switch (ATS demo) — hat listesi
TRANSFER_SWITCH_SPECS: tuple[dict[str, str], ...] = (
    {"id": "cnc_torna", "hat_adi": "CNC Torna"},
    {"id": "cnc_freze", "hat_adi": "CNC Freze"},
    {"id": "arac_sarj", "hat_adi": "Araç Şarj İstasyonu"},
    {"id": "atolye_ust", "hat_adi": "Atölye ve Üst Katlar"},
)

SESSION_TRANSFER_SWITCH_KEY = "enerji_transfer_switch_demo"
SESSION_HAFTALIK_PLAN_KEY = "enerji_haftalik_plan_demo"

_enerji_nav_guard = hidden_nav_access_required(NAV_KEY_ENERJI_YONETIM)


def _ensure_demo_switch_session(request, wobble: float) -> dict:
    """Oturumda demo switch durumu; gerçek donanım yok."""
    data = request.session.get(SESSION_TRANSFER_SWITCH_KEY)
    if not isinstance(data, dict):
        data = {}
    defaults = (
        ("sebeke", 8.2, "normal"),
        ("batarya", 5.4, "normal"),
        ("sebeke", 6.8, "uyari"),
        ("batarya", 3.9, "normal"),
    )
    changed = False
    for spec, (ak, gbase, du) in zip(TRANSFER_SWITCH_SPECS, defaults):
        sid = spec["id"]
        if sid not in data:
            data[sid] = {
                "aktif_kaynak": ak,
                "guc_base": float(gbase + wobble * 0.35),
                "durum": du,
            }
            changed = True
    if changed:
        request.session[SESSION_TRANSFER_SWITCH_KEY] = data
        request.session.modified = True
    return data


def _transfer_switches_for_api(request, wobble: float, t: float) -> list[dict]:
    sess = _ensure_demo_switch_session(request, wobble)
    out: list[dict] = []
    for spec in TRANSFER_SWITCH_SPECS:
        sid = spec["id"]
        row = sess[sid]
        ak = row.get("aktif_kaynak", "kapali")
        gbase = float(row.get("guc_base", 0))
        durum = row.get("durum", "normal")
        if ak == "kapali":
            gkw = 0.0
        else:
            phase = (hash(sid) % 10) * 0.37
            gkw = round(max(0, gbase + 0.28 * math.sin(t / 3.0 + phase)), 2)
        out.append(
            {
                "id": sid,
                "hat_adi": spec["hat_adi"],
                "aktif_kaynak": ak,
                "guc_kw": gkw,
                "durum": durum,
            }
        )
    return out


def _week_monday() -> dt.date:
    bugun = dt.date.today()
    return bugun - dt.timedelta(days=bugun.weekday())


def _aktif_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).lower()
    return s in ("aktif", "true", "1", "on", "evet")


def _default_calisma_plan_rows() -> list[dict]:
    """
    Haftalık çalışma planı — demo varsayılan.
    Şema (ileride DB): tarih, gun, *_aktif bool, planlanan_uretim_yogunlugu, not.
    """
    mon = _week_monday()
    gun_adlari = (
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
        "Pazar",
    )
    sablon: tuple[tuple[str, str, str, str, str, str], ...] = (
        ("aktif", "aktif", "aktif", "aktif", "yuksek", "Tam kapasite üretim; vardiya sonunda hat kapatma kontrolü."),
        ("aktif", "aktif", "pasif", "aktif", "orta", "Araç şarjı geceye kaydırıldı; CNC hatları normal."),
        ("aktif", "pasif", "aktif", "aktif", "orta", "Freze bakım penceresi; torna ve atölye açık."),
        ("aktif", "aktif", "aktif", "pasif", "yuksek", "Üst katlar minimum aydınlatma; üretim zemin katta."),
        ("aktif", "aktif", "aktif", "aktif", "yuksek", "Cuma yoğun çıkış; kompresör kullanımı öğleden sonra."),
        ("pasif", "pasif", "aktif", "pasif", "dusuk", "Cumartesi nöbet; yalnızca araç şarj ve kritik atölye."),
        ("pasif", "pasif", "pasif", "pasif", "dusuk", "Pazar kapalı; yalnızca güvenlik ve IT yükleri."),
    )
    rows: list[dict] = []
    for i in range(7):
        d = mon + dt.timedelta(days=i)
        t, f, a, ato, yg, nt = sablon[i]
        rows.append(
            {
                "tarih": d.isoformat(),
                "gun": gun_adlari[d.weekday()],
                "cnc_torna_aktif": _aktif_bool(t),
                "cnc_freze_aktif": _aktif_bool(f),
                "arac_sarj_istasyonu_aktif": _aktif_bool(a),
                "atolye_ve_ust_katlar_aktif": _aktif_bool(ato),
                "planlanan_uretim_yogunlugu": yg,
                "not": nt,
            }
        )
    return rows


def _demo_soc_now() -> int:
    t = time.time()
    wobble = 0.5 * math.sin(t / 12.0)
    return int(max(15, min(100, round(76 + wobble * 3))))


def _merge_calisma_plan_from_session(request) -> list[dict]:
    """Oturumdaki kullanıcı düzenlemeleri + demo varsayılan (ileride ORM ile değiştirilecek)."""
    base = _default_calisma_plan_rows()
    raw = request.session.get(SESSION_HAFTALIK_PLAN_KEY)
    if not isinstance(raw, list):
        return base
    overrides = {
        item["tarih"]: item for item in raw if isinstance(item, dict) and item.get("tarih")
    }
    out: list[dict] = []
    for row in base:
        tr = row["tarih"]
        o = overrides.get(tr)
        if not o:
            out.append(dict(row))
            continue
        merged = dict(row)
        for k in (
            "cnc_torna_aktif",
            "cnc_freze_aktif",
            "arac_sarj_istasyonu_aktif",
            "atolye_ve_ust_katlar_aktif",
        ):
            if k in o:
                merged[k] = bool(o[k])
        if "planlanan_uretim_yogunlugu" in o and o["planlanan_uretim_yogunlugu"] in (
            "dusuk",
            "orta",
            "yuksek",
        ):
            merged["planlanan_uretim_yogunlugu"] = o["planlanan_uretim_yogunlugu"]
        if "not" in o and isinstance(o["not"], str):
            merged["not"] = o["not"][:2000]
        out.append(merged)
    return out


def _compute_planlama_ozet(request) -> dict:
    """Dashboard özet kartı (tek seferlik yükleme)."""
    soc = _demo_soc_now()
    hava = _weekly_hava_gunes(soc)
    calisma = _merge_calisma_plan_from_session(request)
    c_map = {r["tarih"]: r for r in calisma}

    sunniest = max(hava, key=lambda r: r["tahmini_guneslenme_saat"])
    en_gunesli = (
        f"{sunniest['gun']} ({sunniest['tarih']}) — "
        f"~{sunniest['tahmini_guneslenme_saat']} saat güneşlenme"
    )

    ev_candidates = [
        h
        for h in hava
        if c_map.get(h["tarih"], {}).get("arac_sarj_istasyonu_aktif")
    ]
    if ev_candidates:
        best_ev = max(ev_candidates, key=lambda r: r["tahmini_guneslenme_saat"])
        en_uygun_arac = (
            f"{best_ev['gun']} ({best_ev['tarih']}) — "
            f"{best_ev['tahmini_guneslenme_saat']} saat, {best_ev['hava_durumu']}"
        )
    else:
        en_uygun_arac = (
            "Haftalık planda araç şarjı aktif gün yok; şarj penceresi için "
            "planlama sayfasında ilgili günleri işaretleyin."
        )

    cnc_days = [
        c
        for c in calisma
        if c.get("planlanan_uretim_yogunlugu") == "yuksek"
        and c.get("cnc_torna_aktif")
        and c.get("cnc_freze_aktif")
    ]
    if cnc_days:
        d0 = cnc_days[0]
        cnc_yogun = f"{d0['gun']} ({d0['tarih']}) — yüksek yoğunluk, torna + freze aktif"
    else:
        cnc_yogun = (
            "Tam kriterlere uyan yoğun CNC günü yok; planlama tablosundan "
            "yoğunluk ve CNC satırlarını güncelleyebilirsiniz."
        )

    if soc < 25:
        bat_uyari = (
            f"Batarya SOC %{soc} ile kritik düşük: yüksek tüketimli işleri şebekeye kaydırın, "
            "araç şarjını sınırlayın."
        )
    elif soc < 45:
        bat_uyari = (
            f"Batarya SOC %{soc} orta seviyede: bulutlu günlerde CNC’yi şebeke ağırlıklı "
            "çalıştırmayı ve şarj pencerelerini daraltmayı düşünün."
        )
    else:
        bat_uyari = (
            f"Batarya SOC %{soc} kabul edilebilir aralıkta; yine de haftalık güneş tahminiyle "
            "yük dengelemesini sürdürün."
        )

    return {
        "en_gunesli_gun": en_gunesli,
        "en_uygun_arac_sarj_gunu": en_uygun_arac,
        "cnc_yogun_onerilen_gun": cnc_yogun,
        "batarya_koruma_uyarisi": bat_uyari,
    }


def _weekly_hava_gunes(batarya_soc: int) -> list[dict]:
    """Haftalık hava ve güneşlenme tahmini (demo) + öneri metni."""
    mon = _week_monday()
    gun_adlari = (
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
        "Pazar",
    )
    # (hava_kisa, gunes_saat, solar_seviye) — seviye: dusuk|orta|yuksek
    sablon: tuple[tuple[str, float, str], ...] = (
        ("Güneşli", 8.5, "yuksek"),
        ("Az bulutlu", 7.2, "orta"),
        ("Parçalı bulutlu", 5.1, "orta"),
        ("Bulutlu", 3.4, "dusuk"),
        ("Sağanak yağışlı", 2.0, "dusuk"),
        ("Parçalı güneşli", 6.0, "orta"),
        ("Açık", 7.8, "yuksek"),
    )
    batarya_dusuk = batarya_soc < 35
    rows: list[dict] = []
    for i in range(7):
        d = mon + dt.timedelta(days=i)
        hava, gs, sev = sablon[i]
        weekend = d.weekday() >= 5
        oneri = _demo_hava_oneri(hava, sev, weekend, batarya_dusuk)
        rows.append(
            {
                "tarih": d.isoformat(),
                "gun": gun_adlari[d.weekday()],
                "hava_durumu": hava,
                "tahmini_guneslenme_saat": round(gs, 1),
                "tahmini_solar_seviye": sev,
                "enerji_yonetim_onerisi": oneri,
            }
        )
    return rows


def _demo_hava_oneri(
    hava: str,
    solar_seviye: str,
    weekend: bool,
    batarya_dusuk: bool,
) -> str:
    """Kullanıcı tarafından verilen örnek cümlelere yakın demo öneriler."""
    h = hava.lower()
    if weekend and batarya_dusuk:
        return "Hafta sonu üretim yoksa bataryayı kritik yüklere ayır."
    if batarya_dusuk and solar_seviye == "dusuk":
        return "Batarya düşükse araç şarjını sınırla."
    if solar_seviye == "yuksek" or "güneşli" in h or h == "açık":
        return "Güneşli günlerde araç şarjını gündüze planla."
    if solar_seviye == "dusuk" or "bulut" in h or "yağış" in h:
        return "Bulutlu günlerde CNC yüklerini şebeke ağırlıklı çalıştır."
    if batarya_dusuk:
        return "Batarya düşükse araç şarjını sınırla."
    return "Güneş tahminini günlük güncelleyerek batarya ve yük dengesini koruyun."


def _fallback_transfer_switches() -> list[dict]:
    return [
        {
            "id": s["id"],
            "hat_adi": s["hat_adi"],
            "aktif_kaynak": "kapali",
            "guc_kw": 0.0,
            "durum": "devre_disi",
        }
        for s in TRANSFER_SWITCH_SPECS
    ]


def _enerji_demo_payload(request) -> dict:
    """Demo enerji özeti; gerçek entegrasyonda bu yapı korunup kaynak değiştirilir."""
    t = time.time()
    wobble = 0.5 * math.sin(t / 12.0)

    grid_status = "var"
    voltage = round(398 + wobble * 2, 1)
    frequency = round(50.0 + wobble * 0.05, 2)
    grid_kw = round(max(0, 12.4 + wobble * 1.5), 2)

    fronius_kw = round(max(0, 18.6 + wobble * 2), 1)
    deye_kw = round(max(0, 4.2 + wobble * 0.8), 1)
    solar_total = round(fronius_kw + deye_kw, 1)

    soc = int(max(15, min(100, round(76 + wobble * 3))))
    bat_v = round(52.4 + wobble * 0.2, 1)
    bat_power = round(-3.5 + wobble * 0.6, 2)
    if bat_power < 0:
        bat_mode = "şarj oluyor"
        est_h = round(max(0.5, 8.0 - soc / 14 + wobble), 1)
    else:
        bat_mode = "deşarj oluyor"
        est_h = round(max(0.5, soc / 18 + wobble), 1)

    total_cons = round(max(2, 16.8 + wobble * 1.2), 1)
    critical_kw = round(max(1, 7.2 + wobble * 0.4), 1)
    ev_kw = round(max(0, 5.5 + wobble * 0.9), 1)
    compressor_active = abs(wobble) > 0.35

    solar_to_site = round(min(solar_total, total_cons) * 0.55 + wobble, 1)
    if bat_power < 0:
        solar_to_bat = round(max(0.1, -bat_power + wobble * 0.15), 1)
    else:
        solar_to_bat = 0.0
    battery_to_site = round(max(0, bat_power) if bat_power > 0 else 0.0, 1)
    grid_to_site = round(max(0, grid_kw), 1)
    battery_to_ev = round(min(ev_kw, max(0, ev_kw * 0.35 + wobble)), 1)

    alerts: list[str] = []
    if grid_status != "var":
        alerts.append("Şebeke kesildi")
    if soc < 25:
        alerts.append("Batarya düşük")
    if solar_total > total_cons + 3:
        alerts.append("Solar üretim tüketimden yüksek")
    if ev_kw > 1:
        alerts.append("Araç şarj cihazı aktif")
    if compressor_active:
        alerts.append("Kompresör devrede")
    if deye_kw > 18:
        alerts.append("DEYE aşırı yükte")
    if fronius_kw < 0.5:
        alerts.append("Fronius devre dışı")
    if bat_power < 0:
        alerts.append("Batarya şarj oluyor")
    if not alerts:
        alerts.append("Önemli uyarı yok")

    return {
        "grid": {
            "status": grid_status,
            "voltage": voltage,
            "frequency": frequency,
            "power_kw": grid_kw,
        },
        "solar": {
            "fronius_kw": fronius_kw,
            "deye_kw": deye_kw,
            "total_kw": solar_total,
        },
        "battery": {
            "soc": soc,
            "voltage": bat_v,
            "power_kw": bat_power,
            "mode": bat_mode,
            "estimated_hours": est_h,
        },
        "consumption": {
            "total_kw": total_cons,
            "critical_load_kw": critical_kw,
            "ev_charger_kw": ev_kw,
            "compressor_active": compressor_active,
        },
        "flows": {
            "solar_to_site_kw": max(0, solar_to_site),
            "solar_to_battery_kw": max(0, solar_to_bat),
            "battery_to_site_kw": max(0, battery_to_site),
            "grid_to_site_kw": max(0, grid_to_site),
            "battery_to_ev_kw": max(0, battery_to_ev),
        },
        "alerts": alerts,
        "transfer_switches": _transfer_switches_for_api(request, wobble, t),
        "meta": {
            "demo": True,
            "updated_ts": int(t),
            "hafta_baslangic": _week_monday().isoformat(),
        },
    }


@login_required
@_enerji_nav_guard
def enerji_dashboard(request):
    return render(
        request,
        "stokapp/enerji_dashboard.html",
        {
            "api_url": reverse("stokapp:api_enerji_ozet"),
            "switch_demo_url": reverse("stokapp:api_enerji_transfer_switch_demo"),
            "planlama_ozet_url": reverse("stokapp:api_enerji_planlama_ozet"),
            "planlama_page_url": reverse("stokapp:enerji_planlama"),
        },
    )


@login_required
@_enerji_nav_guard
def api_enerji_ozet(request):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        return JsonResponse(_enerji_demo_payload(request))
    except Exception:
        return JsonResponse(
            {
                "grid": {"status": "?", "voltage": 0, "frequency": 0, "power_kw": 0},
                "solar": {"fronius_kw": 0, "deye_kw": 0, "total_kw": 0},
                "battery": {
                    "soc": 0,
                    "voltage": 0,
                    "power_kw": 0,
                    "mode": "bilinmiyor",
                    "estimated_hours": 0,
                },
                "consumption": {
                    "total_kw": 0,
                    "critical_load_kw": 0,
                    "ev_charger_kw": 0,
                    "compressor_active": False,
                },
                "flows": {
                    "solar_to_site_kw": 0,
                    "solar_to_battery_kw": 0,
                    "battery_to_site_kw": 0,
                    "grid_to_site_kw": 0,
                    "battery_to_ev_kw": 0,
                },
                "alerts": ["Veri üretilemedi"],
                "transfer_switches": _fallback_transfer_switches(),
                "meta": {"demo": True, "error": True},
            }
        )


@login_required
@_enerji_nav_guard
@require_POST
def api_enerji_transfer_switch_demo(request):
    """
    Demo: transfer switch kaynağını oturumda günceller (cihaz kontrolü yok).
    JSON: {"switch_id": "cnc_torna", "action": "sebeke"|"batarya"|"kapat"}
    """
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Geçersiz JSON"}, status=400)

    switch_id = body.get("switch_id")
    action = body.get("action")
    valid_ids = {s["id"] for s in TRANSFER_SWITCH_SPECS}
    if switch_id not in valid_ids:
        return JsonResponse({"ok": False, "error": "Bilinmeyen hat"}, status=400)
    if action not in ("sebeke", "batarya", "kapat"):
        return JsonResponse({"ok": False, "error": "Bilinmeyen işlem"}, status=400)

    t = time.time()
    wobble = 0.5 * math.sin(t / 12.0)
    _ensure_demo_switch_session(request, wobble)
    data = request.session[SESSION_TRANSFER_SWITCH_KEY]
    h = hash(switch_id) % 100

    if action == "kapat":
        data[switch_id] = {
            "aktif_kaynak": "kapali",
            "guc_base": 0.0,
            "durum": "devre_disi",
        }
    elif action == "sebeke":
        data[switch_id] = {
            "aktif_kaynak": "sebeke",
            "guc_base": 5.0 + h / 20.0,
            "durum": "normal",
        }
    else:
        data[switch_id] = {
            "aktif_kaynak": "batarya",
            "guc_base": 3.2 + h / 25.0,
            "durum": "uyari" if h % 4 == 0 else "normal",
        }

    request.session[SESSION_TRANSFER_SWITCH_KEY] = data
    request.session.modified = True

    switches = _transfer_switches_for_api(request, wobble, t)
    return JsonResponse({"ok": True, "demo": True, "transfer_switches": switches})


@login_required
@_enerji_nav_guard
@require_http_methods(["GET", "POST"])
def api_enerji_haftalik_plan(request):
    """
    Haftalık çalışma gün planı (demo + oturum).
    GET: { meta, gunler[] }
    POST: { gunler: [ { tarih, cnc_torna_aktif, ... } ] } — şimdilik session; ileride DB.
    """
    if request.method == "GET":
        gunler = _merge_calisma_plan_from_session(request)
        return JsonResponse(
            {
                "meta": {
                    "demo": True,
                    "hafta_baslangic": _week_monday().isoformat(),
                    "kaynak": "demo+session",
                    "db_notu": "Kalıcı kayıt için HaftalikEnerjiPlanGun benzeri model önerilir.",
                },
                "gunler": gunler,
            }
        )

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Geçersiz JSON"}, status=400)

    incoming = body.get("gunler")
    if not isinstance(incoming, list):
        return JsonResponse({"ok": False, "error": "gunler alanı dizi olmalıdır"}, status=400)

    mon = _week_monday()
    allowed = {(mon + dt.timedelta(days=i)).isoformat() for i in range(7)}
    merged = {r["tarih"]: dict(r) for r in _merge_calisma_plan_from_session(request)}

    for item in incoming:
        if not isinstance(item, dict):
            continue
        tr = item.get("tarih")
        if tr not in allowed or tr not in merged:
            continue
        row = merged[tr]
        for k in (
            "cnc_torna_aktif",
            "cnc_freze_aktif",
            "arac_sarj_istasyonu_aktif",
            "atolye_ve_ust_katlar_aktif",
        ):
            if k in item:
                row[k] = bool(item[k])
        if "planlanan_uretim_yogunlugu" in item and item["planlanan_uretim_yogunlugu"] in (
            "dusuk",
            "orta",
            "yuksek",
        ):
            row["planlanan_uretim_yogunlugu"] = item["planlanan_uretim_yogunlugu"]
        if "not" in item and isinstance(item["not"], str):
            row["not"] = item["not"][:2000]

    out = [merged[(mon + dt.timedelta(days=i)).isoformat()] for i in range(7)]
    request.session[SESSION_HAFTALIK_PLAN_KEY] = out
    request.session.modified = True
    return JsonResponse(
        {
            "ok": True,
            "demo": True,
            "meta": {"kaynak": "session", "db_notu": "POST gövdesi ileride ORM kaydına map edilecek."},
            "gunler": out,
        }
    )


@login_required
@_enerji_nav_guard
def api_enerji_hava_tahmini(request):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    soc = _demo_soc_now()
    gunler = _weekly_hava_gunes(soc)
    return JsonResponse(
        {
            "meta": {
                "demo": True,
                "hafta_baslangic": _week_monday().isoformat(),
                "kaynak": "demo_ic_hesaplama",
                "hava_servisi": "entegrasyon_bekleniyor",
            },
            "gunler": gunler,
        }
    )


@login_required
@_enerji_nav_guard
def api_enerji_planlama_ozet(request):
    """Dashboard haftalık planlama özeti; sayfa açılışında bir kez çağrılmak üzere."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    ozet = _compute_planlama_ozet(request)
    return JsonResponse(
        {
            "meta": {
                "demo": True,
                "batarya_soc_demo": _demo_soc_now(),
                "hafta_baslangic": _week_monday().isoformat(),
            },
            **ozet,
        }
    )


@login_required
@_enerji_nav_guard
def enerji_planlama(request):
    return render(
        request,
        "stokapp/enerji_planlama.html",
        {
            "api_haftalik_plan": reverse("stokapp:api_enerji_haftalik_plan"),
            "api_hava_tahmini": reverse("stokapp:api_enerji_hava_tahmini"),
        },
    )
