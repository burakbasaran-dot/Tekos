from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from core.services.tenancy import user_can_manage_platform


def platform_manage_required(view_func):
    """Require login + platform manage capability (403 if authenticated but not allowed)."""

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not user_can_manage_platform(request.user):
            return HttpResponseForbidden(
                "Bu sayfaya erişim yetkiniz yok. "
                "Firma sahibi/yönetici veya personel yetkisi gerekir."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped
