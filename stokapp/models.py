from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q, Sum
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.utils.text import slugify
import uuid
import hashlib
import json
from pgvector.django import VectorField

class Kategori(models.Model):
    STOK_TIPLERI = [
        ('HAM_MADDE', 'Ham Madde'),
        ('YARI_MAMUL', 'Yarı Mamül'),
        ('URUN', 'Ürün'),
    ]
    ad = models.CharField(max_length=100)
    stok_tipi = models.CharField(max_length=15, choices=STOK_TIPLERI, default='HAM_MADDE')
    aciklama = models.TextField(blank=True)

    def __str__(self):
        return f"{self.ad} ({self.get_stok_tipi_display()})"


class Tedarikci(models.Model):
    ad = models.CharField(max_length=200)
    telefon = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adres = models.TextField(blank=True)
    kategoriler = models.ManyToManyField(
        'Kategori',
        blank=True,
        related_name='tedarikciler',
        verbose_name='Etiketler / Kategoriler',
        help_text='Bu tedarikçinin tedarik ettiği kategori etiketleri. RFQ önerilerinde kullanılır.',
    )
    aktif = models.BooleanField(default=True, verbose_name='Aktif')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.ad


class TedarikciIlgiliKisi(models.Model):
    """Tedarikçi kartına bağlı iletişim / ilgili kişiler."""

    tedarikci = models.ForeignKey(
        Tedarikci, on_delete=models.CASCADE, related_name='ilgili_kisiler', verbose_name='Tedarikçi'
    )
    ad_soyad = models.CharField(max_length=200, verbose_name='Adı Soyadı')
    gorev = models.CharField(max_length=120, blank=True, verbose_name='Görevi')
    telefon = models.CharField(max_length=40, blank=True, verbose_name='Telefon')
    email = models.EmailField(blank=True, verbose_name='E-posta')
    ozel_not = models.TextField(blank=True, verbose_name='Özel not')
    sira = models.PositiveSmallIntegerField(default=0, verbose_name='Sıra')

    class Meta:
        verbose_name = 'Tedarikçi ilgili kişi'
        verbose_name_plural = 'Tedarikçi ilgili kişiler'
        ordering = ['sira', 'id']

    def __str__(self):
        return f'{self.ad_soyad} ({self.tedarikci})'


class StokItem(models.Model):
    PARA_BIRIMLERI = [
        ('TL', 'Türk Lirası (₺)'),
        ('USD', 'Amerikan Doları ($)'),
        ('EUR', 'Euro (€)'),
        ('GBP', 'İngiliz Sterlini (£)'),
    ]
    
    STOK_TIPLERI = [
        ('HAM_MADDE', 'Ham Madde'),
        ('YARI_MAMUL', 'Yarı Mamül'),
        ('URUN', 'Ürün'),
    ]
    URUN_ROLLERI = [
        ('AL_SAT', 'Al - Sat Ürün'),
        ('BILESEN', 'Üretim Bileşeni'),
        ('NIHAI_URUN', 'Nihai Ürün'),
    ]

    stok_kodu = models.CharField(max_length=50, unique=True)
    ad = models.CharField(max_length=200)
    aciklama = models.TextField(blank=True)

    kategori = models.ForeignKey(Kategori, on_delete=models.PROTECT)
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.SET_NULL, null=True, blank=True)

    # Basit tutmak için metin birim (ileride Birim FK'ya dönüştürülebilir)
    birim = models.CharField(max_length=20, default='Adet')

    AGIRLIK_BIRIMLERI = [
        ('kg', 'kg'),
        ('g', 'g'),
        ('ton', 'ton'),
        ('mg', 'mg'),
        ('lb', 'lb'),
    ]
    urun_agirligi = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Ürün / Bileşen Ağırlığı',
    )
    urun_agirlik_birimi = models.CharField(
        max_length=10,
        choices=AGIRLIK_BIRIMLERI,
        default='kg',
        blank=True,
        verbose_name='Ağırlık birimi',
    )

    barkod = models.CharField(max_length=100, blank=True)

    alis_fiyati = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    alis_para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TL')

    mevcut_miktar = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    dis_operasyonda_miktar = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Dış operasyonda (tedarikçide)',
        help_text='Şirket dışı operasyonda / tedarikçide bekleyen miktar (depo dışı takip).',
    )
    minimum_stok = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    maximum_stok = models.DecimalField(max_digits=10, decimal_places=3, default=0, null=True, blank=True)
    guvenlik_stoku = models.DecimalField(max_digits=10, decimal_places=3, default=0)

    uretim_suresi = models.IntegerField(default=0, help_text="Dakika cinsinden")
    uretim_maliyeti = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    fotograf = models.ImageField(upload_to='stok_foto/%Y/%m/%d/', blank=True, null=True)
    teknik_resim = models.FileField(upload_to='stok_teknik_resim/%Y/%m/%d/', blank=True, null=True, verbose_name="Teknik Resim (DXF/DWG)")

    satin_alma_fiyati = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    satis_fiyati = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    satis_para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TL', blank=True, verbose_name="Satış Para Birimi")

    acilis_miktari = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    stok_takip = models.BooleanField(default=True)

    # Depo / Raf
    depo = models.ForeignKey('Depo', null=True, blank=True, on_delete=models.SET_NULL)
    raf = models.ForeignKey('Raf', null=True, blank=True, on_delete=models.SET_NULL)

    urun_tipi = models.CharField(max_length=10, choices=(('SATINAL','Satın Alma'),('URETIM','Üretim')), default='SATINAL')
    urun_rolu = models.CharField(
        max_length=20,
        choices=URUN_ROLLERI,
        default='AL_SAT',
        verbose_name='Ürün Rolü',
    )
    tedarikci_kodu = models.CharField(max_length=120, blank=True, null=True)
    arsivli = models.BooleanField(default=False)
    
    # Stok tipi - kategori stok tipinden bağımsız, her stok için ayrı
    STOK_TIPLERI = [
        ('HAM_MADDE', 'Ham Madde'),
        ('YARI_MAMUL', 'Yarı Mamül'),
        ('URUN', 'Ürün'),
    ]
    stok_tipi = models.CharField(max_length=15, choices=STOK_TIPLERI, blank=True, null=True, verbose_name="Stok Tipi")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_stok_tipi(self):
        """Stok tipini döndür - önce kendi stok tipini, yoksa kategorinin stok tipini"""
        if self.stok_tipi:
            return self.stok_tipi
        return self.kategori.stok_tipi if self.kategori else None

    def __str__(self):
        return f"{self.stok_kodu} - {self.ad}"


class Recete(models.Model):
    urun = models.ForeignKey(StokItem, on_delete=models.CASCADE, related_name='ana_urun')
    versiyon = models.CharField(max_length=20, default='1.0')
    aktif = models.BooleanField(default=True)
    aciklama = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['urun', 'versiyon']

    def __str__(self):
        return f"{self.urun.stok_kodu} - v{self.versiyon}"


class ReceteDetay(models.Model):
    recete = models.ForeignKey(Recete, on_delete=models.CASCADE, related_name='detaylar')
    stok_item = models.ForeignKey(StokItem, on_delete=models.CASCADE)
    miktar = models.DecimalField(max_digits=10, decimal_places=3)
    birim = models.CharField(max_length=20)
    sira = models.IntegerField(default=0)

    class Meta:
        ordering = ['sira']

    def __str__(self):
        return f"{self.recete.urun.stok_kodu} - {self.stok_item.stok_kodu}"


class ReceteOperasyon(models.Model):
    """Reçete operasyonları - bileşen bazlı operasyon adımları"""
    recete = models.ForeignKey(Recete, on_delete=models.CASCADE, related_name='operasyonlar')
    recete_detay = models.ForeignKey(
        ReceteDetay,
        on_delete=models.CASCADE,
        related_name='operasyonlar',
        null=True,
        blank=True,
        verbose_name="Reçete bileşeni",
        help_text="Boş bırakılırsa operasyon Genel Operasyon altında listelenir.",
    )
    operasyon = models.ForeignKey('Operasyon', on_delete=models.PROTECT, verbose_name="Operasyon")
    istasyon = models.ForeignKey('Istasyon', on_delete=models.PROTECT, null=True, blank=True, verbose_name="İstasyon")
    uretim_standarti = models.ForeignKey('UretimStandarti', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Üretim Standartı")
    bagimliliklar = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='bagimli_operasyonlar', verbose_name="Bağımlılıklar")
    maliyet = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Maliyet (TRY/saat)")
    sure_dakika = models.IntegerField(default=0, verbose_name="Süre (Dakika)")
    toplam_maliyet = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Toplam Maliyet (TRY)")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    dis_operasyon_tipi = models.ForeignKey(
        'DisOperasyonTipi',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recete_operasyonlar',
        verbose_name='Dış operasyon tipi',
        help_text='İş emrinde bu adımda “İşi Başlat” ile otomatik dış operasyon oluşturulur.',
    )
    dis_tedarikci = models.ForeignKey(
        'Tedarikci',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recete_dis_operasyon_adimlari',
        verbose_name='Dış operasyon taşeronu',
    )
    dis_gonderim_deposu = models.ForeignKey(
        'Depo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recete_dis_gonderimleri',
        verbose_name='Dış operasyon gönderim deposu',
        help_text='İsteğe bağlı; boşsa hareket deposu boş kaydedilir.',
    )
    dis_birim_fiyat = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        verbose_name='Dış operasyon birim fiyatı',
    )
    dis_para_birimi = models.CharField(
        max_length=3,
        choices=StokItem.PARA_BIRIMLERI,
        default='TL',
        verbose_name='Dış operasyon para birimi',
    )
    dis_beklenen_donus_gun = models.PositiveSmallIntegerField(
        default=7,
        verbose_name='Beklenen dönüş (gün)',
        help_text='Beklenen dönüş tarihi = gönderim + bu gün (gönderim, işi başlattığınız gündür).',
    )
    dis_sevk_evrak_no = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Sevk evrak / irsaliye no (isteğe bağlı)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reçete Operasyonu"
        verbose_name_plural = "Reçete Operasyonları"
        ordering = ['sira', 'id']

    def __str__(self):
        return f"{self.recete.urun.stok_kodu} - {self.operasyon.ad}"
    
    def save(self, *args, **kwargs):
        # Toplam maliyeti hesapla: maliyet * (sure_dakika / 60)
        if self.maliyet and self.sure_dakika:
            from decimal import Decimal
            self.toplam_maliyet = Decimal(str(self.maliyet)) * Decimal(str(self.sure_dakika)) / Decimal('60')
        super().save(*args, **kwargs)
    
    def get_sure_formatted(self):
        """Süreyi HH:MM:SS formatında döndür"""
        saat = self.sure_dakika // 60
        dakika = self.sure_dakika % 60
        saniye = 0
        return f"{saat:02d}:{dakika:02d}:{saniye:02d}"


class ReceteDisOperasyon(models.Model):
    """Reçete dış operasyon atamaları — ürün geneli veya bileşen bazlı."""

    recete = models.ForeignKey(
        Recete,
        on_delete=models.CASCADE,
        related_name='dis_operasyon_atamalari',
    )
    recete_detay = models.ForeignKey(
        ReceteDetay,
        on_delete=models.CASCADE,
        related_name='dis_operasyon_atamalari',
        null=True,
        blank=True,
        verbose_name='Reçete bileşeni',
        help_text='Boş bırakılırsa ürün geneline atanır.',
    )
    dis_operasyon_tipi = models.ForeignKey(
        'DisOperasyonTipi',
        on_delete=models.PROTECT,
        related_name='recete_dis_atamalari',
        verbose_name='Dış operasyon tipi',
    )
    tedarikci = models.ForeignKey(
        'Tedarikci',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recete_dis_atamalari',
        verbose_name='Taşeron / tedarikçi',
    )
    dis_gonderim_deposu = models.ForeignKey(
        'Depo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recete_dis_atama_gonderimleri',
        verbose_name='Gönderim deposu',
    )
    dis_birim_fiyat = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        verbose_name='Birim işlem fiyatı',
    )
    dis_para_birimi = models.CharField(
        max_length=3,
        choices=StokItem.PARA_BIRIMLERI,
        default='TL',
        verbose_name='Para birimi',
    )
    dis_beklenen_donus_gun = models.PositiveSmallIntegerField(
        default=7,
        verbose_name='Beklenen dönüş (gün)',
    )
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    sira = models.IntegerField(default=0, verbose_name='Sıra')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reçete Dış Operasyonu'
        verbose_name_plural = 'Reçete Dış Operasyonları'
        ordering = ['recete_detay__sira', 'recete_detay_id', 'sira', 'id']

    def __str__(self):
        hedef = self.recete_detay.stok_item.stok_kodu if self.recete_detay_id else 'Ürün Geneli'
        return f'{self.recete.urun.stok_kodu} — {hedef} — {self.dis_operasyon_tipi.ad}'


