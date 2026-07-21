from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models_rbac import KullaniciRolu, RolYetkisi
from .rbac_utils import clear_user_permission_cache


def _clear_rol_kullanicilari(rol_id):
    for uid in KullaniciRolu.objects.filter(rol_id=rol_id).values_list('user_id', flat=True):
        clear_user_permission_cache(uid)


@receiver(post_save, sender=KullaniciRolu)
@receiver(post_delete, sender=KullaniciRolu)
def _rbac_kullanici_rolu(sender, instance, **kwargs):
    clear_user_permission_cache(instance.user_id)


@receiver(post_save, sender=RolYetkisi)
@receiver(post_delete, sender=RolYetkisi)
def _rbac_rol_yetkisi(sender, instance, **kwargs):
    _clear_rol_kullanicilari(instance.rol_id)
