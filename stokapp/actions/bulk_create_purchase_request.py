"""Onay sonrası: TEKORA toplu kritik stok önerisinden tek talep + çoklu talep kalemi."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from stokapp.models import Birim, Talep, TalepKalemi


def _to_decimal(value, default=Decimal("1")):
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except Exception:
        return default


def _resolve_user(username):
    if username:
        user = User.objects.filter(username=username).first()
        if user:
            return user
    return User.objects.filter(is_superuser=True).first() or User.objects.filter(is_active=True).first()


def _resolve_birim(unit_name):
    if not unit_name:
        return None
    return Birim.objects.filter(ad__iexact=unit_name).first() or Birim.objects.filter(ad__icontains=unit_name).first()


def handle(payload):
    """
    Payload: TEKORA toplu onay — type bulk_purchase_request, items[].
    Her kalem için TalepKalemi; tek Talep altında toplanır.
    """
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("Toplu talep için en az bir kalem gerekli.")

    approval_request_id = payload.get("_approval_request_id")
    approved_by = payload.get("_approved_by")
    talep_eden = _resolve_user(approved_by)
    if not talep_eden:
        raise ValueError("Satın alma talebi oluşturmak için geçerli bir kullanıcı bulunamadı.")

    reason = (
        "TEKORA kritik stok toplu analizi sonrası onaylanan satın alma önerisi.\n"
        f"Approval Request ID: {approval_request_id or '-'}"
    )
    n = len(items)
    baslik = f"TEKORA Toplu Satın Alma Talebi ({n} kalem)"

    talep = Talep.objects.create(
        talep_tarihi=timezone.localdate(),
        talep_eden=talep_eden,
        kategori="URETIM_MALZ",
        baslik=baslik[:500],
        oncelik="NORMAL",
        durum="YENI",
        aciklama=reason,
    )

    birim_adet = _resolve_birim("adet")
    for it in items:
        if not isinstance(it, dict):
            continue
        code = str(it.get("product_code") or "").strip() or "Bilinmeyen"
        name = str(it.get("product_name") or "").strip()
        label = f"{code} — {name}" if name else code
        qty = it.get("suggested_quantity")
        line_note = (
            f"Mevcut: {it.get('current_stock')}, kritik: {it.get('critical_level')}, "
            f"önem: {it.get('severity', '-')}"
        )
        TalepKalemi.objects.create(
            talep=talep,
            kalem_adi=label[:300],
            aciklama=line_note[:2000],
            miktar=_to_decimal(qty, default=Decimal("1")),
            birim=birim_adet,
        )

    return {
        "success": True,
        "message": "Toplu satın alma talebi oluşturuldu.",
        "result": {
            "created_purchase_request_id": talep.id,
            "created_purchase_request_no": talep.talep_no,
            "line_count": n,
        },
        "payload_updates": {
            "created_purchase_request_id": talep.id,
            "created_purchase_request_no": talep.talep_no,
        },
    }