class ToolMaterial(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "materials"
        verbose_name = "Takım Malzemesi"
        verbose_name_plural = "Takım Malzemeleri"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ToolTypeOption(models.Model):
    name = models.CharField(max_length=100, unique=True)
    prefix = models.CharField(max_length=8, unique=True)
    aktif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_type_options"
        verbose_name = "Takım Tipi"
        verbose_name_plural = "Takım Tipleri"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ToolBrandOption(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_brand_options"
        verbose_name = "Takım Markası"
        verbose_name_plural = "Takım Markaları"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ToolCoatingOption(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_coating_options"
        verbose_name = "Takım Kaplaması"
        verbose_name_plural = "Takım Kaplamaları"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ToolModelOption(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_model_options"
        verbose_name = "Takım Model Numarası"
        verbose_name_plural = "Takım Model Numaraları"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ToolBodyMaterialOption(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_body_material_options"
        verbose_name = "Takım Malzemesi"
        verbose_name_plural = "Takım Malzemeleri"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tool(models.Model):
    STATUS_CHOICES = [
        ("active", "Aktif"),
        ("worn", "Körelmiş"),
        ("broken", "Kırılmış"),
        ("scrapped", "Hurda"),
    ]

    tool_code = models.CharField(max_length=32, unique=True, editable=False)
    tool_type = models.CharField(max_length=64)
    tool_type_option = models.ForeignKey(
        ToolTypeOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="tools"
    )
    diameter = models.DecimalField(max_digits=8, decimal_places=3, verbose_name="Çap (mm)")
    brand = models.CharField(max_length=120, blank=True)
    brand_option = models.ForeignKey(
        ToolBrandOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="tools"
    )
    coating = models.CharField(max_length=120, blank=True)
    coating_option = models.ForeignKey(
        ToolCoatingOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="tools"
    )
    model_no = models.CharField(max_length=120, blank=True)
    model_option = models.ForeignKey(
        ToolModelOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="tools"
    )
    body_material_option = models.ForeignKey(
        ToolBodyMaterialOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="tools"
    )
    max_cutting_mm = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    total_cutting_mm = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tools"
        verbose_name = "Takım"
        verbose_name_plural = "Takımlar"
        ordering = ["-created_at"]

    def __str__(self):
        return self.tool_code

    @property
    def tool_type_label(self):
        if self.tool_type_option_id:
            return self.tool_type_option.name
        return self.tool_type

    @staticmethod
    def _format_diameter_for_code(diameter):
        normalized = f"{diameter:.3f}".rstrip("0").rstrip(".")
        return normalized.replace(".", "P")

    @classmethod
    def _build_next_tool_code(cls, tool_type, diameter):
        tool_type_obj = ToolTypeOption.objects.filter(name=tool_type).first()
        prefix = tool_type_obj.prefix if tool_type_obj else "TL"
        diameter_part = cls._format_diameter_for_code(float(diameter))
        base = f"{prefix}-{diameter_part}-"
        last_tool = cls.objects.filter(tool_code__startswith=base).order_by("-tool_code").first()
        last_serial = 0
        if last_tool and last_tool.tool_code:
            try:
                last_serial = int(last_tool.tool_code.split("-")[-1])
            except (ValueError, IndexError):
                last_serial = 0
        return f"{base}{str(last_serial + 1).zfill(4)}"

    @property
    def usage_ratio(self):
        active_life = self.get_active_life()
        if not self.max_cutting_mm or not active_life:
            return 0
        try:
            return float(active_life.cutting_mm / self.max_cutting_mm)
        except Exception:
            return 0

    @property
    def usage_percent(self):
        return round(self.usage_ratio * 100, 2)

    @property
    def warning_level(self):
        ratio = self.usage_ratio
        if ratio >= 1:
            return "replace_required"
        if ratio >= 0.8:
            return "warning"
        return "ok"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if self.tool_type_option_id and not self.tool_type:
            self.tool_type = self.tool_type_option.name
        if self.brand_option_id and not self.brand:
            self.brand = self.brand_option.name
        if self.coating_option_id and not self.coating:
            self.coating = self.coating_option.name
        if self.model_option_id and not self.model_no:
            self.model_no = self.model_option.name
        if not self.tool_code:
            self.tool_code = self._build_next_tool_code(self.tool_type, self.diameter)
        super().save(*args, **kwargs)
        if is_new and not self.life_cycles.exists():
            ToolLifeCycle.objects.create(
                tool=self,
                life_no=1,
                start_date=timezone.now(),
                status="active",
                cutting_mm=0,
            )

    def get_active_life(self):
        return self.life_cycles.filter(status="active").order_by("-life_no").first()

    def start_new_life(self, reason="regrind", note=""):
        last_life_no = self.life_cycles.aggregate(max_no=models.Max("life_no")).get("max_no") or 0
        return ToolLifeCycle.objects.create(
            tool=self,
            life_no=last_life_no + 1,
            start_date=timezone.now(),
            status="active",
            change_reason=reason,
            note=note or "",
            cutting_mm=0,
        )

    def close_active_life(self, reason, note="", end_date=None):
        active_life = self.get_active_life()
        if not active_life:
            return None
        active_life.status = "finished"
        active_life.end_date = end_date or timezone.now()
        active_life.change_reason = reason
        if note:
            active_life.note = note
        active_life.save(update_fields=["status", "end_date", "change_reason", "note"])
        return active_life

    def apply_life_change(self, reason, note="", end_date=None):
        closed_life = self.close_active_life(reason=reason, note=note, end_date=end_date)
        if reason == "regrind":
            self.status = "active"
            self.save(update_fields=["status"])
            new_life = self.start_new_life(reason="regrind", note=note)
            return closed_life, new_life
        if reason == "broken":
            self.status = "broken"
            self.save(update_fields=["status"])
            return closed_life, None
        if reason == "worn":
            self.status = "worn"
            self.save(update_fields=["status"])
            return closed_life, None
        return closed_life, None


class ToolLifeCycle(models.Model):
    STATUS_CHOICES = [
        ("active", "Aktif"),
        ("finished", "Tamamlandı"),
    ]
    CHANGE_REASON_CHOICES = [
        ("worn", "Körelme"),
        ("broken", "Kırılma"),
        ("regrind", "Bileme"),
    ]

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="life_cycles")
    life_no = models.PositiveIntegerField()
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    cutting_mm = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")
    change_reason = models.CharField(max_length=20, choices=CHANGE_REASON_CHOICES, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_life_cycles"
        verbose_name = "Takım Ömrü"
        verbose_name_plural = "Takım Ömürleri"
        ordering = ["-life_no"]
        constraints = [
            models.UniqueConstraint(fields=["tool", "life_no"], name="uniq_tool_life_no"),
            models.UniqueConstraint(
                fields=["tool"],
                condition=Q(status="active"),
                name="uniq_tool_single_active_life",
            ),
        ]

    def __str__(self):
        return f"{self.tool.tool_code} - Ömür #{self.life_no}"


class ReceteOperasyonTakim(models.Model):
    recete_operasyon = models.ForeignKey(
        ReceteOperasyon,
        on_delete=models.CASCADE,
        related_name="takim_kullanimlari",
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.PROTECT,
        related_name="operation_links",
        null=True,
        blank=True,
    )
    tool_type = models.CharField(max_length=64, blank=True)
    hole_count = models.PositiveIntegerField(default=1, verbose_name="Delik Sayısı")
    hole_depth_mm = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Tek Delik Boyu (mm)")
    material = models.ForeignKey(
        ToolMaterial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operation_tools",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recipe_tools"
        verbose_name = "Reçete Operasyon Takımı"
        verbose_name_plural = "Reçete Operasyon Takımları"
        ordering = ["recete_operasyon__sira", "id"]

    def __str__(self):
        tool_label = self.tool.tool_code if self.tool_id else (self.tool_type or "Takım")
        return f"{self.recete_operasyon} - {tool_label}"

    @property
    def cutting_mm_per_piece(self):
        return self.hole_count * self.hole_depth_mm


class ToolUsageLog(models.Model):
    tool = models.ForeignKey(Tool, on_delete=models.PROTECT, related_name="usage_logs")
    life_cycle = models.ForeignKey("ToolLifeCycle", on_delete=models.SET_NULL, null=True, blank=True, related_name="usage_logs")
    task = models.ForeignKey("UretimAsamasi", on_delete=models.CASCADE, related_name="tool_usage_logs")
    work_order = models.ForeignKey("UretimEmri", on_delete=models.CASCADE, related_name="tool_usage_logs")
    material = models.ForeignKey(ToolMaterial, on_delete=models.SET_NULL, null=True, blank=True, related_name="usage_logs")
    cutting_mm = models.DecimalField(max_digits=14, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_usage_logs"
        verbose_name = "Takım Kullanım Kaydı"
        verbose_name_plural = "Takım Kullanım Kayıtları"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "created_at"]),
            models.Index(fields=["material", "created_at"]),
        ]

    def __str__(self):
        return f"{self.tool.tool_code} - {self.cutting_mm} mm"


class ToolChange(models.Model):
    CHANGE_REASONS = [
        ("broken", "Kırıldı"),
        ("worn", "Köreldi"),
        ("regrind", "Bilemeye Gönderildi"),
    ]

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="changes")
    life_cycle = models.ForeignKey("ToolLifeCycle", on_delete=models.SET_NULL, null=True, blank=True, related_name="changes")
    change_date = models.DateTimeField(default=timezone.now)
    change_reason = models.CharField(max_length=20, choices=CHANGE_REASONS)
    cutting_mm_at_change = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tool_changes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tool_changes"
        verbose_name = "Takım Değişim Kaydı"
        verbose_name_plural = "Takım Değişim Kayıtları"
        ordering = ["-change_date", "-id"]

    def __str__(self):
        return f"{self.tool.tool_code} - {self.get_change_reason_display()}"

    def save(self, *args, **kwargs):
        if not self.cutting_mm_at_change:
            self.cutting_mm_at_change = self.tool.total_cutting_mm
        super().save(*args, **kwargs)


class ReceteTalimat(models.Model):
    """Reçete talimatları - Talimatlar sekmesi için"""
    recete = models.ForeignKey(Recete, on_delete=models.CASCADE, related_name='talimatlar')
    sira = models.IntegerField(default=0, verbose_name="Sıra Numarası")
    aciklama = models.TextField(verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reçete Talimatı"
        verbose_name_plural = "Reçete Talimatları"
        ordering = ['sira', 'id']

    def __str__(self):
        return f"{self.recete.urun.stok_kodu} - Talimat #{self.sira}"


class ReceteTalimatOlcu(models.Model):
    """Talimat ölçü bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='olculer')
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama", help_text="Örn: En, Boy, Kalınlık")
    nominal_deger = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Nominal Değer")
    birim = models.CharField(max_length=20, blank=True, verbose_name="Birim")
    min_deger = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Min Değer")
    max_deger = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Max Değer")
    sira = models.IntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Talimat Ölçü"
        verbose_name_plural = "Talimat Ölçüleri"
        ordering = ['sira', 'id']

    def __str__(self):
        return f"{self.talimat} - Ölçü #{self.sira}"


class ReceteTalimatDosya(models.Model):
    """Talimat dosyaları (fotoğraf ve PDF)"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='dosyalar')
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama", help_text="Örn: İşlem Öncesi Görsel, Montaj Şeması")
    dosya = models.FileField(upload_to='recete_talimat_dosyalari/', verbose_name="Dosya")
    dosya_adi = models.CharField(max_length=255, blank=True, verbose_name="Dosya Adı")
    dosya_tipi = models.CharField(max_length=50, blank=True, verbose_name="Dosya Tipi")  # 'foto', 'pdf'
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talimat Dosyası"
        verbose_name_plural = "Talimat Dosyaları"

    def __str__(self):
        return f"{self.talimat} - {self.dosya_adi or self.dosya.name}"


class ReceteTalimatEkipman(models.Model):
    """Talimat ekipman bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='ekipmanlar')
    ekipman = models.ForeignKey('Ekipman', on_delete=models.PROTECT, verbose_name="Ekipman", null=True, blank=True)
    sira = models.IntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Talimat Ekipman"
        verbose_name_plural = "Talimat Ekipmanları"
        ordering = ['sira', 'id']

    def __str__(self):
        if self.ekipman:
            return f"{self.talimat} - {self.ekipman.ad}"
        return f"{self.talimat} - (Ekipman yok)"


class ReceteTalimatFikstur(models.Model):
    """Talimat fikstür bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='fiksturler')
    fikstur = models.ForeignKey('Fikstur', on_delete=models.PROTECT, verbose_name="Fikstür")
    sira = models.IntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Talimat Fikstür"
        verbose_name_plural = "Talimat Fikstürleri"
        ordering = ['sira', 'id']

    def __str__(self):
        return f"{self.talimat} - {self.fikstur.ad}"


class ReceteTalimatProgram(models.Model):
    """Talimat program adı bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='programlar')
    program_adi = models.CharField(max_length=200, verbose_name="Program Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sira = models.IntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Talimat Program"
        verbose_name_plural = "Talimat Programları"
        ordering = ['sira', 'id']

    def __str__(self):
        return f"{self.talimat} - {self.program_adi}"


class ReceteTalimatOlcuAleti(models.Model):
    """Talimat ölçü aleti bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='olcu_aletleri')
    olcu_aleti = models.ForeignKey('OlcuAleti', on_delete=models.PROTECT, verbose_name="Ölçü Aleti", null=True, blank=True)
    sira = models.IntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Talimat Ölçü Aleti"
        verbose_name_plural = "Talimat Ölçü Aletleri"
        ordering = ['sira', 'id']

    def __str__(self):
        if self.olcu_aleti:
            return f"{self.talimat} - {self.olcu_aleti.seri_no}"
        return f"{self.talimat} - (Ölçü aleti yok)"


class ReceteTalimatAciklama(models.Model):
    """Talimat ek açıklamaları"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='ek_aciklamalar', verbose_name="Talimat")
    aciklama = models.TextField(verbose_name="Açıklama")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Talimat Ek Açıklaması"
        verbose_name_plural = "Talimat Ek Açıklamaları"
        ordering = ['sira', 'created_at']
    
    def __str__(self):
        return f"{self.talimat} - Açıklama #{self.sira}"


class ReceteTalimatKurulumDosyasi(models.Model):
    """Talimat kurulum dosyası bilgileri"""
    talimat = models.ForeignKey(ReceteTalimat, on_delete=models.CASCADE, related_name='kurulum_dosyalari', verbose_name="Talimat")
    kurulum_dosyasi = models.ForeignKey('KurulumDosyasi', on_delete=models.PROTECT, verbose_name="Kurulum Dosyası")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Talimat Kurulum Dosyası"
        verbose_name_plural = "Talimat Kurulum Dosyaları"
        ordering = ['sira', 'created_at']
        unique_together = [['talimat', 'kurulum_dosyasi']]
    
    def __str__(self):
        return f"{self.talimat} - {self.kurulum_dosyasi.urun.stok_kodu} v{self.kurulum_dosyasi.versiyon}"


class UretimEmri(models.Model):
    DURUMLAR = [
        ('PLANLANDI', 'Planlandı'),
        ('BASLADI', 'Üretim Başladı'),
        ('TAMAMLANDI', 'Tamamlandı'),
        ('IPTAL', 'İptal Edildi'),
    ]
    URETIM_TIPLERI = [
        ('ORDER', 'Sipariş'),
        ('STOCK', 'Stok Üretimi'),
    ]

    emir_no = models.CharField(max_length=50, unique=True)
    recete = models.ForeignKey(Recete, on_delete=models.PROTECT)
    miktar = models.DecimalField(max_digits=10, decimal_places=3)
    production_type = models.CharField(max_length=10, choices=URETIM_TIPLERI, default='ORDER')
    durum = models.CharField(max_length=15, choices=DURUMLAR, default='PLANLANDI')
    planlanan_baslama = models.DateTimeField()
    planlanan_bitis = models.DateTimeField()
    gerceklesen_baslama = models.DateTimeField(null=True, blank=True)
    gerceklesen_bitis = models.DateTimeField(null=True, blank=True)
    aciklama = models.TextField(blank=True)
    ust_uretim_emri = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alt_emirler",
        verbose_name="Üst iş emri",
        help_text="Siparişten otomatik oluşturulan ara ürün emrinde ana ürün emrine bağlantı.",
    )
    alt_emir_otomatik = models.BooleanField(
        default=False,
        verbose_name="Otomatik alt emir",
        help_text="Reçete eksikliği için sistem tarafından oluşturuldu.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.emir_no} - {self.recete.urun.ad}"


class UretimAsamasi(models.Model):
    DURUMLAR = [
        ('BEKLIYOR', 'Bekliyor'),
        ('DEVAM_EDIYOR', 'Devam Ediyor'),
        ('BEKLEMEDE', 'Beklemede'),
        ('TAMAMLANDI', 'Tamamlandı'),
        ('SORUNLU', 'Sorunlu / Durduruldu'),
    ]

    uretim_emri = models.ForeignKey(UretimEmri, on_delete=models.CASCADE, related_name='asamalar')
    recete_detay = models.ForeignKey(
        ReceteDetay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uretim_asamalari',
        verbose_name="Reçete bileşeni",
    )
    recete_operasyon = models.ForeignKey(
        ReceteOperasyon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uretim_asamalari',
        verbose_name="Reçete operasyonu",
    )
    ad = models.CharField(max_length=100)
    sira = models.IntegerField(default=0)
    planlanan_sure = models.IntegerField(help_text="Dakika cinsinden")
    atanan_personel = models.ForeignKey('Personel', on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_asamalari', verbose_name="Atanan Personel")
    planlanan_baslama = models.DateTimeField(null=True, blank=True, verbose_name="Planlanan Başlama")
    planlanan_bitis = models.DateTimeField(null=True, blank=True, verbose_name="Planlanan Bitiş")
    gerceklesen_sure = models.IntegerField(null=True, blank=True)
    baslama_zamani = models.DateTimeField(null=True, blank=True)
    bitis_zamani = models.DateTimeField(null=True, blank=True)
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='BEKLIYOR')
    duraklatma_toplam_saniye = models.IntegerField(default=0, verbose_name="Toplam Duraklatma Süresi (sn)")
    notlar = models.TextField(blank=True)
    cnc_program_revision = models.ForeignKey('CncProgramRevision', on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_asamalari', verbose_name="Kullanılan CNC Program")

    class Meta:
        ordering = ['sira']

    def __str__(self):
        return f"{self.uretim_emri.emir_no} - {self.ad}"


class UretimAsamaDurusKaydi(models.Model):
    asama = models.ForeignKey(UretimAsamasi, on_delete=models.CASCADE, related_name='durus_kayitlari')
    baslama_zamani = models.DateTimeField()
    bitis_zamani = models.DateTimeField(null=True, blank=True)
    sure_saniye = models.IntegerField(default=0)
    aciklama = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Üretim Aşama Duruş Kaydı"
        verbose_name_plural = "Üretim Aşama Duruş Kayıtları"
        ordering = ['-baslama_zamani']

    def __str__(self):
        return f"{self.asama} - Duruş {self.baslama_zamani:%d.%m.%Y %H:%M}"


class UretimAsamaNot(models.Model):
    asama = models.ForeignKey(UretimAsamasi, on_delete=models.CASCADE, related_name='not_kayitlari')
    not_metni = models.TextField(verbose_name="Not")
    olusturan = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_asama_notlari')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Üretim Aşama Notu"
        verbose_name_plural = "Üretim Aşama Notları"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.asama} - Not"


class UretimAsamaSorun(models.Model):
    SORUN_TIPLERI = [
        ('MALZEME_EKSIK', 'Malzeme eksik'),
        ('TAKIM_PROBLEMI', 'Takım problemi'),
        ('OLCU_PROBLEMI', 'Ölçü problemi'),
        ('TEKNIK_RESIM_UYUMSUZ', 'Teknik resim uyumsuzluğu'),
        ('MAKINE_ARIZASI', 'Makine arızası'),
        ('DIGER', 'Diğer'),
    ]
    DURUM_SECENEKLERI = [
        ('ACIK', 'Açık'),
        ('KAPALI', 'Kapalı'),
    ]

    asama = models.ForeignKey(UretimAsamasi, on_delete=models.CASCADE, related_name='sorun_kayitlari')
    sorun_tipi = models.CharField(max_length=30, choices=SORUN_TIPLERI, default='DIGER')
    aciklama = models.TextField()
    gorsel = models.ImageField(upload_to='uretim_asama_sorun/%Y/%m/%d/', null=True, blank=True)
    olusturan = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_asama_sorunlari')
    durum = models.CharField(max_length=10, choices=DURUM_SECENEKLERI, default='ACIK')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Üretim Aşama Sorunu"
        verbose_name_plural = "Üretim Aşama Sorunları"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.asama} - {self.get_sorun_tipi_display()}"


class StokHareketi(models.Model):
    HAREKET_TIPLERI = [
        ('GIRIS', 'Stok Girişi'),
        ('CIKIS', 'Stok Çıkışı'),
        ('SATIS_STOK', 'Stoktan Satış Çıkışı'),
        ('TRANSFER', 'Depo Transferi'),
        ('SAYIM', 'Sayım Düzeltmesi'),
        ('URETIM_GIRIS', 'Üretim Girişi'),
        ('URETIM_CIKIS', 'Üretim Çıkışı'),
        ('URETIM_IADE', 'Üretim İadesi'),
        ('DISOP_GONDERIM', 'Dış Operasyon Gönderim'),
        ('DISOP_DONUS', 'Dış Operasyon Dönüş'),
        ('DISOP_FIRE', 'Dış Operasyon Fire'),
        ('DISOP_RED', 'Dış Operasyon Red / Hurda'),
        ('DISOP_EKSIK', 'Dış Operasyon Eksik'),
        ('DISOP_TESLIM_KALITE', 'Dış Operasyon Teslim (Kalite Bekliyor)'),
        ('DISOP_QC_KABUL', 'Dış Operasyon Kalite Kabul (Stoğa)'),
    ]

    stok_item = models.ForeignKey(StokItem, on_delete=models.CASCADE)
    hareket_tipi = models.CharField(max_length=22, choices=HAREKET_TIPLERI)
    miktar = models.DecimalField(max_digits=10, decimal_places=3)
    birim = models.CharField(max_length=20)
    referans_no = models.CharField(max_length=100, blank=True)
    depo = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, related_name='hareketler')
    raf = models.ForeignKey('Raf', on_delete=models.SET_NULL, null=True, blank=True, related_name='hareketler')
    uretim_emri = models.ForeignKey(UretimEmri, on_delete=models.SET_NULL, null=True, blank=True)
    dis_operasyon = models.ForeignKey(
        'DisOperasyon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stok_hareketleri',
        verbose_name='Dış operasyon',
    )
    aciklama = models.TextField(blank=True)
    user = models.CharField(max_length=100, default='Sistem')
    tarih = models.DateTimeField(auto_now_add=True)
    onceki_stok = models.DecimalField(max_digits=10, decimal_places=3)
    sonraki_stok = models.DecimalField(max_digits=10, decimal_places=3)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.onceki_stok = self.stok_item.mevcut_miktar
            if self.hareket_tipi in ['GIRIS', 'URETIM_GIRIS', 'URETIM_IADE']:
                self.stok_item.mevcut_miktar += self.miktar
            elif self.hareket_tipi in ['CIKIS', 'URETIM_CIKIS', 'SATIS_STOK']:
                self.stok_item.mevcut_miktar -= self.miktar
            elif self.hareket_tipi == 'DISOP_GONDERIM':
                self.stok_item.mevcut_miktar -= self.miktar
                self.stok_item.dis_operasyonda_miktar += self.miktar
            elif self.hareket_tipi == 'DISOP_DONUS':
                self.stok_item.mevcut_miktar += self.miktar
                self.stok_item.dis_operasyonda_miktar -= self.miktar
            elif self.hareket_tipi in ('DISOP_FIRE', 'DISOP_RED', 'DISOP_EKSIK', 'DISOP_TESLIM_KALITE'):
                self.stok_item.dis_operasyonda_miktar -= self.miktar
            elif self.hareket_tipi == 'DISOP_QC_KABUL':
                self.stok_item.mevcut_miktar += self.miktar
            elif self.hareket_tipi == 'SAYIM':
                # miktar: sayım anındaki mevcut ile sayılan arasındaki işaretli fark (artış + / azalış -)
                self.stok_item.mevcut_miktar += self.miktar
            self.stok_item.save()
            self.sonraki_stok = self.stok_item.mevcut_miktar
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.stok_item.stok_kodu} - {self.get_hareket_tipi_display()} - {self.miktar}"


class StokSayimi(models.Model):
    """Stok sayım oturumu — sıralı sayım ve rapor."""

    DURUMLAR = [
        ('HAZIR', 'Oluşturuldu'),
        ('DEVAM', 'Devam ediyor'),
        ('TAMAMLANDI', 'Tamamlandı'),
        ('IPTAL', 'İptal'),
    ]

    baslik = models.CharField(max_length=200, blank=True, verbose_name='Başlık')
    durum = models.CharField(max_length=15, choices=DURUMLAR, default='HAZIR', verbose_name='Durum')
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stok_sayimlari',
        verbose_name='Oluşturan',
    )
    depo = models.ForeignKey(
        'Depo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Depo filtresi',
        help_text='Boşsa tüm depolar.',
    )
    sadece_stok_takip = models.BooleanField(
        default=True,
        verbose_name='Sadece stok takibi açık ürünler',
    )
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    created_at = models.DateTimeField(auto_now_add=True)
    tamamlanma_zamani = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Stok sayımı'
        verbose_name_plural = 'Stok sayımları'
        ordering = ['-created_at']

    def __str__(self):
        return self.baslik or f'Stok sayımı #{self.pk}'


class StokSayimiKalemi(models.Model):
    """Tek bir stok satırı için sayım durumu."""

    DURUMLAR = [
        ('BEKLIYOR', 'Bekliyor'),
        ('SAYILDI', 'Sayıldı'),
        ('ATLANDI', 'Atlandı'),
    ]

    sayim = models.ForeignKey(StokSayimi, on_delete=models.CASCADE, related_name='kalemler')
    stok_item = models.ForeignKey(StokItem, on_delete=models.CASCADE, related_name='sayim_kalemleri')
    sira = models.PositiveIntegerField(default=0, verbose_name='Sıra')
    sistem_miktar_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name='Sayım başında sistem miktarı',
    )
    sayilan_miktar = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='Sayılan miktar',
    )
    fark_miktar = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='Uygulanan fark',
        help_text='Hareket oluşturulduğunda işaretli fark.',
    )
    durum = models.CharField(max_length=15, choices=DURUMLAR, default='BEKLIYOR', verbose_name='Durum')
    hareket = models.ForeignKey(
        StokHareketi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sayim_kalemi',
        verbose_name='Sayım hareketi',
    )
    notlar = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = 'Stok sayım kalemi'
        verbose_name_plural = 'Stok sayım kalemleri'
        ordering = ['sayim_id', 'sira', 'id']
        indexes = [
            models.Index(fields=['sayim', 'durum', 'sira']),
        ]

    def __str__(self):
        return f'{self.sayim_id} — {self.stok_item.stok_kodu}'


class Cari(models.Model):
    CARI_TIPLERI = [
        ('MUSTERI', 'Müşteri'),
        ('TEDARIKCI', 'Tedarikçi'),
        ('DIGER', 'Diğer'),
    ]

    # Temel Bilgiler
    cari_kodu = models.CharField(max_length=50, unique=True)
    unvan = models.CharField(max_length=200)
    cari_tipi = models.CharField(max_length=10, choices=CARI_TIPLERI, default='MUSTERI')

    # İletişim Bilgileri
    vergi_dairesi = models.CharField(max_length=100, blank=True)
    yetkili = models.CharField(max_length=100, blank=True, null=True)
    vergi_no = models.CharField(max_length=20, blank=True)
    telefon = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adres = models.TextField(blank=True)

    # Finansal Bilgiler
    bakiye = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    risk_limiti = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Durum
    aktif = models.BooleanField(default=True)
    aciklama = models.TextField(blank=True)

    # Takip
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.cari_kodu} - {self.unvan}"

    class Meta:
        verbose_name = "Cari"
        verbose_name_plural = "Cariler"
        ordering = ['unvan']


class Birim(models.Model):
    ad = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.ad


class Depo(models.Model):
    ad = models.CharField(max_length=120, unique=True)
    def __str__(self):
        return self.ad


class Raf(models.Model):
    depo = models.ForeignKey('Depo', on_delete=models.CASCADE, related_name="raflar")
    ad = models.CharField(max_length=80)
    class Meta:
        unique_together = ("depo", "ad")
    def __str__(self):
        return f"{self.depo}:{self.ad}"


class EkDosya(models.Model):
    stok = models.ForeignKey('StokItem', on_delete=models.CASCADE, related_name='ek_dosyalar')
    dosya = models.FileField(upload_to='stok_ekleri/%Y/%m/%d/')
    ad = models.CharField(max_length=160, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.ad or self.dosya.name


class FiyatGecmisi(models.Model):
    """Stok fiyat değişiklik geçmişi"""
    stok_item = models.ForeignKey(StokItem, on_delete=models.CASCADE, related_name='fiyat_gecmisi')
    
    # Eski fiyatlar
    eski_alis_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    eski_satis_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    eski_satin_alma_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    
    # Yeni fiyatlar
    yeni_alis_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    yeni_satis_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    yeni_satin_alma_fiyati = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    
    # Para birimi
    para_birimi = models.CharField(max_length=3, choices=StokItem.PARA_BIRIMLERI, default='TL')
    
    # Değişiklik bilgileri
    degisen_alan = models.CharField(max_length=30, help_text="Hangi fiyat alanı değişti")
    aciklama = models.TextField(blank=True)
    user = models.CharField(max_length=100, default='Sistem')
    tarih = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-tarih']
        verbose_name = "Fiyat Geçmişi"
        verbose_name_plural = "Fiyat Geçmişleri"
    
    def __str__(self):
        return f"{self.stok_item.stok_kodu} - {self.degisen_alan} - {self.tarih.strftime('%d.%m.%Y %H:%M')}"


class ParaBirimi(models.Model):
    kod = models.CharField(max_length=10, unique=True, help_text="Para birimi kodu (örn: TL, USD, EUR)")
    ad = models.CharField(max_length=100, help_text="Para birimi adı (örn: Türk Lirası)")
    sembol = models.CharField(max_length=10, help_text="Para birimi sembolü (örn: ₺, $, €)")
    aktif = models.BooleanField(default=True, help_text="Para birimi aktif mi?")
    
    class Meta:
        verbose_name = "Para Birimi"
        verbose_name_plural = "Para Birimleri"
        ordering = ['kod']
    
    def __str__(self):
        return f"{self.sembol} {self.ad} ({self.kod})"


class GenelAyarlar(models.Model):
    """Genel ayarlar - Singleton pattern (tek kayıt)"""
    # Firma Bilgileri
    firma_ismi = models.CharField(max_length=200, default="", blank=True, verbose_name="Firma İsmi")
    firma_logo = models.ImageField(upload_to='firma_logo/', blank=True, verbose_name="Firma Logosu")
    telefon = models.CharField(max_length=20, default="", blank=True, verbose_name="Telefon Numarası")
    email = models.EmailField(default="", blank=True, verbose_name="E-Posta")
    teslimat_adresi = models.TextField(
        default="",
        blank=True,
        verbose_name="Teslimat Adresi",
        help_text="Satınalma sipariş formunda teslimat adresi olarak kullanılır.",
    )
    fatura_adresi = models.TextField(
        default="",
        blank=True,
        verbose_name="Fatura Adresi",
        help_text="Satınalma sipariş formunda fatura adresi olarak kullanılır.",
    )
    vergi_dairesi = models.CharField(max_length=120, default="", blank=True, verbose_name="Vergi Dairesi")
    vergi_no = models.CharField(max_length=30, default="", blank=True, verbose_name="Vergi Numarası")
    tekora_aktif = models.BooleanField(
        default=True,
        verbose_name="TEKORA Aktif",
        help_text="Kapalıysa TEKORA IMAP mail takibi durur.",
    )
    musteri_mail_cc_adresi = models.EmailField(
        default="",
        blank=True,
        verbose_name="Müşteri gönderimleri CC adresi",
        help_text="Teklif ve sipariş onay e-postalarında otomatik CC adresi.",
    )
    satinalma_mail_cc_adresi = models.EmailField(
        default="",
        blank=True,
        verbose_name="Satınalma gönderimleri CC adresi",
        help_text="Tedarikçi teklif/sipariş/RFQ e-postalarında otomatik CC adresi.",
    )

    EMAIL_BACKEND_CHOICES = [
        ("stokapp.email_backend.CustomSMTPEmailBackend", "SMTP (Özel SSL — önerilen)"),
        ("django.core.mail.backends.smtp.EmailBackend", "SMTP (Django varsayılan)"),
        ("django.core.mail.backends.console.EmailBackend", "Konsol (test)"),
        ("django.core.mail.backends.filebased.EmailBackend", "Dosyaya yaz (test)"),
    ]

    # SMTP — giden posta
    email_backend = models.CharField(
        max_length=120,
        choices=EMAIL_BACKEND_CHOICES,
        default="stokapp.email_backend.CustomSMTPEmailBackend",
        verbose_name="Giden posta backend",
    )
    smtp_host = models.CharField(max_length=255, blank=True, default="", verbose_name="SMTP sunucu")
    smtp_port = models.PositiveIntegerField(default=587, verbose_name="SMTP port")
    smtp_use_tls = models.BooleanField(default=True, verbose_name="SMTP STARTTLS")
    smtp_use_ssl = models.BooleanField(default=False, verbose_name="SMTP SSL")
    smtp_username = models.CharField(max_length=255, blank=True, default="", verbose_name="SMTP kullanıcı")
    smtp_password = models.CharField(max_length=255, blank=True, default="", verbose_name="SMTP şifre")
    smtp_timeout = models.PositiveIntegerField(null=True, blank=True, verbose_name="SMTP zaman aşımı (sn)")
    default_from_email = models.EmailField(blank=True, default="", verbose_name="Gönderen (From)")
    server_email = models.EmailField(blank=True, default="", verbose_name="Sunucu e-postası")
    email_subject_prefix = models.CharField(max_length=80, blank=True, default="", verbose_name="Konu öneki")

    # IMAP — gelen posta (TEKORA vb.)
    imap_server = models.CharField(max_length=255, blank=True, default="", verbose_name="IMAP sunucu")
    imap_port = models.PositiveIntegerField(default=993, verbose_name="IMAP port")
    imap_use_ssl = models.BooleanField(default=True, verbose_name="IMAP SSL")
    imap_mailbox = models.CharField(max_length=100, default="INBOX", blank=True, verbose_name="IMAP klasör")
    imap_body_max_chars = models.PositiveIntegerField(default=524288, verbose_name="IMAP gövde max karakter")
    imap_hesaplari = models.JSONField(
        default=list,
        blank=True,
        verbose_name="IMAP hesapları",
        help_text='[{"email": "...", "password": "..."}] formatında hesap listesi.',
    )

    # POP — gelen posta (alternatif)
    pop_server = models.CharField(max_length=255, blank=True, default="", verbose_name="POP sunucu")
    pop_port = models.PositiveIntegerField(default=995, verbose_name="POP port")
    pop_use_ssl = models.BooleanField(default=True, verbose_name="POP SSL")
    pop_username = models.CharField(max_length=255, blank=True, default="", verbose_name="POP kullanıcı")
    pop_password = models.CharField(max_length=255, blank=True, default="", verbose_name="POP şifre")
    
    # Para Birimi
    para_birimi = models.ForeignKey('ParaBirimi', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Para Birimi", help_text="Varsayılan para birimi")
    
    # Ön Tanımlı Lokasyonlar
    on_tanimli_satis_lokasyonu = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, related_name='satis_lokasyonu', verbose_name="Ön Tanımlı Satış Lokasyonu", help_text="Varsayılan satış lokasyonu")
    on_tanimli_satin_alma_lokasyonu = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, related_name='satin_alma_lokasyonu', verbose_name="Ön Tanımlı Satın Alma Lokasyonu", help_text="Varsayılan satın alma lokasyonu")
    on_tanimli_uretim_lokasyonu = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, related_name='uretim_lokasyonu', verbose_name="Ön Tanımlı Üretim Lokasyonu", help_text="Varsayılan üretim lokasyonu")
    
    # Varsayılan Teslimat Süreleri (Gün cinsinden)
    varsayilan_satis_teslimat_suresi = models.IntegerField(default=15, verbose_name="Varsayılan Satış Siparişi Teslimat Süresi", help_text="Gün cinsinden")
    varsayilan_satin_alma_teslimat_suresi = models.IntegerField(default=5, verbose_name="Varsayılan Satın Alma Teslimat Süresi", help_text="Gün cinsinden")
    varsayilan_uretim_suresi = models.IntegerField(default=16, verbose_name="Varsayılan Üretim Süresi", help_text="Gün cinsinden")
    
    # Önekler
    satis_irsaliyesi_oneki = models.CharField(max_length=20, default="SO", verbose_name="Satış İrsaliyesi Öneki")
    satin_alma_irsaliyesi_oneki = models.CharField(max_length=20, default="TSAT", verbose_name="Satın Alma İrsaliyesi Öneki")
    is_emri_oneki = models.CharField(max_length=20, default="TWRK", verbose_name="İş Emri Öneki")

    stok_tamamlanma_kurallari = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Stok Tamamlanma Kuralları",
        help_text="Stok tipine göre tamamlanması beklenen alanlar (true=gerekli).",
    )
    
    # Takip
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Genel Ayarlar"
        verbose_name_plural = "Genel Ayarlar"
    
    def __str__(self):
        return "Genel Ayarlar"
    
    @classmethod
    def get_ayarlar(cls):
        """Singleton pattern - tek kayıt döndürür veya oluşturur"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    
    def save(self, *args, **kwargs):
        """Her zaman pk=1 olarak kaydet (singleton)"""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_musteri_mail_cc_adresi(cls) -> str:
        try:
            ayarlar = cls.get_ayarlar()
            return (ayarlar.musteri_mail_cc_adresi or "").strip()
        except Exception:
            return ""

    @classmethod
    def get_satinalma_mail_cc_adresi(cls) -> str:
        try:
            ayarlar = cls.get_ayarlar()
            return (ayarlar.satinalma_mail_cc_adresi or "").strip()
        except Exception:
            return ""


class UserProfile(models.Model):
    """Kullanıcı profil bilgileri - telefon numarası için"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon Numarası")
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.telefon}"
    
    class Meta:
        verbose_name = "Kullanıcı Profili"
        verbose_name_plural = "Kullanıcı Profilleri"


class Operasyon(models.Model):
    """Üretim aşamalarında kullanılacak operasyonlar"""
    ad = models.CharField(max_length=200, unique=True, verbose_name="Operasyon Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    akis_dis_operasyon = models.BooleanField(
        default=False,
        verbose_name='Canlı akışta dış operasyon',
        help_text='İş emri bu adımdayken haritada dış operasyon (sarı/kırmızı) mantığı uygulanır.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Operasyon"
        verbose_name_plural = "Operasyonlar"
        ordering = ['sira', 'ad']
    
    def __str__(self):
        return self.ad


class Istasyon(models.Model):
    """Üretim istasyonları"""
    CNC_MACHINE_GROUP_CHOICES = [
        ("", "Belirtilmedi (kurulumda yalnızca ortak CNC ekipmanları)"),
        ("cnc_lathe", "CNC Torna"),
        ("cnc_mill", "CNC Freze"),
    ]
    ad = models.CharField(max_length=200, unique=True, verbose_name="İstasyon Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    fotograf = models.ImageField(upload_to='istasyonlar/', blank=True, null=True, verbose_name="İstasyon Fotoğrafı")
    maliyet = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Maliyet (TRY)")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    cnc_makine_grubu = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=CNC_MACHINE_GROUP_CHOICES,
        verbose_name="CNC makine grubu",
        help_text="Kurulum dosyasında bu istasyon için torna veya freze ekipmanları ile birlikte ortak ekipmanlar listelenir. Boş bırakılırsa yalnızca ortak CNC ekipmanları seçilebilir.",
    )
    akis_harita_emoji = models.CharField(
        max_length=16,
        blank=True,
        default='',
        verbose_name='Canlı akış ikonu',
        help_text='Boşsa istasyon adına göre varsayılan emoji kullanılır. İleride görsel URL alanı eklenebilir.',
    )
    akis_harita_kisa_aciklama = models.CharField(
        max_length=240,
        blank=True,
        default='',
        verbose_name='Canlı akış kısa açıklama',
    )
    akis_harita_goster = models.BooleanField(
        default=True,
        verbose_name='Canlı akış haritasında göster',
    )
    akis_tip_dis = models.BooleanField(
        default=False,
        verbose_name='Dış operasyon istasyonu',
        help_text='Açık dış operasyon kayıtları bu istasyon sütununda listelenebilir (operasyon tipi ile eşleştirme).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "İstasyon"
        verbose_name_plural = "İstasyonlar"
        ordering = ['sira', 'ad']
    
    def __str__(self):
        return self.ad


class Ekipman(models.Model):
    """Üretim ekipmanları"""
    ekipman_numarasi = models.CharField(max_length=50, unique=True, verbose_name="Ekipman Numarası")
    ad = models.CharField(max_length=200, verbose_name="Ekipman Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    fotograf = models.ImageField(upload_to='ekipmanlar/', blank=True, null=True, verbose_name="Ekipman Fotoğrafı")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ekipman"
        verbose_name_plural = "Ekipmanlar"
        ordering = ['sira', 'ekipman_numarasi']
    
    def __str__(self):
        return f"{self.ekipman_numarasi} - {self.ad}"


class Fikstur(models.Model):
    """Üretim fikstürleri"""
    fikstur_numarasi = models.CharField(max_length=50, unique=True, verbose_name="Fikstür Numarası")
    ad = models.CharField(max_length=200, verbose_name="Fikstür Adı")
    aciklama = models.TextField(blank=True, verbose_name="Fikstür Açıklaması")
    fotograf = models.ImageField(upload_to='fiksturler/', blank=True, null=True, verbose_name="Fikstür Fotoğrafı")
    depo = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Depo")
    raf = models.ForeignKey('Raf', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Raf")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Fikstür"
        verbose_name_plural = "Fikstürler"
        ordering = ['sira', 'fikstur_numarasi']
    
    def __str__(self):
        return f"{self.fikstur_numarasi} - {self.ad}"


class OlcuAletiTuru(models.Model):
    """Ölçü aleti türleri"""
    ad = models.CharField(max_length=100, unique=True, verbose_name="Alet Türü")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ölçü Aleti Türü"
        verbose_name_plural = "Ölçü Aleti Türleri"
        ordering = ['sira', 'ad']
    
    def __str__(self):
        return self.ad


class OlcuAleti(models.Model):
    """Ölçü aletleri - Measurement Devices"""
    
    # Device Type Enum (cihaz tipi)
    DEVICE_TYPE_CHOICES = [
        ('digital_caliper', 'Dijital Kumpas'),
        ('analog_caliper', 'Analog Kumpas'),
        ('outside_micrometer', 'Dış Mikrometre'),
        ('inside_micrometer', 'İç Mikrometre'),
        ('coating_thickness_gauge', 'Kaplama Kalınlık Ölçer'),
        ('roughness_tester', 'Pürüzlülük Ölçer'),
        ('hardness_tester', 'Sertlik Ölçer'),
    ]
    
    # Status Enum
    STATUS_CHOICES = [
        ('active', 'Aktif'),
        ('blocked', 'Blokeli'),
        ('out_of_service', 'Hizmet Dışı'),
    ]
    
    # Calibration Method Enum
    CALIBRATION_METHOD_CHOICES = [
        ('internal_reference', 'İç Referans (Şirket İçi)'),
        ('external_accredited', 'Dış Akredite (Akredite Firma)'),
    ]
    
    DURUM_SECENEKLERI = [
        ('AKTIF', 'Aktif'),
        ('KARANTINADA', 'Karantinada'),
        ('HURDA', 'Hurda'),
        ('KALIBRASYONDA', 'Kalibrasyonda'),
    ]
    
    KRITIKLIK_SECENEKLERI = [
        ('KRITIK', 'Kritik'),
        ('DESTEKLEYICI', 'Destekleyici'),
    ]
    
    # Temel Bilgiler
    device_id = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name="Cihaz ID", help_text="Örn: KMP-001, MIC-075")
    device_type = models.CharField(max_length=50, choices=DEVICE_TYPE_CHOICES, blank=True, verbose_name="Cihaz Tipi")
    alet_turu = models.ForeignKey(OlcuAletiTuru, on_delete=models.PROTECT, verbose_name="Alet Türü", null=True, blank=True)
    marka = models.CharField(max_length=200, verbose_name="Marka")
    model = models.CharField(max_length=200, blank=True, verbose_name="Model")
    seri_no = models.CharField(max_length=100, unique=True, verbose_name="Seri No")
    
    # Fotoğraf
    fotograf = models.ImageField(upload_to='olcu_aletleri/', blank=True, null=True, verbose_name="Cihaz Fotoğrafı")
    
    # Teknik Bilgiler
    olcum_araligi = models.CharField(max_length=200, blank=True, verbose_name="Ölçüm Aralığı (Measurement Range)")
    hassasiyet = models.CharField(max_length=200, blank=True, verbose_name="Hassasiyet")
    
    # Kullanım Bilgileri
    department = models.CharField(max_length=200, blank=True, verbose_name="Departman/Bölüm")
    kullanim_yeri = models.CharField(max_length=200, blank=True, verbose_name="Kullanım Yeri / İstasyon")
    sorumlu_kisi = models.CharField(max_length=200, blank=True, verbose_name="Sorumlu Kişi")
    
    # Durum Bilgileri
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Durum (Status)")
    kritiklik_seviyesi = models.CharField(max_length=20, choices=KRITIKLIK_SECENEKLERI, default='DESTEKLEYICI', verbose_name="Kritiklik Seviyesi")
    durum = models.CharField(max_length=20, choices=DURUM_SECENEKLERI, default='AKTIF', verbose_name="Durum (Eski)")
    
    # Şirket İçi Kalibrasyon Periyodu
    calibration_period_months = models.IntegerField(default=12, verbose_name="Kalibrasyon Periyodu (Ay)", help_text="Aylar cinsinden")
    kalibrasyon_periyot_tipi = models.CharField(max_length=10, choices=[('GUN', 'Gün'), ('HAFTA', 'Hafta'), ('AY', 'Ay'), ('YIL', 'Yıl')], default='YIL', verbose_name="Periyot Tipi")
    kalibrasyon_periyot_sayisi = models.IntegerField(default=1, verbose_name="Periyot Sayısı")
    calibration_method = models.CharField(max_length=30, choices=CALIBRATION_METHOD_CHOICES, blank=True, verbose_name="Kalibrasyon Yöntemi")
    
    # Satın Alma Bilgileri
    satın_alma_tarihi = models.DateField(null=True, blank=True, verbose_name="Satın Alma Tarihi")
    
    # Şirket İçi Son Kalibrasyon Bilgileri
    last_calibration_date = models.DateField(null=True, blank=True, verbose_name="Son Kalibrasyon Tarihi")
    next_calibration_date = models.DateField(null=True, blank=True, verbose_name="Bir Sonraki Kalibrasyon Tarihi")
    son_kalibrasyon_tarihi = models.DateField(null=True, blank=True, verbose_name="Son Kalibrasyon Tarihi (Eski)")
    sonraki_kalibrasyon_tarihi = models.DateField(null=True, blank=True, verbose_name="Bir Sonraki Kalibrasyon Tarihi (Eski)")
    
    # Dış Kalibrasyon Bilgileri
    dis_kalibrasyon_gerekli = models.BooleanField(default=False, verbose_name="Dış Kalibrasyon Gerekli")
    dis_kalibrasyon_periyot_tipi = models.CharField(max_length=10, choices=[('GUN', 'Gün'), ('HAFTA', 'Hafta'), ('AY', 'Ay'), ('YIL', 'Yıl')], blank=True, verbose_name="Dış Kalibrasyon Periyot Tipi")
    dis_kalibrasyon_periyot_sayisi = models.IntegerField(null=True, blank=True, verbose_name="Dış Kalibrasyon Periyot Sayısı")
    dis_kalibrasyon_son_tarih = models.DateField(null=True, blank=True, verbose_name="Dış Kalibrasyon Son Tarihi")
    dis_kalibrasyon_sonraki_tarih = models.DateField(null=True, blank=True, verbose_name="Dış Kalibrasyon Sonraki Tarihi")
    
    # Notlar
    notes = models.TextField(blank=True, verbose_name="Notlar")
    
    # Takip
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ölçü Aleti"
        verbose_name_plural = "Ölçü Aletleri"
        ordering = ['seri_no']
    
    def __str__(self):
        alet_turu_adi = self.alet_turu.ad if self.alet_turu else (self.get_device_type_display() if self.device_type else 'Belirtilmemiş')
        device_id = self.device_id or self.seri_no
        return f"{device_id} - {alet_turu_adi}"
    
    def save(self, *args, **kwargs):
        from datetime import date, timedelta
        
        # Device ID yoksa seri_no'dan oluştur (geriye dönük uyumluluk)
        if not self.device_id and self.seri_no:
            # Eğer benzersiz değilse, seri_no'yu kullan
            # Mevcut kayıt için kontrol et (self.pk varsa)
            if self.pk:
                if not OlcuAleti.objects.filter(device_id=self.seri_no).exclude(pk=self.pk).exists():
                    self.device_id = self.seri_no
            else:
                # Yeni kayıt için kontrol et
                if not OlcuAleti.objects.filter(device_id=self.seri_no).exists():
                    self.device_id = self.seri_no
        
        # Bir sonraki kalibrasyon tarihini otomatik hesapla
        cal_date = self.last_calibration_date or self.son_kalibrasyon_tarihi
        
        # Yeni periyot sistemi (ay cinsinden) - öncelikli
        if cal_date and self.calibration_period_months and not self.next_calibration_date:
            try:
                from dateutil.relativedelta import relativedelta
                self.next_calibration_date = cal_date + relativedelta(months=self.calibration_period_months)
            except ImportError:
                # dateutil yoksa basit hesaplama
                self.next_calibration_date = cal_date + timedelta(days=self.calibration_period_months * 30)
        
        # Eski periyot sistemi (geriye dönük uyumluluk)
        if cal_date and not self.next_calibration_date and not self.sonraki_kalibrasyon_tarihi:
            if self.kalibrasyon_periyot_tipi == 'GUN':
                delta = timedelta(days=self.kalibrasyon_periyot_sayisi)
            elif self.kalibrasyon_periyot_tipi == 'HAFTA':
                delta = timedelta(weeks=self.kalibrasyon_periyot_sayisi)
            elif self.kalibrasyon_periyot_tipi == 'AY':
                delta = timedelta(days=self.kalibrasyon_periyot_sayisi * 30)
            else:  # YIL
                delta = timedelta(days=self.kalibrasyon_periyot_sayisi * 365)
            self.sonraki_kalibrasyon_tarihi = cal_date + delta
            if not self.next_calibration_date:
                self.next_calibration_date = self.sonraki_kalibrasyon_tarihi
        
        # Status kontrolü: Eğer next_calibration_date geçmişse ve status active ise, blocked yap
        if self.next_calibration_date and self.status == 'active':
            today = date.today()
            if self.next_calibration_date < today:
                self.status = 'blocked'
        
        # Eski durum alanını senkronize et (geriye dönük uyumluluk)
        if self.status == 'active':
            if self.durum != 'AKTIF':
                self.durum = 'AKTIF'
        elif self.status == 'blocked':
            if self.durum != 'KARANTINADA':
                self.durum = 'KARANTINADA'
        
        super().save(*args, **kwargs)
    
    def kalibrasyon_durumu(self):
        """Kalibrasyon durumunu döndür: 'SAGLIKLI', 'YAKLASIYOR', 'ACIL', 'GECMIS'"""
        if not self.sonraki_kalibrasyon_tarihi:
            return 'BILINMIYOR'
        
        from datetime import date
        bugun = date.today()
        fark = (self.sonraki_kalibrasyon_tarihi - bugun).days
        
        if fark < 0:
            return 'GECMIS'
        elif fark <= 7:
            return 'ACIL'
        elif fark <= 30:
            return 'YAKLASIYOR'
        else:
            return 'SAGLIKLI'
    
    def kalibrasyon_durum_rengi(self):
        """Kalibrasyon durumuna göre renk döndür"""
        durum = self.kalibrasyon_durumu()
        renkler = {
            'SAGLIKLI': '#22c55e',  # Yeşil
            'YAKLASIYOR': '#eab308',  # Sarı
            'ACIL': '#f97316',  # Turuncu
            'GECMIS': '#ef4444',  # Kırmızı
            'BILINMIYOR': '#6b7280',  # Gri
        }
        return renkler.get(durum, '#6b7280')


class KalibrasyonKaydi(models.Model):
    """Kalibrasyon kayıtları - Calibration Records"""
    
    # Calibration Type Enum
    CALIBRATION_TYPE_CHOICES = [
        ('routine', 'Rutin Kalibrasyon'),
        ('after_impact', 'Darbe Sonrası'),
        ('verification', 'Doğrulama'),
    ]
    
    # Result Enum
    RESULT_CHOICES = [
        ('suitable', 'Uygun'),
        ('conditional', 'Şartlı Uygun'),
        ('unsuitable', 'Uygunsuz'),
    ]
    
    KALIBRASYON_TIPI = [
        ('IC', 'İç (şirket içinde)'),
        ('DIS', 'Dış (akredite firma)'),
    ]
    
    SONUC_SECENEKLERI = [
        ('UYGUN', 'Uygun'),
        ('SARTLI_UYGUN', 'Şartlı Uygun'),
        ('UYGUNSUZ', 'Uygunsuz'),
    ]
    
    # Foreign Key
    olcu_aleti = models.ForeignKey(OlcuAleti, on_delete=models.CASCADE, related_name='kalibrasyonlar', verbose_name="Ölçü Aleti")
    
    # Calibration Type
    calibration_type = models.CharField(max_length=20, choices=CALIBRATION_TYPE_CHOICES, blank=True, verbose_name="Kalibrasyon Tipi")
    kalibrasyon_tarihi = models.DateField(verbose_name="Kalibrasyon Tarihi")
    calibration_date = models.DateField(null=True, blank=True, verbose_name="Kalibrasyon Tarihi (Yeni)")
    kalibrasyon_tipi = models.CharField(max_length=10, choices=KALIBRASYON_TIPI, blank=True, verbose_name="Kalibrasyon Tipi (Eski)")
    
    # Reference Used
    reference_used = models.CharField(max_length=200, blank=True, verbose_name="Kullanılan Referans", help_text="Örn: blok mastar, üretici mastarı, test plakası, sertlik bloğu")
    standart_referansi = models.CharField(max_length=200, blank=True, verbose_name="Standart Referansı")
    
    # Environment
    environment_temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Ortam Sıcaklığı (°C)")
    environment_humidity = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Ortam Nem (%)")
    
    # Result
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, blank=True, verbose_name="Sonuç")
    sonuc = models.CharField(max_length=20, choices=SONUC_SECENEKLERI, blank=True, verbose_name="Sonuç (Eski)")
    sapma_degeri = models.CharField(max_length=200, blank=True, verbose_name="Sapma Değeri")
    
    # Next Calibration Date
    next_due_date = models.DateField(null=True, blank=True, verbose_name="Sonraki Kalibrasyon Tarihi")
    
    # Users
    controlled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='calibrations_controlled', verbose_name="Kontrol Eden")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='calibrations_approved', verbose_name="Onaylayan")
    
    # Remarks
    remarks = models.TextField(blank=True, verbose_name="Açıklama/Notlar")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama (Eski)")
    
    # Files
    sertifika_rapor = models.FileField(upload_to='kalibrasyonlar/', blank=True, null=True, verbose_name="Sertifika / Rapor Dosyası (PDF)")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kalibrasyon Kaydı"
        verbose_name_plural = "Kalibrasyon Kayıtları"
        ordering = ['-kalibrasyon_tarihi']
    
    def __str__(self):
        device_id = self.olcu_aleti.device_id if (self.olcu_aleti and self.olcu_aleti.device_id) else (self.olcu_aleti.seri_no if self.olcu_aleti else 'Bilinmiyor')
        cal_date = self.calibration_date or self.kalibrasyon_tarihi
        result = self.get_result_display() if self.result else (self.get_sonuc_display() if self.sonuc else 'Sonuç Yok')
        return f"{device_id} - {cal_date} - {result}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Ölçü aleti'nin durumunu güncelle
        if self.olcu_aleti:
            # Eğer sonuç uygunsuzsa, cihazı bloke et
            if (self.result == 'unsuitable') or (self.sonuc == 'UYGUNSUZ'):
                self.olcu_aleti.status = 'blocked'
            
            # Son kalibrasyon tarihini güncelle
            cal_date = self.calibration_date or self.kalibrasyon_tarihi
            if cal_date:
                self.olcu_aleti.last_calibration_date = cal_date
                self.olcu_aleti.son_kalibrasyon_tarihi = cal_date
                
                # Bir sonraki kalibrasyon tarihini hesapla
                from datetime import timedelta
                try:
                    from dateutil.relativedelta import relativedelta
                except ImportError:
                    # dateutil yoksa basit ay hesaplaması yap
                    relativedelta = None
                
                # Yeni periyot sistemi (ay cinsinden)
                if self.olcu_aleti.calibration_period_months:
                    if relativedelta:
                        next_date = cal_date + relativedelta(months=self.olcu_aleti.calibration_period_months)
                    else:
                        # Basit ay hesaplaması (30 gün = 1 ay)
                        next_date = cal_date + timedelta(days=self.olcu_aleti.calibration_period_months * 30)
                    self.olcu_aleti.next_calibration_date = next_date
                    if not self.next_due_date:
                        self.next_due_date = next_date
                
                # Eski periyot sistemi (geriye dönük uyumluluk)
                if self.olcu_aleti.kalibrasyon_periyot_tipi == 'GUN':
                    delta = timedelta(days=self.olcu_aleti.kalibrasyon_periyot_sayisi)
                elif self.olcu_aleti.kalibrasyon_periyot_tipi == 'HAFTA':
                    delta = timedelta(weeks=self.olcu_aleti.kalibrasyon_periyot_sayisi)
                elif self.olcu_aleti.kalibrasyon_periyot_tipi == 'AY':
                    delta = timedelta(days=self.olcu_aleti.kalibrasyon_periyot_sayisi * 30)
                else:  # YIL
                    delta = timedelta(days=self.olcu_aleti.kalibrasyon_periyot_sayisi * 365)
                
                if not self.olcu_aleti.next_calibration_date:
                    self.olcu_aleti.next_calibration_date = cal_date + delta
                if not self.olcu_aleti.sonraki_kalibrasyon_tarihi:
                    self.olcu_aleti.sonraki_kalibrasyon_tarihi = cal_date + delta
            
            self.olcu_aleti.save()


class CalibrationMeasurement(models.Model):
    """Ölçüm sonuç tablosu - Calibration Measurements"""
    
    # Result choices
    RESULT_CHOICES = [
        ('pass', 'Geçti'),
        ('fail', 'Geçmedi'),
    ]
    
    record_id = models.ForeignKey(KalibrasyonKaydi, on_delete=models.CASCADE, related_name='measurements', verbose_name="Kalibrasyon Kaydı")
    reference_value = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Referans Değer")
    measurement_1 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Ölçüm 1")
    measurement_2 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Ölçüm 2")
    measurement_3 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Ölçüm 3")
    average_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Ortalama Değer")
    deviation = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Sapma")
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, blank=True, verbose_name="Sonuç")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kalibrasyon Ölçümü"
        verbose_name_plural = "Kalibrasyon Ölçümleri"
        ordering = ['reference_value']
    
    def __str__(self):
        return f"{self.record_id} - Ref: {self.reference_value} - {self.get_result_display() if self.result else 'Değerlendirilmemiş'}"
    
    def calculate_average(self):
        """Ortalama değeri hesapla"""
        measurements = [m for m in [self.measurement_1, self.measurement_2, self.measurement_3] if m is not None]
        if measurements:
            from decimal import Decimal
            self.average_value = sum(Decimal(str(m)) for m in measurements) / len(measurements)
        return self.average_value
    
    def calculate_deviation(self):
        """Sapmayı hesapla"""
        if self.average_value and self.reference_value:
            from decimal import Decimal
            self.deviation = Decimal(str(self.average_value)) - Decimal(str(self.reference_value))
        return self.deviation
    
    def save(self, *args, **kwargs):
        # Ortalama ve sapmayı otomatik hesapla
        if any([self.measurement_1, self.measurement_2, self.measurement_3]):
            self.calculate_average()
            self.calculate_deviation()
        
        # Tolerans kontrolü yap (eğer tolerans tanımlıysa)
        if self.average_value and self.record_id.olcu_aleti:
            device = self.record_id.olcu_aleti
            tolerance = CalibrationTolerance.get_tolerance(device.device_type, self.reference_value)
            if tolerance:
                if abs(float(self.deviation or 0)) <= float(tolerance.tolerance_value):
                    self.result = 'pass'
                else:
                    self.result = 'fail'
        
        super().save(*args, **kwargs)


class CalibrationTolerance(models.Model):
    """Kabul kriterleri - Calibration Tolerances"""
    
    TOLERANCE_UNIT_CHOICES = [
        ('mm', 'Milimetre (mm)'),
        ('%', 'Yüzde (%)'),
        ('HRC', 'Rockwell C Sertliği'),
        ('Ra', 'Pürüzlülük (Ra)'),
    ]
    
    device_type = models.CharField(max_length=50, choices=OlcuAleti.DEVICE_TYPE_CHOICES, verbose_name="Cihaz Tipi")
    min_range = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Minimum Aralık")
    max_range = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Maximum Aralık")
    tolerance_value = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Tolerans Değeri")
    tolerance_unit = models.CharField(max_length=10, choices=TOLERANCE_UNIT_CHOICES, default='mm', verbose_name="Tolerans Birimi")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kalibrasyon Toleransı"
        verbose_name_plural = "Kalibrasyon Toleransları"
        ordering = ['device_type', 'min_range']
    
    def __str__(self):
        return f"{self.get_device_type_display()} - {self.min_range} - {self.max_range}: ±{self.tolerance_value} {self.tolerance_unit}"
    
    @classmethod
    def get_tolerance(cls, device_type, reference_value):
        """Belirli bir cihaz tipi ve referans değer için toleransı döndür"""
        if not device_type or not reference_value:
            return None
        
        try:
            tolerance = cls.objects.filter(
                device_type=device_type,
                min_range__lte=reference_value,
                max_range__gte=reference_value
            ).first()
            return tolerance
        except:
            return None


class Sigorta(models.Model):
    """Sigorta poliçe takibi"""
    VARLIK_TURLERI = [
        ('KISISEL', 'Kişisel'),
        ('SIRKET', 'Şirket'),
    ]
    
    # Varlık Bilgileri
    varlik_adi = models.CharField(max_length=200, verbose_name="Varlık Adı")
    varlik_kimlik_no = models.CharField(max_length=100, blank=True, verbose_name="Varlık Kimlik Numarası")
    varlik_aciklama = models.TextField(blank=True, verbose_name="Varlık Açıklaması")
    varlik_turu = models.CharField(max_length=10, choices=VARLIK_TURLERI, default='SIRKET', verbose_name="Varlık Türü")
    
    # Poliçe Bilgileri
    police_no = models.CharField(max_length=100, unique=True, verbose_name="Poliçe Numarası")
    police_baslangic_tarihi = models.DateField(verbose_name="Poliçe Başlangıç Tarihi")
    police_bitis_tarihi = models.DateField(verbose_name="Poliçe Bitiş Tarihi")
    police_duzenleyen_firma = models.CharField(max_length=200, verbose_name="Poliçeyi Düzenleyen Firma")
    police_prim_bedeli = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Poliçe Prim Bedeli")
    odeme_hesap_kart = models.CharField(max_length=200, blank=True, verbose_name="Ödemenin Yapıldığı Hesap/Kart Bilgisi")
    police_dosyasi = models.FileField(upload_to='sigortalar/', blank=True, null=True, verbose_name="Poliçe Dosyası (PDF)")
    
    # Durum
    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Sigorta"
        verbose_name_plural = "Sigortalar"
        ordering = ['-police_bitis_tarihi', 'varlik_adi']
    
    def __str__(self):
        return f"{self.varlik_adi} - {self.police_no}"
    
    def suresi_doldu_mu(self):
        """Poliçe süresinin dolup dolmadığını kontrol et"""
        from django.utils import timezone
        return timezone.now().date() > self.police_bitis_tarihi


class Personel(models.Model):
    """Yevmiyeli çalışan personel bilgileri"""
    CINSIYET = [
        ('ERKEK', 'Erkek'),
        ('KADIN', 'Kadın'),
    ]
    
    MEDENI_HAL = [
        ('BEKAR', 'Bekar'),
        ('EVLI', 'Evli'),
        ('DUL', 'Dul'),
        ('BOSANMIS', 'Boşanmış'),
    ]
    
    KAN_GRUBU = [
        ('A_RH_POS', 'A Rh +'),
        ('A_RH_NEG', 'A Rh -'),
        ('B_RH_POS', 'B Rh +'),
        ('B_RH_NEG', 'B Rh -'),
        ('AB_RH_POS', 'AB Rh +'),
        ('AB_RH_NEG', 'AB Rh -'),
        ('O_RH_POS', '0 Rh +'),
        ('O_RH_NEG', '0 Rh -'),
    ]
    
    # Temel Bilgiler
    personel_no = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Personel No")
    sicil_no = models.CharField(max_length=50, blank=True, verbose_name="Sicil No")
    ad = models.CharField(max_length=100, verbose_name="Ad")
    soyad = models.CharField(max_length=100, verbose_name="Soyad")
    telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    email = models.EmailField(blank=True, verbose_name="E-Mail")
    cinsiyet = models.CharField(max_length=10, choices=CINSIYET, blank=True, verbose_name="Cinsiyeti")
    dogum_tarihi = models.DateField(blank=True, null=True, verbose_name="Doğum Tarihi")
    dogum_yeri = models.CharField(max_length=100, blank=True, verbose_name="Doğum Yeri")
    tc_kimlik_no = models.CharField(max_length=11, blank=True, unique=True, null=True, verbose_name="TC Kimlik No")
    medeni_hali = models.CharField(max_length=15, choices=MEDENI_HAL, blank=True, verbose_name="Medeni Hali")
    kan_grubu = models.CharField(max_length=10, choices=KAN_GRUBU, blank=True, verbose_name="Kan Grubu")
    
    # Nüfus Bilgileri
    baba_adi = models.CharField(max_length=100, blank=True, verbose_name="Baba Adı")
    ana_adi = models.CharField(max_length=100, blank=True, verbose_name="Ana Adı")
    onceki_soyadi = models.CharField(max_length=100, blank=True, verbose_name="Önceki Soyadı")
    cilt_no = models.CharField(max_length=20, blank=True, verbose_name="Cilt No")
    sayfa_no = models.CharField(max_length=20, blank=True, verbose_name="Sayfa No")
    kutu_no = models.CharField(max_length=20, blank=True, verbose_name="Kütük No")
    ilce = models.CharField(max_length=100, blank=True, verbose_name="İlçesi")
    mahalle = models.CharField(max_length=100, blank=True, verbose_name="Mahalle")
    
    # Kimlik Kartı Bilgileri
    cuzdan_seri_no = models.CharField(max_length=20, blank=True, verbose_name="Cüzdan Seri No")
    cuzdan_kayit_no = models.CharField(max_length=20, blank=True, verbose_name="Cüzdan Kayıt No")
    cuzdan_verilis_tarihi = models.DateField(blank=True, null=True, verbose_name="Cüzdan Veriliş Tarihi")
    cuzdan_verilis_nedeni = models.CharField(max_length=100, blank=True, verbose_name="Cüzdan Veriliş Nedeni")
    
    # İş Bilgileri
    birim = models.CharField(max_length=100, blank=True, verbose_name="Birim")
    sinif = models.CharField(max_length=100, blank=True, verbose_name="Sınıf")
    unvan = models.CharField(max_length=100, blank=True, verbose_name="Ünvanı")
    gorev = models.CharField(max_length=100, blank=True, verbose_name="Görevi")
    firma = models.CharField(max_length=100, blank=True, verbose_name="Firma")
    takip_no = models.IntegerField(blank=True, null=True, verbose_name="Takip No")
    ozel_kod = models.CharField(max_length=50, blank=True, verbose_name="Özel Kod")
    pdks_takip = models.BooleanField(default=False, verbose_name="PDKS Takip")
    bordro_islem = models.BooleanField(default=False, verbose_name="Bordro İşlem")
    
    # Ücret Bilgileri
    saatlik_ucret = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, verbose_name="Saatlik Ücret (TRY)")
    
    # Adres Bilgileri
    adres = models.TextField(blank=True, verbose_name="Adres")
    sehir = models.CharField(max_length=100, blank=True, verbose_name="Şehir")
    posta_kodu = models.CharField(max_length=10, blank=True, verbose_name="Posta Kodu")
    ulke = models.CharField(max_length=100, default="Türkiye", blank=True, verbose_name="Ülke")
    
    # Fotoğraf
    fotograf = models.ImageField(upload_to='personel/', blank=True, null=True, verbose_name="Profil Fotoğrafı")
    
    # Durum
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Personel"
        verbose_name_plural = "Personeller"
        ordering = ['ad', 'soyad']
    
    def __str__(self):
        return f"{self.ad} {self.soyad}"
    
    def toplam_calisma_suresi(self):
        """Toplam çalışma süresi (saat)"""
        from django.db.models import Sum
        return self.gunluk_calismalar.aggregate(
            toplam=Sum('calisma_suresi')
        )['toplam'] or 0
    
    def toplam_odenecek_tutar(self):
        """Toplam ödenecek tutar"""
        from django.db.models import Sum
        return self.gunluk_calismalar.aggregate(
            toplam=Sum('odenecek_tutar')
        )['toplam'] or 0
    
    def toplam_odenen_tutar(self):
        """Toplam ödenen tutar"""
        from django.db.models import Sum
        return self.gunluk_calismalar.aggregate(
            toplam=Sum('odenen_tutar')
        )['toplam'] or 0
    
    def toplam_avans(self):
        """Toplam avans ödemeleri"""
        from django.db.models import Sum
        return self.avans_odemeler.aggregate(
            toplam=Sum('tutar')
        )['toplam'] or 0
    
    def kalan_bakiye(self):
        """Kalan bakiye"""
        return (self.toplam_odenecek_tutar() + self.toplam_avans()) - self.toplam_odenen_tutar()


class GunlukCalisma(models.Model):
    """Günlük çalışma kayıtları"""
    ODEME_DURUMU = [
        ('ODENMEDI', 'Ödenmedi'),
        ('KISMI', 'Kısmi Ödendi'),
        ('ODENDI', 'Ödendi'),
    ]
    
    ODEME_SEKLI = [
        ('NAKIT', 'Nakit'),
        ('HAVALE', 'Havale/EFT'),
        ('KREDI_KARTI', 'Kredi Kartı'),
        ('BANKA_KARTI', 'Banka Kartı'),
        ('DIGER', 'Diğer'),
    ]
    
    personel = models.ForeignKey(Personel, on_delete=models.CASCADE, related_name='gunluk_calismalar', verbose_name="Personel")
    tarih = models.DateField(verbose_name="Çalışma Tarihi")
    calisma_suresi = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Çalışma Süresi (Saat)")
    saat_ucreti = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Saat Ücreti (TRY)")
    odenecek_tutar = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Ödenecek Tutar (TRY)")
    odeme_durumu = models.CharField(max_length=10, choices=ODEME_DURUMU, default='ODENMEDI', verbose_name="Ödeme Durumu")
    odeme_sekli = models.CharField(max_length=15, choices=ODEME_SEKLI, blank=True, verbose_name="Ödeme Şekli")
    odenen_tutar = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Ödenen Tutar (TRY)")
    kalan_bakiye = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Kalan Bakiye (TRY)")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Günlük Çalışma"
        verbose_name_plural = "Günlük Çalışmalar"
        ordering = ['-tarih', 'personel']
        unique_together = ['personel', 'tarih']  # Aynı personel aynı gün iki kez kaydedilemez
    
    def __str__(self):
        return f"{self.personel} - {self.tarih} - {self.calisma_suresi} saat"
    
    def save(self, *args, **kwargs):
        # Ödenecek tutarı hesapla
        if not self.odenecek_tutar:
            self.odenecek_tutar = self.calisma_suresi * self.saat_ucreti
        
        # Kalan bakiyeyi hesapla
        self.kalan_bakiye = self.odenecek_tutar - self.odenen_tutar
        
        # Ödeme durumunu güncelle
        if self.odenen_tutar == 0:
            self.odeme_durumu = 'ODENMEDI'
        elif self.odenen_tutar >= self.odenecek_tutar:
            self.odeme_durumu = 'ODENDI'
        else:
            self.odeme_durumu = 'KISMI'
        
        super().save(*args, **kwargs)


class AvansOdeme(models.Model):
    """Avans ödemeleri"""
    ODEME_SEKLI = [
        ('NAKIT', 'Nakit'),
        ('HAVALE', 'Havale/EFT'),
        ('KREDI_KARTI', 'Kredi Kartı'),
        ('BANKA_KARTI', 'Banka Kartı'),
        ('DIGER', 'Diğer'),
    ]
    
    personel = models.ForeignKey(Personel, on_delete=models.CASCADE, related_name='avans_odemeler', verbose_name="Personel")
    tarih = models.DateField(verbose_name="Ödeme Tarihi")
    tutar = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Avans Tutarı (TRY)")
    odeme_sekli = models.CharField(max_length=15, choices=ODEME_SEKLI, blank=True, verbose_name="Ödeme Şekli")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Avans Ödeme"
        verbose_name_plural = "Avans Ödemeleri"
        ordering = ['-tarih', 'personel']
    
    def __str__(self):
        return f"{self.personel} - {self.tarih} - {self.tutar} TRY"


class PersonelIzin(models.Model):
    """Personel izin kayıtları (tarih+saat aralığı)"""
    IZIN_TIPLERI = [
        ("YILLIK", "Yıllık İzin"),
        ("RAPOR", "Raporlu"),
        ("MAZERET", "Mazeret İzni"),
        ("DIGER", "Diğer"),
    ]

    personel = models.ForeignKey(Personel, on_delete=models.CASCADE, related_name="izin_kayitlari", verbose_name="Personel")
    izin_tipi = models.CharField(max_length=15, choices=IZIN_TIPLERI, default="DIGER", verbose_name="İzin Tipi")
    baslangic_zamani = models.DateTimeField(verbose_name="Başlangıç Tarih/Saat")
    bitis_zamani = models.DateTimeField(verbose_name="Bitiş Tarih/Saat")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personel İzin"
        verbose_name_plural = "Personel İzinleri"
        ordering = ["-baslangic_zamani", "personel"]

    def __str__(self):
        return f"{self.personel} - {self.baslangic_zamani:%d.%m.%Y %H:%M} / {self.bitis_zamani:%d.%m.%Y %H:%M}"


class PersonelBelgesi(models.Model):
    """Personel belge ve yenileme takibi"""
    personel = models.ForeignKey(Personel, on_delete=models.CASCADE, related_name="belgeler", verbose_name="Personel")
    belge_adi = models.CharField(max_length=150, verbose_name="Belge Adı")
    belge_no = models.CharField(max_length=100, blank=True, verbose_name="Belge No")
    belge_dosyasi = models.FileField(upload_to="personel_belgeler/%Y/%m/%d/", blank=True, null=True, verbose_name="Belge Dosyası")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    yenileme_gerekli = models.BooleanField(default=False, verbose_name="Yenileme Gerekli mi?")
    yenileme_tarihi = models.DateField(blank=True, null=True, verbose_name="Yenileme Tarihi")
    hatirlatma_gun_once = models.PositiveIntegerField(blank=True, null=True, verbose_name="Yenileme Hatırlatma (Gün)")
    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personel Belgesi"
        verbose_name_plural = "Personel Belgeleri"
        ordering = ["yenileme_tarihi", "-created_at"]

    def __str__(self):
        return f"{self.personel} - {self.belge_adi}"


class Siparis(models.Model):
    """Sipariş modeli"""
    SIPARIS_DURUMU = [
        ('ONAY_BEKLIYOR', 'Onay Bekliyor'),
        ('ONAYLANDI', 'Onaylandı'),
        ('TESLIM_EDILDI', 'Teslim Edildi'),
        ('RED', 'Red'),
    ]
    
    STOK_DURUMU = [
        ('STOKTA_VAR', 'Stokta Var'),
        ('STOKTA_YOK', 'Stokta Yok'),
        ('KISMI_STOK', 'Kısmi Stok'),
    ]
    
    URETIM_DURUMU = [
        ('BEKLEMEDE', 'Beklemede'),
        ('DEVAM_EDIYOR', 'Devam Ediyor'),
        ('TAMAMLANDI', 'Tamamlandı'),
    ]
    
    TESLIMAT_DURUMU = [
        ('HAZIRLANIYOR', 'Hazırlanıyor'),
        ('KARGOYA_VERILDI', 'Kargoya Verildi'),
        ('TESLIM_EDILDI', 'Teslim Edildi'),
    ]
    
    FATURA_DURUMU = [
        ('FATURALANMADI', 'Faturalanmadı'),
        ('FATURALANDI', 'Faturalandı'),
        ('KISMI_FATURA', 'Kısmi Fatura'),
    ]
    
    siparis_numarasi = models.CharField(max_length=50, unique=True, verbose_name="Sipariş Numarası")
    musteri = models.ForeignKey('Musteri', on_delete=models.PROTECT, null=True, blank=True, verbose_name="Müşteri")
    musteri_adi = models.CharField(max_length=200, blank=True, verbose_name="Müşteri Adı (Manuel)")  # Eğer dropdown'dan seçilmezse
    etiketler = models.CharField(max_length=200, blank=True, verbose_name="Etiketler")
    toplam = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Toplam")
    para_birimi = models.CharField(max_length=3, default='USD', verbose_name="Para Birimi")
    olusturulma_tarihi = models.DateField(verbose_name="Oluşturulma Tarihi")
    tamamlanma_tarihi = models.DateField(null=True, blank=True, verbose_name="Tamamlanma Tarihi")
    stok_durumu = models.CharField(max_length=20, choices=STOK_DURUMU, default='STOKTA_VAR', verbose_name="Stok Durumu")
    hammadde_durumu = models.CharField(max_length=20, choices=STOK_DURUMU, default='STOKTA_VAR', verbose_name="Hammadde Durumu")
    uretim_durumu = models.CharField(max_length=20, choices=URETIM_DURUMU, default='BEKLEMEDE', verbose_name="Üretim Durumu")
    teslimat_durumu = models.CharField(max_length=20, choices=TESLIMAT_DURUMU, default='HAZIRLANIYOR', verbose_name="Teslimat Durumu")
    fatura_durumu = models.CharField(max_length=20, choices=FATURA_DURUMU, default='FATURALANMADI', verbose_name="Fatura Durumu")
    siparis_durumu = models.CharField(max_length=20, choices=SIPARIS_DURUMU, default='ONAY_BEKLIYOR', verbose_name="Sipariş Durumu")
    kaynak_teklif = models.ForeignKey(
        'Teklif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='olusturulan_siparisler',
        verbose_name='Kaynak teklif',
    )
    siparis_mektubu = models.FileField(
        upload_to='siparis_mektuplari/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Sipariş mektubu (PDF)',
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    red_nedeni = models.TextField(blank=True, verbose_name="Red Nedeni")
    red_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Red Tarihi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Sipariş"
        verbose_name_plural = "Siparişler"
        ordering = ['-olusturulma_tarihi']
    
    def __str__(self):
        return f"{self.siparis_numarasi} - {self.musteri}"


class SiparisKalemi(models.Model):
    """Sipariş kalemleri"""
    siparis = models.ForeignKey(Siparis, on_delete=models.CASCADE, related_name='kalemler', verbose_name="Sipariş")
    stok_item = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Ürün",
        help_text="Serbest satırlar için boş bırakılabilir; açıklama alanı kullanılır.",
    )
    kaynak_teklif_kalemi = models.ForeignKey(
        'TeklifKalemi',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='siparis_kalemleri',
        verbose_name='Kaynak teklif kalemi',
    )
    miktar = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Miktar")
    birim_fiyat = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birim Fiyat")
    indirim_yuzdesi = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="İndirim (%)")
    toplam = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Toplam")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Sipariş Kalemi"
        verbose_name_plural = "Sipariş Kalemleri"
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['kaynak_teklif_kalemi'],
                condition=Q(kaynak_teklif_kalemi__isnull=False),
                name='siparis_kalem_unique_kaynak_teklif_kalemi',
            ),
        ]
    
    def __str__(self):
        ad = self.stok_item.ad if self.stok_item_id else (self.aciklama or "Serbest kalem")
        return f"{self.siparis.siparis_numarasi} - {ad}"

    def save(self, *args, **kwargs):
        # Toplam hesaplama: (miktar * birim_fiyat) * (1 - indirim_yuzdesi/100)
        indirim_tutar = (self.miktar * self.birim_fiyat) * (self.indirim_yuzdesi / 100)
        self.toplam = (self.miktar * self.birim_fiyat) - indirim_tutar
        super().save(*args, **kwargs)


class TeklifSartSablonu(models.Model):
    baslik = models.CharField(max_length=200, verbose_name='Başlık')
    icerik = models.TextField(verbose_name='İçerik')
    aktif = models.BooleanField(default=True, verbose_name='Aktif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_conditions'
        verbose_name = 'Teklif şart şablonu'
        verbose_name_plural = 'Teklif şart şablonları'
        ordering = ['baslik']

    def __str__(self):
        return self.baslik


class MusteriTeklifSartlari(models.Model):
    musteri = models.OneToOneField(
        'Musteri', on_delete=models.CASCADE, related_name='teklif_sartlari', verbose_name='Müşteri'
    )
    odeme_sarti = models.TextField(blank=True, verbose_name='Ödeme şartı')
    teslim_suresi = models.CharField(max_length=200, blank=True, verbose_name='Teslim süresi')
    genel_notlar = models.TextField(blank=True, verbose_name='Genel notlar')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_offer_conditions'
        verbose_name = 'Müşteri teklif şartları'
        verbose_name_plural = 'Müşteri teklif şartları'

    def __str__(self):
        return f'{self.musteri.ad} — şartlar'


def _default_teklif_banka_ids():
    return []


class Teklif(models.Model):
    DURUM_SECENEKLERI = [
        ('draft', 'Taslak'),
        ('sent', 'Gönderildi'),
        ('accepted', 'Kabul edildi'),
        ('rejected', 'Reddedildi'),
    ]

    RED_SEBEP_SECENEKLERI = [
        ('FIYAT_YUKSEK', 'Fiyat yüksek bulundu'),
        ('TERMIN_UYGUN_DEGIL', 'Termin uygun değil'),
        ('RAKIP_TERCIH', 'Rakip firma tercih edildi'),
        ('TEKNIK_UYGUN_DEGIL', 'Teknik şartlar uygun değil'),
        ('PROJE_ERTELEDI', 'Müşteri projeyi erteledi'),
        ('PROJE_IPTAL', 'Müşteri projeyi iptal etti'),
        ('BUTCE_ONAY', 'Bütçe onayı alınamadı'),
        ('YANLIS_TEKLIF', 'Yanlış / gereksiz teklif'),
        ('DIGER', 'Diğer'),
    ]

    teklif_no = models.CharField(max_length=50, unique=True, verbose_name='Teklif no')
    ad = models.CharField(max_length=300, blank=True, verbose_name='Teklif adı')
    musteri = models.ForeignKey(
        'Musteri', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Müşteri'
    )
    musteri_adi = models.CharField(max_length=200, blank=True, verbose_name='Müşteri adı (anlık)')
    musteri_telefon = models.CharField(max_length=40, blank=True, verbose_name='Telefon (anlık)')
    musteri_email = models.EmailField(blank=True, verbose_name='E-posta (anlık)')
    musteri_adres = models.TextField(blank=True, verbose_name='Adres (anlık)')
    kaynak_siparis = models.ForeignKey(
        'Siparis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='olusturulan_teklifler',
        verbose_name='Kaynak sipariş',
    )
    duzenleme_tarihi = models.DateField(verbose_name='Düzenleme tarihi')
    vade_tarihi = models.DateField(null=True, blank=True, verbose_name='Vade tarihi')
    doviz_kuru = models.DecimalField(max_digits=14, decimal_places=6, default=1, verbose_name='Döviz kuru')
    sartlar_metni = models.TextField(blank=True, verbose_name='Teklif şartları')
    teklif_banka_hesap_ids = models.JSONField(
        default=_default_teklif_banka_ids,
        blank=True,
        verbose_name='Seçili banka hesabı kimlikleri',
        help_text='PDF/teklif özeti için sıralı banka hesabı pk listesi.',
    )
    durum = models.CharField(
        max_length=20, choices=DURUM_SECENEKLERI, default='draft', verbose_name='Durum'
    )
    arsivlendi = models.BooleanField(default=False, verbose_name='Arşivlendi')
    toplam_tutar = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Toplam tutar')
    para_birimi = models.CharField(max_length=3, default='TRY', verbose_name='Para birimi')
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='olusturdugu_teklifler',
        verbose_name='Oluşturan',
    )
    red_sebebi = models.CharField(
        max_length=40,
        blank=True,
        choices=RED_SEBEP_SECENEKLERI,
        verbose_name='Red sebebi',
    )
    red_sebebi_diger_aciklama = models.TextField(blank=True, verbose_name='Red — Diğer açıklama')
    red_notu = models.TextField(blank=True, verbose_name='Red notu')
    red_tarihi = models.DateTimeField(null=True, blank=True, verbose_name='Red tarihi')
    reddeden_kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reddettigi_teklifler',
        verbose_name='Reddeden kullanıcı',
    )
    pdf_dosyasi = models.FileField(
        upload_to='teklif_pdf/%Y/%m/',
        blank=True,
        verbose_name='Son gönderilen PDF',
    )
    siparis_mektubu = models.FileField(
        upload_to='teklif_siparis_mektuplari/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Sipariş mektubu (PDF)',
    )
    son_gonderim_tarihi = models.DateTimeField(null=True, blank=True, verbose_name='Son gönderim tarihi')
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    guncelleme_tarihi = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offers'
        verbose_name = 'Teklif'
        verbose_name_plural = 'Teklifler'
        ordering = ['-duzenleme_tarihi', '-id']

    def __str__(self):
        ad = (self.ad or '').strip()
        return f'{self.teklif_no} — {ad}' if ad else self.teklif_no


class TeklifKalemi(models.Model):
    TIP_SECENEKLERI = [
        ('product', 'Stoktan ürün'),
        ('custom', 'Serbest kalem'),
    ]

    teklif = models.ForeignKey(Teklif, on_delete=models.CASCADE, related_name='kalemler', verbose_name='Teklif')
    tip = models.CharField(max_length=20, choices=TIP_SECENEKLERI, default='product', verbose_name='Tip')
    stok_item = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Ürün',
        help_text='Serbest satırlar için boş bırakılabilir.',
    )
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    miktar = models.DecimalField(max_digits=14, decimal_places=3, default=1, verbose_name='Miktar')
    birim = models.CharField(max_length=40, default='Adet', verbose_name='Birim')
    birim_fiyat = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Birim fiyat')
    para_birimi = models.CharField(
        max_length=3,
        choices=StokItem.PARA_BIRIMLERI,
        default='TL',
        verbose_name='Para birimi',
    )
    vergi_yuzdesi = models.DecimalField(max_digits=5, decimal_places=2, default=20, verbose_name='Vergi %')
    satir_toplam = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Satır toplamı')
    satir_notu = models.TextField(blank=True, verbose_name='Satır notu')
    sira = models.PositiveIntegerField(default=0, verbose_name='Sıra')

    class Meta:
        db_table = 'offer_items'
        verbose_name = 'Teklif kalemi'
        verbose_name_plural = 'Teklif kalemleri'
        ordering = ['sira', 'id']

    def __str__(self):
        return f'{self.teklif.teklif_no} — kalem {self.sira}'


class TeklifSarti(models.Model):
    """Teklif başına seçilmiş parametrik veya özel şart satırı (PDF/e-posta ile uyumlu)."""

    TIP_HAZIR = 'HAZIR'
    TIP_OZEL = 'OZEL'
    TIP_SECENEKLERI = [
        (TIP_HAZIR, 'Hazır şablon'),
        (TIP_OZEL, 'Özel şart'),
    ]

    teklif = models.ForeignKey(
        Teklif,
        on_delete=models.CASCADE,
        related_name='sart_kayitlari',
        verbose_name='Teklif',
    )
    tip = models.CharField(max_length=10, choices=TIP_SECENEKLERI, verbose_name='Tip')
    sablon_kodu = models.CharField(
        max_length=80, blank=True, verbose_name='Şablon kodu', db_index=True
    )
    baslik = models.CharField(max_length=300, verbose_name='Başlık')
    degerler_json = models.JSONField(default=dict, verbose_name='Parametreler')
    metin = models.TextField(blank=True, verbose_name='Üretilen metin')
    sira = models.PositiveIntegerField(default=0, verbose_name='Sıra')
    aktif = models.BooleanField(default=True, verbose_name='Aktif')

    class Meta:
        db_table = 'offer_terms_lines'
        verbose_name = 'Teklif şartı'
        verbose_name_plural = 'Teklif şartları'
        ordering = ['sira', 'id']

    def __str__(self):
        return f'{self.teklif_id} — {self.baslik}'


class TeklifGonderimGecmisi(models.Model):
    """Müşteriye teklif PDF e-posta gönderim kaydı."""

    DURUM_SECENEKLERI = [
        ('GONDERILDI', 'Gönderildi'),
        ('HATA', 'Hata'),
    ]

    teklif = models.ForeignKey(
        Teklif,
        on_delete=models.CASCADE,
        related_name='gonderim_gecmisi',
        verbose_name='Teklif',
    )
    alicilar = models.JSONField(default=list, verbose_name='Alıcılar')
    cc = models.JSONField(default=list, blank=True, verbose_name='CC')
    bcc = models.JSONField(default=list, blank=True, verbose_name='BCC')
    konu = models.CharField(max_length=400, verbose_name='Konu')
    mesaj = models.TextField(verbose_name='Mesaj')
    pdf_dosyasi = models.FileField(
        upload_to='teklif_gonderimleri/%Y/%m/', blank=True, verbose_name='PDF dosyası'
    )
    gonderen_kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teklif_mail_gonderimleri',
        verbose_name='Gönderen',
    )
    gonderim_tarihi = models.DateTimeField(auto_now_add=True, verbose_name='Gönderim tarihi')
    durum = models.CharField(
        max_length=20, choices=DURUM_SECENEKLERI, default='GONDERILDI', verbose_name='Durum'
    )
    hata_mesaji = models.TextField(blank=True, verbose_name='Hata mesajı')

    class Meta:
        verbose_name = 'Teklif gönderim geçmişi'
        verbose_name_plural = 'Teklif gönderim geçmişi'
        ordering = ['-gonderim_tarihi']

    def __str__(self):
        return f'{self.teklif.teklif_no} — {self.gonderim_tarihi:%d.%m.%Y %H:%M}'


class SiparisMaliyeti(models.Model):
    """Sipariş maliyetleri - malzeme ve operasyon maliyetleri"""
    MALIYET_TIPLERI = [
        ('MALZEME', 'Malzeme'),
        ('OPERASYON', 'Operasyon'),
    ]
    
    siparis = models.ForeignKey(Siparis, on_delete=models.CASCADE, related_name='maliyetler', verbose_name="Sipariş")
    maliyet_tipi = models.CharField(max_length=20, choices=MALIYET_TIPLERI, verbose_name="Maliyet Tipi")
    aciklama = models.CharField(max_length=500, verbose_name="Açıklama")  # Malzeme adı veya operasyon adı
    miktar = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Miktar")
    birim_fiyat = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Birim Fiyat")
    toplam = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Toplam")
    para_birimi = models.CharField(max_length=3, default='TRY', verbose_name="Para Birimi")
    birim = models.CharField(max_length=20, default='Adet', verbose_name="Birim")
    kayit_tarihi = models.DateField(verbose_name="Kayıt Tarihi")  # Hangi tarihte kaydedildi
    aciklama_detay = models.TextField(blank=True, verbose_name="Detay Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Sipariş Maliyeti"
        verbose_name_plural = "Sipariş Maliyetleri"
        ordering = ['maliyet_tipi', 'kayit_tarihi', 'id']
    
    def __str__(self):
        return f"{self.siparis.siparis_numarasi} - {self.get_maliyet_tipi_display()}: {self.aciklama}"
    
    def save(self, *args, **kwargs):
        # Toplam hesapla: miktar * birim_fiyat
        self.toplam = self.miktar * self.birim_fiyat
        super().save(*args, **kwargs)


class Musteri(models.Model):
    ad = models.CharField(max_length=200, verbose_name="Müşteri Adı")
    telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    email = models.EmailField(blank=True, verbose_name="E-posta")
    adres = models.TextField(blank=True, verbose_name="Adres")
    kategoriler = models.ManyToManyField(
        'Kategori',
        blank=True,
        related_name='musteriler',
        verbose_name='Etiketler / Kategoriler',
        help_text='Müşterinin ilgilendiği ürün/hizmet etiketleri. Teklif ve segmentasyon için kullanılır.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Müşteri"
        verbose_name_plural = "Müşteriler"
        ordering = ['ad']

    def __str__(self):
        return self.ad


class MusteriIlgiliKisi(models.Model):
    """Müşteri kartına bağlı iletişim / ilgili kişiler."""

    musteri = models.ForeignKey(
        Musteri, on_delete=models.CASCADE, related_name='ilgili_kisiler', verbose_name='Müşteri'
    )
    ad_soyad = models.CharField(max_length=200, verbose_name='Adı Soyadı')
    gorev = models.CharField(max_length=120, blank=True, verbose_name='Görevi')
    telefon = models.CharField(max_length=40, blank=True, verbose_name='Telefon')
    email = models.EmailField(blank=True, verbose_name='E-posta')
    ozel_not = models.TextField(blank=True, verbose_name='Özel not')
    sira = models.PositiveSmallIntegerField(default=0, verbose_name='Sıra')

    class Meta:
        verbose_name = 'Müşteri ilgili kişi'
        verbose_name_plural = 'Müşteri ilgili kişiler'
        ordering = ['sira', 'id']

    def __str__(self):
        return f'{self.ad_soyad} ({self.musteri})'


class Satinalma(models.Model):
    """Satın alma siparişi modeli"""
    TESLIM_DURUMU = [
        ('BEKLIYOR', 'Bekliyor'),
        ('KISMI_TESLIM', 'Kısmi Teslim'),
        ('TESLIM_ALINDI', 'Teslim Alındı'),
    ]
    
    satinalma_numarasi = models.CharField(max_length=50, unique=True, verbose_name="Satın Alma Numarası")
    tedarikci = models.ForeignKey('Tedarikci', on_delete=models.PROTECT, null=True, blank=True, verbose_name="Tedarikçi")
    kaynak_siparis = models.ForeignKey(
        'Siparis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bagli_satinalmalar',
        verbose_name='Kaynak Sipariş',
    )
    tedarikci_adi = models.CharField(max_length=200, blank=True, verbose_name="Tedarikçi Adı (Manuel)")  # Eğer dropdown'dan seçilmezse
    etiketler = models.CharField(max_length=200, blank=True, verbose_name="Etiketler")
    lokasyon = models.ForeignKey('Depo', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Lokasyon")
    toplam = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Toplam")
    para_birimi = models.CharField(max_length=3, default='TRY', verbose_name="Para Birimi")
    olusturulma_tarihi = models.DateField(verbose_name="Oluşturulma Tarihi")
    tamamlanma_tarihi = models.DateField(null=True, blank=True, verbose_name="Tamamlanması Beklenen Tarih")
    teslim_durumu = models.CharField(max_length=20, choices=TESLIM_DURUMU, default='BEKLIYOR', verbose_name="Teslim Alındı")
    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Satın Alma"
        verbose_name_plural = "Satın Almalar"
        ordering = ['-olusturulma_tarihi']
    
    def __str__(self):
        return f"{self.satinalma_numarasi} - {self.tedarikci_adi or (self.tedarikci.ad if self.tedarikci else '')}"


class SatinalmaKalemi(models.Model):
    """Satın alma kalemleri"""
    satinalma = models.ForeignKey(Satinalma, on_delete=models.CASCADE, related_name='kalemler', verbose_name="Satın Alma")
    stok_item = models.ForeignKey(StokItem, on_delete=models.PROTECT, verbose_name="Stok")
    miktar = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Miktar")
    birim_fiyat = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birim Fiyatı")
    vergi_yuzdesi = models.DecimalField(max_digits=5, decimal_places=2, default=20, verbose_name="Vergi (%)")
    toplam_fiyat = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Toplam Fiyat")
    teslim_alinan_miktar = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Teslim Alınan Miktar")
    teknik_resim_guncellenmis = models.FileField(upload_to='satinalma_teknik_resim/%Y/%m/%d/', blank=True, null=True, verbose_name="Güncellenmiş Teknik Resim")
    tedarikci_fiyat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Tedarikçi Fiyatı", help_text="Tedarikçiden gelen teklif fiyatı")
    teslim_suresi = models.IntegerField(null=True, blank=True, verbose_name="Teslim Süresi (Gün)", help_text="Tedarikçiden gelen teslim süresi")
    kaynak_rfq_kalemi = models.ForeignKey(
        'TeklifTalebiKalemi',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='donusen_satinalma_kalemleri',
        verbose_name='Kaynak RFQ Kalemi',
    )
    kaynak_teklif_kalemi = models.ForeignKey(
        'TedarikciTeklifKalemi',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='donusen_satinalma_kalemleri',
        verbose_name='Kaynak Tedarikçi Teklifi',
    )
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Satın Alma Kalemi"
        verbose_name_plural = "Satın Alma Kalemleri"
        ordering = ['id']
    
    def __str__(self):
        return f"{self.satinalma.satinalma_numarasi} - {self.stok_item.ad}"
    
    def save(self, *args, **kwargs):
        # Toplam hesaplama: (miktar * birim_fiyat) * (1 + vergi_yuzdesi/100)
        ara_toplam = self.miktar * self.birim_fiyat
        vergi_tutari = ara_toplam * (self.vergi_yuzdesi / 100)
        self.toplam_fiyat = ara_toplam + vergi_tutari
        super().save(*args, **kwargs)


class Talep(models.Model):
    """Şirket içi satın alma / ihtiyaç talebi."""

    DURUMLAR = [
        ("YENI", "Yeni Talep"),
        ("INCELEMEDE", "İncelemede"),
        ("ONAYLANDI", "Onaylandı"),
        ("SATINALMAYA_AKTARILDI", "Satınalmaya Aktarıldı"),
        ("SIPARIS_VERILDI", "Sipariş Verildi"),
        ("KISMEN_KARSILANDI", "Kısmen Karşılandı"),
        ("TAMAMLANDI", "Tamamlandı"),
        ("REDDEDILDI", "Reddedildi"),
        ("IPTAL", "İptal Edildi"),
    ]
    ONCELIKLER = [
        ("DUSUK", "Düşük"),
        ("NORMAL", "Normal"),
        ("ACIL", "Acil"),
        ("KRITIK", "Kritik"),
    ]
    KATEGORILER = [
        ("SARF", "Sarf Malzemesi"),
        ("URETIM_MALZ", "Üretim Malzemesi"),
        ("BAKIM_ONARIM", "Bakım / Onarım"),
        ("EKIPMAN", "Ekipman"),
        ("OFIS", "Ofis Malzemesi"),
        ("HIZMET", "Hizmet"),
        ("YEDEK_PARCA", "Yedek Parça"),
        ("DIGER", "Diğer"),
    ]
    KAPANIS_TIPLERI = [
        ("TAMAMLANDI", "Tamamlandı"),
        ("KISMEN", "Kısmen karşılandı"),
        ("RED", "Reddedildi"),
        ("IPTAL", "İptal"),
    ]

    talep_no = models.CharField(max_length=40, unique=True, editable=False, verbose_name="Talep No")
    talep_tarihi = models.DateField(verbose_name="Talep Tarihi")
    talep_eden = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="talepler",
        verbose_name="Talep Eden",
    )
    departman = models.CharField(max_length=200, blank=True, verbose_name="Departman / Bölüm")
    kategori = models.CharField(max_length=20, choices=KATEGORILER, default="DIGER", verbose_name="Kategori")
    baslik = models.CharField(max_length=500, verbose_name="Talep Başlığı")
    oncelik = models.CharField(max_length=20, choices=ONCELIKLER, default="NORMAL", verbose_name="Öncelik")
    durum = models.CharField(max_length=30, choices=DURUMLAR, default="YENI", verbose_name="Durum")
    istenen_termin = models.DateField(null=True, blank=True, verbose_name="İstenen Termin Tarihi")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama / İhtiyaç Nedeni")
    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    satinalma = models.ForeignKey(
        "Satinalma",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaynak_talepler",
        verbose_name="Bağlı Satın Alma",
    )
    kapanis_tipi = models.CharField(
        max_length=20, choices=KAPANIS_TIPLERI, blank=True, verbose_name="Kapanış Tipi"
    )
    gerceklesen_toplam_tutar = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Gerçekleşen Toplam Tutar"
    )
    kapanis_tedarikci = models.ForeignKey(
        "Tedarikci",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talep_kapanislari",
        verbose_name="Satın Alınan Firma / Tedarikçi",
    )
    fatura_no = models.CharField(max_length=120, blank=True, verbose_name="Fatura No")
    irsaliye_no = models.CharField(max_length=120, blank=True, verbose_name="İrsaliye No")
    alim_tarihi = models.DateField(null=True, blank=True, verbose_name="Alım Tarihi")
    teslim_alan_kisi = models.CharField(max_length=200, blank=True, verbose_name="Teslim Alan Kişi")
    kapanis_notu = models.TextField(blank=True, verbose_name="Kapanış Notu")
    kapanis_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Kapanış Tarihi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Satın Alma Talebi"
        verbose_name_plural = "Satın Alma Talepleri"
        ordering = ["-talep_tarihi", "-pk"]

    def __str__(self):
        return f"{self.talep_no} — {self.baslik[:40]}"

    def save(self, *args, **kwargs):
        if not self.talep_no:
            self.talep_no = self._uret_talep_no()
        super().save(*args, **kwargs)

    @staticmethod
    def _uret_talep_no():
        from datetime import date

        today = date.today()
        pref = f"TALEP_{today.day:02d}{today.month:02d}{str(today.year)[-2:]}_"
        n = Talep.objects.filter(talep_no__startswith=pref).count()
        return f"{pref}{n + 1:04d}"

    def gecikti_mi(self):
        from datetime import date

        if not self.istenen_termin:
            return False
        if self.durum in ("TAMAMLANDI", "REDDEDILDI", "IPTAL"):
            return False
        return self.istenen_termin < date.today()

    def tamamlanmis_sayilir_mi(self):
        return self.durum in ("TAMAMLANDI", "REDDEDILDI", "IPTAL")

    def tahmini_toplam(self):
        from decimal import Decimal

        return Decimal("0")


class TalepKalemi(models.Model):
    KALEM_DURUMLAR = [
        ("BEKLIYOR", "Bekliyor"),
        ("ONAYLANDI", "Onaylandı"),
        ("ALINDI", "Alındı"),
        ("REDDEDILDI", "Reddedildi"),
        ("IPTAL", "İptal"),
    ]

    talep = models.ForeignKey(Talep, on_delete=models.CASCADE, related_name="kalemler", verbose_name="Talep")
    kalem_adi = models.CharField(max_length=300, verbose_name="Kalem Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    miktar = models.DecimalField(max_digits=12, decimal_places=3, default=1, verbose_name="Miktar")
    birim = models.ForeignKey(Birim, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Birim")
    marka_model_tercihi = models.CharField(max_length=300, blank=True, verbose_name="Marka / Model Tercihi")
    kullanim_yeri = models.CharField(max_length=200, blank=True, verbose_name="Kullanım Yeri")
    not_text = models.TextField(blank=True, verbose_name="Not")
    durum = models.CharField(max_length=20, choices=KALEM_DURUMLAR, default="BEKLIYOR", verbose_name="Durum")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talep Kalemi"
        verbose_name_plural = "Talep Kalemleri"
        ordering = ["id"]

    def __str__(self):
        return f"{self.kalem_adi} ({self.miktar})"


class TalepDosya(models.Model):
    TIPLER = [
        ("TALEP", "Talep eki"),
        ("KAPANIS", "Kapanış belgesi"),
        ("DIGER", "Diğer"),
    ]

    talep = models.ForeignKey(Talep, on_delete=models.CASCADE, related_name="dosyalar", verbose_name="Talep")
    dosya = models.FileField(upload_to="talep_dosyalari/%Y/%m/", verbose_name="Dosya")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    tip = models.CharField(max_length=20, choices=TIPLER, default="TALEP", verbose_name="Tip")
    yukleyen = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="talep_dosyalari"
    )
    yuklenme_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talep Dosyası"
        verbose_name_plural = "Talep Dosyaları"
        ordering = ["-yuklenme_zamani"]


class TalepGecmisi(models.Model):
    talep = models.ForeignKey(Talep, on_delete=models.CASCADE, related_name="gecmis", verbose_name="Talep")
    kullanici = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    olay = models.CharField(max_length=80, verbose_name="Olay")
    eski_durum = models.CharField(max_length=30, blank=True)
    yeni_durum = models.CharField(max_length=30, blank=True)
    mesaj = models.TextField(blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talep Geçmişi"
        verbose_name_plural = "Talep Geçmişi"
        ordering = ["-olusturulma"]


class TalepSatinalmaBilgisi(models.Model):
    ALIM_YONTEMI = [
        ("FIRMA_SIPARIS", "Firmaya sipariş verildi"),
        ("ELDEN", "Elden / dışarıdan alındı"),
        ("STOKTAN", "Stoktan karşılandı"),
        ("IPTAL", "İptal edildi"),
    ]

    talep = models.OneToOneField(Talep, on_delete=models.CASCADE, related_name="satinalma_bilgi", verbose_name="Talep")
    satinalma_sorumlusu = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorumlu_oldugu_talepler",
        verbose_name="Satınalma Sorumlusu",
    )
    tedarikci = models.ForeignKey(
        "Tedarikci", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tedarikçi"
    )
    teklif_alindi = models.BooleanField(default=False, verbose_name="Teklif Alındı mı?")
    siparis_verildi = models.BooleanField(default=False, verbose_name="Sipariş Verildi mi?")
    alim_yontemi = models.CharField(
        max_length=20, choices=ALIM_YONTEMI, blank=True, verbose_name="Alım Yöntemi"
    )
    notlar = models.TextField(blank=True, verbose_name="Satınalma Notları")
    aktarilma_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Satınalmaya Aktarılma Zamanı")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Talep Satınalma Bilgisi"
        verbose_name_plural = "Talep Satınalma Bilgileri"


class YazdirmaSablonu(models.Model):
    """Yazdırma şablonları - Teklif, Sipariş, Malzeme Listesi, İş Emri, Barkod"""
    SABLON_TIPLERI = [
        ('TEKLIF_TALEBI', 'Teklif Talebi Formu'),
        ('SIPARIS', 'Sipariş Formu'),
        ('MALZEME_LISTESI', 'Malzeme Listesi Formu'),
        ('IS_EMRI', 'İş Emri Formu'),
        ('BARKOD', 'Barkod Baskısı'),
    ]
    
    tip = models.CharField(max_length=20, choices=SABLON_TIPLERI, unique=True, verbose_name="Şablon Tipi")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    # Logo ayarları
    logo_goster = models.BooleanField(default=True, verbose_name="Logo Göster")
    logo_yolu = models.ImageField(upload_to='sablon_logolar/%Y/%m/%d/', blank=True, null=True, verbose_name="Logo Dosyası")
    logo_pozisyon = models.CharField(
        max_length=20,
        choices=[('SOL', 'Sol'), ('SAG', 'Sağ'), ('ORTA', 'Orta')],
        default='SOL',
        verbose_name="Logo Pozisyonu"
    )
    logo_genislik = models.IntegerField(default=150, verbose_name="Logo Genişliği (px)")
    logo_yukseklik = models.IntegerField(default=80, verbose_name="Logo Yüksekliği (px)")
    
    # Başlık ayarları
    baslik_metni = models.CharField(max_length=200, default="", blank=True, verbose_name="Başlık Metni")
    baslik_font_boyutu = models.IntegerField(default=24, verbose_name="Başlık Font Boyutu")
    baslik_font_rengi = models.CharField(max_length=7, default="#000000", verbose_name="Başlık Font Rengi")
    baslik_kalin = models.BooleanField(default=True, verbose_name="Başlık Kalın")
    baslik_pozisyon = models.CharField(
        max_length=20,
        choices=[('SOL', 'Sol'), ('SAG', 'Sağ'), ('ORTA', 'Orta')],
        default='ORTA',
        verbose_name="Başlık Pozisyonu"
    )
    
    # Tarih ayarları
    tarih_goster = models.BooleanField(default=True, verbose_name="Tarih Göster")
    tarih_format = models.CharField(
        max_length=50,
        default="%d.%m.%Y",
        verbose_name="Tarih Formatı"
    )
    tarih_pozisyon = models.CharField(
        max_length=20,
        choices=[('SOL', 'Sol'), ('SAG', 'Sağ'), ('ORTA', 'Orta')],
        default='SAG',
        verbose_name="Tarih Pozisyonu"
    )
    
    # Firma bilgileri
    firma_adi = models.CharField(max_length=200, blank=True, verbose_name="Firma Adı")
    firma_adres = models.TextField(blank=True, verbose_name="Firma Adres")
    firma_telefon = models.CharField(max_length=50, blank=True, verbose_name="Firma Telefon")
    firma_email = models.CharField(max_length=100, blank=True, verbose_name="Firma E-posta")
    firma_vergi_no = models.CharField(max_length=50, blank=True, verbose_name="Vergi No")
    
    # Alt bilgi (footer)
    alt_bilgi_goster = models.BooleanField(default=True, verbose_name="Alt Bilgi Göster")
    alt_bilgi_metni = models.TextField(blank=True, verbose_name="Alt Bilgi Metni")
    
    # Sayfa ayarları
    sayfa_kenar_bosluk = models.IntegerField(default=20, verbose_name="Kenar Boşluğu (mm)")
    font_ailesi = models.CharField(max_length=50, default="Arial", verbose_name="Font Ailesi")
    varsayilan_font_boyutu = models.IntegerField(default=12, verbose_name="Varsayılan Font Boyutu")
    
    # Özel CSS/HTML (ileride genişletilebilir)
    ozel_css = models.TextField(blank=True, verbose_name="Özel CSS")
    ozel_html = models.TextField(blank=True, verbose_name="Özel HTML")
    
    # PDF Generator API entegrasyonu
    api_kullan = models.BooleanField(default=False, verbose_name="API ile Düzenle")
    api_key = models.CharField(max_length=200, blank=True, verbose_name="API Key")
    template_id = models.CharField(max_length=200, blank=True, verbose_name="Template ID")
    editor_url = models.URLField(blank=True, verbose_name="Editor URL")
    template_data = models.JSONField(default=dict, blank=True, verbose_name="Template Data (JSON)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Yazdırma Şablonu"
        verbose_name_plural = "Yazdırma Şablonları"
        ordering = ['tip']
    
    def __str__(self):
        return self.get_tip_display()
    
    def get_default_settings(self):
        """Varsayılan ayarları döndür"""
        return {
            'logo_goster': True,
            'baslik_metni': self.get_tip_display(),
            'tarih_goster': True,
            'alt_bilgi_goster': True,
        }


class UretimStandarti(models.Model):
    """Üretim standart talimatları"""
    kod = models.CharField(max_length=50, unique=True, verbose_name="Standart Kodu")
    ad = models.CharField(max_length=200, verbose_name="Standart Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    pdf_dosya = models.FileField(upload_to='uretim_standartlari/%Y/%m/%d/', verbose_name="PDF Dosyası")
    olusturma_tarihi = models.DateField(verbose_name="İlk Oluşturma Tarihi")
    revizyon_tarihi = models.DateField(null=True, blank=True, verbose_name="Son Revizyon Tarihi")
    revizyon_aciklama = models.TextField(blank=True, verbose_name="Revizyon Açıklaması")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Üretim Standartı"
        verbose_name_plural = "Üretim Standartları"
        ordering = ['sira', 'kod']
    
    def __str__(self):
        return f"{self.kod} - {self.ad}"
    
    def revizyon_sayisi(self):
        """Toplam revizyon sayısını döndür"""
        return self.arsivlenmis_versiyonlar.count()


class UretimStandartiArsiv(models.Model):
    """Arşivlenmiş üretim standart versiyonları"""
    standart = models.ForeignKey(UretimStandarti, on_delete=models.CASCADE, related_name='arsivlenmis_versiyonlar', verbose_name="Standart")
    pdf_dosya = models.FileField(upload_to='uretim_standartlari/arsiv/%Y/%m/%d/', verbose_name="PDF Dosyası")
    revizyon_tarihi = models.DateField(verbose_name="Revizyon Tarihi")
    revizyon_aciklama = models.TextField(blank=True, verbose_name="Revizyon Açıklaması")
    arsiv_tarihi = models.DateTimeField(auto_now_add=True, verbose_name="Arşivlenme Tarihi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Arşivlenmiş Standart Versiyonu"
        verbose_name_plural = "Arşivlenmiş Standart Versiyonları"
        ordering = ['-revizyon_tarihi', '-arsiv_tarihi']
    
    def __str__(self):
        return f"{self.standart.kod} - Revizyon {self.revizyon_tarihi}"


class KurulumDosyasi(models.Model):
    """CNC malzeme bağlama teknikleri kurulum dosyaları"""
    urun = models.ForeignKey('StokItem', on_delete=models.CASCADE, verbose_name="Ürün", related_name='kurulum_dosyalari')
    urun_parcasi = models.CharField(max_length=200, verbose_name="Ürün Parçası", help_text="Örn: Alt Plaka, Üst Plaka, Yan Duvar")
    istasyon = models.ForeignKey('Istasyon', on_delete=models.PROTECT, verbose_name="İstasyon", null=True, blank=True)
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    versiyon = models.CharField(max_length=50, default='1.0', verbose_name="Versiyon", help_text="Örn: 1.0, 1.1, 2.0")
    pdf_dosya = models.FileField(upload_to='kurulum_dosyalari/%Y/%m/%d/', verbose_name="PDF Dosyası", null=True, blank=True)
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    cnc_ekipmanlar = models.ManyToManyField(
        "CncEkipman",
        blank=True,
        related_name="kurulum_dosyalari",
        verbose_name="CNC ekipmanları",
        help_text="Bu kurulum için kullanılacak CNC aparat / yardımcı ekipmanlar (istasyon ve ortak listeye göre filtrelenir).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kurulum Dosyası"
        verbose_name_plural = "Kurulum Dosyaları"
        ordering = ['urun__stok_kodu', 'urun_parcasi', '-versiyon']
        # unique_together kaldırıldı - aynı ürün/parça/istasyon için farklı versiyonlar olabilir
    
    def __str__(self):
        return f"{self.urun.stok_kodu} - {self.urun_parcasi} - v{self.versiyon}"


class KurulumDosyasiArsiv(models.Model):
    """Arşivlenmiş kurulum dosyası versiyonları"""
    kurulum_dosyasi = models.ForeignKey(KurulumDosyasi, on_delete=models.CASCADE, related_name='arsivlenmis_versiyonlar', verbose_name="Kurulum Dosyası")
    pdf_dosya = models.FileField(upload_to='kurulum_dosyalari/arsiv/%Y/%m/%d/', verbose_name="PDF Dosyası")
    versiyon = models.CharField(max_length=50, verbose_name="Versiyon")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    arsiv_tarihi = models.DateTimeField(auto_now_add=True, verbose_name="Arşivlenme Tarihi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Arşivlenmiş Kurulum Dosyası"
        verbose_name_plural = "Arşivlenmiş Kurulum Dosyaları"
        ordering = ['-arsiv_tarihi']
    
    def __str__(self):
        return f"{self.kurulum_dosyasi.urun.stok_kodu} - {self.kurulum_dosyasi.urun_parcasi} - v{self.versiyon} (Arşiv)"


class SkalaSuiteEntegrasyon(models.Model):
    """Skala Suite MRP entegrasyon ayarları"""
    email = models.EmailField(verbose_name="E-posta")
    password = models.CharField(max_length=255, verbose_name="Şifre", help_text="Skala Suite giriş şifresi")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    # Son senkronizasyon bilgileri
    son_stok_senkronizasyon = models.DateTimeField(null=True, blank=True, verbose_name="Son Stok Senkronizasyonu")
    son_cari_senkronizasyon = models.DateTimeField(null=True, blank=True, verbose_name="Son Cari Senkronizasyonu")
    son_recete_senkronizasyon = models.DateTimeField(null=True, blank=True, verbose_name="Son Reçete Senkronizasyonu")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Skala Suite Entegrasyon"
        verbose_name_plural = "Skala Suite Entegrasyon Ayarları"
    
    def __str__(self):
        return f"Skala Suite - {self.email}"
    
    @classmethod
    def get_ayarlar(cls):
        """Singleton pattern - tek bir ayar kaydı döndür"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class Arac(models.Model):
    """Araç yönetimi modeli"""
    ARAC_TIPLERI = [
        ('BINEK', 'Binek Araç'),
        ('TICARI', 'Ticari Araç'),
        ('MOTOSIKLET', 'Motosiklet'),
        ('DIGER', 'Diğer'),
    ]
    
    plaka = models.CharField(max_length=20, unique=True, verbose_name="Plaka")
    marka = models.CharField(max_length=100, verbose_name="Marka")
    model = models.CharField(max_length=100, verbose_name="Model")
    yil = models.IntegerField(verbose_name="Yıl")
    arac_tipi = models.CharField(max_length=20, choices=ARAC_TIPLERI, default='BINEK', verbose_name="Araç Tipi")
    renk = models.CharField(max_length=50, blank=True, verbose_name="Renk")
    sasi_no = models.CharField(max_length=100, blank=True, verbose_name="Şasi No")
    motor_no = models.CharField(max_length=100, blank=True, verbose_name="Motor No")
    
    # Araç fotoğrafı
    foto = models.ImageField(upload_to='arac_foto/%Y/%m/%d/', blank=True, null=True, verbose_name="Araç Fotoğrafı")
    
    # Ruhsat PDF
    ruhsat_pdf = models.FileField(upload_to='arac_ruhsat/%Y/%m/%d/', blank=True, null=True, verbose_name="Ruhsat PDF")
    
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Araç"
        verbose_name_plural = "Araçlar"
        ordering = ['plaka']
    
    def __str__(self):
        return f"{self.plaka} - {self.marka} {self.model}"


class AracBelgeTuru(models.Model):
    """Araç belge türleri — formda + ile eklenebilir."""
    kod = models.CharField(max_length=20, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=120, verbose_name="Ad")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    bitis_tarihi_gerekmez = models.BooleanField(
        default=False,
        verbose_name="Bitiş Tarihi Gerekmez",
        help_text="Hasar tutanağı, araç tescil belgesi gibi süresiz belgeler için.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Araç Belge Türü"
        verbose_name_plural = "Araç Belge Türleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad

    @classmethod
    def bitis_tarihi_gerekmez_mi(cls, kod):
        if not kod:
            return False
        return cls.objects.filter(kod=kod, bitis_tarihi_gerekmez=True).exists()


class AracBelgesi(models.Model):
    """Araç belgeleri modeli - TÜVTÜRK, EGZOZ, Sigorta, Kasko, MTV, SRC, Psikoteknik, K belgesi, Servis, Hasar"""
    BELGE_TURLERI = [
        ('TUVTURK', 'TÜVTÜRK Muayene'),
        ('EGZOZ', 'Egzoz Emisyon'),
        ('TRAFIK_SIGORTA', 'Zorunlu Trafik Sigortası'),
        ('KASKO', 'Kasko'),
        ('MTV', 'MTV Ödeme'),
        ('SRC', 'SRC Belgesi'),
        ('PSIKOTEKNIK', 'Psikoteknik Belgesi'),
        ('K_BELGESI', 'K Belgesi'),
        ('SERVIS', 'Servis Formu'),
        ('HASAR', 'Hasar Tutanağı'),
    ]
    
    arac = models.ForeignKey(Arac, on_delete=models.CASCADE, related_name='belgeler', verbose_name="Araç")
    belge_turu = models.CharField(max_length=20, verbose_name="Belge Türü")
    
    # Tarihler
    gecerlilik_baslangic = models.DateField(null=True, blank=True, verbose_name="Geçerlilik Başlangıç Tarihi")
    gecerlilik_bitis = models.DateField(null=True, blank=True, verbose_name="Geçerlilik Bitiş Tarihi")
    
    # Belgeler
    belge_pdf = models.FileField(upload_to='arac_belgeler/%Y/%m/%d/', blank=True, null=True, verbose_name="Belge PDF")
    
    # Hasar için ekstra alanlar
    hasar_foto = models.ImageField(upload_to='arac_hasar/%Y/%m/%d/', blank=True, null=True, verbose_name="Hasar Fotoğrafı", help_text="Sadece hasar belgesi için")
    
    # Ek bilgiler
    belge_no = models.CharField(max_length=100, blank=True, verbose_name="Belge No")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    arsivlenme_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Arşivlenme Tarihi")
    onceki_belge = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yenilemeler",
        verbose_name="Önceki Belge",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Araç Belgesi"
        verbose_name_plural = "Araç Belgeleri"
        ordering = ['-gecerlilik_bitis', 'arac']
    
    def __str__(self):
        return f"{self.arac.plaka} - {self.get_belge_turu_display()}"

    def get_belge_turu_display(self):
        tur = AracBelgeTuru.objects.filter(kod=self.belge_turu).first()
        if tur:
            return tur.ad
        return dict(self.BELGE_TURLERI).get(self.belge_turu, self.belge_turu)

    def bitis_tarihi_gerekmez_mi(self):
        return AracBelgeTuru.bitis_tarihi_gerekmez_mi(self.belge_turu)
    
    def hatirlatma_gecerli_mi(self, gun=7):
        """Belgenin bitmesine belirtilen gün kala hatırlatma gösterilsin mi?"""
        if self.bitis_tarihi_gerekmez_mi() or not self.gecerlilik_bitis:
            return False
        from datetime import date, timedelta
        bugun = date.today()
        uyari_tarihi = bugun + timedelta(days=gun)
        return self.gecerlilik_bitis <= uyari_tarihi and self.gecerlilik_bitis >= bugun
    
    def suresi_doldu_mu(self):
        """Belgenin süresi doldu mu?"""
        if self.bitis_tarihi_gerekmez_mi() or not self.gecerlilik_bitis:
            return False
        from datetime import date
        return self.gecerlilik_bitis < date.today()

    def sync_belge_pdf(self):
        """İlk dosyayı eski belge_pdf alanıyla senkron tutar."""
        first = self.dosyalar.order_by("id").first()
        self.belge_pdf = first.dosya if first else None
        self.save(update_fields=["belge_pdf"])


class AracBelgesiDosya(models.Model):
    belge = models.ForeignKey(
        AracBelgesi, on_delete=models.CASCADE, related_name="dosyalar", verbose_name="Belge"
    )
    dosya = models.FileField(upload_to="arac_belgeler/%Y/%m/%d/", verbose_name="Dosya")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Araç Belgesi Dosyası"
        verbose_name_plural = "Araç Belgesi Dosyaları"
        ordering = ["id"]

    @property
    def dosya_adi(self):
        if not self.dosya:
            return ""
        return self.dosya.name.rsplit("/", 1)[-1]

    def __str__(self):
        return self.dosya_adi or f"Dosya #{self.pk}"


class Gayrimenkul(models.Model):
    """Şirket gayrimenkulleri — sahip olunan veya kiralanan taşınmazlar."""

    GM_TIPLERI = [
        ("ARSA", "Arsa"),
        ("OFIS", "Ofis"),
        ("DEPO", "Depo"),
        ("FABRIKA", "Fabrika"),
        ("DUKKAN", "Dükkan"),
        ("KONUT", "Konut"),
        ("DIGER", "Diğer"),
    ]
    SAHIPLIK_TIPLERI = [
        ("SAHIP", "Sahip olunan"),
        ("KIRALIK", "Kiralık"),
    ]
    KULLANIM_DURUMU = [
        ("AKTIF", "Aktif"),
        ("PASIF", "Pasif"),
        ("KIRADA", "Kirada"),
        ("BOS", "Boş"),
    ]
    VERGI_PERIYODU = [
        ("YILLIK", "Yıllık"),
        ("ALTI_AY", "6 aylık"),
        ("UC_AY", "3 aylık"),
    ]

    ad = models.CharField(max_length=250, verbose_name="Gayrimenkul adı")
    tip = models.CharField(max_length=20, choices=GM_TIPLERI, default="OFIS", verbose_name="Gayrimenkul tipi")
    sahiplik_tipi = models.CharField(
        max_length=20, choices=SAHIPLIK_TIPLERI, default="SAHIP", verbose_name="Sahiplik tipi"
    )
    il = models.CharField(max_length=80, verbose_name="İl")
    ilce = models.CharField(max_length=80, verbose_name="İlçe")
    adres = models.TextField(verbose_name="Açık adres")
    ada_parsel = models.CharField(max_length=200, blank=True, verbose_name="Ada / parsel")
    tapu_no = models.CharField(max_length=120, blank=True, verbose_name="Tapu no")
    metrekare = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Metrekare"
    )
    kullanim_durumu = models.CharField(
        max_length=20, choices=KULLANIM_DURUMU, default="AKTIF", verbose_name="Kullanım durumu"
    )
    sorumlu_kisi = models.CharField(max_length=200, blank=True, verbose_name="Sorumlu kişi")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    alis_veya_kira_bedeli = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Alış bedeli veya kira bedeli"
    )
    para_birimi = models.CharField(max_length=3, default="TRY", verbose_name="Para birimi")
    kira_baslangic_tarihi = models.DateField(null=True, blank=True, verbose_name="Kira başlangıç tarihi")
    kira_bitis_tarihi = models.DateField(null=True, blank=True, verbose_name="Kira bitiş tarihi")
    yillik_emlak_vergisi = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Yıllık emlak vergisi tutarı"
    )
    vergi_odeme_periyodu = models.CharField(
        max_length=20, choices=VERGI_PERIYODU, default="YILLIK", verbose_name="Vergi ödeme periyodu"
    )
    sigorta_police_no = models.CharField(max_length=120, blank=True, verbose_name="Sigorta poliçe no")
    sigorta_firmasi = models.CharField(max_length=200, blank=True, verbose_name="Sigorta firması")
    sigorta_baslangic_tarihi = models.DateField(null=True, blank=True, verbose_name="Sigorta başlangıç tarihi")
    sigorta_bitis_tarihi = models.DateField(null=True, blank=True, verbose_name="Sigorta bitiş tarihi")
    sigorta_tutari = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Sigorta tutarı"
    )
    aidat_site_gideri = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Aidat / site gideri"
    )
    bakim_giderleri_notu = models.TextField(blank=True, verbose_name="Bakım giderleri notu")
    yonetim_notlari = models.TextField(blank=True, verbose_name="Yönetim notları")

    arsivlendi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gayrimenkul"
        verbose_name_plural = "Gayrimenkuller"
        ordering = ["il", "ilce", "ad"]

    def __str__(self):
        return f"{self.ad} ({self.get_tip_display()})"


