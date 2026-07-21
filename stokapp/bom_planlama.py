"""Çok seviyeli reçete (BOM) planlama: alt üretim emirleri ve malzeme ihtiyacı patlatma."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from .models import Recete, ReceteDetay, StokItem, UretimEmri
from .uretim_emri_service import create_uretim_emri_with_stages


def aktif_recete_id_by_urun() -> dict[int, int]:
    return dict(Recete.objects.filter(aktif=True).values_list("urun_id", "id"))


def build_kapsanan_urun_ids_by_emir(uretim_emirleri) -> dict[int, frozenset[int]]:
    """Açık alt emirlerle karşılanan ara ürün stok_item (urun) id'leri — emir bazında."""
    emir_ids = {emir.id for emir in uretim_emirleri}
    children_by_parent: dict[int, list] = defaultdict(list)
    for emir in uretim_emirleri:
        parent_id = emir.ust_uretim_emri_id
        if parent_id and parent_id in emir_ids:
            children_by_parent[parent_id].append(emir)

    result: dict[int, frozenset[int]] = {}
    for emir in uretim_emirleri:
        covered: set[int] = set()
        stack = list(children_by_parent.get(emir.id, []))
        while stack:
            alt = stack.pop()
            if alt.durum in ("PLANLANDI", "BASLADI"):
                covered.add(alt.recete.urun_id)
            stack.extend(children_by_parent.get(alt.id, []))
        result[emir.id] = frozenset(covered)
    return result


def recete_yaprak_malzeme_satirlari(
    recete_id: int,
    miktar: Decimal,
    kapsanan_urun_ids: frozenset[int],
    recete_id_by_urun: dict[int, int],
    visit_urun_ids: frozenset[int] | None = None,
) -> list[tuple[int, Decimal, str]]:
    """
    Reçeteyi yaprak malzemelere patlatır.
    Aktif reçetesi olan ara ürünler satınalma listesine eklenmez;
    alt emirle karşılanan ara ürünler atlanır (çift sayım önlenir).
  """
    urun_id = (
        Recete.objects.filter(pk=recete_id).values_list("urun_id", flat=True).first()
    )
    if urun_id is None:
        return []

    visit = visit_urun_ids or frozenset()
    if urun_id in visit:
        return []
    visit_next = frozenset(set(visit) | {urun_id})

    satirlar: list[tuple[int, Decimal, str]] = []
    detaylar = ReceteDetay.objects.filter(recete_id=recete_id).order_by("sira", "id")
    for detay in detaylar:
        gerekli = Decimal(str(detay.miktar)) * miktar
        if gerekli <= 0:
            continue

        comp_id = detay.stok_item_id
        child_recete_id = recete_id_by_urun.get(comp_id)
        if child_recete_id and comp_id in kapsanan_urun_ids:
            continue
        if child_recete_id:
            satirlar.extend(
                recete_yaprak_malzeme_satirlari(
                    child_recete_id,
                    gerekli,
                    kapsanan_urun_ids,
                    recete_id_by_urun,
                    visit_next,
                )
            )
        else:
            satirlar.append((comp_id, gerekli, detay.birim))
    return satirlar


def uretim_emri_malzeme_satirlari(
    emir: UretimEmri,
    kapsanan_urun_ids: frozenset[int],
    recete_id_by_urun: dict[int, int],
    cikis_by_emir_stok: dict[tuple[int, int], Decimal] | None = None,
) -> list[tuple[int, Decimal, str]]:
    """Açık emir için satınalma planına girecek yaprak malzeme satırları (kalan ihtiyaç)."""
    detayli = uretim_emri_malzeme_satirlari_detayli(
        emir, kapsanan_urun_ids, recete_id_by_urun, cikis_by_emir_stok
    )
    return [
        (sid, d["kalan"], d["birim"])
        for sid, d in detayli.items()
        if d["kalan"] > 0
    ]


