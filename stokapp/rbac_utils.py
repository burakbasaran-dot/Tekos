"""
RBAC yardımcıları: kullanıcı yetkileri, kontrol, önbellek.
"""

from __future__ import annotations

from functools import lru_cache
from typing import FrozenSet

from django.core.cache import cache

from .models_rbac import KullaniciRolu, Rol, RolYetkisi, SistemYetkisi

CACHE_PREFIX = 'rbac:perms:'
CACHE_TTL = 120


def _cache_key(user_id: int) -> str:
    return f'{CACHE_PREFIX}{user_id}'


def clear_user_permission_cache(user_id: int | None = None) -> None:
    if user_id is not None:
        cache.delete(_cache_key(user_id))
        return
    # tüm rbac önbelleği temizlenemezse kullanıcı bazlı silinir; toplu flush yok
    pass


def get_user_permissions(user) -> FrozenSet[str]:
    """Kullanıcının sahip olduğu tüm yetki kodları (immutable set)."""
    if not getattr(user, 'is_authenticated', False):
        return frozenset()
    if getattr(user, 'is_superuser', False):
        return frozenset(SistemYetkisi.objects.values_list('kod', flat=True))

    key = _cache_key(user.pk)
    cached = cache.get(key)
    if cached is not None:
        return frozenset(cached)

    rol_ids = list(
        KullaniciRolu.objects.filter(user_id=user.pk).values_list('rol_id', flat=True)
    )
    if not rol_ids:
        cache.set(key, [], CACHE_TTL)
        return frozenset()

    admin_rol = Rol.objects.filter(slug='admin').values_list('id', flat=True).first()
    if admin_rol and admin_rol in rol_ids:
        all_codes = list(SistemYetkisi.objects.values_list('kod', flat=True))
        cache.set(key, all_codes, CACHE_TTL)
        return frozenset(all_codes)

    kodlar = set(
        RolYetkisi.objects.filter(rol_id__in=rol_ids).values_list('yetki__kod', flat=True)
    )
    lst = sorted(kodlar)
    cache.set(key, lst, CACHE_TTL)
    return frozenset(lst)


def user_is_admin(user) -> bool:
    """Superuser veya RBAC admin rolü."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    admin_rol = Rol.objects.filter(slug='admin').values_list('id', flat=True).first()
    if not admin_rol:
        return False
    return KullaniciRolu.objects.filter(user_id=user.pk, rol_id=admin_rol).exists()


def has_permission(user, kod: str) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    perms = get_user_permissions(user)
    return kod in perms


def user_has_any(user, kodlar: list[str]) -> bool:
    return any(has_permission(user, k) for k in kodlar)