class GayrimenkulIslemi(models.Model):
    """Gayrimenkule bağlı yükümlülük ve ödeme takip kayıtları."""

    ISLEM_TIPLERI = [
        ("EMLAK_VERGISI", "Emlak vergisi"),
        ("SIGORTA", "Sigorta"),
        ("KIRA", "Kira"),
        ("AIDAT", "Aidat"),
        ("BAKIM", "Bakım"),
        ("ABONELIK", "Abonelik"),
        ("DIGER", "Diğer"),
    ]
    DURUM_SECENEKLERI = [
        ("BEKLIYOR", "Bekliyor"),
        ("ODENDI", "Ödendi"),
        ("GECIKTI", "Gecikti"),
        ("IPTAL", "İptal"),
    ]

    gayrimenkul = models.ForeignKey(
        Gayrimenkul,
        on_delete=models.CASCADE,
        related_name="islemler",
        verbose_name="Gayrimenkul",
    )
    islem_tipi = models.CharField(max_length=20, choices=ISLEM_TIPLERI, verbose_name="İşlem tipi")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    tutar = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Tutar")
    para_birimi = models.CharField(max_length=3, default="TRY", verbose_name="Para birimi")
    vade_tarihi = models.DateField(verbose_name="Vade tarihi")
    odeme_tarihi = models.DateField(null=True, blank=True, verbose_name="Ödeme tarihi")
    durum = models.CharField(
        max_length=20, choices=DURUM_SECENEKLERI, default="BEKLIYOR", verbose_name="Durum"
    )
    dosya = models.FileField(
        upload_to="gayrimenkul_islem/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name="Dosya eki",
        help_text="Poliçe, dekont, fatura vb.",
    )
    hatirlatma_tarihi = models.DateField(null=True, blank=True, verbose_name="Hatırlatma tarihi")
    not_metni = models.TextField(blank=True, verbose_name="Not")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gayrimenkul işlemi"
        verbose_name_plural = "Gayrimenkul işlemleri"
        ordering = ["vade_tarihi", "id"]

    def __str__(self):
        return f"{self.gayrimenkul.ad} — {self.get_islem_tipi_display()} ({self.vade_tarihi})"


