"""
RBAC: URL adına göre yetki kontrolü (registry).
"""

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render
from django.conf import settings

from .rbac_registry import RBAC_URL_PERMISSIONS
from .rbac_utils import has_permission


class RbacMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = getattr(request, 'resolver_match', None)
        if match and match.app_name == 'stokapp':
            url_name = match.url_name
            kod = RBAC_URL_PERMISSIONS.get(url_name)
            if kod:
                if not request.user.is_authenticated:
                    return redirect_to_login(
                        request.get_full_path(),
                        settings.LOGIN_URL,
                        'next',
                    )
                if not has_permission(request.user, kod):
                    return render(
                        request,
                        'stokapp/rbac/403_yetki.html',
                        {'gerekli_yetki': kod},
                        status=403,
                    )
        return self.get_response(request)
