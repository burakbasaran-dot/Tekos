"""Public signup feature flags and settings."""

from __future__ import annotations

import os

from django.conf import settings


def _env_flag(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


def public_signup_enabled() -> bool:
    return _env_flag("PUBLIC_SIGNUP_ENABLED", "True")


def trial_signup_enabled() -> bool:
    return public_signup_enabled() and _env_flag("TRIAL_SIGNUP_ENABLED", "True")


def developer_signup_enabled() -> bool:
    return public_signup_enabled() and _env_flag("DEVELOPER_SIGNUP_ENABLED", "True")


def trial_days() -> int:
    try:
        return max(1, int(os.getenv("TRIAL_DAYS", "30")))
    except ValueError:
        return 30


def email_verification_hours() -> int:
    try:
        return max(1, int(os.getenv("EMAIL_VERIFICATION_HOURS", "48")))
    except ValueError:
        return 48


def max_trials_per_email() -> int:
    try:
        return max(1, int(os.getenv("MAX_TRIALS_PER_EMAIL", "1")))
    except ValueError:
        return 1


def max_trials_per_ip() -> int:
    try:
        return max(1, int(os.getenv("MAX_TRIALS_PER_IP", "5")))
    except ValueError:
        return 5


def application_upload_max_mb() -> int:
    try:
        return max(1, int(os.getenv("APPLICATION_UPLOAD_MAX_MB", "5")))
    except ValueError:
        return 5


def admin_notification_email() -> str:
    return os.getenv("ADMIN_NOTIFICATION_EMAIL", "").strip()


def site_base_url() -> str:
    url = getattr(settings, "SITE_URL", "") or ""
    if url:
        return url.rstrip("/")
    return "http://localhost:8000"


def captcha_enabled() -> bool:
    return _env_flag("CAPTCHA_ENABLED", "False")
