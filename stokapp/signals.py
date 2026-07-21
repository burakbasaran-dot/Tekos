from django.db.models.signals import pre_save, post_save, post_delete, pre_init
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import (
    StokItem, FiyatGecmisi,
    Complaint, CapaAction, EcoChange, AlertRule, ControlPlan,
    AuditLog
)

User = get_user_model()


@receiver(pre_save, sender=StokItem)
def fiyat_degisiklik_kaydet(sender, instance, **kwargs):
    """StokItem kaydedilmeden önce fiyat değişikliklerini kontrol et ve kaydet"""
    if instance.pk:  # Yeni kayıt değilse (güncelleme)
        try:
            eski_kayit = StokItem.objects.get(pk=instance.pk)
            
            # Fiyat değişikliklerini kontrol et
            fiyat_degisiklikleri = []
            
            # Alış fiyatı değişti mi?
            if eski_kayit.alis_fiyati != instance.alis_fiyati:
                fiyat_degisiklikleri.append({
                    'alan': 'alis_fiyati',
                    'eski': eski_kayit.alis_fiyati,
                    'yeni': instance.alis_fiyati
                })
            
            # Satış fiyatı değişti mi?
            if eski_kayit.satis_fiyati != instance.satis_fiyati:
                fiyat_degisiklikleri.append({
                    'alan': 'satis_fiyati',
                    'eski': eski_kayit.satis_fiyati,
                    'yeni': instance.satis_fiyati
                })
            
            # Satın alma fiyatı değişti mi?
            if eski_kayit.satin_alma_fiyati != instance.satin_alma_fiyati:
                fiyat_degisiklikleri.append({
                    'alan': 'satin_alma_fiyati',
                    'eski': eski_kayit.satin_alma_fiyati,
                    'yeni': instance.satin_alma_fiyati
                })
            
            # Her değişiklik için geçmiş kaydı oluştur
            for degisiklik in fiyat_degisiklikleri:
                # Kullanıcı bilgisini al (eğer request context'inde varsa)
                # Şimdilik 'Sistem' olarak kaydediyoruz, view'da override edilebilir
                user_name = 'Sistem'
                
                # Geçmiş kaydı oluştur
                gecmis = FiyatGecmisi(
                    stok_item=instance,
                    degisen_alan=degisiklik['alan'],
                    para_birimi=instance.alis_para_birimi,
                    user=user_name
                )
                
                # Alan bazlı eski ve yeni değerleri ata
                if degisiklik['alan'] == 'alis_fiyati':
                    gecmis.eski_alis_fiyati = degisiklik['eski']
                    gecmis.yeni_alis_fiyati = degisiklik['yeni']
                elif degisiklik['alan'] == 'satis_fiyati':
                    gecmis.eski_satis_fiyati = degisiklik['eski']
                    gecmis.yeni_satis_fiyati = degisiklik['yeni']
                elif degisiklik['alan'] == 'satin_alma_fiyati':
                    gecmis.eski_satin_alma_fiyati = degisiklik['eski']
                    gecmis.yeni_satin_alma_fiyati = degisiklik['yeni']
                
                gecmis.save()
                
        except StokItem.DoesNotExist:
            pass  # Yeni kayıt, geçmiş kaydı gerekmez


# ============================================================================
# Audit Log Signal Handlers
# ============================================================================

def create_audit_log(instance, action_type, user=None, field_name=None, old_value=None, new_value=None, notes=None):
    """Audit log kaydı oluştur"""
    content_type = instance.__class__.__name__
    object_id = instance.pk
    
    if user is None:
        # Thread-local'dan user'ı almayı dene (view'da set edilecek)
        try:
            import threading
            user = getattr(threading.current_thread(), 'request_user', None)
        except:
            user = None
    
    AuditLog.objects.create(
        content_type=content_type,
        object_id=object_id,
        action_type=action_type,
        field_name=field_name or '',
        old_value=str(old_value) if old_value is not None else '',
        new_value=str(new_value) if new_value is not None else '',
        user=user,
        notes=notes or ''
    )


# Complaint signals
@receiver(post_save, sender=Complaint)
def complaint_saved(sender, instance, created, **kwargs):
    """Complaint kaydedildiğinde audit log oluştur"""
    action_type = 'CREATE' if created else 'UPDATE'
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, action_type, user=user)


