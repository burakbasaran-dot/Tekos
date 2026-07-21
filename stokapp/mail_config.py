"""Genel ayarlardan e-posta (SMTP/IMAP/POP) yapılandırmasını okur ve Django'ya uygular."""

from __future__ import annotations

import json
import os
from typing import Any

from django.conf import settings

PASSWORD_MASK = "••••••••••"


def _is_masked(value: str) -> bool:
    if not value:
        return True
    return value == PASSWORD_MASK or set(value) <= {"•", "*", "·"}


def mask_secret(value: str) -> str:
    return PASSWORD_MASK if (value or "").strip() else ""


def merge_imap_accounts_json(new_raw: str, old_accounts: list | None) -> list:
    """JSON metninde maskeli şifreleri mevcut kayıttan korur."""
    try:
        parsed = json.loads(new_raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("IMAP hesapları geçerli JSON olmalıdır.") from exc
    if not isinstance(parsed, list):
        raise ValueError("IMAP hesapları bir dizi (liste) olmalıdır.")

    old_by_email = {
        (acc or {}).get("email", "").strip().lower(): acc
        for acc in (old_accounts or [])
        if (acc or {}).get("email")
    }
    merged: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        email = (item.get("email") or "").strip()
        if not email:
            continue
        password = (item.get("password") or "").strip()
        if _is_masked(password):
            old = old_by_email.get(email.lower()) or {}
            password = (old.get("password") or "").strip()
        merged.append({"email": email, "password": password})
    return merged


def format_imap_accounts_for_display(accounts: list | None) -> str:
    masked = []
    for acc in accounts or []:
        if not isinstance(acc, dict):
            continue
        email = (acc.get("email") or "").strip()
        if not email:
            continue
        masked.append({"email": email, "password": mask_secret(acc.get("password") or "")})
    return json.dumps(masked, indent=2, ensure_ascii=False)


def ensure_mail_defaults_from_env(ayarlar) -> bool:
    """Boş mail alanlarını yalnızca TEKOS_MAIL_SYNC_FROM_ENV=1 ise .env'den doldurur."""
    if os.getenv('TEKOS_MAIL_SYNC_FROM_ENV', '').lower() not in ('1', 'true', 'yes'):
        return False

    changed = False

    def _set(field: str, value):
        nonlocal changed
        if value in (None, ""):
            return
        if not getattr(ayarlar, field, None):
            setattr(ayarlar, field, value)
            changed = True

    _set("email_backend", os.getenv("EMAIL_BACKEND", ""))
    _set("smtp_host", os.getenv("EMAIL_HOST", ""))
    if ayarlar.smtp_port in (None, 0):
        port = os.getenv("EMAIL_PORT", "")
        if port:
            ayarlar.smtp_port = int(port)
            changed = True
    if ayarlar.smtp_use_tls is None:
        ayarlar.smtp_use_tls = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
        changed = True
    if ayarlar.smtp_use_ssl is None:
        ayarlar.smtp_use_ssl = os.getenv("EMAIL_USE_SSL", "false").lower() in ("1", "true", "yes")
        changed = True
    _set("smtp_username", os.getenv("EMAIL_HOST_USER", ""))
    _set("smtp_password", os.getenv("EMAIL_HOST_PASSWORD", ""))
    timeout = os.getenv("EMAIL_TIMEOUT", "")
    if timeout and not ayarlar.smtp_timeout:
        ayarlar.smtp_timeout = int(timeout)
        changed = True
    _set("default_from_email", os.getenv("DEFAULT_FROM_EMAIL", ""))
    _set("server_email", os.getenv("SERVER_EMAIL", ""))
    _set("email_subject_prefix", os.getenv("EMAIL_SUBJECT_PREFIX", ""))

    _set("imap_server", os.getenv("IMAP_SERVER", ""))
    if ayarlar.imap_port in (None, 0):
        imap_port = os.getenv("IMAP_PORT", "")
        if imap_port:
            ayarlar.imap_port = int(imap_port)
            changed = True
    if not ayarlar.imap_hesaplari:
        raw = os.getenv("MAIL_ACCOUNTS_JSON", "[]")
        try:
            ayarlar.imap_hesaplari = json.loads(raw or "[]")
        except json.JSONDecodeError:
            ayarlar.imap_hesaplari = []
        changed = True

    if changed:
        ayarlar.save()
    return changed


def get_imap_config(ayarlar=None) -> dict[str, Any]:
    from .models import GenelAyarlar

    ayarlar = ayarlar or GenelAyarlar.get_ayarlar()
    return {
        "server": (ayarlar.imap_server or "").strip() or os.getenv("IMAP_SERVER", ""),
        "port": int(ayarlar.imap_port or os.getenv("IMAP_PORT", 993) or 993),
        "use_ssl": bool(ayarlar.imap_use_ssl),
        "mailbox": (ayarlar.imap_mailbox or "INBOX").strip() or "INBOX",
        "body_max_chars": int(ayarlar.imap_body_max_chars or 524288),
        "accounts": list(ayarlar.imap_hesaplari or []),
    }


def get_pop_config(ayarlar=None) -> dict[str, Any]:
    from .models import GenelAyarlar

    ayarlar = ayarlar or GenelAyarlar.get_ayarlar()
    return {
        "server": (ayarlar.pop_server or "").strip(),
        "port": int(ayarlar.pop_port or 995),
        "use_ssl": bool(ayarlar.pop_use_ssl),
        "username": (ayarlar.pop_username or "").strip(),
        "password": (ayarlar.pop_password or "").strip(),
    }


def apply_mail_settings(ayarlar=None) -> None:
    """Django settings ve IMAP ortam değişkenlerini günceller."""
    from .models import GenelAyarlar

    ayarlar = ayarlar or GenelAyarlar.get_ayarlar()
    backend = (ayarlar.email_backend or "").strip()
    if backend:
        settings.EMAIL_BACKEND = backend
    if ayarlar.smtp_host:
        settings.EMAIL_HOST = ayarlar.smtp_host
    if ayarlar.smtp_port:
        settings.EMAIL_PORT = int(ayarlar.smtp_port)
    settings.EMAIL_USE_TLS = bool(ayarlar.smtp_use_tls)
    settings.EMAIL_USE_SSL = bool(ayarlar.smtp_use_ssl)
    if ayarlar.smtp_username:
        settings.EMAIL_HOST_USER = ayarlar.smtp_username
    if ayarlar.smtp_password:
        settings.EMAIL_HOST_PASSWORD = ayarlar.smtp_password
    if ayarlar.smtp_timeout:
        settings.EMAIL_TIMEOUT = int(ayarlar.smtp_timeout)
    if ayarlar.default_from_email:
        settings.DEFAULT_FROM_EMAIL = ayarlar.default_from_email
    if ayarlar.server_email:
        settings.SERVER_EMAIL = ayarlar.server_email
    if ayarlar.email_subject_prefix is not None:
        settings.EMAIL_SUBJECT_PREFIX = ayarlar.email_subject_prefix

    imap = get_imap_config(ayarlar)
    if imap["server"]:
        os.environ["IMAP_SERVER"] = imap["server"]
        settings.IMAP_SERVER = imap["server"]
    os.environ["IMAP_PORT"] = str(imap["port"])
    settings.IMAP_PORT = imap["port"]
    os.environ["IMAP_BODY_MAX_CHARS"] = str(imap["body_max_chars"])
    if imap["accounts"]:
        os.environ["MAIL_ACCOUNTS_JSON"] = json.dumps(imap["accounts"], ensure_ascii=False)
        settings.MAIL_ACCOUNTS_JSON = os.environ["MAIL_ACCOUNTS_JSON"]
