"""Tenant / company access helpers."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from core.models import Company, CompanyMembership

SESSION_COMPANY_KEY = "active_company_id"


def get_user_companies(user, *, active_only: bool = True):
    if not user or not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        qs = Company.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.order_by("name")
    memberships = CompanyMembership.objects.filter(user=user, is_active=True)
    company_ids = memberships.values_list("company_id", flat=True)
    qs = Company.objects.filter(id__in=company_ids)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("name")


def user_can_access_company(user, company) -> bool:
    if not user or not user.is_authenticated or company is None:
        return False
    if not company.is_active and not user.is_superuser:
        return False
    if user.is_superuser:
        return True
    return CompanyMembership.objects.filter(
        user=user, company=company, is_active=True
    ).exists()


def get_default_company_for_user(user):
    if not user or not user.is_authenticated:
        return None
    membership = (
        CompanyMembership.objects.filter(user=user, is_active=True, is_default=True)
        .select_related("company")
        .first()
    )
    if membership and membership.company.is_active:
        return membership.company
    companies = get_user_companies(user)
    return companies.first()


def set_active_company(request, company) -> bool:
    if not user_can_access_company(request.user, company):
        return False
    request.session[SESSION_COMPANY_KEY] = company.pk
    request.company = company
    request.tenant = company
    return True


def resolve_company_from_request(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    company_id = request.session.get(SESSION_COMPANY_KEY)
    if company_id:
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            company = None
        if company and user_can_access_company(user, company):
            return company
        request.session.pop(SESSION_COMPANY_KEY, None)

    return get_default_company_for_user(user)


def user_can_manage_platform(user) -> bool:
    """Superuser, staff, or active company owner/admin membership."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return CompanyMembership.objects.filter(
        user=user,
        is_active=True,
        role__in=[CompanyMembership.ROLE_OWNER, CompanyMembership.ROLE_ADMIN],
    ).exists()


def ensure_default_company_bootstrap():
    """
    Create a default company and attach existing users if none exist.
    Safe to call from migrations / management commands.
    """
    User = get_user_model()
    if Company.objects.exists():
        return Company.objects.order_by("pk").first()

    name = "Default Company"
    try:
        from stokapp.models import GenelAyarlar

        ayar = GenelAyarlar.objects.filter(pk=1).first()
        if ayar and (ayar.firma_ismi or "").strip():
            name = ayar.firma_ismi.strip()
    except Exception:
        pass

    company = Company.objects.create(
        name=name,
        setup_completed=True,
        is_active=True,
    )
    for user in User.objects.all():
        CompanyMembership.objects.get_or_create(
            user=user,
            company=company,
            defaults={
                "role": CompanyMembership.ROLE_OWNER,
                "is_active": True,
                "is_default": True,
            },
        )
    return company
