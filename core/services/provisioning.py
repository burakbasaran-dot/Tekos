"""Automatic trial company provisioning."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.models import Company, CompanyMembership, Plan, SignupApplication, Subscription
from core.services.applications import generate_idempotency_key, set_application_status
from core.services.audit import log_action
from core.services.demo_seed import seed_trial_company_data
from core.services.licensing import start_trial_subscription
from core.services.signup_email import send_provisioning_failed_admin, send_trial_welcome_email
from core.services.signup_settings import max_trials_per_email, trial_days
from core.views_setup import DEFAULT_DEPARTMENTS, DEFAULT_WAREHOUSES

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class ProvisionResult:
    success: bool
    application: SignupApplication
    user: User | None = None
    company: Company | None = None
    subscription: Subscription | None = None
    error: str = ""


def _active_trial_count_for_email(email: str) -> int:
    email_l = email.lower().strip()
    return SignupApplication.objects.filter(
        application_type=SignupApplication.TYPE_TRIAL,
        email__iexact=email_l,
        status__in=(
            SignupApplication.STATUS_ACTIVE,
            SignupApplication.STATUS_PROVISIONING,
        ),
        created_company__isnull=False,
    ).count()


def _get_or_create_user(application: SignupApplication, password: str):
    email = application.email.lower().strip()
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        username = (application.username_preference or "").strip()
        if not username:
            username = email.split("@")[0][:30]
        base_username = username
        n = 1
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base_username}{n}"[:150]
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=application.first_name,
            last_name=application.last_name,
            is_active=True,
        )
    else:
        user.set_password(password)
        user.first_name = application.first_name or user.first_name
        user.last_name = application.last_name or user.last_name
        user.is_active = True
        user.save()
    try:
        from stokapp.models import UserProfile

        UserProfile.objects.get_or_create(
            user=user,
            defaults={"telefon": application.phone},
        )
        if application.phone:
            UserProfile.objects.filter(user=user).update(telefon=application.phone)
    except Exception:
        pass
    return user


def _provision_company_structure(application: SignupApplication, user) -> tuple[Company, Subscription]:
    company = Company.objects.create(
        name=application.company_name.strip() or f"{application.first_name} Deneme",
        is_active=True,
        is_demo=True,
        setup_completed=True,
        demo_seed_completed=False,
        phone=application.phone,
        email=application.email,
        website=application.website,
        address=application.city or "",
    )
    from core.models import Department

    for dept_name in DEFAULT_DEPARTMENTS:
        Department.objects.get_or_create(company=company, name=dept_name)

    try:
        from stokapp.models import Depo

        prefix = f"DEMO-{company.slug}"
        for wh in DEFAULT_WAREHOUSES[:2]:
            Depo.objects.get_or_create(ad=f"{prefix}-{wh}")
    except Exception:
        logger.exception("Warehouse creation failed for %s", company.slug)

    CompanyMembership.objects.update_or_create(
        user=user,
        company=company,
        defaults={
            "role": CompanyMembership.ROLE_OWNER,
            "is_active": True,
            "is_default": True,
        },
    )

    plan = Plan.objects.filter(code="free_trial", is_active=True).first()
    if plan is None:
        plan = Plan.objects.filter(is_active=True).order_by("pk").first()
    if plan is None:
        raise ValueError("Aktif plan bulunamadı.")

    today = timezone.localdate()
    trial_end = today + timedelta(days=trial_days())
    subscription = Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.STATUS_TRIAL,
        start_date=today,
        trial_end_date=trial_end,
        end_date=trial_end,
        is_auto_renew=False,
    )
    return company, subscription


@transaction.atomic
def provision_trial_company(
    application: SignupApplication,
    password: str,
    *,
    request=None,
    force: bool = False,
) -> ProvisionResult:
    if application.created_company_id and not force:
        return ProvisionResult(
            success=True,
            application=application,
            user=application.created_user,
            company=application.created_company,
            subscription=application.created_subscription,
        )

    if not application.email_verified:
        return ProvisionResult(
            success=False,
            application=application,
            error="E-posta doğrulanmamış.",
        )

    if (
        application.application_type == SignupApplication.TYPE_TRIAL
        and _active_trial_count_for_email(application.email) >= max_trials_per_email()
    ):
        set_application_status(
            application,
            SignupApplication.STATUS_DUPLICATE,
            note="Aktif deneme limiti aşıldı",
        )
        return ProvisionResult(
            success=False,
            application=application,
            error="Bu e-posta için aktif deneme hesabı mevcut.",
        )

    if not application.provisioning_idempotency_key:
        application.provisioning_idempotency_key = generate_idempotency_key()
        application.save(update_fields=["provisioning_idempotency_key", "updated_at"])

    set_application_status(application, SignupApplication.STATUS_PROVISIONING, note="Provisioning başladı")

    try:
        user = _get_or_create_user(application, password)
        company, subscription = _provision_company_structure(application, user)
        seed_trial_company_data(company)

        application.created_user = user
        application.created_company = company
        application.created_subscription = subscription
        application.failure_summary = ""
        application.save(
            update_fields=[
                "created_user",
                "created_company",
                "created_subscription",
                "failure_summary",
                "updated_at",
            ]
        )
        set_application_status(application, SignupApplication.STATUS_ACTIVE, note="Deneme hesabı oluşturuldu")

        log_action(
            action="signup",
            user=user,
            company=company,
            model_name="SignupApplication",
            object_id=application.pk,
            object_repr=str(application),
            new_values={"status": "active", "company": company.slug},
            request=request,
        )
        send_trial_welcome_email(application)
        return ProvisionResult(
            success=True,
            application=application,
            user=user,
            company=company,
            subscription=subscription,
        )
    except Exception as exc:
        logger.exception("Provisioning failed for application %s", application.pk)
        application.failure_summary = type(exc).__name__
        application.save(update_fields=["failure_summary", "updated_at"])
        set_application_status(
            application,
            SignupApplication.STATUS_FAILED,
            note=str(exc)[:500],
        )
        send_provisioning_failed_admin(application)
        return ProvisionResult(success=False, application=application, error="Hesap oluşturulamadı.")
