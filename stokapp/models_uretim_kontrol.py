"""
Üretim Kontrol modülü — fotoğraflı kontrol planı ve ölçüm oturumları.
"""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .models import Siparis, StokItem, UretimEmri


MEASUREMENT_UNIT_CHOICES = [
    ('mm', 'mm'),
    ('cm', 'cm'),
    ('metre', 'metre'),
    ('adet', 'adet'),
    ('derece', 'derece'),
    ('kg', 'kg'),
    ('gr', 'gr'),
    ('N', 'N'),
    ('Nm', 'Nm'),
    ('bar', 'bar'),
    ('mikron', 'mikron'),
    ('diger', 'diğer'),
]

MEASUREMENT_METHOD_CHOICES = [
    ('kumpas', 'Kumpas'),
    ('mikrometre', 'Mikrometre'),
    ('mihengir', 'Mihengir'),
    ('komparator', 'Komparatör'),
    ('serit_metre', 'Şerit metre'),
    ('gozle', 'Gözle kontrol'),
    ('diger', 'Diğer'),
]

SESSION_STATUS_CHOICES = [
    ('DRAFT', 'Taslak'),
    ('IN_PROGRESS', 'Devam ediyor'),
    ('PAUSED', 'Duraklatıldı'),
    ('COMPLETED', 'Tamamlandı'),
    ('CANCELLED', 'İptal'),
]

FINAL_RESULT_CHOICES = [
    ('', 'Belirlenmedi'),
    ('KABUL', 'Kabul'),
    ('RED', 'Red'),
    ('SARTLI', 'Şartlı Kabul'),
]

RESULT_STATUS_CHOICES = [
    ('PENDING', 'Bekliyor'),
    ('OK', 'Uygun'),
    ('NOK', 'Uygun Değil'),
    ('MISSING', 'Eksik ölçüm'),
    ('OUT_OF_REVISION', 'Revizyon dışı'),
]


def next_revision_no(current: str) -> str:
    """R00 -> R01, R09 -> R10"""
    if not current or not current.startswith('R'):
        return 'R00'
    try:
        n = int(current[1:])
    except ValueError:
        return 'R00'
    return f'R{n + 1:02d}'


class ProductionControlPlan(models.Model):
    product = models.ForeignKey(
        StokItem, on_delete=models.PROTECT, related_name='uretim_kontrol_planlari', verbose_name='Ürün'
    )
    sub_part = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='uretim_kontrol_alt_parca_planlari',
        verbose_name='Alt parça',
    )
    revision_no = models.CharField(max_length=10, default='R00', verbose_name='Revizyon no')
    description = models.TextField(blank=True, verbose_name='Genel açıklama')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='olusturdugu_uretim_kontrol_planlari'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name='Arşivlenme')
    superseded_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='onceki_revizyonlar',
        verbose_name='Yerini alan plan',
    )
    photo_annotation_schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Fotoğraf işaretleme şeması (ileride)',
        help_text='İleride ok/daire/çizgi için altyapı.',
    )

    class Meta:
        verbose_name = 'Üretim Kontrol Planı'
        verbose_name_plural = 'Üretim Kontrol Planları'
        ordering = ['product', 'sub_part', '-revision_no']
        unique_together = [['product', 'sub_part', 'revision_no']]

    def __str__(self):
        sp = self.sub_part.stok_kodu if self.sub_part else '—'
        return f'{self.product.stok_kodu} / {sp} [{self.revision_no}]'

    @property
    def sub_part_label(self):
        if self.sub_part:
            return f'{self.sub_part.stok_kodu} — {self.sub_part.ad}'
        return 'Ana ürün (tümü)'

    def deactivate(self):
        self.is_active = False
        self.archived_at = timezone.now()
        self.save(update_fields=['is_active', 'archived_at', 'updated_at'])


