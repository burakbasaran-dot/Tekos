"""Tedarikçi Performans Raporu.

KPI'lar:
- Toplam teklif kalemi sayısı (girilmiş)
- Kazanılan kalem sayısı / kazanma oranı
- Ortalama söz verilen teslim süresi (gün)
- Ortalama fiyat sapması (kazanan teklife göre %)
- Toplam ciro (siparişe dönüşen tutar)

Filtreler: kategori, tarih aralığı, durum (aktif/pasif tedarikçi).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from .models import (
    Kategori,
    Satinalma,
    SatinalmaKalemi,
    Tedarikci,
    TeklifTalebi,
    TeklifTalebiTedarikci,
    TedarikciTeklifKalemi,
)


DEFAULT_KUR_TABLOSU = {
    "TRY": Decimal("1"),
    "TL": Decimal("1"),
    "USD": Decimal("34"),
    "EUR": Decimal("37"),
    "GBP": Decimal("43"),
}


def _try_karsiligi(birim_fiyat, para_birimi):
    if birim_fiyat is None:
        return None
    pb = (para_birimi or "TRY").upper()
    if pb in ("TRY", "TL"):
        return Decimal(str(birim_fiyat))
    return Decimal(str(birim_fiyat)) * DEFAULT_KUR_TABLOSU.get(pb, Decimal("1"))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@login_required
def tedarikci_performans(request):
    kategori_id = request.GET.get("kategori")
    tarih_basla = _parse_date(request.GET.get("tarih_basla"))
    tarih_bitis = _parse_date(request.GET.get("tarih_bitis"))
    durum = request.GET.get("durum", "aktif")

    tedarikci_qs = Tedarikci.objects.all().prefetch_related("kategoriler")
    if durum == "aktif":
        tedarikci_qs = tedarikci_qs.filter(aktif=True)
    elif durum == "pasif":
        tedarikci_qs = tedarikci_qs.filter(aktif=False)
    if kategori_id and kategori_id.isdigit():
        tedarikci_qs = tedarikci_qs.filter(kategoriler__pk=int(kategori_id)).distinct()

    # Tarih filtresi: TeklifTalebi.olusturma_tarihi
    teklif_qs = TedarikciTeklifKalemi.objects.filter(
        rfq_tedarikci__tedarikci__isnull=False,
    ).select_related(
        "rfq_tedarikci",
        "rfq_tedarikci__rfq",
        "rfq_tedarikci__tedarikci",
        "rfq_kalemi",
    )
    if tarih_basla:
        teklif_qs = teklif_qs.filter(rfq_tedarikci__rfq__olusturma_tarihi__gte=tarih_basla)
    if tarih_bitis:
        teklif_qs = teklif_qs.filter(rfq_tedarikci__rfq__olusturma_tarihi__lte=tarih_bitis)

    # Tedarikçi bazlı agg
    bilgi_map = defaultdict(lambda: {
        "tedarikci": None,
        "toplam_teklif": 0,
        "girilmis_teklif": 0,
        "kazanilan": 0,
        "teslim_sureleri": [],
        "fiyat_sapma_yuzdeleri": [],
        "ciro": Decimal("0"),
    })

    # Her RFQ kalemi için kazanan TRY karşılığını sakla
    kalem_kazanan_try = {}
    kalem_teklifleri_try = defaultdict(list)
    for tk in teklif_qs:
        if tk.birim_fiyat is None:
            continue
        try_karsilik = _try_karsiligi(tk.birim_fiyat, tk.para_birimi)
        if try_karsilik is None:
            continue
        kalem_teklifleri_try[tk.rfq_kalemi_id].append((tk.pk, try_karsilik))
        if tk.secildi:
            kalem_kazanan_try[tk.rfq_kalemi_id] = try_karsilik

    for tk in teklif_qs:
        ted = tk.rfq_tedarikci.tedarikci
        bilgi = bilgi_map[ted.pk]
        bilgi["tedarikci"] = ted
        bilgi["toplam_teklif"] += 1
        if tk.birim_fiyat is not None or tk.teslim_suresi_gun is not None:
            bilgi["girilmis_teklif"] += 1
        if tk.secildi:
            bilgi["kazanilan"] += 1
        if tk.teslim_suresi_gun is not None:
            bilgi["teslim_sureleri"].append(tk.teslim_suresi_gun)
        # Fiyat sapması: tedarikçinin teklifi vs kazanan teklif
        kazanan_try = kalem_kazanan_try.get(tk.rfq_kalemi_id)
        if (
            kazanan_try is not None
            and tk.birim_fiyat is not None
        ):
            try_karsilik = _try_karsiligi(tk.birim_fiyat, tk.para_birimi)
            if try_karsilik is not None and kazanan_try > 0:
                sapma = ((try_karsilik - kazanan_try) / kazanan_try) * Decimal("100")
                bilgi["fiyat_sapma_yuzdeleri"].append(sapma)

    # Ciro: tedarikçinin yer aldığı Satinalma'ların toplamı (RFQ kapsamında)
    satinalma_qs = Satinalma.objects.filter(tedarikci__isnull=False).select_related("tedarikci")
    if tarih_basla:
        satinalma_qs = satinalma_qs.filter(olusturulma_tarihi__gte=tarih_basla)
    if tarih_bitis:
        satinalma_qs = satinalma_qs.filter(olusturulma_tarihi__lte=tarih_bitis)
    for sa in satinalma_qs:
        if sa.tedarikci_id in bilgi_map:
            bilgi_map[sa.tedarikci_id]["ciro"] += Decimal(str(sa.toplam or 0))

    # Tedarikçileri bilgi map'i + kategori filtresine göre listele
    izinli_pkler = set(tedarikci_qs.values_list("pk", flat=True))
    sonuc = []
    for pk, bilgi in bilgi_map.items():
        if pk not in izinli_pkler:
            continue
        ted = bilgi["tedarikci"]
        toplam = bilgi["toplam_teklif"]
        kazanma_orani = (
            (Decimal(bilgi["kazanilan"]) / Decimal(toplam) * Decimal("100"))
            if toplam else Decimal("0")
        )
        ort_teslim = (
            sum(bilgi["teslim_sureleri"]) / len(bilgi["teslim_sureleri"])
            if bilgi["teslim_sureleri"] else None
        )
        ort_sapma = (
            sum(bilgi["fiyat_sapma_yuzdeleri"]) / Decimal(len(bilgi["fiyat_sapma_yuzdeleri"]))
            if bilgi["fiyat_sapma_yuzdeleri"] else None
        )
        sonuc.append({
            "tedarikci": ted,
            "kategoriler": list(ted.kategoriler.all()),
            "toplam_teklif": toplam,
            "girilmis_teklif": bilgi["girilmis_teklif"],
            "kazanilan": bilgi["kazanilan"],
            "kazanma_orani": kazanma_orani,
            "ort_teslim_suresi": ort_teslim,
            "ort_fiyat_sapma": ort_sapma,
            "ciro": bilgi["ciro"],
        })

    # Hiç teklifi olmayan tedarikçileri de listede göster (filtreye uygunsa)
    teklif_olmayan = []
    for ted in tedarikci_qs.exclude(pk__in=bilgi_map.keys()):
        teklif_olmayan.append({
            "tedarikci": ted,
            "kategoriler": list(ted.kategoriler.all()),
            "toplam_teklif": 0,
            "girilmis_teklif": 0,
            "kazanilan": 0,
            "kazanma_orani": Decimal("0"),
            "ort_teslim_suresi": None,
            "ort_fiyat_sapma": None,
            "ciro": Decimal("0"),
        })

    # Sıralama
    sort = request.GET.get("sort", "kazanma_orani")
    sort_dir = request.GET.get("dir", "desc")
    reverse = sort_dir != "asc"

    def _sort_key(d):
        v = d.get(sort)
        if v is None:
            return Decimal("-99999999") if reverse else Decimal("99999999")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    sonuc.sort(key=_sort_key, reverse=reverse)
    sonuc.extend(teklif_olmayan)

    context = {
        "sonuc": sonuc,
        "kategoriler": Kategori.objects.all().order_by("ad"),
        "filtre_kategori": kategori_id,
        "filtre_tarih_basla": tarih_basla.isoformat() if tarih_basla else "",
        "filtre_tarih_bitis": tarih_bitis.isoformat() if tarih_bitis else "",
        "filtre_durum": durum,
        "sort": sort,
        "sort_dir": sort_dir,
        "ozet": {
            "tedarikci_sayisi": len(sonuc),
            "toplam_ciro": sum((x["ciro"] for x in sonuc), Decimal("0")),
            "toplam_teklif": sum(x["toplam_teklif"] for x in sonuc),
            "toplam_kazanan": sum(x["kazanilan"] for x in sonuc),
        },
    }
    return render(request, "stokapp/tedarikci_performans.html", context)