class GayrimenkulDosya(models.Model):
    """Gayrimenkule eklenen genel dosyalar (tapu, sözleşme vb.)."""

    gayrimenkul = models.ForeignKey(
        Gayrimenkul,
        on_delete=models.CASCADE,
        related_name="dosyalar",
        verbose_name="Gayrimenkul",
    )
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    dosya = models.FileField(upload_to="gayrimenkul_dosya/%Y/%m/%d/", verbose_name="Dosya")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gayrimenkul dosyası"
        verbose_name_plural = "Gayrimenkul dosyaları"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.baslik}"


class BankaHesabi(models.Model):
    """Banka hesabı kayıtları"""
    HESAP_TIPLERI = [
        ('SAHSI', 'Şahsi'),
        ('TICARI', 'Ticari'),
    ]
    
    hesap_adi = models.CharField(max_length=200, verbose_name="Hesap Adı")
    banka_adi = models.CharField(max_length=200, verbose_name="Banka Adı")
    iban = models.CharField(max_length=34, verbose_name="IBAN Numarası", help_text="TR ile başlayan 26 haneli IBAN")
    hesap_tipi = models.CharField(max_length=10, choices=HESAP_TIPLERI, default='TICARI', verbose_name="Hesap Tipi")
    hesap_sahibi = models.CharField(max_length=200, blank=True, verbose_name="Hesap Sahibi")
    sube_kodu = models.CharField(max_length=20, blank=True, verbose_name="Şube Kodu")
    hesap_no = models.CharField(max_length=50, blank=True, verbose_name="Hesap Numarası")
    para_birimi = models.CharField(
        max_length=3,
        choices=StokItem.PARA_BIRIMLERI,
        default='TL',
        verbose_name='Hesap para birimi',
    )
    fotograf = models.ImageField(upload_to='banka_hesaplari/%Y/%m/%d/', blank=True, null=True, verbose_name="Fotoğraf")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Banka Hesabı"
        verbose_name_plural = "Banka Hesapları"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.banka_adi} - {self.hesap_adi} ({self.get_hesap_tipi_display()})"


