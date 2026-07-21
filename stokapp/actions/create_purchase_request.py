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
    recommendation = payload.get("purchase_recommendation") or {}
    detected_items = payload.get("detected_items") or []
    first_item = detected_items[0] if detected_items else {}

    product_code = (
        recommendation.get("product_code")
        or first_item.get("product_code")
        or "Bilinmeyen Ürün"
    )
    required_quantity = (
        recommendation.get("required_quantity")
        if recommendation.get("required_quantity") is not None
        else first_item.get("quantity")
    )
    unit = recommendation.get("unit") or first_item.get("unit") or "adet"
    reason = recommendation.get("reason") or "TEKORA önerisi ile otomatik satın alma talebi oluşturuldu."

    approval_request_id = payload.get("_approval_request_id")
    approved_by = payload.get("_approved_by")
    talep_eden = _resolve_user(approved_by)
    if not talep_eden:
        raise ValueError("Satın alma talebi oluşturmak için geçerli bir kullanıcı bulunamadı.")

    talep = Talep.objects.create(
        talep_tarihi=timezone.localdate(),
        talep_eden=talep_eden,
        kategori="URETIM_MALZ",
        baslik=f"TEKORA Satın Alma Talebi - {product_code}",
        oncelik="NORMAL",
        durum="YENI",
        aciklama=f"{reason}\nKaynak: tekora\nApproval Request ID: {approval_request_id or '-'}",
    )

    TalepKalemi.objects.create(
        talep=talep,
        kalem_adi=product_code,
        aciklama=reason,
        miktar=_to_decimal(required_quantity, default=Decimal("1")),
        birim=_resolve_birim(unit),
    )

    return {
        "success": True,
        "message": "Satın alma talebi oluşturuldu.",
        "result": {
            "created_purchase_request_id": talep.id,
            "created_purchase_request_no": talep.talep_no,
            "product_code": product_code,
        },
        "payload_updates": {
            "created_purchase_request_id": talep.id,
            "created_purchase_request_no": talep.talep_no,
        },
    }
