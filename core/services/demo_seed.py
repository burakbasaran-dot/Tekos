"""Scoped demo seed data for trial companies (prefix-based, idempotent)."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from core.models import Company

logger = logging.getLogger(__name__)


def _prefix(company: Company) -> str:
    return f"DEMO-{company.slug}"


@transaction.atomic
def seed_trial_company_data(company: Company) -> dict:
    """Create minimal sample data tagged with DEMO-{slug}- prefix. Idempotent."""
    if company.demo_seed_completed:
        return {"skipped": True}

    prefix = _prefix(company)
    stats = {"stok": 0, "cari": 0, "depo": 0}

    try:
        from stokapp.models import Cari, Depo, Kategori, StokItem

        depo, _ = Depo.objects.get_or_create(ad=f"{prefix}-Ana Depo")
        depo2, _ = Depo.objects.get_or_create(ad=f"{prefix}-Üretim Deposu")
        stats["depo"] = 2

        kategori, _ = Kategori.objects.get_or_create(ad=f"{prefix}-Örnek Kategori")

        sample_items = [
            ("Sac Levha", "001"),
            ("Vida M8", "002"),
            ("Conta", "003"),
            ("Boya", "004"),
            ("Profil Alüminyum", "005"),
            ("Rulman", "006"),
        ]
        for name, code in sample_items:
            kod = f"{prefix}-{code}"
            if not StokItem.objects.filter(stok_kodu=kod).exists():
                StokItem.objects.create(
                    stok_kodu=kod,
                    ad=f"[Örnek] {name}",
                    kategori=kategori,
                    birim="Adet",
                    mevcut_miktar=Decimal("100"),
                    minimum_stok=Decimal("10"),
                    stok_takip=True,
                    aciklama=f"Demo veri — {company.name}",
                )
                stats["stok"] += 1

        cari_samples = [
            ("Örnek Müşteri A", "MUSTERI"),
            ("Örnek Müşteri B", "MUSTERI"),
            ("Örnek Tedarikçi X", "TEDARIKCI"),
        ]
        for i, (cari_name, tip) in enumerate(cari_samples, 1):
            kod = f"{prefix}-CARI-{i:03d}"
            if not Cari.objects.filter(cari_kodu=kod).exists():
                Cari.objects.create(
                    cari_kodu=kod,
                    unvan=f"[Örnek] {cari_name}",
                    cari_tipi=tip,
                )
                stats["cari"] += 1

    except Exception:
        logger.exception("Demo seed partial failure for company %s", company.slug)

    company.demo_seed_completed = True
    company.save(update_fields=["demo_seed_completed", "updated_at"])
    return stats