class KrediKarti(models.Model):
    """Kredi kartı kayıtları"""
    
    kart_adi = models.CharField(max_length=200, verbose_name="Kart Adı")
    kart_numarasi = models.CharField(max_length=19, verbose_name="Kart Numarası", help_text="16 haneli kart numarası (son 4 hanesi görünebilir)")
    son_kullanim_tarihi = models.CharField(max_length=5, verbose_name="Son Kullanma Tarihi", help_text="MM/YY formatında")
    cvv = models.CharField(max_length=4, verbose_name="CVV Kodu", help_text="3 veya 4 haneli güvenlik kodu")
    kart_sahibi = models.CharField(max_length=200, blank=True, verbose_name="Kart Sahibi")
    banka_adi = models.CharField(max_length=200, blank=True, verbose_name="Banka Adı")
    fotograf = models.ImageField(upload_to='kredi_kartlari/%Y/%m/%d/', blank=True, null=True, verbose_name="Fotoğraf")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kredi Kartı"
        verbose_name_plural = "Kredi Kartları"
        ordering = ['-created_at']
    
    def __str__(self):
        # Kart numarasının son 4 hanesini göster
        son_dort = self.kart_numarasi[-4:] if len(self.kart_numarasi) >= 4 else "****"
        return f"{self.kart_adi} - ****{son_dort}"
    
    def maskelenmis_kart_numarasi(self):
        """Kart numarasının maskelenmiş halini döndür"""
        if len(self.kart_numarasi) >= 4:
            return f"**** **** **** {self.kart_numarasi[-4:]}"
        return "**** **** **** ****"


class AylikOdeme(models.Model):
    """Aylık ödemeler takibi"""
    ODEME_SEKLI = [
        ('HAVALE_EFT', 'Havale/EFT'),
        ('KREDI_KARTI', 'Kredi Kartı'),
        ('BANKA_HESABI', 'Banka Hesabı'),
    ]
    
    ODEME_DURUMU = [
        ('BEKLEMEDE', 'Beklemede'),
        ('ODENDI', 'Ödendi'),
        ('GECIKMIS', 'Gecikmiş'),
    ]
    
    odeme_aciklamasi = models.CharField(max_length=500, verbose_name="Ödeme Açıklaması")
    odeme_sekli = models.CharField(max_length=20, choices=ODEME_SEKLI, verbose_name="Ödeme Şekli")
    
    # Dinamik seçimler - ödeme şekline göre
    banka_hesabi = models.ForeignKey(BankaHesabi, on_delete=models.SET_NULL, null=True, blank=True, 
                                     verbose_name="Banka Hesabı", related_name='aylik_odemeler')
    kredi_karti = models.ForeignKey(KrediKarti, on_delete=models.SET_NULL, null=True, blank=True,
                                    verbose_name="Kredi Kartı", related_name='aylik_odemeler')
    
    kayit_tarihi = models.DateField(verbose_name="Kayıt Tarihi")
    odeme_tarihi = models.DateField(verbose_name="Ödeme Tarihi")
    tutar = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tutar")
    para_birimi = models.ForeignKey('ParaBirimi', on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name="Para Birimi", related_name='aylik_odemeler')
    
    # Tekrarlayan ödemeler için
    tekrar_eden = models.BooleanField(default=False, verbose_name="Tekrar Eden Ödeme", 
                                     help_text="Bu ödeme her ay tekrarlanıyor mu?")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    odeme_durumu = models.CharField(max_length=20, choices=ODEME_DURUMU, default='BEKLEMEDE', verbose_name="Ödeme Durumu")
    odeme_yapildi_tarih = models.DateField(null=True, blank=True, verbose_name="Ödeme Yapıldı Tarihi")

    hatirlatma_gun_once = models.PositiveIntegerField(
        default=7,
        verbose_name="Hatırlatma (gün önce)",
        help_text="Ödeme tarihinden kaç gün önce hatırlatma ve vurgu başlasın (panel, liste).",
    )
    
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    plan_uid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Tekrar planı kimliği",
        help_text="Aynı taksit planındaki kayıtlar bu kimlik ile gruplanır.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Aylık Ödeme"
        verbose_name_plural = "Aylık Ödemeler"
        ordering = ['-odeme_tarihi', '-kayit_tarihi']
    
    def __str__(self):
        return f"{self.odeme_aciklamasi} - {self.odeme_tarihi} ({self.get_odeme_durumu_display()})"

    def plan_odemeleri(self):
        """Aynı tekrar planındaki kayıtlar (ödeme tarihine göre)."""
        if self.plan_uid:
            return AylikOdeme.objects.filter(plan_uid=self.plan_uid).order_by(
                "odeme_tarihi", "id"
            )
        aciklama = (self.odeme_aciklamasi or "").strip()
        return AylikOdeme.objects.filter(odeme_aciklamasi=aciklama).order_by(
            "odeme_tarihi", "id"
        )
    
    def hatirlatma_gecerli_mi(self, gun=None):
        """Ödeme tarihi gelmeden önce, ayarlanan gün sayısı içinde hatırlatma gösterilsin mi?"""
        from datetime import date, timedelta
        if gun is None:
            gun = self.hatirlatma_gun_once if self.hatirlatma_gun_once else 7
        bugun = date.today()
        uyari_tarihi = bugun + timedelta(days=gun)
        return self.odeme_durumu == "BEKLEMEDE" and self.odeme_tarihi <= uyari_tarihi and self.odeme_tarihi >= bugun
    
    def gecikmis_mi(self):
        """Ödeme gecikmiş mi?"""
        from datetime import date
        return (self.odeme_durumu == 'BEKLEMEDE' and 
                self.odeme_tarihi < date.today())


# ============================================================================
# Kalite Yönetimi Modülü: Müşteri Şikayet & Uygunsuzluk (NCR/Complaint) + CAPA + ECO + Üretim Uyarı
# ============================================================================

class Complaint(models.Model):
    """Müşteri şikayeti ve uygunsuzluk kayıtları"""
    COMPLAINT_TYPES = [
        ('COMPLAINT', 'Müşteri Şikayeti'),
        ('NCR', 'Uygunsuzluk (NCR)'),
        ('INTERNAL', 'İç Uygunsuzluk'),
    ]
    
    STATUS_CHOICES = [
        ('OPEN', 'Açık'),
        ('IN_REVIEW', 'İnceleniyor'),
        ('ACTIONED', 'Aksiyon Alındı'),
        ('VERIFIED', 'Doğrulandı'),
        ('CLOSED', 'Kapatıldı'),
    ]
    
    type = models.CharField(max_length=20, choices=COMPLAINT_TYPES, default='COMPLAINT', verbose_name="Tip")
    customer = models.ForeignKey(Musteri, on_delete=models.PROTECT, verbose_name="Müşteri")
    related_order = models.ForeignKey(Siparis, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="İlgili Sipariş")
    product = models.ForeignKey(StokItem, on_delete=models.PROTECT, verbose_name="Ürün")
    product_revision = models.CharField(max_length=50, blank=True, verbose_name="Ürün Revizyonu")
    lot_serial = models.CharField(max_length=100, blank=True, verbose_name="Lot/Seri No")
    category = models.CharField(max_length=200, verbose_name="Kategori")
    severity = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=3, verbose_name="Şiddet (1-5)")
    affected_qty = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Etkilenen Miktar")
    description = models.TextField(verbose_name="Açıklama")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN', verbose_name="Durum")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_complaints', verbose_name="Oluşturan")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Kapanış Tarihi")
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_complaints', verbose_name="Kapatan")
    
    class Meta:
        verbose_name = "Şikayet/Uygunsuzluk"
        verbose_name_plural = "Şikayetler/Uygunsuzluklar"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_type_display()} - {self.customer.ad} - {self.product.ad} ({self.get_status_display()})"


class ComplaintAttachment(models.Model):
    """Şikayet ekleri"""
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='attachments', verbose_name="Şikayet")
    file = models.FileField(upload_to='complaints/%Y/%m/%d/', verbose_name="Dosya")
    note = models.TextField(blank=True, verbose_name="Not")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yüklenme Tarihi")
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Yükleyen")
    
    class Meta:
        verbose_name = "Şikayet Eki"
        verbose_name_plural = "Şikayet Ekleri"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.complaint} - {self.file.name}"


class CapaAction(models.Model):
    """CAPA (Corrective/Preventive Action) Aksiyonları"""
    ACTION_TYPES = [
        ('CORRECTIVE', 'Düzeltici Aksiyon'),
        ('PREVENTIVE', 'Önleyici Aksiyon'),
    ]
    
    ROOT_CAUSE_METHODS = [
        ('5WHY', '5 Why Analizi'),
        ('ISHIKAWA', 'Ishikawa (Balık Kılçığı)'),
        ('OTHER', 'Diğer'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Beklemede'),
        ('IN_PROGRESS', 'Devam Ediyor'),
        ('COMPLETED', 'Tamamlandı'),
        ('VERIFIED', 'Doğrulandı'),
        ('CLOSED', 'Kapatıldı'),
    ]
    
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='capa_actions', verbose_name="Şikayet")
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name="Aksiyon Tipi")
    root_cause_method = models.CharField(max_length=20, choices=ROOT_CAUSE_METHODS, blank=True, verbose_name="Kök Neden Analiz Yöntemi")
    root_cause_text = models.TextField(verbose_name="Kök Neden")
    action_text = models.TextField(verbose_name="Aksiyon")
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='capa_actions_owned', verbose_name="Sorumlu")
    due_date = models.DateField(verbose_name="Bitiş Tarihi")
    done_date = models.DateField(null=True, blank=True, verbose_name="Tamamlanma Tarihi")
    verification_text = models.TextField(blank=True, verbose_name="Doğrulama")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="Durum")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    
    class Meta:
        verbose_name = "CAPA Aksiyonu"
        verbose_name_plural = "CAPA Aksiyonları"
        ordering = ['due_date', 'status']
    
    def __str__(self):
        return f"{self.complaint} - {self.get_action_type_display()} ({self.get_status_display()})"


