"""
RBAC view decorator.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render
from django.conf import settings

from .rbac_utils import has_permission


def permission_required(kod: str, login_url=None):
    """
    @permission_required("stok.ekle")
    Yetkisiz → 403 (giriş yapılmamışsa login).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(),
                    login_url or settings.LOGIN_URL,
                    'next',
                )
            if not has_permission(request.user, kod):
                return render(
                    request,
                    'stokapp/rbac/403_yetki.html',
                    {'gerekli_yetki': kod},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
