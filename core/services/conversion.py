"""Convert demo company to paying customer."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from core.models import Company, Plan, SignupApplication, Subscription
from core.services.applications import set_application_status
from core.services.audit import log_action

logger = logging.getLogger(__name__)


@transaction.atomic
def convert_demo_to_customer(
    company: Company,
    plan: Plan,
    *,
    keep_sample_data: bool = True,
    changed_by=None,
    request=None,
) -> Company:
    company.is_demo = False
    company.save(update_fields=["is_demo", "updated_at"])

    sub = (
        Subscription.objects.filter(company=company)
        .order_by("-created_at")
        .first()
    )
    if sub:
        sub.status = Subscription.STATUS_ACTIVE
        sub.is_auto_renew = True
        sub.save(update_fields=["status", "is_auto_renew", "updated_at"])

    if not keep_sample_data:
        _remove_demo_prefix_data(company)

    app = SignupApplication.objects.filter(created_company=company).order_by("-created_at").first()
    if app:
        set_application_status(
            app,
            SignupApplication.STATUS_CONVERTED,
            changed_by=changed_by,
            note="Demo müşteriye dönüştürüldü",
        )

    log_action(
        action="update",
        user=changed_by,
        company=company,
        model_name="Company",
        object_id=company.pk,
        object_repr=company.name,
        new_values={"is_demo": False, "converted_at": timezone.now().isoformat()},
        request=request,
    )
    return company


def _remove_demo_prefix_data(company: Company) -> None:
    prefix = f"DEMO-{company.slug}"
    try:
        from stokapp.models import Cari, Depo, StokItem

        StokItem.objects.filter(stok_kodu__startswith=prefix).delete()
        Cari.objects.filter(cari_kodu__startswith=prefix).delete()
        Depo.objects.filter(ad__startswith=prefix).delete()
        company.demo_seed_completed = False
        company.save(update_fields=["demo_seed_completed"])
    except Exception:
        logger.exception("Failed to remove demo data for %s", company.slug)
