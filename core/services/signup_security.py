"""Rate limiting, honeypot, CAPTCHA abstraction for public signup."""

from __future__ import annotations

import logging
from typing import Protocol

from django.core.cache import cache
from django.core.exceptions import ValidationError

from core.services.signup_settings import (
    application_upload_max_mb,
    captcha_enabled,
    max_trials_per_ip,
)

logger = logging.getLogger(__name__)

ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx"}
ALLOWED_CV_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class CaptchaVerifier(Protocol):
    def verify(self, token: str, remote_ip: str | None) -> bool: ...


class NullCaptchaVerifier:
    def verify(self, token: str, remote_ip: str | None) -> bool:
        return True


def get_captcha_verifier() -> CaptchaVerifier:
    if not captcha_enabled():
        return NullCaptchaVerifier()
    # Future: HCaptchaVerifier / reCAPTCHA
    return NullCaptchaVerifier()


def _cache_key(prefix: str, identifier: str) -> str:
    return f"signup:{prefix}:{identifier}"


def check_rate_limit(prefix: str, identifier: str, limit: int, window_seconds: int = 3600) -> bool:
    """Return True if under limit, False if exceeded."""
    if not identifier:
        return True
    key = _cache_key(prefix, identifier)
    count = cache.get(key, 0)
    if count >= limit:
        return False
    cache.set(key, count + 1, window_seconds)
    return True


def enforce_signup_rate_limits(request, email: str) -> None:
    from core.services.audit import client_ip_from_request

    ip = client_ip_from_request(request) or "unknown"
    if not check_rate_limit("ip_submit", ip, max_trials_per_ip(), 3600):
        raise ValidationError("Çok fazla başvuru denemesi. Lütfen daha sonra tekrar deneyin.")
    email_key = (email or "").lower().strip()
    if email_key and not check_rate_limit("email_submit", email_key, 3, 3600):
        raise ValidationError("Bu e-posta adresi için çok fazla deneme yapıldı.")


def validate_honeypot(value: str) -> None:
    if value:
        raise ValidationError("Geçersiz form gönderimi.")


def validate_captcha(request) -> None:
    verifier = get_captcha_verifier()
    token = request.POST.get("captcha_token", "")
    from core.services.audit import client_ip_from_request

    if not verifier.verify(token, client_ip_from_request(request)):
        raise ValidationError("Güvenlik doğrulaması başarısız.")


def validate_cv_upload(uploaded_file) -> None:
    if not uploaded_file:
        return
    max_bytes = application_upload_max_mb() * 1024 * 1024
    if uploaded_file.size > max_bytes:
        raise ValidationError(f"Dosya boyutu en fazla {application_upload_max_mb()} MB olabilir.")
    name = (uploaded_file.name or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_CV_EXTENSIONS:
        raise ValidationError("Yalnızca PDF veya Word dosyası yükleyebilirsiniz.")
    content_type = (uploaded_file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CV_MIMES:
        raise ValidationError("Geçersiz dosya türü.")


def _get_session(session_or_request):
    return getattr(session_or_request, "session", session_or_request)


def store_pending_password(session_or_request, application_id: int, password: str) -> None:
    """Store password in session until email verification (not in DB)."""
    session = _get_session(session_or_request)
    session[f"signup_pw_{application_id}"] = password
    session.modified = True


def pop_pending_password(session_or_request, application_id: int) -> str | None:
    session = _get_session(session_or_request)
    key = f"signup_pw_{application_id}"
    password = session.pop(key, None)
    session.modified = True
    return password