class EcoChange(models.Model):
    """Engineering Change Order (ECO) - Mühendislik Değişiklik Emri"""
    CHANGE_TYPES = [
        ('BOM', 'BOM (Bill of Materials)'),
        ('ROUTING', 'Yönlendirme'),
        ('CONTROL_FORM', 'Kontrol Formu'),
        ('INSTRUCTION', 'Talimat'),
        ('MATERIAL', 'Malzeme'),
    ]
    
    APPROVAL_STATUS = [
        ('DRAFT', 'Taslak'),
        ('PENDING', 'Onay Bekliyor'),
        ('APPROVED', 'Onaylandı'),
        ('REJECTED', 'Reddedildi'),
    ]
    
    complaint = models.ForeignKey(Complaint, on_delete=models.SET_NULL, null=True, blank=True, related_name='eco_changes', verbose_name="İlgili Şikayet")
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPES, verbose_name="Değişiklik Tipi")
    product = models.ForeignKey(StokItem, on_delete=models.PROTECT, verbose_name="Ürün")
    from_revision = models.CharField(max_length=50, blank=True, verbose_name="Önceki Revizyon")
    to_revision = models.CharField(max_length=50, verbose_name="Yeni Revizyon")
    description = models.TextField(verbose_name="Açıklama")
    effective_from_date = models.DateField(verbose_name="Geçerlilik Başlangıç Tarihi")
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='DRAFT', verbose_name="Onay Durumu")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_ecos', verbose_name="Onaylayan")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Onay Tarihi")
    rejection_reason = models.TextField(blank=True, verbose_name="Red Nedeni")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_ecos', verbose_name="Oluşturan")
    
    class Meta:
        verbose_name = "ECO (Mühendislik Değişiklik Emri)"
        verbose_name_plural = "ECO'lar (Mühendislik Değişiklik Emirleri)"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"ECO - {self.product.ad} ({self.from_revision} → {self.to_revision})"


class UretimDegisiklikKaydi(models.Model):
    """Üretim sırasında tespit edilen hata/değişiklik ihtiyaçlarını takip eder."""

    DURUM_SECENEKLERI = [
        ("ACIK", "Açık"),
        ("DEVAM", "Devam Ediyor"),
        ("TAMAMLANDI", "Tamamlandı"),
    ]

    ONCELIK_SECENEKLERI = [
        ("DUSUK", "Düşük"),
        ("ORTA", "Orta"),
        ("YUKSEK", "Yüksek"),
        ("KRITIK", "Kritik"),
    ]

    degisiklik_tipi = models.CharField(max_length=120, verbose_name="Değişiklik Tipi")
    urun = models.ForeignKey(
        StokItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uretim_degisim_kayitlari",
        verbose_name="Ürün",
    )
    baslik = models.CharField(max_length=220, verbose_name="Başlık")
    aciklama = models.TextField(verbose_name="Açıklama")
    teknik_resim_guncellenecek = models.BooleanField(default=False, verbose_name="Teknik resim güncellenecek")
    kati_model_guncellenecek = models.BooleanField(default=False, verbose_name="Katı model güncellenecek")
    tekos_recete_guncellenecek = models.BooleanField(default=False, verbose_name="Tekos reçetesi güncellenecek")
    cnc_programi_guncellenecek = models.BooleanField(default=False, verbose_name="CNC programı güncellenecek")
    ek_not = models.TextField(blank=True, verbose_name="Ek not")
    durum = models.CharField(max_length=16, choices=DURUM_SECENEKLERI, default="ACIK", verbose_name="Durum")
    oncelik = models.CharField(max_length=12, choices=ONCELIK_SECENEKLERI, default="ORTA", verbose_name="Öncelik")
    termin_tarihi = models.DateField(null=True, blank=True, verbose_name="Termin")
    kapatma_notu = models.TextField(blank=True, verbose_name="Kapatma notu")
    kapatilan_tarih = models.DateTimeField(null=True, blank=True, verbose_name="Kapatılma tarihi")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="olusturulan_uretim_degisim_kayitlari",
        verbose_name="Oluşturan",
    )
    kapatan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kapatilan_uretim_degisim_kayitlari",
        verbose_name="Kapatan",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Üretim Değişiklik Kaydı"
        verbose_name_plural = "Üretim Değişiklik Kayıtları"
        ordering = ["-created_at"]

    def __str__(self):
        urun_adi = self.urun.stok_kodu if self.urun_id else "Ürün Yok"
        return f"{urun_adi} - {self.baslik}"


class AlertRule(models.Model):
    """Üretim uyarı kuralları"""
    SCOPE_CHOICES = [
        ('PRODUCT', 'Ürün'),
        ('PRODUCT_REVISION', 'Ürün Revizyonu'),
        ('CUSTOMER', 'Müşteri'),
        ('CATEGORY', 'Kategori'),
    ]
    
    LEVEL_CHOICES = [
        ('INFO', 'Bilgi'),
        ('ACK_REQUIRED', 'Onay Gerekli'),
        ('BLOCK', 'Engelle'),
    ]
    
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, verbose_name="Kapsam")
    product = models.ForeignKey(StokItem, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Ürün")
    product_revision = models.CharField(max_length=50, blank=True, verbose_name="Ürün Revizyonu")
    customer = models.ForeignKey(Musteri, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Müşteri")
    category = models.CharField(max_length=200, blank=True, verbose_name="Kategori")
    severity_threshold = models.IntegerField(null=True, blank=True, choices=[(i, str(i)) for i in range(1, 6)], verbose_name="Şiddet Eşiği")
    message = models.TextField(verbose_name="Mesaj")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='INFO', verbose_name="Seviye")
    active = models.BooleanField(default=True, verbose_name="Aktif")
    valid_from = models.DateTimeField(verbose_name="Geçerlilik Başlangıç")
    valid_to = models.DateTimeField(null=True, blank=True, verbose_name="Geçerlilik Bitiş")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Oluşturan")
    
    class Meta:
        verbose_name = "Uyarı Kuralı"
        verbose_name_plural = "Uyarı Kuralları"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_scope_display()} - {self.get_level_display()}: {self.message[:50]}"
    
    def is_valid(self):
        """Kural geçerli mi kontrol et"""
        from django.utils import timezone
        now = timezone.now()
        if not self.active:
            return False
        if self.valid_from > now:
            return False
        if self.valid_to and self.valid_to < now:
            return False
        return True
    
    def matches(self, product=None, product_revision=None, customer=None, category=None):
        """Verilen parametrelere göre kural eşleşiyor mu?"""
        if not self.is_valid():
            return False
        
        if self.scope == 'PRODUCT':
            return product and product == self.product
        elif self.scope == 'PRODUCT_REVISION':
            return product and product == self.product and product_revision == self.product_revision
        elif self.scope == 'CUSTOMER':
            return customer and customer == self.customer
        elif self.scope == 'CATEGORY':
            return category and category == self.category
        
        return False


class ControlPlan(models.Model):
    """Kontrol planı - Üretim süreci kontrol planları"""
    STATUS_CHOICES = [
        ('ACTIVE', 'Aktif'),
        ('INACTIVE', 'Pasif'),
    ]
    
    product = models.ForeignKey(StokItem, on_delete=models.PROTECT, verbose_name="Ürün")
    revision = models.CharField(max_length=50, verbose_name="Revizyon")
    effective_from = models.DateField(verbose_name="Geçerlilik Başlangıç Tarihi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Durum")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Oluşturan")
    
    class Meta:
        verbose_name = "Kontrol Planı"
        verbose_name_plural = "Kontrol Planları"
        ordering = ['product', '-revision']
        unique_together = [['product', 'revision']]
    
    def __str__(self):
        return f"{self.product.ad} - Rev.{self.revision} ({self.get_status_display()})"


class ControlItem(models.Model):
    """Kontrol planı maddeleri - Üretim süreci kontrol noktaları"""
    INSPECTION_TYPE_CHOICES = [
        ('NUMERIC', 'Sayısal (Numeric)'),
        ('VISUAL', 'Görsel (Visual)'),
        ('FUNCTIONAL', 'Fonksiyonel (Functional)'),
        ('DOCUMENT', 'Dokümantasyon (Document)'),
    ]
    
    FREQUENCY_TYPE_CHOICES = [
        ('100_PERCENT', '100% (Her birim)'),
        ('FIRST_PIECE', 'İlk parça (First Piece)'),
        ('EVERY_N', 'Her N parça'),
        ('PER_LOT', 'Lot başına'),
        ('PER_SHIFT', 'Vardiya başına'),
    ]
    
    CRITICALITY_CHOICES = [
        ('CRITICAL', 'Kritik'),
        ('MAJOR', 'Önemli'),
        ('MINOR', 'Az Önemli'),
    ]
    
    plan = models.ForeignKey(ControlPlan, on_delete=models.CASCADE, related_name='items', verbose_name="Kontrol Planı")
    operation_step = models.ForeignKey('ReceteOperasyon', on_delete=models.PROTECT, null=True, blank=True, 
                                       related_name='control_items', verbose_name="Operasyon Adımı")
    name = models.CharField(max_length=200, verbose_name="Kontrol Adı")
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPE_CHOICES, default='NUMERIC', verbose_name="Kontrol Tipi")
    
    # Sayısal ölçüm için
    unit = models.CharField(max_length=50, blank=True, verbose_name="Birim")
    nominal = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Nominal Değer")
    min_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Min. Değer")
    max_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Max. Değer")
    
    # Metin kriterleri (görsel/fonksiyonel için)
    text_criteria = models.TextField(blank=True, verbose_name="Metin Kriterleri")
    
    # Ölçüm metodu
    method = models.CharField(max_length=200, blank=True, verbose_name="Ölçüm Metodu", 
                             help_text="Örn: Kumpas, Mikrometre, CMM, Gözle muayene")
    
    # Frekans
    frequency_type = models.CharField(max_length=20, choices=FREQUENCY_TYPE_CHOICES, default='100_PERCENT', verbose_name="Frekans Tipi")
    frequency_n = models.IntegerField(null=True, blank=True, verbose_name="Frekans N Değeri", 
                                     help_text="Her N parça için kullanılır")
    sample_size = models.IntegerField(null=True, blank=True, verbose_name="Örnek Boyutu")
    
    # Kritiklik ve gereksinimler
    criticality = models.CharField(max_length=20, choices=CRITICALITY_CHOICES, default='MAJOR', verbose_name="Kritiklik")
    requires_instrument = models.BooleanField(default=False, verbose_name="Ölçü Aleti Gerekli")
    requires_attachment = models.BooleanField(default=False, verbose_name="Ek Dosya Gerekli")
    requires_ack = models.BooleanField(default=False, verbose_name="Onay Gerekli")
    
    # Eski alanlar (geriye dönük uyumluluk için)
    step = models.IntegerField(null=True, blank=True, verbose_name="Adım (Eski)")
    measurement_name = models.CharField(max_length=200, blank=True, verbose_name="Ölçüm Adı (Eski)")
    spec_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Min. Spec (Eski)")
    spec_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Max. Spec (Eski)")
    frequency = models.CharField(max_length=100, blank=True, verbose_name="Frekans (Eski)")
    required = models.BooleanField(default=True, verbose_name="Zorunlu")
    
    # Sıralama
    display_order = models.IntegerField(default=0, verbose_name="Görüntüleme Sırası")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    
    class Meta:
        verbose_name = "Kontrol Planı Maddesi"
        verbose_name_plural = "Kontrol Planı Maddeleri"
        ordering = ['plan', 'operation_step__sira', 'display_order', 'id']
    
    def __str__(self):
        return f"{self.plan} - {self.name} ({self.get_criticality_display()})"


class AuditLog(models.Model):
    """Audit log - Tüm değişikliklerin kaydı"""
    ACTION_TYPES = [
        ('CREATE', 'Oluşturuldu'),
        ('UPDATE', 'Güncellendi'),
        ('DELETE', 'Silindi'),
        ('STATUS_CHANGE', 'Durum Değişikliği'),
        ('APPROVE', 'Onaylandı'),
        ('REJECT', 'Reddedildi'),
    ]
    
    content_type = models.CharField(max_length=50, verbose_name="İçerik Tipi")  # Complaint, CapaAction, EcoChange, etc.
    object_id = models.IntegerField(verbose_name="Nesne ID")
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name="Aksiyon Tipi")
    field_name = models.CharField(max_length=100, blank=True, verbose_name="Alan Adı")
    old_value = models.TextField(blank=True, verbose_name="Eski Değer")
    new_value = models.TextField(blank=True, verbose_name="Yeni Değer")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Kullanıcı")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Zaman Damgası")
    notes = models.TextField(blank=True, verbose_name="Notlar")
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Loglar"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.content_type} #{self.object_id} - {self.timestamp}"


# ============================================================================
# Üretim Süreci Kontrol (In-Process Inspection) Modülü
# ============================================================================

class WorkOrderInspection(models.Model):
    """İş emri üretim süreci kontrol kayıtları"""
    DISPOSITION_CHOICES = [
        ('PASS', 'Geçti'),
        ('FAIL', 'Başarısız'),
        ('REWORK', 'Yeniden İşleme'),
        ('SCRAP', 'Hurda'),
        ('HOLD', 'Beklet'),
        ('DEVIATION', 'Sapma (Onaylı)'),
    ]
    
    work_order = models.ForeignKey(UretimEmri, on_delete=models.CASCADE, related_name='inspections', verbose_name="İş Emri")
    operation_step = models.ForeignKey('ReceteOperasyon', on_delete=models.PROTECT, related_name='inspections', verbose_name="Operasyon Adımı")
    control_item = models.ForeignKey(ControlItem, on_delete=models.PROTECT, related_name='inspections', verbose_name="Kontrol Maddesi")
    
    # Örnek bilgisi
    sample_no = models.IntegerField(null=True, blank=True, verbose_name="Örnek No", 
                                   help_text="Örnek numarası (ilk parça için 1, her N için N, 2N, vb.)")
    
    # Ölçüm değeri
    measured_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Ölçülen Değer")
    
    # Sonuç
    pass_fail = models.CharField(max_length=20, choices=DISPOSITION_CHOICES, verbose_name="Sonuç")
    
    # Disposition (FAIL durumunda)
    disposition = models.CharField(max_length=20, choices=DISPOSITION_CHOICES, null=True, blank=True, verbose_name="Disposition")
    disposition_reason = models.TextField(blank=True, verbose_name="Disposition Nedeni")
    disposition_approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                            related_name='approved_dispositions', verbose_name="Disposition Onaylayan")
    disposition_approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Disposition Onay Tarihi")
    
    # Ölçü aleti
    instrument = models.ForeignKey(OlcuAleti, on_delete=models.SET_NULL, null=True, blank=True, 
                                  related_name='inspections', verbose_name="Kullanılan Ölçü Aleti")
    
    # Ek dosya
    attachment = models.FileField(upload_to='inspection_attachments/%Y/%m/%d/', null=True, blank=True, verbose_name="Ek Dosya")
    
    # Notlar
    notes = models.TextField(blank=True, verbose_name="Notlar")
    
    # Kim tarafından ölçüldü
    measured_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='performed_inspections', verbose_name="Ölçüm Yapan")
    measured_at = models.DateTimeField(verbose_name="Ölçüm Zamanı")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    
    class Meta:
        verbose_name = "İş Emri Kontrol Kaydı"
        verbose_name_plural = "İş Emri Kontrol Kayıtları"
        ordering = ['-measured_at']
        indexes = [
            models.Index(fields=['work_order', 'operation_step']),
            models.Index(fields=['control_item', 'pass_fail']),
        ]
    
    def __str__(self):
        return f"{self.work_order.emir_no} - {self.control_item.name} - {self.get_pass_fail_display()}"
    
    def auto_calculate_pass_fail(self):
        """Ölçülen değeri kontrol item kriterlerine göre otomatik hesapla"""
        if not self.measured_value or not self.control_item:
            return None
        
        item = self.control_item
        
        # Sayısal kontrol için
        if item.inspection_type == 'NUMERIC' and item.min_value is not None and item.max_value is not None:
            if item.min_value <= self.measured_value <= item.max_value:
                return 'PASS'
            else:
                return 'FAIL'
        
        # Diğer kontroller için manuel giriş gerekir
        return None


class QualityGate(models.Model):
    """Kalite geçidi - Operasyon adımı tamamlanma kontrolü"""
    GATE_TYPE_CHOICES = [
        ('BLOCK_ON_INCOMPLETE', 'Eksik Kontrolleri Engelle'),
        ('BLOCK_ON_FAIL', 'Başarısız Kontrolleri Engelle'),
        ('BLOCK_ON_CRITICAL_FAIL', 'Kritik Başarısızları Engelle'),
    ]
    
    operation_step = models.ForeignKey('ReceteOperasyon', on_delete=models.CASCADE, related_name='quality_gates', 
                                      verbose_name="Operasyon Adımı")
    gate_type = models.CharField(max_length=30, choices=GATE_TYPE_CHOICES, default='BLOCK_ON_INCOMPLETE', 
                                verbose_name="Geçit Tipi")
    applies_to_critical_only = models.BooleanField(default=False, verbose_name="Sadece Kritik Kontrollere Uygula")
    active = models.BooleanField(default=True, verbose_name="Aktif")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    
    class Meta:
        verbose_name = "Kalite Geçidi"
        verbose_name_plural = "Kalite Geçitleri"
        unique_together = [['operation_step', 'gate_type']]
        ordering = ['operation_step__sira']
    
    def __str__(self):
        return f"{self.operation_step} - {self.get_gate_type_display()}"


class NonconformanceAutoRule(models.Model):
    """Uygunsuzluk otomatik kuralı - Başarısız kontroller için otomatik NCR/Complaint oluşturma"""
    TRIGGER_CHOICES = [
        ('CRITICAL_FAIL', 'Kritik Başarısız'),
        ('MAJOR_FAIL', 'Önemli Başarısız'),
        ('ANY_FAIL', 'Herhangi Bir Başarısız'),
        ('MULTIPLE_FAIL', 'Birden Fazla Başarısız'),
    ]
    
    ACTION_CHOICES = [
        ('CREATE_NCR', 'NCR (Uygunsuzluk) Oluştur'),
        ('CREATE_COMPLAINT', 'Şikayet Oluştur'),
        ('HOLD_WORK_ORDER', 'İş Emrini Beklet'),
        ('NOTIFY_QUALITY', 'Kalite Yönetimini Bildir'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Kural Adı")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    
    # Tetikleme koşulları
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='CRITICAL_FAIL', verbose_name="Tetikleme Tipi")
    trigger_count = models.IntegerField(default=1, verbose_name="Tetikleme Sayısı", 
                                       help_text="Kaç adet başarısız kontrol sonrası tetiklensin?")
    
    # Aksiyon
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="Aksiyon Tipi")
    
    # Uygulanacak ürün/kategori filtreleri
    product = models.ForeignKey(StokItem, on_delete=models.CASCADE, null=True, blank=True, 
                               related_name='ncr_auto_rules', verbose_name="Belirli Ürün")
    category = models.ForeignKey('Kategori', on_delete=models.CASCADE, null=True, blank=True, 
                                related_name='ncr_auto_rules', verbose_name="Belirli Kategori")
    
    # Varsayılan şikayet/NCR değerleri
    default_severity = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=3, verbose_name="Varsayılan Şiddet")
    default_category = models.CharField(max_length=200, blank=True, verbose_name="Varsayılan Kategori")
    
    active = models.BooleanField(default=True, verbose_name="Aktif")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Oluşturan")
    
    class Meta:
        verbose_name = "Uygunsuzluk Otomatik Kuralı"
        verbose_name_plural = "Uygunsuzluk Otomatik Kuralları"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_trigger_type_display()} → {self.get_action_type_display()}"


class HataLog(models.Model):
    """Sistem hata raporları"""
    HATA_SEVIYESI_CHOICES = [
        ('ERROR', 'Hata'),
        ('WARNING', 'Uyarı'),
        ('INFO', 'Bilgi'),
        ('SUCCESS', 'Başarılı'),
    ]
    
    mesaj = models.TextField(verbose_name="Hata Mesajı")
    seviye = models.CharField(max_length=20, choices=HATA_SEVIYESI_CHOICES, default='ERROR', verbose_name="Seviye")
    kaynak = models.CharField(max_length=200, blank=True, verbose_name="Kaynak", help_text="Hatanın oluştuğu view/fonksiyon")
    kullanici = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Kullanıcı")
    ip_adresi = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Adresi")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    detay = models.TextField(blank=True, verbose_name="Detaylı Hata Bilgisi")
    cozuldu = models.BooleanField(default=False, verbose_name="Çözüldü mü?")
    cozum_notu = models.TextField(blank=True, verbose_name="Çözüm Notu")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    
    class Meta:
        verbose_name = "Hata Raporu"
        verbose_name_plural = "Hata Raporları"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['seviye']),
            models.Index(fields=['cozuldu']),
        ]
    
    def __str__(self):
        return f"{self.get_seviye_display()} - {self.mesaj[:50]}... ({self.created_at.strftime('%d.%m.%Y %H:%M')})"


# --- Ar-Ge Çalışmaları (ürün geliştirme takibi) ---


class ArGeProje(models.Model):
    """Stok kartına bağlı Ar-Ge projesi; geliştirme sürecinin merkezi kaydı."""

    DURUM_CHOICES = [
        ('FIKIR', 'Fikir'),
        ('TASARIMDA', 'Tasarımda'),
        ('PROTOTIP', 'Prototip'),
        ('DEMO_URETIM', 'Demo Üretim'),
        ('TEST', 'Test'),
        ('REVIZYON', 'Revizyon'),
        ('ONAYLANDI', 'Onaylandı'),
        ('SERI_URETIME_HAZIR', 'Seri Üretime Hazır'),
        ('IPTAL', 'İptal'),
    ]

    ONCELIK_CHOICES = [
        ('DUSUK', 'Düşük'),
        ('NORMAL', 'Normal'),
        ('YUKSEK', 'Yüksek'),
        ('ACIL', 'Acil'),
    ]

    proje_kodu = models.CharField(max_length=40, unique=True, verbose_name='Proje kodu')
    proje_adi = models.CharField(max_length=200, verbose_name='Proje adı')
    stok_item = models.ForeignKey(
        'StokItem',
        on_delete=models.PROTECT,
        related_name='arge_projeleri',
        verbose_name='Stok ürünü',
    )
    sorumlu = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='arge_projeleri_sorumlu',
        verbose_name='Sorumlu',
    )
    durum = models.CharField(max_length=30, choices=DURUM_CHOICES, default='FIKIR', verbose_name='Durum')
    baslangic_tarihi = models.DateField(null=True, blank=True, verbose_name='Başlangıç tarihi')
    hedef_tarih = models.DateField(null=True, blank=True, verbose_name='Hedef tarih')
    oncelik = models.CharField(
        max_length=10, choices=ONCELIK_CHOICES, default='NORMAL', verbose_name='Öncelik'
    )
    hedef_maliyet = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name='Hedef maliyet'
    )
    hedef_satis_fiyati = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name='Hedef satış fiyatı'
    )
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    arsivli = models.BooleanField(default=False, verbose_name='Arşivlendi')

    teknik_resim_hazir = models.BooleanField(default=False, verbose_name='Teknik resim hazır')
    cad_hazir = models.BooleanField(default=False, verbose_name='CAD hazır')
    malzeme_tanimli = models.BooleanField(default=False, verbose_name='Malzeme tanımlı')
    operasyon_tanimli = models.BooleanField(default=False, verbose_name='Operasyon tanımlı')
    maliyet_hesaplandi = models.BooleanField(default=False, verbose_name='Maliyet hesaplandı')
    kontrol_plani_hazir = models.BooleanField(default=False, verbose_name='Kontrol planı hazır')
    paketleme_hazir = models.BooleanField(default=False, verbose_name='Paketleme hazır')
    stok_kodu_var = models.BooleanField(default=False, verbose_name='Stok kodu var')
    satis_fiyati_belirlendi = models.BooleanField(default=False, verbose_name='Satış fiyatı belirlendi')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Güncellenme')

    class Meta:
        verbose_name = 'Ar-Ge projesi'
        verbose_name_plural = 'Ar-Ge projeleri'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['durum']),
            models.Index(fields=['arsivli', '-created_at']),
            models.Index(fields=['stok_item']),
        ]

    def __str__(self):
        return f'{self.proje_kodu} — {self.proje_adi}'

    @classmethod
    def uret_sonraki_proje_kodu(cls):
        yil = timezone.now().year
        prefix = f'AG-{yil}-'
        son = (
            cls.objects.filter(proje_kodu__startswith=prefix)
            .order_by('-proje_kodu')
            .values_list('proje_kodu', flat=True)
            .first()
        )
        if not son or len(son) <= len(prefix):
            sira = 1
        else:
            try:
                sira = int(son.replace(prefix, '', 1)) + 1
            except ValueError:
                sira = cls.objects.filter(proje_kodu__startswith=prefix).count() + 1
        return f'{prefix}{sira:04d}'

    def seri_uretime_checklist_tamam(self):
        return all(
            [
                self.teknik_resim_hazir,
                self.cad_hazir,
                self.malzeme_tanimli,
                self.operasyon_tanimli,
                self.maliyet_hesaplandi,
                self.kontrol_plani_hazir,
                self.paketleme_hazir,
                self.stok_kodu_var,
                self.satis_fiyati_belirlendi,
            ]
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.durum == 'SERI_URETIME_HAZIR' and not self.seri_uretime_checklist_tamam():
            raise ValidationError(
                {
                    'durum': 'Seri üretime hazır durumuna geçmek için tüm seri üretim kontrol maddeleri işaretlenmiş olmalıdır.'
                }
            )

    def save(self, *args, **kwargs):
        if not self.proje_kodu:
            self.proje_kodu = self.uret_sonraki_proje_kodu()
        uf = kwargs.get('update_fields')
        # Arşiv bayrağı gibi kısmi güncellemelerde tam doğrulama atlanır
        if uf is None or not set(uf).issubset({'arsivli', 'updated_at'}):
            self.full_clean()
        super().save(*args, **kwargs)


class ArGeRevizyon(models.Model):
    """Proje altında sıralı revizyon kaydı (R0, R1, …)."""

    DEGISIKLIK_TIPI_CHOICES = [
        ('TASARIM', 'Tasarım'),
        ('MALZEME', 'Malzeme'),
        ('OLCU', 'Ölçü'),
        ('URETIM', 'Üretim'),
        ('MONTAJ', 'Montaj'),
        ('MALIYET', 'Maliyet'),
        ('KALITE', 'Kalite'),
        ('TEST', 'Test'),
        ('MUSTERI', 'Müşteri'),
        ('DIGER', 'Diğer'),
    ]

    KARAR_CHOICES = [
        ('KABUL', 'Kabul'),
        ('RED', 'Red'),
        ('BEKLEME', 'Beklemede'),
    ]

    proje = models.ForeignKey(
        ArGeProje, on_delete=models.CASCADE, related_name='revizyonlar', verbose_name='Proje'
    )
    revizyon_no = models.CharField(max_length=12, verbose_name='Revizyon no', help_text='Örn: R0, R1')
    tarih = models.DateField(verbose_name='Tarih')
    revizyon_nedeni = models.CharField(max_length=300, verbose_name='Revizyon nedeni')
    degisiklik_tipi = models.CharField(
        max_length=20, choices=DEGISIKLIK_TIPI_CHOICES, default='DIGER', verbose_name='Değişiklik tipi'
    )
    onceki_durum = models.CharField(
        max_length=30, choices=ArGeProje.DURUM_CHOICES, blank=True, verbose_name='Önceki durum'
    )
    yeni_durum = models.CharField(
        max_length=30, choices=ArGeProje.DURUM_CHOICES, blank=True, verbose_name='Yeni durum'
    )
    karar = models.CharField(max_length=12, choices=KARAR_CHOICES, default='BEKLEME', verbose_name='Karar')
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    dosya = models.FileField(upload_to='arge/revizyon/%Y/%m/', blank=True, null=True, verbose_name='Dosya')
    gorsel = models.ImageField(upload_to='arge/revizyon/img/%Y/%m/', blank=True, null=True, verbose_name='Görsel')

    class Meta:
        verbose_name = 'Ar-Ge revizyonu'
        verbose_name_plural = 'Ar-Ge revizyonları'
        ordering = ['proje', 'revizyon_no']
        unique_together = [['proje', 'revizyon_no']]

    def __str__(self):
        return f'{self.proje.proje_kodu} {self.revizyon_no}'

    def clean(self):
        import re
        from django.core.exceptions import ValidationError

        if self.revizyon_no:
            self.revizyon_no = self.revizyon_no.strip().upper()
        m = re.match(r'^R(\d+)$', self.revizyon_no or '')
        if not m:
            raise ValidationError({'revizyon_no': 'Revizyon numarası R0, R1, R2 biçiminde olmalıdır.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def sonraki_revizyon_no(proje):
        """Projede bir sonraki R{n} değeri."""
        import re

        nums = []
        for rno in proje.revizyonlar.values_list('revizyon_no', flat=True):
            m = re.match(r'^R(\d+)$', (rno or '').strip().upper())
            if m:
                nums.append(int(m.group(1)))
        n = max(nums) + 1 if nums else 0
        return f'R{n}'


class ArGeDosya(models.Model):
    """Projeye bağlı teknik / test / maliyet dosyaları."""

    DOSYA_TIPI_CHOICES = [
        ('TASARIM', 'Tasarım'),
        ('TEKNIK_RESIM', 'Teknik resim'),
        ('PROTOTIP', 'Prototip'),
        ('TEST', 'Test'),
        ('MALIYET', 'Maliyet'),
        ('KALITE', 'Kalite'),
        ('DIGER', 'Diğer'),
    ]

    proje = models.ForeignKey(
        ArGeProje, on_delete=models.CASCADE, related_name='dosyalar', verbose_name='Proje'
    )
    dosya = models.FileField(upload_to='arge/dosya/%Y/%m/', verbose_name='Dosya')
    dosya_tipi = models.CharField(
        max_length=20, choices=DOSYA_TIPI_CHOICES, default='DIGER', verbose_name='Dosya tipi'
    )
    aciklama = models.CharField(max_length=500, blank=True, verbose_name='Açıklama')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Yüklenme')

    class Meta:
        verbose_name = 'Ar-Ge dosyası'
        verbose_name_plural = 'Ar-Ge dosyaları'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.proje.proje_kodu} — {self.get_dosya_tipi_display()}'


class GelistirmeTalebi(models.Model):
    """Uygulama geliştirme talebi"""
    DURUM_CHOICES = [
        ('ACIK', 'Açık'),
        ('TAMAMLANDI', 'Tamamlandı'),
    ]

    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    durum = models.CharField(max_length=20, choices=DURUM_CHOICES, default='ACIK', verbose_name="Durum")
    tamamlanma_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Tamamlanma Zamanı")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        verbose_name = "Geliştirme Talebi"
        verbose_name_plural = "Geliştirme Talepleri"
        ordering = ['-created_at']

    def __str__(self):
        return self.baslik


class CncDosyaAgaciMakina(models.Model):
    """CNC dosya ağacı için istasyon tabanlı makina tanımı."""

    istasyon = models.OneToOneField(
        'Istasyon',
        on_delete=models.CASCADE,
        related_name='cnc_dosya_agaci_makina',
        verbose_name="İstasyon",
    )
    slug = models.SlugField(max_length=220, unique=True, verbose_name="Slug")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        verbose_name = "CNC Dosya Ağacı Makinası"
        verbose_name_plural = "CNC Dosya Ağacı Makinaları"
        ordering = ['sira', 'istasyon__ad']

    def __str__(self):
        return self.istasyon.ad

    @property
    def effective_machine_type(self):
        return istasyon_effective_cnc_makine_grubu(self.istasyon)

    def save(self, *args, **kwargs):
        base = slugify((self.istasyon.ad or '').strip()) if self.istasyon_id else ''
        if not base:
            base = f"makina-{self.istasyon_id or 'x'}"
        slug = base
        i = 2
        while CncDosyaAgaciMakina.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        self.slug = slug
        super().save(*args, **kwargs)


class CncDosyaAgaciKlasor(models.Model):
    """CNC dosya/program klasör ağacı (hafıza kartı / makine hafızası dizin yapısı).

    Klasörler hiyerarşik (parent-child) tutulur ve her klasör bir makinaya bağlıdır.
    Aynı parent altında aynı isim olamaz.
    """

    name = models.CharField(max_length=200, verbose_name="Klasör Adı")
    makina = models.ForeignKey(
        'CncDosyaAgaciMakina',
        on_delete=models.CASCADE,
        related_name='klasorler',
        verbose_name="Makina",
    )
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children', verbose_name="Üst Klasör",
    )
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    aciklama = models.CharField(max_length=500, blank=True, default='', verbose_name="Açıklama")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cnc_dosya_agaci_klasorleri', verbose_name="Oluşturan",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        verbose_name = "CNC Dosya Ağacı Klasörü"
        verbose_name_plural = "CNC Dosya Ağacı Klasörleri"
        ordering = ['sira', 'name']
        unique_together = [['parent', 'name', 'makina']]
        indexes = [
            models.Index(fields=['makina', 'parent']),
        ]

    def __str__(self):
        return self.full_path()

    def full_path(self, separator='/'):
        parts = [self.name]
        cur = self.parent
        depth = 0
        while cur is not None and depth < 50:
            parts.append(cur.name)
            cur = cur.parent
            depth += 1
        return separator.join(reversed(parts))

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.parent and self.parent.makina_id != self.makina_id:
            raise ValidationError({'parent': 'Üst klasör farklı bir makinaya ait olamaz.'})
        # Döngü kontrolü
        cur = self.parent
        depth = 0
        while cur is not None and depth < 50:
            if cur.pk == self.pk:
                raise ValidationError({'parent': 'Klasör kendisinin alt klasörü olamaz (döngü).'})
            cur = cur.parent
            depth += 1


class CncProgram(models.Model):
    """CNC Program Ana Kartı"""
    
    MACHINE_TYPE_CHOICES = [
        ('cnc_lathe', 'CNC Torna'),
        ('cnc_mill', 'CNC Freze'),
    ]
    
    FILE_FORMAT_CHOICES = [
        ('nc', 'NC'),
        ('txt', 'TXT'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Aktif'),
        ('archived', 'Arşivlenmiş'),
    ]
    
    program_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="Program ID")
    product = models.ForeignKey(StokItem, on_delete=models.CASCADE, related_name='cnc_programs', verbose_name="Ürün")
    urun_parcasi = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name="Ürün Parçası",
        help_text="Programın yapıldığı reçete bileşeni (örn: Alt Plaka, Üst Plaka)",
    )
    machine_type = models.CharField(max_length=20, choices=MACHINE_TYPE_CHOICES, verbose_name="Makine Tipi")
    machine_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Makine Adı", help_text="Örn: Doosan Lynx, Haas VF2")
    program_name = models.CharField(max_length=200, verbose_name="Program Adı", help_text="Örn: BD410_TORNA_OP10")
    program_number = models.CharField(max_length=100, blank=True, verbose_name="Program Numarası", help_text="Örn: O1234")
    file_format = models.CharField(max_length=10, choices=FILE_FORMAT_CHOICES, default='nc', verbose_name="Dosya Formatı")
    dosya_konumu = models.ForeignKey(
        'CncDosyaAgaciKlasor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cnc_programlar', verbose_name="Dosya Konumu",
        help_text="Hafıza kartı / makine hafızasındaki klasör konumu",
    )
    current_revision = models.CharField(max_length=20, blank=True, verbose_name="Aktif Revizyon", help_text="Örn: R01, R02")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Durum")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")
    
    class Meta:
        verbose_name = "CNC Program"
        verbose_name_plural = "CNC Programlar"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['status']),
            models.Index(fields=['machine_type']),
        ]
    
    def __str__(self):
        return f"{self.program_name} - {self.get_machine_type_display()}"
    
    def get_active_revision(self):
        """Aktif revizyonu döndür"""
        return self.revisions.filter(is_active=True).first()
    
    def get_revision_count(self):
        """Toplam revizyon sayısını döndür"""
        return self.revisions.count()


