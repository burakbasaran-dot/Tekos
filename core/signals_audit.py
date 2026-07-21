"""Pilot audit signals for platform + RBAC models."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.models import (
    Company,
    CompanyMembership,
    PlatformAuditLog,
    Subscription,
)
from core.services.audit import log_action, model_to_dict_safe

_pre_save_cache: dict[tuple, dict] = {}


def _cache_key(sender, instance):
    return (sender, instance.pk)


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    log_action(
        action=PlatformAuditLog.ACTION_LOGIN,
        user=user,
        request=request,
        model_name="auth.User",
        object_id=user.pk,
        object_repr=str(user),
    )


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    log_action(
        action=PlatformAuditLog.ACTION_LOGOUT,
        user=user,
        request=request,
        model_name="auth.User",
        object_id=getattr(user, "pk", ""),
        object_repr=str(user) if user else "",
    )


@receiver(pre_save, sender=Company)
@receiver(pre_save, sender=CompanyMembership)
@receiver(pre_save, sender=Subscription)
def cache_old_values(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        _pre_save_cache[_cache_key(sender, instance)] = model_to_dict_safe(old)
    except sender.DoesNotExist:
        pass


def _log_save(sender, instance, created, action_create, action_update):
    key = _cache_key(sender, instance)
    old_values = _pre_save_cache.pop(key, {}) if not created else {}
    new_values = model_to_dict_safe(instance)
    company = getattr(instance, "company", None)
    if sender is Company:
        company = instance
    log_action(
        action=action_create if created else action_update,
        company=company,
        model_name=f"{sender._meta.app_label}.{sender._meta.object_name}",
        object_id=instance.pk,
        object_repr=str(instance)[:255],
        old_values=old_values,
        new_values=new_values,
    )


@receiver(post_save, sender=Company)
def audit_company_save(sender, instance, created, **kwargs):
    _log_save(
        sender,
        instance,
        created,
        PlatformAuditLog.ACTION_SETTINGS_CHANGE if not created else PlatformAuditLog.ACTION_CREATE,
        PlatformAuditLog.ACTION_SETTINGS_CHANGE,
    )


@receiver(post_save, sender=CompanyMembership)
def audit_membership_save(sender, instance, created, **kwargs):
    _log_save(
        sender,
        instance,
        created,
        PlatformAuditLog.ACTION_PERMISSION_CHANGE,
        PlatformAuditLog.ACTION_PERMISSION_CHANGE,
    )


@receiver(post_save, sender=Subscription)
def audit_subscription_save(sender, instance, created, **kwargs):
    _log_save(
        sender,
        instance,
        created,
        PlatformAuditLog.ACTION_CREATE,
        PlatformAuditLog.ACTION_UPDATE,
    )


@receiver(post_delete, sender=CompanyMembership)
def audit_membership_delete(sender, instance, **kwargs):
    log_action(
        action=PlatformAuditLog.ACTION_DELETE,
        company=instance.company,
        model_name=f"{sender._meta.app_label}.{sender._meta.object_name}",
        object_id=instance.pk,
        object_repr=str(instance)[:255],
        old_values=model_to_dict_safe(instance),
    )


def _register_rbac_signals():
    try:
        from stokapp.models_rbac import KullaniciRolu, RolYetkisi
    except Exception:
        return

    @receiver(pre_save, sender=KullaniciRolu)
    @receiver(pre_save, sender=RolYetkisi)
    def cache_rbac_old(sender, instance, **kwargs):
        if not instance.pk:
            return
        try:
            old = sender.objects.get(pk=instance.pk)
            _pre_save_cache[_cache_key(sender, instance)] = model_to_dict_safe(old)
        except sender.DoesNotExist:
            pass

    @receiver(post_save, sender=KullaniciRolu)
    @receiver(post_save, sender=RolYetkisi)
    def audit_rbac_save(sender, instance, created, **kwargs):
        key = _cache_key(sender, instance)
        old_values = _pre_save_cache.pop(key, {}) if not created else {}
        log_action(
            action=PlatformAuditLog.ACTION_PERMISSION_CHANGE,
            model_name=f"{sender._meta.app_label}.{sender._meta.object_name}",
            object_id=instance.pk,
            object_repr=str(instance)[:255],
            old_values=old_values,
            new_values=model_to_dict_safe(instance),
        )

    @receiver(post_delete, sender=KullaniciRolu)
    @receiver(post_delete, sender=RolYetkisi)
    def audit_rbac_delete(sender, instance, **kwargs):
        log_action(
            action=PlatformAuditLog.ACTION_DELETE,
            model_name=f"{sender._meta.app_label}.{sender._meta.object_name}",
            object_id=instance.pk,
            object_repr=str(instance)[:255],
            old_values=model_to_dict_safe(instance),
        )


_register_rbac_signals()
