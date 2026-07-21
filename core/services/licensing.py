"""Subscription / license checks (payment-provider agnostic)."""

from __future__ import annotations

from datetime import timedelta
from functools import wraps

from django.http import HttpResponseForbidden
from django.utils import timezone

from core.models import CompanyMembership, PlanModuleEntitlement, Subscription


ACTIVE_STATUSES = {
    Subscription.STATUS_TRIAL,
    Subscription.STATUS_ACTIVE,
}


def get_active_subscription(company) -> Subscription | None:
    if company is None:
        return None
    today = timezone.localdate()
    qs = (
        Subscription.objects.filter(company=company)
        .select_related("plan")
        .order_by("-created_at")
    )
    for sub in qs:
        if sub.status == Subscription.STATUS_TRIAL:
            if sub.trial_end_date and sub.trial_end_date < today:
                continue
            return sub
        if sub.status == Subscription.STATUS_ACTIVE:
            if sub.end_date and sub.end_date < today:
                continue
            return sub
    return None


def subscription_allows_access(company) -> bool:
    """True if company may use the app (active/trial). Expired → False (read-only callers)."""
    return get_active_subscription(company) is not None


def is_read_only(company) -> bool:
    return not subscription_allows_access(company)


def can_add_user(company) -> bool:
    sub = get_active_subscription(company)
    if sub is None:
        return False
    limit = sub.plan.user_limit
    current = CompanyMembership.objects.filter(company=company, is_active=True).count()
    return current < limit


def plan_has_module(company, module_code: str) -> bool:
    sub = get_active_subscription(company)
    if sub is None:
        return False
    ent = PlanModuleEntitlement.objects.filter(
        plan=sub.plan, module_code=module_code
    ).first()
    if ent is None:
        # No explicit entitlement row → allow (open by default for pilot)
        return True
    return ent.is_enabled


def require_writable_subscription(view_func):
    """Pilot decorator for /platform write endpoints."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        company = getattr(request, "company", None)
        if company and is_read_only(company) and request.method not in ("GET", "HEAD", "OPTIONS"):
            return HttpResponseForbidden("Abonelik süresi dolmuş veya kısıtlı (salt okunur).")
        return view_func(request, *args, **kwargs)

    return _wrapped


def start_trial_subscription(company, plan) -> Subscription:
    today = timezone.localdate()
    trial_end = today + timedelta(days=plan.trial_days or 14)
    return Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.STATUS_TRIAL,
        start_date=today,
        trial_end_date=trial_end,
        end_date=trial_end,
        renewal_type=Subscription.RENEWAL_MONTHLY,
        is_auto_renew=False,
    )