class CncProgramRevision(models.Model):
    """CNC Program Revizyon Kayıtları"""
    
    REVISION_TYPE_CHOICES = [
        ('new', 'Yeni Program'),
        ('correction', 'Düzeltme'),
        ('optimization', 'Optimizasyon'),
        ('emergency_fix', 'Acil Düzeltme'),
    ]
    
    revision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="Revizyon ID")
    program = models.ForeignKey(CncProgram, on_delete=models.CASCADE, related_name='revisions', verbose_name="Program")
    revision_code = models.CharField(max_length=20, verbose_name="Revizyon Kodu", help_text="Örn: R01, R02, R03")
    revision_type = models.CharField(max_length=20, choices=REVISION_TYPE_CHOICES, verbose_name="Revizyon Tipi")
    file_path = models.FileField(upload_to='cnc_programs/%Y/%m/%d/', verbose_name="Program Dosyası", help_text=".nc veya .txt dosyası")
    file_hash = models.CharField(max_length=64, blank=True, verbose_name="Dosya Hash", help_text="SHA-256 hash değeri")
    revision_note = models.TextField(verbose_name="Revizyon Notu", help_text="Örn: OP10 paso derinliği düşürüldü, chatter problemi giderildi.")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cnc_program_revisions', verbose_name="Oluşturan")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    is_active = models.BooleanField(default=False, verbose_name="Aktif")
    
    class Meta:
        verbose_name = "CNC Program Revizyonu"
        verbose_name_plural = "CNC Program Revizyonları"
        ordering = ['-created_at']
        unique_together = [['program', 'revision_code']]
        indexes = [
            models.Index(fields=['program', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.program.program_name} - {self.revision_code}"
    
    def save(self, *args, **kwargs):
        # Yeni revizyon aktif yapılıyorsa, diğer revizyonları pasif yap
        if self.is_active:
            CncProgramRevision.objects.filter(program=self.program, is_active=True).exclude(pk=self.pk).update(is_active=False)
            # Program'ın current_revision'ını güncelle
            self.program.current_revision = self.revision_code
            self.program.save()
        
        # Dosya hash'ini hesapla (dosya yüklendiyse)
        if self.file_path and not self.file_hash:
            try:
                self.file_path.seek(0)
                file_content = self.file_path.read()
                self.file_hash = hashlib.sha256(file_content).hexdigest()
                self.file_path.seek(0)  # Dosyayı başa al
            except Exception:
                pass  # Hash hesaplanamazsa devam et
        
        super().save(*args, **kwargs)
    
    def calculate_file_hash(self):
        """Dosya hash'ini hesapla ve güncelle"""
        if self.file_path:
            try:
                self.file_path.seek(0)
                file_content = self.file_path.read()
                self.file_hash = hashlib.sha256(file_content).hexdigest()
                self.file_path.seek(0)
                self.save(update_fields=['file_hash'])
                return self.file_hash
            except Exception:
                return None
        return None


class CncProgramLog(models.Model):
    """CNC Program İşlem Logları"""
    
    ACTION_CHOICES = [
        ('created', 'Oluşturuldu'),
        ('revision_added', 'Revizyon Eklendi'),
        ('revision_activated', 'Revizyon Aktifleştirildi'),
        ('revision_rolled_back', 'Revizyon Geri Alındı'),
        ('file_downloaded', 'Dosya İndirildi'),
        ('archived', 'Arşivlendi'),
        ('deleted', 'Silindi'),
    ]
    
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="Log ID")
    program = models.ForeignKey(CncProgram, on_delete=models.CASCADE, related_name='logs', verbose_name="Program")
    revision = models.ForeignKey(CncProgramRevision, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', verbose_name="Revizyon")
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name="İşlem")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cnc_program_logs', verbose_name="Kullanıcı")
    notes = models.TextField(blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Tarih")
    
    class Meta:
        verbose_name = "CNC Program Log"
        verbose_name_plural = "CNC Program Logları"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['program', '-created_at']),
            models.Index(fields=['action']),
        ]
    
    def __str__(self):
        return f"{self.program.program_name} - {self.get_action_display()} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"


class CncEkipman(models.Model):
    """CNC torna / freze için aparat ve yardımcı ekipman tanımları.

    Kurulum dosyaları veya üretim aşamaları ile ilişkilendirilecek kayıtlar için
    merkezi katalog; `machine_scope` ile torna, freze veya ortak kullanım ayrılır.
    """

    MACHINE_SCOPE_CHOICES = [
        ("cnc_lathe", "CNC Torna"),
        ("cnc_mill", "CNC Freze"),
        ("cnc_common", "Ortak (Torna ve Freze)"),
    ]

    machine_scope = models.CharField(
        max_length=20,
        choices=MACHINE_SCOPE_CHOICES,
        verbose_name="Kapsam",
        help_text="Yalnızca tornada, yalnızca frezede veya her iki makine grubunda kullanılabilir.",
    )
    ekipman_numarasi = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Ekipman numarası",
    )
    ad = models.CharField(max_length=200, verbose_name="Ekipman adı")
    marka = models.CharField(max_length=120, blank=True, default="", verbose_name="Marka")
    model_kodu = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Model",
        help_text="Üretici model / tip kodu",
    )
    aciklama = models.TextField(
        blank=True,
        verbose_name="Açıklama",
        help_text="Kullanım yeri, montaj notu veya kurulum talimatına bağlanırken kullanılacak notlar.",
    )
    fotograf = models.ImageField(
        upload_to="cnc_ekipman/foto/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Fotoğraf",
    )
    teknik_pdf = models.FileField(
        upload_to="cnc_ekipman/pdf/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Teknik PDF",
        help_text="Opsiyonel teknik çizim veya talimat PDF’i.",
    )
    barkod_envanter_no = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Barkod / envanter no",
        help_text="Barkod okuma veya depo envanter numarası (opsiyonel).",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cnc_ekipmanlari",
        verbose_name="Oluşturan",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme")

    class Meta:
        verbose_name = "CNC ekipmanı"
        verbose_name_plural = "CNC ekipmanları"
        ordering = ["machine_scope", "sira", "ekipman_numarasi", "ad"]
        indexes = [
            models.Index(fields=["machine_scope", "aktif"]),
            models.Index(fields=["aktif", "sira"]),
        ]

    def __str__(self):
        num = (self.ekipman_numarasi or "").strip()
        if num:
            return f"{num} — {self.ad}"
        return self.ad

    def applies_to_machine(self, machine_type: str) -> bool:
        """machine_type: 'cnc_lathe' veya 'cnc_mill'. Ortak kayıtlar her ikisinde geçerlidir."""
        if self.machine_scope == "cnc_common":
            return True
        return self.machine_scope == machine_type


def istasyon_effective_cnc_makine_grubu(istasyon):
    """
    Kurulum / CNC listesi filtrelemesi için efektif makine grubu.

    Önce ``Istasyon.cnc_makine_grubu`` kullanılır; boşsa istasyon adında
    ``torna`` / ``freze`` (veya ``mill``) geçiyorsa tahmin edilir — böylece
    istasyon kartında grup doldurulmamış olsa bile CNC Torna istasyonunda
    torna ekipmanları listelenir.
    """
    if istasyon is None:
        return ""
    raw = (getattr(istasyon, "cnc_makine_grubu", None) or "").strip()
    if raw in ("cnc_lathe", "cnc_mill"):
        return raw
    ad = (getattr(istasyon, "ad", None) or "").lower()
    ad_norm = ad.replace("ı", "i").replace("İ", "i")
    if "freze" in ad_norm or "mill" in ad_norm:
        return "cnc_mill"
    if "torna" in ad_norm:
        return "cnc_lathe"
    return ""


def kurulum_dosyasi_cnc_ekipman_secenekleri(istasyon):
    """
    Kurulum dosyası formu için seçilebilir aktif CNC ekipmanları.

    - İstasyon yoksa: yalnızca ``cnc_common``.
    - Efektif grup yoksa (ne alan ne ad tahmini): yalnızca ``cnc_common``.
    - Efektif grup torna veya freze ise: ortak + ilgili grup.
    """
    qs = CncEkipman.objects.filter(aktif=True).order_by(
        "machine_scope", "sira", "ekipman_numarasi", "ad"
    )
    if istasyon is None:
        return qs.filter(machine_scope="cnc_common")
    grp = istasyon_effective_cnc_makine_grubu(istasyon)
    if not grp:
        return qs.filter(machine_scope="cnc_common")
    return qs.filter(Q(machine_scope="cnc_common") | Q(machine_scope=grp))


# ============================================================================
# BELGE YÖNETİMİ MODELLERİ
# ============================================================================

class DocumentType(models.Model):
    """Belge Türleri"""
    
    CATEGORY_CHOICES = [
        ('Ruhsat', 'Ruhsat'),
        ('İzin', 'İzin'),
        ('Sertifika', 'Sertifika'),
        ('Sözleşme', 'Sözleşme'),
        ('Sigorta', 'Sigorta'),
        ('Uygunluk', 'Uygunluk'),
        ('Diğer', 'Diğer'),
    ]
    
    RISK_LEVEL_CHOICES = [
        ('LOW', 'Düşük'),
        ('MEDIUM', 'Orta'),
        ('HIGH', 'Yüksek'),
    ]
    
    code = models.CharField(max_length=100, unique=True, verbose_name="Kod", help_text="Örn: ISO9001, CE, SGK, VERGI_LEVHASI")
    name = models.CharField(max_length=200, verbose_name="Ad", help_text="Örn: ISO 9001 Sertifikası")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, verbose_name="Kategori")
    default_risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default='MEDIUM', verbose_name="Varsayılan Risk Seviyesi")
    default_reminder_days = models.TextField(blank=True, verbose_name="Varsayılan Hatırlatma Günleri", help_text="JSON array: [90,60,30,7]")
    is_active = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Belge Türü"
        verbose_name_plural = "Belge Türleri"
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"

    @classmethod
    def get_category_choices(cls):
        """Varsayılan kategoriler + veritabanındaki özel kategoriler."""
        choices = list(cls.CATEGORY_CHOICES)
        known = {value for value, _ in choices}
        for category in (
            cls.objects.exclude(category="")
            .values_list("category", flat=True)
            .distinct()
            .order_by("category")
        ):
            if category and category not in known:
                choices.append((category, category))
                known.add(category)
        return choices
    
    def get_reminder_days_list(self):
        """Hatırlatma günlerini liste olarak döndür"""
        if self.default_reminder_days:
            try:
                return json.loads(self.default_reminder_days)
            except:
                return [90, 60, 30, 7]
        return [90, 60, 30, 7]


class Document(models.Model):
    """Belgeler - Ana Tablo"""
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Aktif'),
        ('EXPIRING', 'Süresi Yaklaşıyor'),
        ('EXPIRED', 'Süresi Dolmuş'),
        ('PENDING_RENEWAL', 'Yenileme Bekliyor'),
        ('CANCELLED', 'İptal Edilmiş'),
        ('ARCHIVED', 'Arşivlenmiş'),
    ]
    
    RISK_LEVEL_CHOICES = [
        ('LOW', 'Düşük'),
        ('MEDIUM', 'Orta'),
        ('HIGH', 'Yüksek'),
    ]
    
    CONFIDENTIALITY_CHOICES = [
        ('INTERNAL', 'İç Kullanım'),
        ('CONFIDENTIAL', 'Gizli'),
        ('PUBLIC', 'Genel'),
    ]
    
    type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name='documents', verbose_name="Belge Türü")
    title = models.CharField(max_length=500, verbose_name="Başlık", help_text="Örn: Tekmar Depo Sigortası 2026")
    issuer_authority = models.CharField(max_length=200, verbose_name="Veren Makam/Kurum", help_text="Örn: TSE, SGK, Sigorta Şirketi")
    issue_date = models.DateField(verbose_name="Evrak Tarihi")
    valid_from = models.DateField(null=True, blank=True, verbose_name="Geçerlilik Başlangıcı")
    valid_until = models.DateField(null=True, blank=True, verbose_name="Geçerlilik Bitişi")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    document_no = models.CharField(max_length=200, blank=True, verbose_name="Belge Numarası/Seri")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Durum")
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default='MEDIUM', verbose_name="Risk Seviyesi")
    owner_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='owned_documents', verbose_name="Sorumlu")
    department = models.CharField(max_length=100, blank=True, verbose_name="Departman")
    confidentiality = models.CharField(max_length=20, choices=CONFIDENTIALITY_CHOICES, default='INTERNAL', verbose_name="Gizlilik")
    requires_original = models.BooleanField(default=False, verbose_name="Aslı Gerekir")
    storage_location = models.CharField(max_length=500, blank=True, verbose_name="Fiziksel Depolama Yeri", help_text="Klasör/Raf bilgisi")
    renewal_required = models.BooleanField(default=True, verbose_name="Yenileme Gerekli")
    renewal_lead_days = models.IntegerField(default=60, verbose_name="Yenileme Öncesi Gün", help_text="Kaç gün önce yenileme başlatılmalı")
    tags = models.TextField(blank=True, verbose_name="Etiketler", help_text="Virgülle ayrılmış etiketler")
    notes_internal = models.TextField(blank=True, verbose_name="İç Notlar")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_documents', verbose_name="Oluşturan")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Belge"
        verbose_name_plural = "Belgeler"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type', 'status']),
            models.Index(fields=['valid_until']),
            models.Index(fields=['owner_user']),
            models.Index(fields=['risk_level']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.type.code})"
    
    def calculate_status(self):
        """Status'u otomatik hesapla"""
        from datetime import date
        today = date.today()
        
        # Manuel statüler değiştirilemez
        if self.status in ['CANCELLED', 'ARCHIVED', 'PENDING_RENEWAL']:
            return self.status
        
        # valid_until yoksa ACTIVE kalır
        if not self.valid_until:
            return 'ACTIVE'
        
        # Süresi dolmuş
        if today > self.valid_until:
            return 'EXPIRED'
        
        # Threshold hesapla (min reminder days veya 30)
        # Yeni belgede (pk yokken) reminders sorgulanamaz; PK olmadan reverse relation kullanılamaz
        threshold = 30
        reminder = None
        if self.pk is not None:
            reminder = self.reminders.filter(is_enabled=True).order_by('days_before').first()
        if reminder:
            threshold = reminder.days_before
        elif self.type and self.type.default_reminder_days:
            days_list = self.type.get_reminder_days_list()
            if days_list:
                threshold = min(days_list)
        
        # Süresi yaklaşıyor
        days_remaining = (self.valid_until - today).days
        if days_remaining <= threshold:
            return 'EXPIRING'
        
        return 'ACTIVE'
    
    def save(self, *args, **kwargs):
        # Status'u otomatik hesapla (manuel set edilmemişse)
        if not self.status in ['CANCELLED', 'ARCHIVED', 'PENDING_RENEWAL']:
            self.status = self.calculate_status()
        super().save(*args, **kwargs)
    
    def get_current_file(self):
        """Güncel dosyayı döndür"""
        return self.files.filter(is_current=True, is_deleted=False).first()
    
    def get_days_remaining(self):
        """Kalan gün sayısını döndür"""
        from datetime import date
        if self.valid_until:
            return (self.valid_until - date.today()).days
        return None


class DocumentFile(models.Model):
    """Belge Dosyaları / Versiyonlar"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='files', verbose_name="Belge")
    version_no = models.IntegerField(default=1, verbose_name="Versiyon Numarası")
    file = models.FileField(upload_to='documents/%Y/%m/%d/', verbose_name="Dosya")
    file_name_original = models.CharField(max_length=500, verbose_name="Orijinal Dosya Adı")
    mime_type = models.CharField(max_length=100, blank=True, verbose_name="MIME Tipi")
    file_size = models.BigIntegerField(default=0, verbose_name="Dosya Boyutu (bytes)")
    checksum_sha256 = models.CharField(max_length=64, blank=True, verbose_name="SHA-256 Checksum")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_document_files', verbose_name="Yükleyen")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yüklenme Tarihi")
    change_note = models.TextField(blank=True, verbose_name="Değişiklik Notu")
    is_current = models.BooleanField(default=True, verbose_name="Güncel Dosya")
    is_deleted = models.BooleanField(default=False, verbose_name="Silindi")
    
    class Meta:
        verbose_name = "Belge Dosyası"
        verbose_name_plural = "Belge Dosyaları"
        ordering = ['-version_no']
        unique_together = [['document', 'version_no']]
        indexes = [
            models.Index(fields=['document', 'is_current']),
            models.Index(fields=['document', 'version_no']),
        ]
    
    def __str__(self):
        return f"{self.document.title} - v{self.version_no}"
    
    def get_file_size_display(self):
        """Dosya boyutunu okunabilir formatta döndür"""
        if not self.file_size:
            return "-"
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1048576:
            return f"{self.file_size / 1024:.2f} KB"
        else:
            return f"{self.file_size / 1048576:.2f} MB"
    
    def save(self, *args, **kwargs):
        # Yeni dosya ise, önceki dosyaları is_current=False yap
        if self.is_current and not self.is_deleted:
            DocumentFile.objects.filter(document=self.document, is_current=True).exclude(pk=self.pk).update(is_current=False)
        
        # Dosya hash'ini hesapla
        if self.file and not self.checksum_sha256:
            try:
                self.file.seek(0)
                file_content = self.file.read()
                self.checksum_sha256 = hashlib.sha256(file_content).hexdigest()
                self.file.seek(0)
            except Exception:
                pass
        
        super().save(*args, **kwargs)


class DocumentRenewal(models.Model):
    """Belge Yenileme Kayıtları"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Taslak'),
        ('REQUESTED', 'Talep Edildi'),
        ('IN_PROGRESS', 'Devam Ediyor'),
        ('SUBMITTED', 'Başvuruldu'),
        ('APPROVED', 'Onaylandı'),
        ('REJECTED', 'Reddedildi'),
        ('COMPLETED', 'Tamamlandı'),
        ('CANCELLED', 'İptal Edildi'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='renewals', verbose_name="Belge")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Talep Tarihi")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_renewals', verbose_name="Talep Eden")
    renewal_due_date = models.DateField(null=True, blank=True, verbose_name="Hedef Tarih")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Durum")
    external_reference = models.CharField(max_length=200, blank=True, verbose_name="Dış Referans", help_text="Başvuru no / e-devlet takip no")
    notes = models.TextField(blank=True, verbose_name="Notlar")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tamamlanma Tarihi")
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_renewals', verbose_name="Tamamlayan")
    new_document = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True, related_name='renewed_from', verbose_name="Yeni Belge")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Belge Yenileme"
        verbose_name_plural = "Belge Yenilemeleri"
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['document', 'status']),
            models.Index(fields=['requested_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.document.title} - {self.get_status_display()}"


class DocumentLink(models.Model):
    """Belge İlişkileri (Generic)"""
    
    ENTITY_TYPE_CHOICES = [
        ('ASSET', 'Demirbaş'),
        ('VEHICLE', 'Araç'),
        ('FACILITY', 'Tesis'),
        ('CUSTOMER', 'Müşteri'),
        ('CONTRACT', 'Sözleşme'),
        ('PROJECT', 'Proje'),
        ('OTHER', 'Diğer'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='links', verbose_name="Belge")
    linked_entity_type = models.CharField(max_length=50, choices=ENTITY_TYPE_CHOICES, verbose_name="Bağlı Varlık Tipi")
    linked_entity_id = models.PositiveIntegerField(verbose_name="Bağlı Varlık ID")
    relation = models.CharField(max_length=100, default='covers', verbose_name="İlişki", help_text="covers, required_for, belongs_to")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Belge İlişkisi"
        verbose_name_plural = "Belge İlişkileri"
        indexes = [
            models.Index(fields=['linked_entity_type', 'linked_entity_id']),
            models.Index(fields=['document']),
        ]
    
    def __str__(self):
        return f"{self.document.title} -> {self.get_linked_entity_type_display()} #{self.linked_entity_id}"


class DocumentReminder(models.Model):
    """Belge Hatırlatma Kuralları"""
    
    CHANNEL_CHOICES = [
        ('IN_APP', 'Uygulama İçi'),
        ('EMAIL', 'E-posta'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True, related_name='reminders', verbose_name="Belge (Özel)")
    type = models.ForeignKey(DocumentType, on_delete=models.CASCADE, null=True, blank=True, related_name='reminders', verbose_name="Belge Türü (Genel)")
    days_before = models.IntegerField(verbose_name="Kaç Gün Önce")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='IN_APP', verbose_name="Kanal")
    is_enabled = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Belge Hatırlatması"
        verbose_name_plural = "Belge Hatırlatmaları"
        ordering = ['days_before']
    
    def __str__(self):
        if self.document:
            return f"{self.document.title} - {self.days_before} gün önce"
        elif self.type:
            return f"{self.type.name} (Tür) - {self.days_before} gün önce"
        return f"{self.days_before} gün önce"


class DocumentEvent(models.Model):
    """Belge Olay Kayıtları (Audit Log)"""
    
    EVENT_TYPE_CHOICES = [
        ('CREATED', 'Oluşturuldu'),
        ('UPDATED', 'Güncellendi'),
        ('FILE_UPLOADED', 'Dosya Yüklendi'),
        ('STATUS_CHANGED', 'Durum Değişti'),
        ('REMINDER_SENT', 'Hatırlatma Gönderildi'),
        ('RENEWAL_STARTED', 'Yenileme Başlatıldı'),
        ('RENEWAL_COMPLETED', 'Yenileme Tamamlandı'),
        ('DELETED_SOFT', 'Silindi (Soft)'),
        ('DOWNLOADED', 'İndirildi'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='events', verbose_name="Belge")
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, verbose_name="Olay Tipi")
    payload = models.TextField(blank=True, verbose_name="Ek Bilgi (JSON)", help_text="JSON formatında ek bilgiler")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='document_events', verbose_name="Kullanıcı")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Tarih")
    
    class Meta:
        verbose_name = "Belge Olayı"
        verbose_name_plural = "Belge Olayları"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', '-created_at']),
            models.Index(fields=['event_type']),
        ]
    
    def __str__(self):
        return f"{self.document.title} - {self.get_event_type_display()} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"


# ============================================================================
# Kalite Yönetimi: Müşteri Ürün Kontrol Formları
# ============================================================================

TEKMAR_KONTROL_FORM_TEDARIKCI_DEFAULT = (
    "Tekmar Endüstriyel Makina Otomasyon Sanayi ve Ticaret Ltd Şti."
)


class MusteriKontrolFormSablonu(models.Model):
    """Müşteri kontrol formu için şablon tanımı (ör. Üretim Malzeme Kontrol Formu)."""

    SABLON_TIPLERI = [
        ("WORD", "Word (.dotx/docx)"),
        ("HTML", "HTML şablon"),
        ("DIGER", "Diğer"),
    ]

    musteri = models.ForeignKey(
        "Musteri",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="musteri_kontrol_form_sablonlari",
        verbose_name="İlgili müşteri",
        help_text="Boş bırakılırsa şablon genel kullanım içindir.",
    )
    form_adi = models.CharField(max_length=200, verbose_name="Form adı")
    form_kodu = models.SlugField(max_length=80, unique=True, verbose_name="Form kodu")
    revizyon = models.CharField(max_length=20, default="A", verbose_name="Revizyon")
    sablon_dosyasi = models.FileField(
        upload_to="kalite/kontrol_form_sablonlari/%Y/%m/",
        blank=True,
        verbose_name="Şablon dosyası",
        help_text="Örn. BOŞ FORM.dotx — opsiyonel.",
    )
    sablon_tipi = models.CharField(
        max_length=10,
        choices=SABLON_TIPLERI,
        default="HTML",
        verbose_name="Şablon tipi",
    )
    html_sablon = models.TextField(
        blank=True,
        verbose_name="HTML şablon (opsiyonel)",
        help_text="Boş bırakılırsa sistem gövdesi (include) kullanılır.",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Müşteri kontrol form şablonu"
        verbose_name_plural = "Müşteri kontrol form şablonları"
        ordering = ["form_adi"]

    def __str__(self):
        return f"{self.form_adi} ({self.form_kodu} Rev.{self.revizyon})"


class MusteriKontrolFormu(models.Model):
    """Doldurulmuş müşteri ürün kontrol formu örneği."""

    DURUM_CHOICES = [
        ("TASLAK", "Taslak"),
        ("KONTROL_EDILIYOR", "Kontrol Ediliyor"),
        ("TAMAMLANDI", "Tamamlandı"),
        ("MUSTERIYE_GONDERILDI", "Müşteriye Gönderildi"),
        ("REVIZE_EDILDI", "Revize Edildi"),
        ("ARSIVLENDI", "Arşivlendi"),
    ]

    sablon = models.ForeignKey(
        MusteriKontrolFormSablonu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formlar",
        verbose_name="Şablon",
    )
    musteri = models.ForeignKey(
        "Musteri",
        on_delete=models.PROTECT,
        related_name="musteri_kontrol_formlari",
        verbose_name="Müşteri",
    )
    form_adi = models.CharField(max_length=200, verbose_name="Form adı")
    form_no = models.CharField(
        max_length=80,
        unique=True,
        verbose_name="Form no",
        help_text="Benzersiz form numarası.",
    )
    siparis_no = models.CharField(max_length=80, blank=True, verbose_name="Sipariş no")
    uretim_emri_no = models.CharField(max_length=80, blank=True, verbose_name="Üretim emri no")
    urun_kodu = models.CharField(
        max_length=120, blank=True, verbose_name="Ürün / parça kodu (SAP)"
    )
    urun_adi = models.CharField(max_length=300, blank=True, verbose_name="Ürün / parça adı")
    miktar = models.CharField(max_length=50, blank=True, verbose_name="Adet")
    parti_no = models.CharField(max_length=80, blank=True, verbose_name="Parti / lot no")
    seri_no = models.CharField(max_length=80, blank=True, verbose_name="Seri no")
    resim_numarasi = models.CharField(max_length=120, blank=True, verbose_name="Resim numarası")
    dokuman_no = models.CharField(max_length=80, blank=True, verbose_name="Döküman no")
    tedarikci_unvan = models.CharField(max_length=400, blank=True, verbose_name="Tedarikçi")
    kontrol_tarihi = models.DateField(null=True, blank=True, verbose_name="Kontrol tarihi")
    hazirlayan = models.CharField(max_length=200, blank=True, verbose_name="Hazırlayan")
    kontrol_eden = models.CharField(max_length=200, blank=True, verbose_name="Kontrol eden")
    durum = models.CharField(
        max_length=30, choices=DURUM_CHOICES, default="TASLAK", verbose_name="Durum"
    )
    revizyon = models.CharField(max_length=20, default="A", verbose_name="Revizyon")
    form_verisi_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Form hücre verisi (JSON)",
        help_text="Tablo ve ek alanların gövde verisi.",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    arsivli = models.BooleanField(default=False, verbose_name="Arşivli")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_musteri_kontrol_formlari",
        verbose_name="Oluşturan",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guncelledigi_musteri_kontrol_formlari",
        verbose_name="Son güncelleyen",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme tarihi")

    class Meta:
        verbose_name = "Müşteri ürün kontrol formu"
        verbose_name_plural = "Müşteri ürün kontrol formları"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["form_no"]),
            models.Index(fields=["durum", "arsivli"]),
        ]

    def __str__(self):
        return f"{self.form_no} — {self.form_adi}"

    def save(self, *args, **kwargs):
        if not (self.tedarikci_unvan or "").strip():
            self.tedarikci_unvan = TEKMAR_KONTROL_FORM_TEDARIKCI_DEFAULT
        super().save(*args, **kwargs)


