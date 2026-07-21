from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from stokapp.models import Musteri, ParaBirimi, Siparis, SiparisKalemi, StokItem
from stokapp.views_mail import _normalize_mail_currency_for_order, _resolve_stok_for_detected_item

TEKORA_ETIKET = "TEKORA"


def _to_decimal(value, default=None):
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except Exception:
        return default


def _resolve_musteri(customer_name):
    if not customer_name or not str(customer_name).strip():
        return None, ""
    name = str(customer_name).strip()
    lowered = name.lower()
    if lowered in ("unknown", "-", "bilinmiyor"):
        return None, ""
    m = Musteri.objects.filter(ad__iexact=name).first()
    if m:
        return m, m.ad
    m = Musteri.objects.filter(ad__icontains=name).first()
    if m:
        return m, m.ad
    return None, name


def _next_so_number():
    son_siparis = Siparis.objects.order_by("-id").first()
    if son_siparis:
        try:
            num = int(son_siparis.siparis_numarasi.replace("SO-", "")) + 1
        except Exception:
            num = 1
    else:
        num = 1
    return f"SO-{num}"


def _allocate_unique_siparis_numarasi(preferred):
    """
    TF vb. tercih edilen numara kullanılır; çakışmada -2, -3 ...
    Tercih yoksa SO-* üretilir.
    """
    pref = (preferred or "").strip()
    if pref:
        base = pref[:50]
        if not Siparis.objects.filter(siparis_numarasi__iexact=base).exists():
            return base
        for n in range(2, 10000):
            suffix = f"-{n}"
            stem = base[: 50 - len(suffix)] if len(base) + len(suffix) > 50 else base
            candidate = (stem + suffix)[:50]
            if not Siparis.objects.filter(siparis_numarasi__iexact=candidate).exists():
                return candidate
        return _next_so_number()
    return _next_so_number()


def _default_para_birimi():
    pb = ParaBirimi.objects.filter(aktif=True).order_by("kod").first()
    return pb.kod if pb else "USD"


def _resolve_para_birimi_from_mail(preferred_code):
    pc = _normalize_mail_currency_for_order(preferred_code)
    if pc:
        pb = ParaBirimi.objects.filter(kod__iexact=pc, aktif=True).first()
        if pb:
            return pb.kod
    return _default_para_birimi()


def _build_aciklama(payload, siparis_no):
    parts = []
    sub = payload.get("subject")
    if sub:
        parts.append(f"Konu: {sub}")
    pr = payload.get("purchase_recommendation") or {}
    if pr.get("reason"):
        parts.append(pr["reason"])
    sc = payload.get("stock_checks") or []
    warn = [x for x in sc if x.get("status") in ("insufficient", "product_not_found")]
    if warn:
        parts.append("Stok özeti: " + ", ".join(f"{w.get('product_code')} ({w.get('status')})" for w in warn[:8]))
    aid = payload.get("_approval_request_id")
    if aid:
        parts.append(f"Kaynak: TEKORA — Onay kaydı: {aid}")
    parts.append(f"Sipariş no: {siparis_no}")
    return "\n".join(parts)


def handle(payload):
    detected_items = payload.get("detected_items") or []
    preferred = payload.get("preferred_siparis_numarasi") or payload.get("extracted_order_number")
    customer_name = payload.get("customer_name") or ""

    kalemler_input = []
    order_currency_hint = None
    for item in detected_items:
        code = (item.get("product_code") or "").strip()
        if not code:
            continue
        qty = _to_decimal(item.get("quantity"), Decimal("1"))
        if qty is None or qty <= 0:
            qty = Decimal("1")
        curr = item.get("currency")
        if curr and order_currency_hint is None:
            order_currency_hint = curr
        kalemler_input.append({"item": item, "quantity": qty})

    if not kalemler_input:
        raise ValueError(
            "Sipariş oluşturulamadı: mailden ürün kodu çıkarılamadı veya tüm kalemlerde kod boş."
        )

    lines_to_create = []
    for row in kalemler_input:
        item = row["item"]
        stok = _resolve_stok_for_detected_item(item)
        if not stok:
            continue
        mail_price = _to_decimal(item.get("unit_price"))
        stok_price = _to_decimal(stok.satis_fiyati, Decimal("0")) or Decimal("0")
        if mail_price is not None and mail_price > 0:
            birim_fiyat = mail_price
        else:
            birim_fiyat = stok_price
        lines_to_create.append(
            {
                "stok_item": stok,
                "miktar": row["quantity"],
                "birim_fiyat": birim_fiyat,
                "aciklama": "",
            }
        )

    if not lines_to_create:
        codes = ", ".join((r["item"].get("product_code") or "").strip() for r in kalemler_input[:12])
        raise ValueError(
            f"Sipariş oluşturulamadı: stok kartında bulunamayan ürün kodları: {codes}"
        )

    musteri, musteri_adi_metin = _resolve_musteri(customer_name)
    para_kodu = _resolve_para_birimi_from_mail(order_currency_hint)

    with transaction.atomic():
        siparis_no = _allocate_unique_siparis_numarasi(preferred)
        aciklama = _build_aciklama(payload, siparis_no)

        toplam = Decimal("0")
        for line in lines_to_create:
            t = line["miktar"] * line["birim_fiyat"]
            toplam += t

        siparis = Siparis.objects.create(
            siparis_numarasi=siparis_no,
            musteri=musteri,
            musteri_adi=musteri_adi_metin if musteri is None else musteri.ad,
            etiketler=TEKORA_ETIKET,
            toplam=toplam,
            para_birimi=para_kodu,
            olusturulma_tarihi=timezone.localdate(),
            siparis_durumu="ONAY_BEKLIYOR",
            aciklama=aciklama,
        )

        for line in lines_to_create:
            SiparisKalemi.objects.create(
                siparis=siparis,
                stok_item=line["stok_item"],
                miktar=line["miktar"],
                birim_fiyat=line["birim_fiyat"],
                indirim_yuzdesi=Decimal("0"),
                aciklama=line["aciklama"],
            )

    return {
        "success": True,
        "message": f'Satış siparişi "{siparis_no}" oluşturuldu (onay bekliyor).',
        "result": {
            "created_siparis_id": siparis.id,
            "siparis_numarasi": siparis_no,
            "customer_name": customer_name,
            "items_count": len(lines_to_create),
        },
        "payload_updates": {
            "created_siparis_id": siparis.id,
            "siparis_numarasi": siparis_no,
        },
    }