@receiver(pre_save, sender=Complaint)
def complaint_status_changed_pre(sender, instance, **kwargs):
    """Complaint durumu değiştiğinde özel log (pre_save)"""
    if instance.pk:
        try:
            old = Complaint.objects.get(pk=instance.pk)
            if old.status != instance.status:
                # Thread-local'a kaydet, post_save'de kullanılacak
                try:
                    import threading
                    setattr(threading.current_thread(), '_complaint_status_changed', {
                        'old_status': old.status,
                        'new_status': instance.status
                    })
                except:
                    pass
        except Complaint.DoesNotExist:
            pass


@receiver(post_save, sender=Complaint)
def complaint_status_changed_post(sender, instance, created, **kwargs):
    """Complaint durumu değiştiğinde özel log (post_save)"""
    if not created:
        try:
            import threading
            status_change = getattr(threading.current_thread(), '_complaint_status_changed', None)
            if status_change:
                try:
                    user = getattr(threading.current_thread(), 'request_user', None)
                except:
                    user = None
                old_obj = Complaint()
                old_obj.status = status_change['old_status']
                create_audit_log(
                    instance, 'STATUS_CHANGE', user=user,
                    field_name='status',
                    old_value=old_obj.get_status_display(),
                    new_value=instance.get_status_display()
                )
                # Temizle
                try:
                    delattr(threading.current_thread(), '_complaint_status_changed')
                except:
                    pass
        except:
            pass


# CapaAction signals
@receiver(post_save, sender=CapaAction)
def capa_saved(sender, instance, created, **kwargs):
    """CapaAction kaydedildiğinde audit log oluştur"""
    action_type = 'CREATE' if created else 'UPDATE'
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, action_type, user=user)


# EcoChange signals
@receiver(post_save, sender=EcoChange)
def eco_saved(sender, instance, created, **kwargs):
    """EcoChange kaydedildiğinde audit log oluştur"""
    action_type = 'CREATE' if created else 'UPDATE'
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, action_type, user=user)


@receiver(pre_save, sender=EcoChange)
def eco_approval_changed_pre(sender, instance, **kwargs):
    """ECO onay durumu değiştiğinde log (pre_save)"""
    if instance.pk:
        try:
            old = EcoChange.objects.get(pk=instance.pk)
            if old.approval_status != instance.approval_status:
                try:
                    import threading
                    setattr(threading.current_thread(), '_eco_approval_changed', {
                        'old_status': old.approval_status,
                        'new_status': instance.approval_status
                    })
                except:
                    pass
        except EcoChange.DoesNotExist:
            pass


@receiver(post_save, sender=EcoChange)
def eco_approval_changed_post(sender, instance, created, **kwargs):
    """ECO onay durumu değiştiğinde log (post_save)"""
    if not created:
        try:
            import threading
            approval_change = getattr(threading.current_thread(), '_eco_approval_changed', None)
            if approval_change:
                try:
                    user = getattr(threading.current_thread(), 'request_user', None)
                except:
                    user = instance.approved_by
                
                action_type = 'APPROVE' if instance.approval_status == 'APPROVED' else 'REJECT' if instance.approval_status == 'REJECTED' else 'STATUS_CHANGE'
                old_obj = EcoChange()
                old_obj.approval_status = approval_change['old_status']
                create_audit_log(
                    instance, action_type, user=user,
                    field_name='approval_status',
                    old_value=old_obj.get_approval_status_display(),
                    new_value=instance.get_approval_status_display()
                )
                # Temizle
                try:
                    delattr(threading.current_thread(), '_eco_approval_changed')
                except:
                    pass
        except:
            pass


# AlertRule signals
@receiver(post_save, sender=AlertRule)
def alert_rule_saved(sender, instance, created, **kwargs):
    """AlertRule kaydedildiğinde audit log oluştur"""
    action_type = 'CREATE' if created else 'UPDATE'
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, action_type, user=user)


# Delete signals
@receiver(post_delete, sender=Complaint)
def complaint_deleted(sender, instance, **kwargs):
    """Complaint silindiğinde audit log"""
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, 'DELETE', user=user)


@receiver(post_delete, sender=CapaAction)
def capa_deleted(sender, instance, **kwargs):
    """CapaAction silindiğinde audit log"""
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, 'DELETE', user=user)


@receiver(post_delete, sender=EcoChange)
def eco_deleted(sender, instance, **kwargs):
    """EcoChange silindiğinde audit log"""
    try:
        import threading
        user = getattr(threading.current_thread(), 'request_user', None)
    except:
        user = None
    create_audit_log(instance, 'DELETE', user=user)