def uretim_emri_malzeme_satirlari_detayli(
    emir: UretimEmri,
    kapsanan_urun_ids: frozenset[int],
    recete_id_by_urun: dict[int, int],
    cikis_by_emir_stok: dict[tuple[int, int], Decimal] | None = None,
) -> dict[int, dict]:
    """
    Emir bazında yaprak malzeme ihtiyacı.
    Dönüş: stok_item_id -> {toplam, dusulen, kalan, birim}
    BASLADI emirlerde URETIM_CIKIS düşülerek kalan hesaplanır.
    """
    recete_miktar = Decimal(str(emir.miktar))
    satirlar = recete_yaprak_malzeme_satirlari(
        emir.recete_id,
        recete_miktar,
        kapsanan_urun_ids,
        recete_id_by_urun,
    )

    leaf_totals: dict[int, tuple[Decimal, str]] = {}
    for sid, mik, birim in satirlar:
        if sid not in leaf_totals:
            leaf_totals[sid] = (Decimal("0"), birim)
        acc, b = leaf_totals[sid]
        leaf_totals[sid] = (acc + mik, b)

    result: dict[int, dict] = {
        sid: {
            "toplam": tot,
            "dusulen": Decimal("0"),
            "kalan": tot,
            "birim": birim,
        }
        for sid, (tot, birim) in leaf_totals.items()
    }

    if emir.durum != "BASLADI" or not cikis_by_emir_stok:
        return result

    # Direkt bileşen çıkışlarını yaprak ihtiyacından düş
    detaylar = ReceteDetay.objects.filter(recete_id=emir.recete_id).order_by("sira", "id")
    for detay in detaylar:
        comp_id = detay.stok_item_id
        cikis = cikis_by_emir_stok.get((emir.id, comp_id), Decimal("0"))
        if cikis <= 0:
            continue
        child_recete_id = recete_id_by_urun.get(comp_id)
        if child_recete_id and comp_id not in kapsanan_urun_ids:
            for leaf_sid, leaf_mik, _birim in recete_yaprak_malzeme_satirlari(
                child_recete_id,
                cikis,
                kapsanan_urun_ids,
                recete_id_by_urun,
            ):
                if leaf_sid in result:
                    result[leaf_sid]["dusulen"] += leaf_mik
        elif comp_id in result:
            result[comp_id]["dusulen"] += cikis

    for sid, data in result.items():
        data["kalan"] = max(Decimal("0"), data["toplam"] - data["dusulen"])

    return result


def _aggregate_eksik_bilesen_miktarlari(ust_emir: UretimEmri) -> dict[int, Decimal]:
    """Üst emrin reçetesine göre stok_item_id -> eksik üretim ihtiyacı (mevcut stok düşük olanlar)."""
    agg: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for detay in ust_emir.recete.detaylar.select_related("stok_item").order_by("sira", "id"):
        gerekli = Decimal(str(detay.miktar)) * Decimal(str(ust_emir.miktar))
        comp = StokItem.objects.select_for_update().get(pk=detay.stok_item_id)
        eksik = max(Decimal("0"), gerekli - comp.mevcut_miktar)
        if eksik > 0:
            agg[comp.id] += eksik
    return dict(agg)


def _plan_alt_emirler_post_order(
    recete: Recete, miktar: Decimal, visit_products: frozenset
) -> list[tuple[Recete, Decimal]]:
    """Ara ürün emirleri: BOM post-order (önce alt seviye, sonra üst)."""
    out: list[tuple[Recete, Decimal]] = []
    if recete.urun_id in visit_products:
        return out
    visit_next = frozenset(set(visit_products) | {recete.urun_id})
    for detay in ReceteDetay.objects.filter(recete=recete).select_related("stok_item").order_by("sira", "id"):
        gerekli = Decimal(str(detay.miktar)) * miktar
        comp = StokItem.objects.select_for_update().get(pk=detay.stok_item_id)
        eksik = max(Decimal("0"), gerekli - comp.mevcut_miktar)
        if eksik <= 0:
            continue
        child_recete = Recete.objects.filter(urun_id=comp.id, aktif=True).first()
        if not child_recete:
            continue
        out.extend(_plan_alt_emirler_post_order(child_recete, eksik, visit_next))
        out.append((child_recete, eksik))
    return out


