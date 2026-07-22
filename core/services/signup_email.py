"""Platform-level transactional emails for signup flows."""

from __future__ import annotations

import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.models import SignupApplication
from core.services.email_verification import build_verification_url
from core.services.signup_settings import admin_notification_email, site_base_url

logger = logging.getLogger(__name__)


def _send(template_base: str, subject: str, to: list[str], context: dict) -> bool:
    if not to or not to[0]:
        return False
    try:
        text_body = render_to_string(f"core/emails/{template_base}.txt", context)
        html_body = render_to_string(f"core/emails/{template_base}.html", context)
        msg = EmailMultiAlternatives(subject=subject, body=text_body, to=to)
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email: %s to %s", template_base, to)
        return False


def send_trial_verification_email(application: SignupApplication, signed_token: str) -> bool:
    url = build_verification_url(signed_token)
    ctx = {"application": application, "verify_url": url, "site_url": site_base_url()}
    return _send(
        "trial_email_verification",
        "TEKOS — E-posta adresinizi doğrulayın",
        [application.email],
        ctx,
    )


def send_developer_verification_email(application: SignupApplication, signed_token: str) -> bool:
    url = build_verification_url(signed_token)
    ctx = {"application": application, "verify_url": url, "site_url": site_base_url()}
    return _send(
        "developer_email_verification",
        "TEKOS — Geliştirici başvurusu e-posta doğrulama",
        [application.email],
        ctx,
    )


def send_developer_received_email(application: SignupApplication) -> bool:
    ctx = {"application": application, "site_url": site_base_url()}
    return _send(
        "developer_application_received",
        "TEKOS — Geliştirici başvurunuz alındı",
        [application.email],
        ctx,
    )


def send_trial_welcome_email(application: SignupApplication) -> bool:
    company = application.created_company
    sub = application.created_subscription
    ctx = {
        "application": application,
        "company": company,
        "subscription": sub,
        "login_url": f"{site_base_url()}/accounts/login/",
        "site_url": site_base_url(),
    }
    return _send(
        "trial_welcome",
        "TEKOS deneme hesabınız hazır",
        [application.email],
        ctx,
    )


def send_provisioning_failed_admin(application: SignupApplication) -> bool:
    admin_email = admin_notification_email()
    if not admin_email:
        return False
    ctx = {"application": application, "site_url": site_base_url()}
    return _send(
        "trial_provisioning_failed_admin",
        f"[TEKOS] Deneme provisioning başarısız — {application.email}",
        [admin_email],
        ctx,
    )


def send_developer_admin_notification(application: SignupApplication) -> bool:
    admin_email = admin_notification_email()
    if not admin_email:
        return False
    ctx = {"application": application, "site_url": site_base_url()}
    return _send(
        "developer_application_admin_notification",
        f"[TEKOS] Yeni geliştirici başvurusu — {application.full_name}",
        [admin_email],
        ctx,
    )


def send_trial_reminder_email(application: SignupApplication, days_left: int) -> bool:
    template_map = {7: "trial_7_days_remaining", 3: "trial_3_days_remaining", 1: "trial_1_day_remaining"}
    template = template_map.get(days_left)
    if not template:
        return False
    ctx = {
        "application": application,
        "company": application.created_company,
        "subscription": application.created_subscription,
        "days_left": days_left,
        "site_url": site_base_url(),
    }
    return _send(template, f"TEKOS deneme süreniz — {days_left} gün kaldı", [application.email], ctx)


def send_trial_expired_email(application: SignupApplication) -> bool:
    ctx = {
        "application": application,
        "company": application.created_company,
        "site_url": site_base_url(),
    }
    return _send("trial_expired", "TEKOS deneme süreniz sona erdi", [application.email], ctx)
