from django.contrib import admin
from .models import (
    DisOperasyon,
    DisOperasyonDonus,
    DisOperasyonDosya,
    DisOperasyonKaliteKontrol,
    DisOperasyonLog,
    DisOperasyonTipi,
)
from .models import Cari
from .models import (StokItem, Kategori, Tedarikci, StokHareketi, 
                    Recete, ReceteDetay, UretimEmri, UretimAsamasi)
from .models import FiyatGecmisi
from .models import (OlcuAleti, OlcuAletiTuru, KalibrasyonKaydi, 
                    CalibrationMeasurement, CalibrationTolerance,
                    CncProgram, CncProgramRevision, CncProgramLog, CncEkipman,
                    ArGeProje, ArGeRevizyon, ArGeDosya,
                    TekoraAlert, TekoraChatLog, TekoraDecisionLog, TekoraMemory,
                    TekoraMemoryEmbedding, TekoraToolLog)

class KategoriAdmin(admin.ModelAdmin):
    list_display = ['ad', 'stok_tipi', 'aciklama']
    list_filter = ['stok_tipi']
    search_fields = ['ad']

class TedarikciAdmin(admin.ModelAdmin):
    list_display = ['ad', 'telefon', 'email']
    search_fields = ['ad']

class StokItemAdmin(admin.ModelAdmin):
    list_display = [
        'stok_kodu', 'ad', 'kategori', 'stok_tipi',
        'mevcut_miktar', 'dis_operasyonda_miktar', 'minimum_stok', 'alis_fiyati', 'stok_durumu'
    ]
    list_filter = ['kategori__stok_tipi', 'kategori']
    search_fields = ['stok_kodu', 'ad', 'barkod']
    
    def stok_tipi(self, obj):
        return obj.kategori.get_stok_tipi_display()
    
    def stok_durumu(self, obj):
        if obj.mevcut_miktar <= 0:
            return '❌ STOK YOK'
        elif obj.mevcut_miktar <= obj.minimum_stok:
            return '⚠️ KRİTİK'
        else:
            return '✅ NORMAL'

class ReceteDetayInline(admin.TabularInline):
    model = ReceteDetay
    extra = 1

class ReceteAdmin(admin.ModelAdmin):
    list_display = ['urun', 'versiyon', 'aktif', 'created_at']
    list_filter = ['aktif', 'urun__kategori__stok_tipi']
    inlines = [ReceteDetayInline]

class UretimAsamasiInline(admin.TabularInline):
    model = UretimAsamasi
    extra = 0

class UretimEmriAdmin(admin.ModelAdmin):
    list_display = ['emir_no', 'recete', 'miktar', 'durum', 'planlanan_baslama', 'planlanan_bitis']
    list_filter = ['durum', 'recete__urun__kategori__stok_tipi']
    inlines = [UretimAsamasiInline]

class StokHareketiAdmin(admin.ModelAdmin):
    list_display = ['stok_item', 'hareket_tipi', 'miktar', 'birim', 'tarih', 'user']
    list_filter = ['hareket_tipi', 'tarih']
    readonly_fields = ['onceki_stok', 'sonraki_stok', 'tarih']

class FiyatGecmisiAdmin(admin.ModelAdmin):
    list_display = ['stok_item', 'degisen_alan', 'tarih', 'user']
    list_filter = ['degisen_alan', 'tarih']
    search_fields = ['stok_item__stok_kodu', 'stok_item__ad']
    readonly_fields = ['tarih']

admin.site.register(Kategori, KategoriAdmin)
admin.site.register(Tedarikci, TedarikciAdmin)
admin.site.register(StokItem, StokItemAdmin)
admin.site.register(Recete, ReceteAdmin)
admin.site.register(UretimEmri, UretimEmriAdmin)
admin.site.register(StokHareketi, StokHareketiAdmin)
admin.site.register(FiyatGecmisi, FiyatGecmisiAdmin)

class CariAdmin(admin.ModelAdmin):
    list_display = ['cari_kodu', 'unvan', 'cari_tipi', 'telefon', 'email', 'bakiye', 'aktif']
    list_filter = ['cari_tipi', 'aktif']
    search_fields = ['cari_kodu', 'unvan', 'vergi_no']
    list_editable = ['aktif']

admin.site.register(Cari, CariAdmin)


@admin.register(DisOperasyonTipi)
class DisOperasyonTipiAdmin(admin.ModelAdmin):
    list_display = ['ad', 'operasyon_kodu', 'ic_dis_tipi', 'aktif']
    list_filter = ['ic_dis_tipi', 'aktif']
    search_fields = ['ad', 'operasyon_kodu']