class ProductionControlStep(models.Model):
    control_plan = models.ForeignKey(
        ProductionControlPlan, on_delete=models.CASCADE, related_name='steps', verbose_name='Kontrol planı'
    )
    step_no = models.PositiveIntegerField(verbose_name='Adım no')
    title = models.CharField(max_length=200, verbose_name='Başlık')
    description = models.TextField(blank=True, verbose_name='Açıklama')
    photo = models.ImageField(
        upload_to='uretim_kontrol/steps/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Kontrol fotoğrafı',
    )
    photo_annotation_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Fotoğraf üzeri işaretleme (ileride)',
    )
    nominal_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Nominal değer'
    )
    nominal_unit = models.CharField(
        max_length=20, choices=MEASUREMENT_UNIT_CHOICES, default='mm', verbose_name='Nominal birim'
    )
    plus_tolerance = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Artı tolerans'
    )
    plus_tolerance_unit = models.CharField(
        max_length=20, choices=MEASUREMENT_UNIT_CHOICES, default='mm', verbose_name='Artı tolerans birimi'
    )
    minus_tolerance = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Eksi tolerans'
    )
    minus_tolerance_unit = models.CharField(
        max_length=20, choices=MEASUREMENT_UNIT_CHOICES, default='mm', verbose_name='Eksi tolerans birimi'
    )
    measurement_method = models.CharField(
        max_length=50, choices=MEASUREMENT_METHOD_CHOICES, default='kumpas', verbose_name='Ölçüm yöntemi'
    )
    measurement_method_other = models.CharField(max_length=120, blank=True, verbose_name='Diğer yöntem')
    is_required = models.BooleanField(default=True, verbose_name='Zorunlu kontrol')
    is_critical = models.BooleanField(default=False, verbose_name='Kritik ölçü')
    note = models.TextField(blank=True, verbose_name='Not')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Sıra')

    class Meta:
        verbose_name = 'Kontrol adımı'
        verbose_name_plural = 'Kontrol adımları'
        ordering = ['sort_order', 'step_no', 'id']

    def __str__(self):
        return f'{self.step_no}. {self.title}'

    def lower_limit(self):
        if self.nominal_value is None:
            return None
        tol = self.minus_tolerance or Decimal('0')
        return self.nominal_value - tol

    def upper_limit(self):
        if self.nominal_value is None:
            return None
        tol = self.plus_tolerance or Decimal('0')
        return self.nominal_value + tol

    def evaluate_measurement(self, measured_value):
        """Ölçüm sonucuna göre uygunluk."""
        if measured_value is None:
            return 'MISSING', None
        lo = self.lower_limit()
        hi = self.upper_limit()
        if lo is None or hi is None:
            return 'PENDING', None
        measured = Decimal(str(measured_value))
        deviation = measured - self.nominal_value
        if lo <= measured <= hi:
            return 'OK', deviation
        return 'NOK', deviation

    def snapshot_dict(self):
        return {
            'step_no': self.step_no,
            'title': self.title,
            'description': self.description,
            'photo': self.photo.name if self.photo else '',
            'nominal_value': str(self.nominal_value) if self.nominal_value is not None else None,
            'nominal_unit': self.nominal_unit,
            'plus_tolerance': str(self.plus_tolerance) if self.plus_tolerance is not None else None,
            'plus_tolerance_unit': self.plus_tolerance_unit,
            'minus_tolerance': str(self.minus_tolerance) if self.minus_tolerance is not None else None,
            'minus_tolerance_unit': self.minus_tolerance_unit,
            'measurement_method': self.measurement_method,
            'is_critical': self.is_critical,
            'note': self.note,
        }


class ProductionControlRevisionArchive(models.Model):
    product = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        related_name='uretim_kontrol_revizyon_urun',
        verbose_name='Ürün',
    )
    sub_part = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='uretim_kontrol_revizyon_alt_parca',
        verbose_name='Alt parça',
    )
    old_revision_no = models.CharField(max_length=10, verbose_name='Eski revizyon')
    new_revision_no = models.CharField(max_length=10, verbose_name='Yeni revizyon')
    change_note = models.TextField(verbose_name='Değişiklik açıklaması')
    archived_data_json = models.JSONField(default=dict, verbose_name='Arşiv verisi')
    old_plan = models.ForeignKey(
        ProductionControlPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revision_archives',
    )
    new_plan = models.ForeignKey(
        ProductionControlPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_from_archives',
    )
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kontrol planı revizyon arşivi'
        verbose_name_plural = 'Kontrol planı revizyon arşivleri'
        ordering = ['-changed_at']


