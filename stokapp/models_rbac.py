"""
RBAC: Rol, sistem yetkisi, rol–yetki, kullanıcı–rol.
"""

from django.conf import settings
from django.db import models


class Rol(models.Model):
    """Uygulama rolü (Admin, Yönetici, …)."""

    ad = models.CharField(max_length=100, verbose_name='Ad')
    slug = models.SlugField(max_length=50, unique=True, verbose_name='Kod')
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')

    class Meta:
        db_table = 'rbac_rol'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roller'
        ordering = ['ad']

    def __str__(self):
        return self.ad


class SistemYetkisi(models.Model):
    """Tek bir izin: modül + eylem (örn. stok.ekle)."""

    kod = models.CharField(max_length=120, unique=True, verbose_name='Kod')
    ad = models.CharField(max_length=200, verbose_name='Ad')
    modul = models.CharField(max_length=80, db_index=True, verbose_name='Modül')

    class Meta:
        db_table = 'rbac_sistem_yetkisi'
        verbose_name = 'Yetki'
        verbose_name_plural = 'Yetkiler'
        ordering = ['modul', 'kod']

    def __str__(self):
        return self.kod


class RolYetkisi(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='yetkiler', verbose_name='Rol')
    yetki = models.ForeignKey(
        SistemYetkisi, on_delete=models.CASCADE, related_name='rol_baglantilari', verbose_name='Yetki'
    )

    class Meta:
        db_table = 'rbac_rol_yetkisi'
        verbose_name = 'Rol yetkisi'
        verbose_name_plural = 'Rol yetkileri'
        unique_together = [['rol', 'yetki']]

    def __str__(self):
        return f'{self.rol} → {self.yetki.kod}'


class KullaniciRolu(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tekos_rolleri',
        verbose_name='Kullanıcı',
    )
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='kullanicilar', verbose_name='Rol')

    class Meta:
        db_table = 'rbac_kullanici_rolu'
        verbose_name = 'Kullanıcı rolü'
        verbose_name_plural = 'Kullanıcı rolleri'
        unique_together = [['user', 'rol']]

    def __str__(self):
        return f'{self.user} — {self.rol}'