class DisOperasyonDonusInline(admin.TabularInline):
    model = DisOperasyonDonus
    extra = 0


@admin.register(DisOperasyon)
class DisOperasyonAdmin(admin.ModelAdmin):
    list_display = [
        'operasyon_no',
        'stok_item',
        'operasyon_tipi',
        'tedarikci',
        'durum',
        'gonderilen_miktar',
        'miktar_tedarikcide_kalan',
        'arsivli',
    ]
    list_filter = ['durum', 'kalite_durumu', 'arsivli', 'operasyon_tipi']
    search_fields = ['operasyon_no', 'stok_item__stok_kodu', 'sevk_evrak_no']
    inlines = [DisOperasyonDonusInline]


@admin.register(DisOperasyonKaliteKontrol)
class DisOperasyonKaliteKontrolAdmin(admin.ModelAdmin):
    list_display = ['dis_operasyon', 'kontrol_tarihi', 'sonuc', 'kabul_miktari', 'red_miktari']


# Ölçü Aletleri ve Kalibrasyon Admin
class CalibrationMeasurementInline(admin.TabularInline):
    model = CalibrationMeasurement
    extra = 1
    fields = ['reference_value', 'measurement_1', 'measurement_2', 'measurement_3', 
              'average_value', 'deviation', 'result']

class KalibrasyonKaydiAdmin(admin.ModelAdmin):
    list_display = ['olcu_aleti', 'calibration_date', 'calibration_type', 'result', 
                    'controlled_by', 'approved_by', 'next_due_date']
    list_filter = ['calibration_type', 'result', 'calibration_date']
    search_fields = ['olcu_aleti__device_id', 'olcu_aleti__seri_no', 'reference_used']
    date_hierarchy = 'calibration_date'
    inlines = [CalibrationMeasurementInline]
    readonly_fields = ['created_at', 'updated_at']

class OlcuAletiAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'seri_no', 'device_type', 'status', 
                    'last_calibration_date', 'next_calibration_date', 'department']
    list_filter = ['status', 'device_type', 'calibration_method', 'department']
    search_fields = ['device_id', 'seri_no', 'marka', 'model', 'department']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Temel Bilgiler', {
            'fields': ('device_id', 'device_type', 'alet_turu', 'marka', 'model', 'seri_no')
        }),
        ('Teknik Bilgiler', {
            'fields': ('olcum_araligi', 'hassasiyet', 'fotograf')
        }),
        ('Kullanım Bilgileri', {
            'fields': ('department', 'kullanim_yeri', 'sorumlu_kisi')
        }),
        ('Durum ve Kalibrasyon', {
            'fields': ('status', 'durum', 'kritiklik_seviyesi', 
                      'calibration_method', 'calibration_period_months',
                      'last_calibration_date', 'next_calibration_date',
                      'son_kalibrasyon_tarihi', 'sonraki_kalibrasyon_tarihi')
        }),
        ('Diğer', {
            'fields': ('notes', 'aktif', 'created_at', 'updated_at')
        }),
    )

class OlcuAletiTuruAdmin(admin.ModelAdmin):
    list_display = ['ad', 'sira', 'aktif']
    list_filter = ['aktif']
    search_fields = ['ad']
    list_editable = ['sira', 'aktif']

class CalibrationToleranceAdmin(admin.ModelAdmin):
    list_display = ['device_type', 'min_range', 'max_range', 'tolerance_value', 'tolerance_unit']
    list_filter = ['device_type', 'tolerance_unit']
    search_fields = ['device_type']

admin.site.register(OlcuAleti, OlcuAletiAdmin)
admin.site.register(OlcuAletiTuru, OlcuAletiTuruAdmin)
admin.site.register(KalibrasyonKaydi, KalibrasyonKaydiAdmin)
admin.site.register(CalibrationMeasurement)
admin.site.register(CalibrationTolerance, CalibrationToleranceAdmin)

# CNC Program Admin
class CncProgramRevisionInline(admin.TabularInline):
    model = CncProgramRevision
    extra = 0
    readonly_fields = ['revision_code', 'revision_type', 'created_at', 'created_by', 'is_active', 'file_hash']
    can_delete = False

