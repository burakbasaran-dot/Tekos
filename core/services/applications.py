"""Signup application status transitions and helpers."""

from __future__ import annotations

import uuid

from django.utils import timezone

from core.models import ApplicationStatusHistory, SignupApplication


def generate_idempotency_key() -> str:
    return uuid.uuid4().hex


def set_application_status(
    application: SignupApplication,
    new_status: str,
    *,
    changed_by=None,
    note: str = "",
    save: bool = True,
) -> SignupApplication:
    old_status = application.status
    if old_status == new_status:
        return application
    application.status = new_status
    if new_status in (
        SignupApplication.STATUS_ACTIVE,
        SignupApplication.STATUS_APPROVED,
        SignupApplication.STATUS_CONVERTED,
    ):
        application.completed_at = timezone.now()
    ApplicationStatusHistory.objects.create(
        application=application,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        note=note[:500],
    )
    if save:
        application.save(update_fields=["status", "completed_at", "updated_at"])
    return application


def capture_request_meta(application: SignupApplication, request) -> None:
    from core.services.audit import client_ip_from_request

    application.ip_address = client_ip_from_request(request)
    application.user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]
    application.source = (request.GET.get("source") or request.POST.get("source") or "")[:40]
    application.utm_source = (request.GET.get("utm_source") or "")[:80]
    application.utm_medium = (request.GET.get("utm_medium") or "")[:80]
    application.utm_campaign = (request.GET.get("utm_campaign") or "")[:120]
    application.referrer_url = (request.META.get("HTTP_REFERER") or "")[:200]