class ProductionControlSession(models.Model):
    control_plan = models.ForeignKey(
        ProductionControlPlan, on_delete=models.PROTECT, related_name='sessions', verbose_name='Kontrol planı'
    )
    control_plan_revision_no = models.CharField(max_length=10, verbose_name='Plan revizyon no')
    order = models.ForeignKey(
        Siparis, on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_kontrol_oturumlari'
    )
    work_order = models.ForeignKey(
        UretimEmri,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uretim_kontrol_oturumlari',
    )
    product = models.ForeignKey(StokItem, on_delete=models.PROTECT, related_name='uretim_kontrol_oturumlari')
    sub_part = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='uretim_kontrol_oturum_alt_parca',
    )
    inspector = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='yaptigi_uretim_kontrolleri', verbose_name='Kontrolcü'
    )
    control_date = models.DateField(verbose_name='Kontrol tarihi')
    lot_no = models.CharField(max_length=80, blank=True, verbose_name='Parti / lot no')
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=1, verbose_name='Kontrol miktarı'
    )
    general_note = models.TextField(blank=True, verbose_name='Genel not')
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default='DRAFT')
    final_result = models.CharField(max_length=10, choices=FINAL_RESULT_CHOICES, default='', blank=True)
    current_step_index = models.PositiveIntegerField(default=0, verbose_name='Güncel adım indeksi')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False, verbose_name='Arşivlendi')
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name='Arşivlenme tarihi')
    archived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='arsivledigi_uretim_kontrolleri',
        verbose_name='Arşivleyen',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Üretim kontrol oturumu'
        verbose_name_plural = 'Üretim kontrol oturumları'
        ordering = ['-created_at']

    def __str__(self):
        return f'Oturum #{self.pk} — {self.product.stok_kodu} [{self.control_plan_revision_no}]'

    def total_steps(self):
        return self.control_plan.steps.count()

    def compute_final_result(self):
        results = self.results.select_related('step')
        if results.filter(status='NOK', step__is_critical=True).exists():
            return 'RED'
        if results.filter(status='NOK').exists():
            return 'SARTLI'
        if results.filter(status__in=('PENDING', 'MISSING')).exists():
            return ''
        return 'KABUL'


class ProductionControlResult(models.Model):
    session = models.ForeignKey(
        ProductionControlSession, on_delete=models.CASCADE, related_name='results', verbose_name='Oturum'
    )
    step = models.ForeignKey(
        ProductionControlStep, on_delete=models.PROTECT, related_name='session_results', verbose_name='Adım'
    )
    step_snapshot_json = models.JSONField(default=dict, blank=True, verbose_name='Adım anlık görüntüsü')
    measured_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Ölçülen değer'
    )
    measured_unit = models.CharField(max_length=20, choices=MEASUREMENT_UNIT_CHOICES, blank=True)
    deviation = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    lower_limit = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    upper_limit = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=20, choices=RESULT_STATUS_CHOICES, default='PENDING')
    measurement_note = models.TextField(blank=True, verbose_name='Ölçüm notu')
    measured_at = models.DateTimeField(null=True, blank=True)
    sample_index = models.PositiveIntegerField(
        default=1,
        verbose_name='Örnek no',
        help_text='İleride tekrar ölçüm için örnek indeksi.',
    )

    class Meta:
        verbose_name = 'Kontrol ölçüm sonucu'
        verbose_name_plural = 'Kontrol ölçüm sonuçları'
        ordering = ['step__sort_order', 'step__step_no', 'sample_index']
        unique_together = [['session', 'step', 'sample_index']]

    def refresh_from_measurement(self):
        snap = self.step_snapshot_json or self.step.snapshot_dict()
        nominal_raw = snap.get('nominal_value')
        nominal = Decimal(str(nominal_raw)) if nominal_raw is not None else self.step.nominal_value
        minus_raw = snap.get('minus_tolerance')
        plus_raw = snap.get('plus_tolerance')
        minus = Decimal(str(minus_raw)) if minus_raw is not None else (self.step.minus_tolerance or Decimal('0'))
        plus = Decimal(str(plus_raw)) if plus_raw is not None else (self.step.plus_tolerance or Decimal('0'))
        if nominal is not None:
            self.lower_limit = nominal - minus
            self.upper_limit = nominal + plus
        if self.measured_value is not None and nominal is not None:
            measured = Decimal(str(self.measured_value))
            self.deviation = measured - nominal
            if self.lower_limit is not None and self.upper_limit is not None:
                if self.lower_limit <= measured <= self.upper_limit:
                    self.status = 'OK'
                else:
                    self.status = 'NOK'
            else:
                self.status = 'PENDING'
        else:
            self.deviation = None
            self.status = 'MISSING' if self.measured_value is None else 'PENDING'


class ProductionControlResultChangeLog(models.Model):
    result = models.ForeignKey(
        ProductionControlResult, on_delete=models.CASCADE, related_name='change_logs'
    )
    old_value = models.CharField(max_length=50, blank=True)
    new_value = models.CharField(max_length=50, blank=True)
    change_note = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']