class CncProgramAdmin(admin.ModelAdmin):
    list_display = ['program_name', 'program_number', 'product', 'machine_type', 'machine_name', 'current_revision', 'status', 'created_at']
    list_filter = ['machine_type', 'status', 'file_format', 'created_at']
    search_fields = ['program_name', 'program_number', 'product__stok_kodu', 'product__ad', 'machine_name']
    readonly_fields = ['program_id', 'current_revision', 'created_at', 'updated_at']
    inlines = [CncProgramRevisionInline]

class CncProgramRevisionAdmin(admin.ModelAdmin):
    list_display = ['program', 'revision_code', 'revision_type', 'is_active', 'created_by', 'created_at']
    list_filter = ['revision_type', 'is_active', 'created_at']
    search_fields = ['program__program_name', 'revision_code', 'revision_note']
    readonly_fields = ['revision_id', 'file_hash', 'created_at']

class CncProgramLogAdmin(admin.ModelAdmin):
    list_display = ['program', 'revision', 'action', 'user', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['program__program_name', 'notes']
    readonly_fields = ['log_id', 'created_at']

admin.site.register(CncProgram, CncProgramAdmin)
admin.site.register(CncProgramRevision, CncProgramRevisionAdmin)
admin.site.register(CncProgramLog, CncProgramLogAdmin)


class CncEkipmanAdmin(admin.ModelAdmin):
    list_display = [
        "ad",
        "ekipman_numarasi",
        "barkod_envanter_no",
        "machine_scope",
        "marka",
        "model_kodu",
        "aktif",
        "sira",
        "updated_at",
    ]
    list_filter = ["machine_scope", "aktif"]
    search_fields = ["ad", "ekipman_numarasi", "barkod_envanter_no", "marka", "model_kodu", "aciklama"]
    ordering = ["machine_scope", "sira", "ad"]


admin.site.register(CncEkipman, CncEkipmanAdmin)


class ArGeRevizyonInline(admin.TabularInline):
    model = ArGeRevizyon
    extra = 0


class ArGeDosyaInline(admin.TabularInline):
    model = ArGeDosya
    extra = 0


@admin.register(ArGeProje)
class ArGeProjeAdmin(admin.ModelAdmin):
    list_display = ['proje_kodu', 'proje_adi', 'stok_item', 'durum', 'oncelik', 'arsivli', 'created_at']
    list_filter = ['durum', 'arsivli', 'oncelik']
    search_fields = ['proje_kodu', 'proje_adi', 'stok_item__stok_kodu']
    inlines = [ArGeRevizyonInline, ArGeDosyaInline]


@admin.register(ArGeRevizyon)
class ArGeRevizyonAdmin(admin.ModelAdmin):
    list_display = ['proje', 'revizyon_no', 'tarih', 'degisiklik_tipi', 'karar']
    list_filter = ['degisiklik_tipi', 'karar']


@admin.register(ArGeDosya)
class ArGeDosyaAdmin(admin.ModelAdmin):
    list_display = ['proje', 'dosya_tipi', 'uploaded_at']
    list_filter = ['dosya_tipi']


@admin.register(TekoraAlert)
class TekoraAlertAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "alert_type",
        "severity",
        "title",
        "is_read",
        "is_resolved",
        "created_at",
    ]
    list_filter = ["severity", "is_read", "is_resolved", "created_at", "alert_type"]
    search_fields = ["title", "message", "alert_type"]
    readonly_fields = ["created_at", "resolved_at"]
    date_hierarchy = "created_at"


@admin.register(TekoraChatLog)
class TekoraChatLogAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "source", "success", "created_at"]
    list_filter = ["success", "source", "created_at"]
    search_fields = ["user_message", "ai_response", "error_message"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(TekoraToolLog)
class TekoraToolLogAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "tool_name", "success", "dangerous", "approval_required", "created_at"]
    list_filter = ["tool_name", "success", "dangerous", "approval_required", "created_at"]
    search_fields = ["tool_name", "error_message"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(TekoraDecisionLog)
class TekoraDecisionLogAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "decision_type", "title", "status", "related_approval", "created_at"]
    list_filter = ["decision_type", "status", "created_at"]
    search_fields = ["title", "description", "decision_type"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(TekoraMemory)
class TekoraMemoryAdmin(admin.ModelAdmin):
    list_display = ["id", "memory_type", "title", "importance", "is_active", "source", "updated_at"]
    list_filter = ["memory_type", "is_active", "created_at"]
    search_fields = ["title", "content", "memory_type", "source"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(TekoraMemoryEmbedding)
class TekoraMemoryEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "memory", "chat_log", "created_at")
    list_filter = ("source_type", "created_at")
    search_fields = ("text", "source_id")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
