"""
Kenar çubuğu / sekme içi menü öğelerinin görünürlüğü.

Gizli öğeler: yalnızca superuser (sistem admin) sönük önizleme ile görür.
RBAC Admin rolü bu öğeleri açmaz — sunum kullanıcıları menüleri kullanabilir
ama "Yakında / Gizli" öğeleri görmez.
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.conf import settings
from django.shortcuts import render

# Menü anahtarları
NAV_KEY_URETIM_TEKORA_ONAY = 'uretim.tekora_onay_merkezi'
NAV_KEY_URETIM_CANLI_AKIS = 'uretim.canli_akis_haritasi'
NAV_KEY_URETIM_KONTROL = 'uretim.kontrol'
NAV_KEY_STOK_TAMAMLANMA_RAPORU = 'stok.tamamlanma_raporu'
NAV_KEY_STOK_TAMAMLANMA_KURALLARI = 'stok.tamamlanma_kurallari'
NAV_KEY_ENERJI_YONETIM = 'enerji.yonetim'
NAV_KEY_AYARLAR_GELISTIRME = 'ayarlar.gelistirme_talepleri'

# Gizli menü öğeleri (yalnızca superuser görür)
NAV_HIDDEN_ITEMS: frozenset[str] = frozenset({
    NAV_KEY_URETIM_TEKORA_ONAY,
    NAV_KEY_URETIM_CANLI_AKIS,
    NAV_KEY_URETIM_KONTROL,
    NAV_KEY_STOK_TAMAMLANMA_RAPORU,
    NAV_KEY_STOK_TAMAMLANMA_KURALLARI,
    NAV_KEY_ENERJI_YONETIM,
    NAV_KEY_AYARLAR_GELISTIRME,
})


def can_see_hidden_nav(user) -> bool:
    """Gizli menü önizlemesi yalnızca Django superuser için."""
    return bool(
        getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_superuser', False)
    )


def is_nav_item_hidden(nav_key: str) -> bool:
    return nav_key in NAV_HIDDEN_ITEMS


def nav_item_visible_to_user(user, nav_key: str) -> bool:
    if not is_nav_item_hidden(nav_key):
        return True
    return can_see_hidden_nav(user)


def hidden_nav_access_required(nav_key: str, login_url=None):
    """Gizli menü öğesine bağlı view: superuser dışı erişimi engeller."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(),
                    login_url or settings.LOGIN_URL,
                    'next',
                )
            if is_nav_item_hidden(nav_key) and not can_see_hidden_nav(request.user):
                return render(
                    request,
                    'stokapp/rbac/403_yetki.html',
                    {'gerekli_yetki': 'Sistem yöneticisi (superuser)'},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
