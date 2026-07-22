"""Email verification tokens for signup applications."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.core import signing
from django.utils import timezone

from core.models import EmailVerificationToken, SignupApplication
from core.services.applications import set_application_status
from core.services.signup_settings import email_verification_hours, site_base_url


class VerificationError(Exception):
    pass


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_verification_token(application: SignupApplication) -> str:
    """Create signed token and store hash in DB. Returns raw token for URL."""
    raw = secrets.token_urlsafe(32)
    expires = timezone.now() + timedelta(hours=email_verification_hours())
    EmailVerificationToken.objects.create(
        application=application,
        token_hash=_hash_token(raw),
        expires_at=expires,
    )
    signed = signing.dumps(
        {"app_id": application.pk, "token": raw},
        salt="tekos-email-verify",
    )
    return signed


def build_verification_url(signed_token: str) -> str:
    return f"{site_base_url()}/accounts/verify-email/{signed_token}/"


def verify_email_token(signed_token: str) -> SignupApplication:
    try:
        payload = signing.loads(
            signed_token,
            salt="tekos-email-verify",
            max_age=email_verification_hours() * 3600,
        )
    except signing.BadSignature as exc:
        raise VerificationError("Doğrulama bağlantısı geçersiz veya süresi dolmuş.") from exc

    app_id = payload.get("app_id")
    raw = payload.get("token")
    if not app_id or not raw:
        raise VerificationError("Geçersiz doğrulama bağlantısı.")

    try:
        application = SignupApplication.objects.get(pk=app_id)
    except SignupApplication.DoesNotExist as exc:
        raise VerificationError("Başvuru bulunamadı.") from exc

    token_hash = _hash_token(raw)
    token_row = (
        EmailVerificationToken.objects.filter(
            application=application,
            token_hash=token_hash,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
    if token_row is None:
        raise VerificationError("Doğrulama bağlantısı geçersiz veya zaten kullanılmış.")

    token_row.used_at = timezone.now()
    token_row.save(update_fields=["used_at"])

    application.email_verified = True
    application.email_verified_at = timezone.now()
    application.save(update_fields=["email_verified", "email_verified_at", "updated_at"])

    return application


def resend_verification(application: SignupApplication) -> str:
    if application.email_verified:
        raise VerificationError("E-posta zaten doğrulanmış.")
    if application.status not in (
        SignupApplication.STATUS_EMAIL_VERIFICATION_PENDING,
        SignupApplication.STATUS_SUBMITTED,
    ):
        raise VerificationError("Bu başvuru için doğrulama e-postası gönderilemez.")
    return create_verification_token(application)
