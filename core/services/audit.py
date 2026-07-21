"""Platform audit logging with sensitive-field redaction."""

from __future__ import annotations

from typing import Any

from core.models import PlatformAuditLog

SENSITIVE_KEYS = {
    "password",
    "password1",
    "password2",
    "token",
    "secret",
    "secret_key",
    "api_key",
    "apikey",
    "session",
    "cookie",
    "csrfmiddlewaretoken",
    "authorization",
}


def redact_dict(data: dict | None) -> dict:
    if not data:
        return {}
    redacted = {}
    for key, value in data.items():
        key_l = str(key).lower()
        if any(s in key_l for s in SENSITIVE_KEYS):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        else:
            redacted[key] = value
    return redacted


def client_ip_from_request(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # Take first hop only; do not trust blindly in high-security setups
        return forwarded.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or None)


def log_action(
    *,
    action: str,
    user=None,
    company=None,
    model_name: str = "",
    object_id: Any = "",
    object_repr: str = "",
    old_values: dict | None = None,
    new_values: dict | None = None,
    request=None,
) -> PlatformAuditLog:
    ip = None
    ua = ""
    path = ""
    method = ""
    if request is not None:
        ip = getattr(request, "audit_ip", None) or client_ip_from_request(request)
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:512]
        path = (request.path or "")[:512]
        method = (request.method or "")[:16]
        if company is None:
            company = getattr(request, "company", None)
        if user is None and getattr(request, "user", None) and request.user.is_authenticated:
            user = request.user

    return PlatformAuditLog.objects.create(
        company=company,
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        model_name=model_name or "",
        object_id=str(object_id) if object_id is not None else "",
        object_repr=(object_repr or "")[:255],
        old_values=redact_dict(old_values),
        new_values=redact_dict(new_values),
        ip_address=ip,
        user_agent=ua,
        request_path=path,
        request_method=method,
    )


def model_to_dict_safe(instance, fields=None) -> dict:
    data = {}
    for field in instance._meta.fields:
        name = field.name
        if fields is not None and name not in fields:
            continue
        try:
            value = getattr(instance, name)
            if hasattr(value, "pk"):
                value = value.pk
            elif hasattr(value, "url") or hasattr(value, "name"):
                # FileField / ImageField
                value = str(getattr(value, "name", value) or "")
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, (str, int, float, bool, type(None))):
                pass
            else:
                value = str(value)
            data[name] = value
        except Exception:
            continue
    return data