class MusteriKontrolFormDosya(models.Model):
    """Form ile ilişkili üretilen veya yüklenen dosyalar."""

    DOSYA_TIPLERI = [
        ("PDF", "PDF"),
        ("WORD", "Word"),
        ("EXCEL", "Excel"),
        ("DIGER", "Diğer"),
    ]

    form = models.ForeignKey(
        MusteriKontrolFormu,
        on_delete=models.CASCADE,
        related_name="dosyalar",
        verbose_name="Form",
    )
    dosya = models.FileField(
        upload_to="kalite/musteri_kontrol_formlari/%Y/%m/", verbose_name="Dosya"
    )
    dosya_tipi = models.CharField(
        max_length=10, choices=DOSYA_TIPLERI, default="DIGER", verbose_name="Dosya tipi"
    )
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yüklenme tarihi")

    class Meta:
        verbose_name = "Müşteri kontrol form dosyası"
        verbose_name_plural = "Müşteri kontrol form dosyaları"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.form.form_no} — {self.get_dosya_tipi_display()}"


class MusteriKontrolFormGecmisi(models.Model):
    """Durum ve işlem geçmişi."""

    form = models.ForeignKey(
        MusteriKontrolFormu,
        on_delete=models.CASCADE,
        related_name="gecmis_kayitlari",
        verbose_name="Form",
    )
    islem = models.CharField(max_length=120, verbose_name="İşlem")
    eski_durum = models.CharField(max_length=30, blank=True, verbose_name="Eski durum")
    yeni_durum = models.CharField(max_length=30, blank=True, verbose_name="Yeni durum")
    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="musteri_kontrol_form_gecmisi",
        verbose_name="Kullanıcı",
    )
    tarih = models.DateTimeField(auto_now_add=True, verbose_name="Tarih")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    class Meta:
        verbose_name = "Müşteri kontrol form geçmişi"
        verbose_name_plural = "Müşteri kontrol form geçmişi"
        ordering = ["-tarih"]

    def __str__(self):
        return f"{self.form.form_no} — {self.islem} ({self.tarih})"


class ApprovalRequest(models.Model):
    ACTION_CREATE_SALES_ORDER = "create_sales_order"
    ACTION_CREATE_PURCHASE_REQUEST = "create_purchase_request"
    ACTION_BULK_CREATE_PURCHASE_REQUEST = "bulk_create_purchase_request"
    ACTION_SEND_SUPPLIER_QUOTE_REQUEST = "send_supplier_quote_request"
    ACTION_APPROVE_SUPPLIER_OFFER = "approve_supplier_offer"
    ACTION_CREATE_PURCHASE_ORDER = "create_purchase_order"
    ACTION_CREATE_PRODUCTION_ORDER = "create_production_order"
    ACTION_PLAN_PAYMENT = "plan_payment"
    ACTION_SEND_CUSTOMER_EMAIL = "send_customer_email"

    ACTION_TYPES = [
        (ACTION_CREATE_SALES_ORDER, "Satış siparişi oluştur"),
        (ACTION_CREATE_PURCHASE_REQUEST, "Satınalma talebi oluştur"),
        (ACTION_BULK_CREATE_PURCHASE_REQUEST, "Toplu satınalma talebi oluştur"),
        (ACTION_SEND_SUPPLIER_QUOTE_REQUEST, "Tedarikçiye teklif talebi gönder"),
        (ACTION_APPROVE_SUPPLIER_OFFER, "Tedarikçi teklifini onayla"),
        (ACTION_CREATE_PURCHASE_ORDER, "Satınalma siparişi oluştur"),
        (ACTION_CREATE_PRODUCTION_ORDER, "Üretim emri oluştur"),
        (ACTION_PLAN_PAYMENT, "Ödeme planla"),
        (ACTION_SEND_CUSTOMER_EMAIL, "Müşteriye e-posta gönder"),
    ]

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"
    RISK_LEVELS = [
        (RISK_LOW, "Low"),
        (RISK_MEDIUM, "Medium"),
        (RISK_HIGH, "High"),
        (RISK_CRITICAL, "Critical"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_EXECUTED = "executed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Onay Bekliyor"),
        (STATUS_APPROVED, "Onaylandı"),
        (STATUS_REJECTED, "Reddedildi"),
        (STATUS_EXECUTED, "İşleme Alındı"),
        (STATUS_FAILED, "Hatalı"),
    ]

    SOURCE_EMAIL = "email"
    SOURCE_STOCK = "stock"
    SOURCE_PURCHASE = "purchase"
    SOURCE_FINANCE = "finance"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_EMAIL, "Email"),
        (SOURCE_STOCK, "Stok"),
        (SOURCE_PURCHASE, "Satınalma"),
        (SOURCE_FINANCE, "Finans"),
        (SOURCE_MANUAL, "Manuel"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=100, choices=ACTION_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    ai_summary = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS, default=RISK_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    approved_by = models.CharField(max_length=150, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.CharField(max_length=150, null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.TextField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "approval_requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


# --- TEKORA AI Memory (SQLite / PostgreSQL uyumlu; pgvector yok) ---


class TekoraChatLog(models.Model):
    """TEKORA sohbet oturumu kaydı."""

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tekora_chat_logs",
        verbose_name="Kullanıcı",
    )
    user_message = models.TextField(verbose_name="Kullanıcı mesajı")
    ai_response = models.TextField(blank=True, default="", verbose_name="AI yanıtı")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    source = models.CharField(max_length=40, default="web_chat", verbose_name="Kaynak")
    session_key = models.CharField(max_length=80, blank=True, default="", verbose_name="Oturum anahtarı")
    raw_context = models.JSONField(default=dict, blank=True, verbose_name="Ham bağlam (ERP / araç özeti)")
    success = models.BooleanField(default=True, verbose_name="Başarılı")
    error_message = models.TextField(null=True, blank=True, verbose_name="Hata mesajı")

    class Meta:
        db_table = "tekora_chat_logs"
        ordering = ["-created_at"]
        verbose_name = "TEKORA sohbet logu"
        verbose_name_plural = "TEKORA sohbet logları"

    def __str__(self):
        return f"TekoraChat {self.pk} ({self.created_at})"


class TekoraToolLog(models.Model):
    """TEKORA tool çağrı kaydı."""

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tekora_tool_logs",
        verbose_name="Kullanıcı",
    )
    tool_name = models.CharField(max_length=120, verbose_name="Tool adı")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Payload")
    result = models.JSONField(default=dict, blank=True, verbose_name="Sonuç")
    dangerous = models.BooleanField(default=False, verbose_name="Tehlikeli")
    approval_required = models.BooleanField(default=False, verbose_name="Onay gerekli")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    success = models.BooleanField(default=True, verbose_name="Başarılı")
    error_message = models.TextField(null=True, blank=True, verbose_name="Hata mesajı")

    class Meta:
        db_table = "tekora_tool_logs"
        ordering = ["-created_at"]
        verbose_name = "TEKORA tool logu"
        verbose_name_plural = "TEKORA tool logları"

    def __str__(self):
        return f"{self.tool_name} @ {self.created_at}"


class TekoraDecisionLog(models.Model):
    """TEKORA / AI karar ve öneri kaydı (onay oluşturma, kritik özet vb.)."""

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tekora_decision_logs",
        verbose_name="Kullanıcı",
    )
    decision_type = models.CharField(max_length=80, verbose_name="Karar tipi")
    title = models.CharField(max_length=255, verbose_name="Başlık")
    description = models.TextField(blank=True, default="", verbose_name="Açıklama")
    related_approval = models.ForeignKey(
        "ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tekora_decision_logs",
        verbose_name="İlişkili onay",
    )
    payload = models.JSONField(default=dict, blank=True, verbose_name="Ek veri")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    status = models.CharField(max_length=40, default="recorded", verbose_name="Durum")

    class Meta:
        db_table = "tekora_decision_logs"
        ordering = ["-created_at"]
        verbose_name = "TEKORA karar logu"
        verbose_name_plural = "TEKORA karar logları"

    def __str__(self):
        return f"{self.decision_type}: {self.title[:40]}"


class TekoraMemory(models.Model):
    """Öğrenilebilir / manuel TEKORA hafıza satırı (embedding sonrası genişletilebilir)."""

    memory_type = models.CharField(max_length=80, verbose_name="Hafıza tipi")
    title = models.CharField(max_length=255, verbose_name="Başlık")
    content = models.TextField(verbose_name="İçerik")
    source = models.CharField(max_length=80, blank=True, default="", verbose_name="Kaynak")
    importance = models.IntegerField(default=1, verbose_name="Önem")
    is_active = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Meta veri")

    class Meta:
        db_table = "tekora_memories"
        ordering = ["-importance", "-updated_at"]
        verbose_name = "TEKORA hafıza"
        verbose_name_plural = "TEKORA hafızalar"

    def __str__(self):
        return f"{self.memory_type}: {self.title[:40]}"


class TekoraMemoryEmbedding(models.Model):
    """
    TekoraMemory / TekoraChatLog içeriklerini pgvector ile aratılabilir hale getirir.
    memory veya chat_log dolu olabilir; source_type kaynak türünü belirtir.
    """

    memory = models.ForeignKey(
        "TekoraMemory",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="embeddings",
        verbose_name="Memory",
    )
    chat_log = models.ForeignKey(
        "TekoraChatLog",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="embeddings",
        verbose_name="Chat log",
    )
    source_type = models.CharField(
        max_length=50,
        default="chat_log",
        db_index=True,
        verbose_name="Kaynak tipi",
    )
    source_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Kaynak ID",
    )
    text = models.TextField(verbose_name="Metin")
    embedding = VectorField(dimensions=768, verbose_name="Embedding")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Meta veri")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")

    class Meta:
        db_table = "tekora_memory_embeddings"
        ordering = ["-created_at"]
        verbose_name = "TEKORA Memory Embedding"
        verbose_name_plural = "TEKORA Memory Embeddings"
        indexes = [
            models.Index(fields=["source_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_type} - {self.created_at}"


class TekoraAlert(models.Model):
    """TEKORA proaktif operasyonel risk uyarısı."""

    SEVERITY_LOW = "low"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_HIGH = "high"
    SEVERITY_CRITICAL = "critical"
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, "Düşük"),
        (SEVERITY_MEDIUM, "Orta"),
        (SEVERITY_HIGH, "Yüksek"),
        (SEVERITY_CRITICAL, "Kritik"),
    ]

    alert_type = models.CharField(max_length=80, verbose_name="Uyarı tipi")
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_MEDIUM,
        verbose_name="Önem",
    )
    title = models.CharField(max_length=255, verbose_name="Başlık")
    message = models.TextField(verbose_name="Mesaj")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Ek veri")
    source = models.CharField(max_length=80, default="tekora_alert_engine", verbose_name="Kaynak")
    is_read = models.BooleanField(default=False, verbose_name="Okundu")
    is_resolved = models.BooleanField(default=False, verbose_name="Çözüldü")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Çözülme zamanı")
    related_object_id = models.CharField(max_length=64, blank=True, default="", verbose_name="İlişkili nesne ID")
    related_object_type = models.CharField(max_length=120, blank=True, default="", verbose_name="İlişkili nesne tipi")

    class Meta:
        db_table = "tekora_alerts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["alert_type", "related_object_type", "related_object_id", "created_at"]),
            models.Index(fields=["is_resolved", "created_at"]),
        ]
        verbose_name = "TEKORA uyarısı"
        verbose_name_plural = "TEKORA uyarıları"

    def __str__(self):
        return f"{self.alert_type} ({self.severity}) {self.title[:40]}"


# Satınalma RFQ (Teklif Talebi) Modelleri
class TeklifTalebi(models.Model):
    """Birden fazla tedarikçiye gönderilen teklif talebi (Request For Quotation)."""

    DURUMLAR = [
        ('TASLAK', 'Taslak'),
        ('TEKLIF_BEKLENIYOR', 'Teklif Bekleniyor'),
        ('DEGERLENDIRMEDE', 'Değerlendirmede'),
        ('SIPARISE_DONUSTURULDU', 'Siparişe Dönüştürüldü'),
        ('IPTAL', 'İptal'),
    ]

    ONCELIKLER = [
        ('FIYAT', 'Fiyat'),
        ('TERMIN', 'Termin'),
    ]

    rfq_no = models.CharField(max_length=40, unique=True, editable=False, verbose_name='RFQ No')
    baslik = models.CharField(max_length=300, verbose_name='Başlık')
    durum = models.CharField(max_length=30, choices=DURUMLAR, default='TASLAK', verbose_name='Durum')
    oncelik = models.CharField(max_length=10, choices=ONCELIKLER, default='FIYAT', verbose_name='Öncelik')
    olusturma_tarihi = models.DateField(verbose_name='Oluşturma Tarihi')
    son_teklif_tarihi = models.DateField(null=True, blank=True, verbose_name='Son Teklif Tarihi')
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='olusturulan_rfqlar',
        verbose_name='Oluşturan',
    )
    kaynak_talep = models.ForeignKey(
        'Talep',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rfqlar',
        verbose_name='Kaynak Talep',
    )
    kaynak_siparis = models.ForeignKey(
        'Siparis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='olusturulan_rfqlar',
        verbose_name='Kaynak Sipariş',
    )
    notlar = models.TextField(blank=True, verbose_name='Notlar')
    para_birimi = models.CharField(max_length=3, default='TRY', verbose_name='Varsayılan Para Birimi')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Teklif Talebi (RFQ)'
        verbose_name_plural = 'Teklif Talepleri (RFQ)'
        ordering = ['-olusturma_tarihi', '-pk']

    def __str__(self):
        return f'{self.rfq_no} — {self.baslik[:40]}'

    def save(self, *args, **kwargs):
        if not self.rfq_no:
            self.rfq_no = self._uret_rfq_no()
        super().save(*args, **kwargs)

    @staticmethod
    def _uret_rfq_no():
        from datetime import date
        today = date.today()
        pref = f'RFQ_{today.day:02d}{today.month:02d}{str(today.year)[-2:]}_'
        n = TeklifTalebi.objects.filter(rfq_no__startswith=pref).count()
        return f'{pref}{n + 1:04d}'


class TeklifTalebiKalemi(models.Model):
    """RFQ üzerindeki kalemler — fiyat soracağımız ürünler."""

    rfq = models.ForeignKey(TeklifTalebi, on_delete=models.CASCADE, related_name='kalemler', verbose_name='RFQ')
    stok_item = models.ForeignKey(
        StokItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='rfq_kalemleri',
        verbose_name='Stok',
    )
    kalem_adi = models.CharField(max_length=300, verbose_name='Kalem Adı')
    miktar = models.DecimalField(max_digits=12, decimal_places=3, default=1, verbose_name='Miktar')
    birim = models.CharField(max_length=20, default='Adet', verbose_name='Birim')
    teknik_notlar = models.TextField(blank=True, verbose_name='Teknik Notlar')
    istenen_termin = models.DateField(null=True, blank=True, verbose_name='İstenen Termin')
    sira = models.PositiveSmallIntegerField(default=0, verbose_name='Sıra')

    class Meta:
        verbose_name = 'RFQ Kalemi'
        verbose_name_plural = 'RFQ Kalemleri'
        ordering = ['sira', 'id']

    def __str__(self):
        return f'{self.kalem_adi} ({self.miktar})'


class TeklifTalebiTedarikci(models.Model):
    """Bir RFQ'nun gönderildiği tedarikçi (veya harici email) kaydı."""

    DURUMLAR = [
        ('BEKLIYOR', 'Teklif Bekleniyor'),
        ('TEKLIF_GIRDI', 'Teklif Girdi'),
        ('IPTAL', 'İptal'),
    ]

    rfq = models.ForeignKey(TeklifTalebi, on_delete=models.CASCADE, related_name='tedarikci_baglantilari', verbose_name='RFQ')
    tedarikci = models.ForeignKey(
        Tedarikci,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rfq_baglantilari',
        verbose_name='Tedarikçi',
    )
    harici_ad = models.CharField(max_length=200, blank=True, verbose_name='Harici Firma Adı')
    harici_email = models.EmailField(blank=True, verbose_name='Harici E-posta')
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='BEKLIYOR', verbose_name='Durum')
    gonderim_tarihi = models.DateTimeField(null=True, blank=True, verbose_name='Mail Gönderim Tarihi')
    mail_gonderildi = models.BooleanField(default=False, verbose_name='Mail Gönderildi')
    notlar = models.TextField(blank=True, verbose_name='Notlar')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'RFQ Tedarikçisi'
        verbose_name_plural = 'RFQ Tedarikçileri'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['rfq', 'tedarikci'],
                condition=Q(tedarikci__isnull=False),
                name='uniq_rfq_tedarikci',
            ),
        ]

    def __str__(self):
        if self.tedarikci:
            return f'{self.rfq.rfq_no} → {self.tedarikci.ad}'
        return f'{self.rfq.rfq_no} → {self.harici_ad or self.harici_email}'

    @property
    def gosterim_adi(self):
        if self.tedarikci:
            return self.tedarikci.ad
        return self.harici_ad or self.harici_email or 'Harici'

    @property
    def gosterim_email(self):
        if self.tedarikci and self.tedarikci.email:
            return self.tedarikci.email
        return self.harici_email


class TedarikciTeklifKalemi(models.Model):
    """Tedarikçinin RFQ'daki bir kalem için verdiği fiyat ve teslim süresi."""

    PARA_BIRIMLERI = [
        ('TRY', 'Türk Lirası (₺)'),
        ('USD', 'Amerikan Doları ($)'),
        ('EUR', 'Euro (€)'),
        ('GBP', 'İngiliz Sterlini (£)'),
    ]

    rfq_tedarikci = models.ForeignKey(
        TeklifTalebiTedarikci,
        on_delete=models.CASCADE,
        related_name='kalem_teklifleri',
        verbose_name='RFQ Tedarikçisi',
    )
    rfq_kalemi = models.ForeignKey(
        TeklifTalebiKalemi,
        on_delete=models.CASCADE,
        related_name='tedarikci_teklifleri',
        verbose_name='RFQ Kalemi',
    )
    birim_fiyat = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Birim Fiyat')
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TRY', verbose_name='Para Birimi')
    teslim_suresi_gun = models.IntegerField(null=True, blank=True, verbose_name='Teslim Süresi (gün)')
    teslim_tarihi = models.DateField(null=True, blank=True, verbose_name='Teslim Tarihi')
    notlar = models.TextField(blank=True, verbose_name='Notlar')
    secildi = models.BooleanField(default=False, verbose_name='Kazanan Teklif')
    girildi_mi = models.BooleanField(default=False, verbose_name='Girildi mi')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tedarikçi Teklif Kalemi'
        verbose_name_plural = 'Tedarikçi Teklif Kalemleri'
        ordering = ['rfq_kalemi__sira', 'id']
        unique_together = [('rfq_tedarikci', 'rfq_kalemi')]

    def __str__(self):
        return f'{self.rfq_tedarikci.gosterim_adi} | {self.rfq_kalemi.kalem_adi}'


# --- Dış Operasyonlar modülü ---


class DisOperasyonTipi(models.Model):
    """Operasyon tipi (iç/dış); dış operasyon süreçleri için tanımlar."""

    IC_DIS_TIPI = [
        ('IC', 'İç Operasyon'),
        ('DIS', 'Dış Operasyon'),
    ]

    ad = models.CharField(max_length=120, verbose_name='Ad')
    operasyon_kodu = models.SlugField(max_length=64, unique=True, verbose_name='Operasyon kodu')
    ic_dis_tipi = models.CharField(max_length=3, choices=IC_DIS_TIPI, default='DIS', verbose_name='İç / Dış')
    aktif = models.BooleanField(default=True, verbose_name='Aktif')

    class Meta:
        verbose_name = 'Operasyon Tipi'
        verbose_name_plural = 'Operasyon Tipleri'
        ordering = ['ad']

    def __str__(self):
        return f'{self.ad} ({self.get_ic_dis_tipi_display()})'


class DisOperasyon(models.Model):
    """Dış tedarikçiye gönderilen operasyon emri."""

    DURUMLAR = [
        ('TASLAK', 'Taslak'),
        ('GONDERILDI', 'Gönderildi'),
        ('TEDARIKCIDE', 'Tedarikçide / İşlemde'),
        ('KISMI_DONUS', 'Kısmi Dönüş'),
        ('TAMAMLANDI', 'Tamamlandı'),
        ('KALITE_BEKLIYOR', 'Kalite Kontrol Bekliyor'),
        ('REDDEDILDI', 'Reddedildi'),
        ('IPTAL', 'İptal Edildi'),
        ('ARSIV', 'Arşivlendi'),
    ]
    KALITE_DURUMLARI = [
        ('BEKLIYOR', 'Bekliyor'),
        ('KABUL', 'Kabul'),
        ('SARTLI_KABUL', 'Şartlı Kabul'),
        ('RED', 'Red'),
    ]

    operasyon_no = models.CharField(max_length=40, unique=True)
    stok_item = models.ForeignKey(
        StokItem, on_delete=models.PROTECT, related_name='dis_operasyonlari', verbose_name='Stok ürünü'
    )
    uretim_emri = models.ForeignKey(
        UretimEmri,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dis_operasyonlari',
        verbose_name='Üretim emri',
    )
    recete_operasyon = models.ForeignKey(
        'ReceteOperasyon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dis_kayitlari',
        verbose_name='Reçete operasyon adımı',
        help_text='Reçeteden otomatik oluşturulduysa bağlantı.',
    )
    parti_no = models.CharField(max_length=120, blank=True, verbose_name='Parti / Lot No')
    operasyon_tipi = models.ForeignKey(
        DisOperasyonTipi, on_delete=models.PROTECT, related_name='dis_operasyonlar', verbose_name='Operasyon tipi'
    )
    tedarikci = models.ForeignKey(
        Tedarikci, on_delete=models.PROTECT, related_name='dis_operasyonlar', verbose_name='Tedarikçi'
    )
    gonderim_deposu = models.ForeignKey(
        'Depo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dis_operasyon_gonderimleri',
        verbose_name='Gönderim deposu',
    )
    dis_operasyon_lokasyonu = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Dış operasyon lokasyonu / tedarikçi deposu',
    )
    gonderilen_miktar = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Gönderilen miktar')
    birim = models.CharField(max_length=20, default='Adet', verbose_name='Birim')
    gonderim_tarihi = models.DateField(verbose_name='Gönderim tarihi')
    beklenen_donus_tarihi = models.DateField(null=True, blank=True, verbose_name='Beklenen dönüş tarihi')
    birim_fiyat = models.DecimalField(max_digits=14, decimal_places=4, default=0, verbose_name='Birim işlem fiyatı')
    para_birimi = models.CharField(
        max_length=3, choices=StokItem.PARA_BIRIMLERI, default='TL', verbose_name='Para birimi'
    )
    tahmini_toplam_maliyet = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name='Tahmini toplam maliyet'
    )
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='TASLAK', verbose_name='Durum')
    kalite_durumu = models.CharField(
        max_length=16, choices=KALITE_DURUMLARI, default='BEKLIYOR', verbose_name='Kalite durumu'
    )
    miktar_tedarikcide_kalan = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Tedarikçide kalan miktar',
        help_text='Bu emir için henüz kapatılmamış (dönüş/fire/eksik ile düşülür).',
    )
    miktar_kalite_bekliyor = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Kalite bekleyen miktar',
        help_text='Depoya alınmayı bekleyen dönen miktar.',
    )
    toplam_donen_miktar = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, verbose_name='Toplam dönen (kabul öncesi)'
    )
    toplam_fire_miktar = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Toplam fire')
    toplam_eksik_miktar = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Toplam eksik')
    toplam_gerceklesen_maliyet = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name='Toplam gerçekleşen maliyet'
    )
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    sevk_evrak_no = models.CharField(max_length=120, blank=True, verbose_name='Sevk evrak / irsaliye no')
    arsivli = models.BooleanField(default=False, verbose_name='Arşivli')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dış Operasyon'
        verbose_name_plural = 'Dış Operasyonlar'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['durum', 'arsivli']),
            models.Index(fields=['tedarikci', 'durum']),
            models.Index(fields=['stok_item', 'durum']),
        ]

    def __str__(self):
        return f'{self.operasyon_no} — {self.stok_item.stok_kodu}'


class DisOperasyonDonus(models.Model):
    dis_operasyon = models.ForeignKey(
        DisOperasyon, on_delete=models.CASCADE, related_name='donuslar', verbose_name='Dış operasyon'
    )
    donus_tarihi = models.DateField(verbose_name='Dönüş tarihi')
    donen_miktar = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Dönen miktar')
    fire_miktari = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Fire miktarı')
    eksik_miktari = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Eksik miktar')
    gerceklesen_birim_fiyat = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name='Gerçekleşen birim fiyat'
    )
    nakliye_maliyeti = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Nakliye maliyeti')
    ek_maliyet = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Ek maliyet')
    toplam_maliyet = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='Toplam işlem maliyeti')
    kalite_kontrol_gerekli = models.BooleanField(default=False, verbose_name='Kalite kontrol gerekli')
    kalite_islenildi = models.BooleanField(default=False, verbose_name='Kalite işlendi')
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dış Operasyon Dönüşü'
        verbose_name_plural = 'Dış Operasyon Dönüşleri'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.dis_operasyon.operasyon_no} dönüş #{self.pk}'


class DisOperasyonKaliteKontrol(models.Model):
    SONUCLAR = [
        ('KABUL', 'Kabul'),
        ('SARTLI_KABUL', 'Şartlı Kabul'),
        ('RED', 'Red'),
    ]

    dis_operasyon = models.ForeignKey(
        DisOperasyon, on_delete=models.CASCADE, related_name='kalite_kayitlari', verbose_name='Dış operasyon'
    )
    donus = models.ForeignKey(
        DisOperasyonDonus,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='kalite_kayitlari',
        verbose_name='İlgili dönüş',
    )
    kontrol_tarihi = models.DateField(verbose_name='Kontrol tarihi')
    kontrol_eden = models.CharField(max_length=200, verbose_name='Kontrol eden')
    sonuc = models.CharField(max_length=16, choices=SONUCLAR, verbose_name='Sonuç')
    kabul_miktari = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Kabul edilen miktar')
    red_miktari = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name='Reddedilen miktar')
    sartli_kabul_notu = models.TextField(blank=True, verbose_name='Şartlı kabul notu')
    red_nedeni = models.TextField(blank=True, verbose_name='Red nedeni')
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dış Operasyon Kalite Kontrolü'
        verbose_name_plural = 'Dış Operasyon Kalite Kontrolleri'
        ordering = ['-created_at', '-id']


class DisOperasyonDosya(models.Model):
    DOSYA_TIPLERI = [
        ('GENEL', 'Genel'),
        ('GONDERIM', 'Gönderim'),
        ('DONUS', 'Dönüş'),
        ('KALITE', 'Kalite'),
    ]

    dis_operasyon = models.ForeignKey(
        DisOperasyon, on_delete=models.CASCADE, related_name='dosyalar', verbose_name='Dış operasyon'
    )
    dosya = models.FileField(upload_to='dis_operasyon/%Y/%m/%d/', verbose_name='Dosya')
    dosya_tipi = models.CharField(max_length=16, choices=DOSYA_TIPLERI, default='GENEL', verbose_name='Dosya tipi')
    aciklama = models.CharField(max_length=255, blank=True, verbose_name='Açıklama')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dış Operasyon Dosyası'
        verbose_name_plural = 'Dış Operasyon Dosyaları'
        ordering = ['-uploaded_at']


class DisOperasyonLog(models.Model):
    dis_operasyon = models.ForeignKey(
        DisOperasyon, on_delete=models.CASCADE, related_name='loglar', verbose_name='Dış operasyon'
    )
    islem = models.CharField(max_length=80, verbose_name='İşlem')
    eski_durum = models.CharField(max_length=20, blank=True, verbose_name='Eski durum')
    yeni_durum = models.CharField(max_length=20, blank=True, verbose_name='Yeni durum')
    kullanici = models.CharField(max_length=120, blank=True, verbose_name='Kullanıcı')
    tarih = models.DateTimeField(auto_now_add=True, verbose_name='Tarih')
    aciklama = models.TextField(blank=True, verbose_name='Açıklama')

    class Meta:
        verbose_name = 'Dış Operasyon Log'
        verbose_name_plural = 'Dış Operasyon Logları'
        ordering = ['-tarih', '-id']


# Üretim Kontrol modülü
from .models_uretim_kontrol import (  # noqa: E402,F401
    MEASUREMENT_METHOD_CHOICES,
    MEASUREMENT_UNIT_CHOICES,
    ProductionControlPlan,
    ProductionControlRevisionArchive,
    ProductionControlResult,
    ProductionControlResultChangeLog,
    ProductionControlSession,
    ProductionControlStep,
    next_revision_no,
)

# RBAC (Yetkilendirme)
from .models_rbac import KullaniciRolu, Rol, RolYetkisi, SistemYetkisi  # noqa: E402,F401