def _collapse_alt_emir_plan(plan: list[tuple[Recete, Decimal]]) -> list[tuple[Recete, Decimal]]:
    """Aynı reçete birden fazla satırdan ihtiyaç duyulursa miktarları birleştir."""
    order: list[int] = []
    totals: dict[int, tuple[Recete, Decimal]] = {}
    for cr, m in plan:
        rid = cr.id
        if rid not in totals:
            order.append(rid)
            totals[rid] = (cr, Decimal("0"))
        cr0, acc = totals[rid]
        totals[rid] = (cr0, acc + m)
    return [totals[rid] for rid in order]


def build_siparis_alt_emir_plan(ust_emir: UretimEmri) -> list[tuple[Recete, Decimal]]:
    """Ana emir için eksik ara ürünlerin üretim planı (başlatma sırasına uygun)."""
    root_visit = frozenset({ust_emir.recete.urun_id})
    raw: list[tuple[Recete, Decimal]] = []
    for _sid, eksik_miktar in _aggregate_eksik_bilesen_miktarlari(ust_emir).items():
        child_recete = Recete.objects.filter(urun_id=_sid, aktif=True).first()
        if not child_recete or eksik_miktar <= 0:
            continue
        raw.extend(_plan_alt_emirler_post_order(child_recete, eksik_miktar, root_visit))
    return _collapse_alt_emir_plan(raw)


def create_alt_uretim_emirleri(
    ust_emir: UretimEmri,
    *,
    planlanan_baslama,
    planlanan_bitis,
    aciklama: str,
    production_type: str,
) -> list[UretimEmri]:
    """Eksik ara ürünler için otomatik alt üretim emirleri oluşturur."""
    alt_plan = build_siparis_alt_emir_plan(ust_emir)
    alt_emirler: list[UretimEmri] = []
    for cr_alt, mik_alt in alt_plan:
        alt_emirler.append(
            create_uretim_emri_with_stages(
                recete=cr_alt,
                miktar=mik_alt,
                planlanan_baslama=planlanan_baslama,
                planlanan_bitis=planlanan_bitis,
                aciklama=aciklama,
                production_type=production_type,
                ust_uretim_emri=ust_emir,
                alt_emir_otomatik=True,
            )
        )
    return alt_emirler


def create_uretim_emri_with_alt_emirler(
    *,
    recete: Recete,
    miktar: Decimal,
    planlanan_baslama,
    planlanan_bitis,
    aciklama: str = "",
    production_type: str = "STOCK",
    alt_emir_aciklama: str | None = None,
) -> tuple[UretimEmri, list[UretimEmri]]:
    """Ana üretim emrini ve gerekiyorsa otomatik alt emirlerini tek transaction içinde oluşturur."""
    with transaction.atomic():
        ust_emir = create_uretim_emri_with_stages(
            recete=recete,
            miktar=miktar,
            planlanan_baslama=planlanan_baslama,
            planlanan_bitis=planlanan_bitis,
            aciklama=aciklama,
            production_type=production_type,
        )
        alt_aciklama = alt_emir_aciklama or (
            f"Ana emir {ust_emir.emir_no} için otomatik ara ürün"
        )
        alt_emirler = create_alt_uretim_emirleri(
            ust_emir,
            planlanan_baslama=planlanan_baslama,
            planlanan_bitis=planlanan_bitis,
            aciklama=alt_aciklama,
            production_type=production_type,
        )
    return ust_emir, alt_emirler
