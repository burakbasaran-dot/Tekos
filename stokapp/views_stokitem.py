from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_http_methods
import os

from .forms import StokItemForm
from .stok_tamamlanma import stok_tamamlanma_detay_for_item
from .models import (
    StokItem,
    Depo,
    Raf,
    Kategori,
    Tedarikci,
    Birim,
    ParaBirimi,
    GenelAyarlar,
    FiyatGecmisi,
    SiparisKalemi,
    SatinalmaKalemi,
    Recete,
    UretimEmri,
    Complaint,
    EcoChange,
    ControlPlan,
)
from decimal import Decimal

# Models import - modelleri güvenli şekilde import et
try:
    from .models import Recete, ReceteDetay, ReceteOperasyon
except ImportError:
    Recete = None
    ReceteDetay = None
    ReceteOperasyon = None

try:
    from .models import EkDosya
except ImportError:
    EkDosya = None

# ReportLab ve barkod için import
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.graphics import renderPM
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import qrcode
    from io import BytesIO
    import re
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    qrcode = None
    canvas = None
    A4 = None
    mm = None
    ImageReader = None
    pdfmetrics = None
    TTFont = None
    re = None

# Placeholder fonksiyonlar - Eksik fonksiyonlar için geçici çözüm
# Bu fonksiyonlar daha sonra tam implementasyon ile değiştirilebilir

def _post_instance_ile_birlestir(post, instance):
    """
    POST'ta gelmeyen (disabled/readonly) alanları mevcut kayıt değerleriyle doldur.
    Böylece form doğrulaması geçer ve kullanıcının gönderdiği alanlar kaybolmaz.
    """
    if not instance or not instance.pk:
        return post

    merged = post.copy()

    fk_alanlar = {
        'kategori': instance.kategori_id,
        'tedarikci': instance.tedarikci_id,
        'depo': instance.depo_id,
        'raf': instance.raf_id,
    }
    for alan, deger in fk_alanlar.items():
        if alan not in merged and deger:
            merged[alan] = str(deger)

    skaler_alanlar = (
        'stok_kodu', 'ad', 'barkod', 'aciklama',
        'urun_rolu', 'urun_tipi', 'stok_tipi',
        'alis_fiyati', 'satis_fiyati', 'uretim_maliyeti',
        'minimum_stok', 'maximum_stok', 'guvenlik_stoku', 'acilis_miktari',
        'alis_para_birimi', 'satis_para_birimi',
        'urun_agirligi', 'urun_agirlik_birimi', 'arsivli',
    )
    for alan in skaler_alanlar:
        if alan not in merged:
            deger = getattr(instance, alan, None)
            if deger is not None and deger != '':
                merged[alan] = str(deger)

    # POST'ta boş gönderilen sayısal alanları mevcut kayıt değeriyle doldur
    bos_ise_instance_kullan = (
        'alis_fiyati', 'satis_fiyati', 'uretim_maliyeti',
        'minimum_stok', 'maximum_stok', 'guvenlik_stoku', 'acilis_miktari',
    )
    for alan in bos_ise_instance_kullan:
        if (merged.get(alan) or '').strip() == '':
            deger = getattr(instance, alan, None)
            if deger is not None:
                merged[alan] = str(deger)

    if 'birim' not in merged and instance.birim:
        birim_obj = Birim.objects.filter(ad=instance.birim).first()
        if birim_obj:
            merged['birim'] = str(birim_obj.pk)

    if 'stok_takip' not in merged:
        merged['stok_takip'] = 'True' if instance.stok_takip else 'False'

    return merged


def _uygula_ham_post_alanlari(stok, ham_post):
    """Kullanıcının doğrudan gönderdiği alanları forma güvenilir şekilde uygula."""
    if 'barkod' in ham_post:
        stok.barkod = (ham_post.get('barkod') or '').strip()
    if 'aciklama' in ham_post:
        stok.aciklama = (ham_post.get('aciklama') or '').strip()
    if 'depo' in ham_post:
        depo_val = (ham_post.get('depo') or '').strip()
        stok.depo_id = int(depo_val) if depo_val.isdigit() else None
    if 'raf' in ham_post:
        raf_val = (ham_post.get('raf') or '').strip()
        stok.raf_id = int(raf_val) if raf_val.isdigit() else None
    if 'tedarikci' in ham_post:
        ted_val = (ham_post.get('tedarikci') or '').strip()
        stok.tedarikci_id = int(ted_val) if ted_val.isdigit() else None
    if 'urun_agirligi' in ham_post:
        agirlik_val = (ham_post.get('urun_agirligi') or '').strip()
        if agirlik_val:
            try:
                stok.urun_agirligi = Decimal(agirlik_val.replace(',', '.'))
            except Exception:
                pass
        else:
            stok.urun_agirligi = None
    if 'urun_agirlik_birimi' in ham_post:
        stok.urun_agirlik_birimi = (ham_post.get('urun_agirlik_birimi') or '').strip() or 'kg'


def _stok_uretim_maliyetleri(stok):
    """Aktif reçeteden üretim maliyeti bileşenlerini hesaplar."""
    ham_madde_maliyeti = Decimal('0')
    operasyonel_maliyetler = Decimal('0')
    toplam_uretim_maliyeti = Decimal('0')
    para_birimi = 'TL'
    para_sembol = '₺'

    if stok is None or Recete is None:
        return {
            'ham_madde_maliyeti': ham_madde_maliyeti,
            'operasyonel_maliyetler': operasyonel_maliyetler,
            'operasyonel_maliyetler_toplami': operasyonel_maliyetler,
            'toplam_uretim_maliyeti': toplam_uretim_maliyeti,
            'para_birimi': para_birimi,
            'para_sembol': para_sembol,
        }

    aktif_recete = Recete.objects.filter(urun=stok, aktif=True).first()
    if aktif_recete:
        if ReceteDetay is not None:
            detaylar = ReceteDetay.objects.filter(recete=aktif_recete).select_related('stok_item')
            for detay in detaylar:
                birim_fiyat = detay.stok_item.alis_fiyati or Decimal('0')
                ham_madde_maliyeti += detay.miktar * birim_fiyat
                if para_birimi == 'TL' and detay.stok_item.alis_para_birimi:
                    para_birimi = detay.stok_item.alis_para_birimi or 'TL'
                    para_sembol = {
                        'TL': '₺', 'USD': '$', 'EUR': '€', 'GBP': '£',
                    }.get(para_birimi, para_birimi)

        if ReceteOperasyon is not None:
            for op in ReceteOperasyon.objects.filter(recete=aktif_recete):
                operasyonel_maliyetler += op.toplam_maliyet or Decimal('0')

        toplam_uretim_maliyeti = ham_madde_maliyeti + operasyonel_maliyetler

    return {
        'ham_madde_maliyeti': ham_madde_maliyeti,
        'operasyonel_maliyetler': operasyonel_maliyetler,
        'operasyonel_maliyetler_toplami': operasyonel_maliyetler,
        'toplam_uretim_maliyeti': toplam_uretim_maliyeti,
        'para_birimi': para_birimi,
        'para_sembol': para_sembol,
    }


def _kaydet_ek_dosyalar(request, stok):
    """Form gönderiminde yüklenen 'ek_dosyalar' dosyalarını EkDosya olarak kaydeder."""
    if EkDosya is None or stok is None:
        return
    dosyalar = request.FILES.getlist('ek_dosyalar')
    for dosya in dosyalar:
        if not dosya:
            continue
        EkDosya.objects.create(stok=stok, dosya=dosya, ad=dosya.name)
    if dosyalar:
        messages.success(request, f'{len(dosyalar)} ek dosya yüklendi.')


@login_required
def stok_ekle(request, pk=None):
    """Stok ekle/düzenle - Detay görüntüleme ve düzenleme"""
    from django.shortcuts import render, get_object_or_404, redirect
    
    stok = None
    form = None
    is_readonly = False
    
    # Eğer pk varsa, mevcut stok detayını göster/düzenle
    if pk:
        stok = get_object_or_404(StokItem, pk=pk)
        
        if request.method == 'POST':
            # POST isteği - form kaydetme
            ham_post = request.POST
            post_data = _post_instance_ile_birlestir(ham_post, stok)
            form = StokItemForm(post_data, request.FILES, instance=stok)
            form._ham_post_anahtarlari = frozenset(ham_post.keys())
            if form.is_valid():
                stok = form.save(commit=False)
                _uygula_ham_post_alanlari(stok, ham_post)
                
                # Açılış miktarı girilmişse veya değiştirilmişse, mevcut miktarı açılış miktarına eşitle
                # Bu, açılış miktarının stokun başlangıç miktarı olması gerektiği mantığıyla yapılıyor
                yeni_acilis_miktari = stok.acilis_miktari
                if yeni_acilis_miktari is not None and yeni_acilis_miktari > 0:
                    # Açılış miktarı girilmişse, mevcut miktarı buna eşitle
                    stok.mevcut_miktar = yeni_acilis_miktari
                    messages.info(request, f'Açılış miktarı: {yeni_acilis_miktari}. Mevcut miktar açılış miktarına eşitlendi.')
                
                stok.save()
                _kaydet_ek_dosyalar(request, stok)
                messages.success(request, f'Stok "{stok.stok_kodu}" başarıyla güncellendi.')
                return redirect('stokapp:stok_ekle', pk=pk)
            else:
                is_readonly = False
                hatalar = []
                for alan, errs in form.errors.items():
                    hatalar.append(f'{alan}: {", ".join(errs)}')
                if hatalar:
                    messages.error(request, 'Form hatalarını düzeltin: ' + '; '.join(hatalar[:5]))
                else:
                    messages.error(request, 'Form hatalarını düzeltin.')
        else:
            # GET isteği - form görüntüleme (başlangıçta readonly)
            # Eğer açılış miktarı var ama mevcut miktar 0 ise, mevcut miktarı açılış miktarına eşitle
            # Bu, mevcut kayıtlar için açılış miktarının mevcut miktara eşitlenmesini sağlar
            if stok.acilis_miktari is not None and stok.acilis_miktari > 0:
                if stok.mevcut_miktar is None or stok.mevcut_miktar == 0:
                    stok.mevcut_miktar = stok.acilis_miktari
                    stok.save(update_fields=['mevcut_miktar'])
                    messages.info(request, f'Açılış miktarı ({stok.acilis_miktari}) tespit edildi. Mevcut miktar güncellendi.')
            
            form = StokItemForm(instance=stok)
            is_readonly = True  # Başlangıçta readonly modu
            # Form alanlarını başlangıçta readonly yap (JavaScript ile düzenlenebilir hale getirilebilir)
            for field_name in form.fields:
                # Alış fiyat alanını readonly yapma - her zaman düzenlenebilir olmalı
                if field_name != 'alis_fiyati':
                    form.fields[field_name].widget.attrs['readonly'] = True
    else:
        # Yeni stok ekleme
        if request.method == 'POST':
            form = StokItemForm(request.POST, request.FILES)
            if form.is_valid():
                stok = form.save(commit=False)
                
                # Açılış miktarı girilmişse, mevcut miktarı açılış miktarına eşitle
                if stok.acilis_miktari is not None and stok.acilis_miktari > 0:
                    stok.mevcut_miktar = stok.acilis_miktari
                    messages.info(request, f'Açılış miktarı girildi. Mevcut miktar açılış miktarına ({stok.acilis_miktari}) eşitlendi.')
                
                stok.save()
                _kaydet_ek_dosyalar(request, stok)
                messages.success(request, f'Stok "{stok.stok_kodu}" başarıyla oluşturuldu.')
                return redirect('stokapp:stok_ekle', pk=stok.pk)
            else:
                messages.error(request, 'Form hatalarını düzeltin.')
        else:
            form = StokItemForm()
    
    # Template için gerekli verileri hazırla
    # Birim, Kategori ve Tedarikci modellerinde 'aktif' alanı yok, tüm kayıtları al
    birimler = Birim.objects.all().order_by('ad')
    kategoriler = Kategori.objects.all().order_by('ad')
    tedarikciler = Tedarikci.objects.all().order_by('ad')
    # ParaBirimi modelinde 'aktif' alanı var
    para_birimleri = ParaBirimi.objects.filter(aktif=True).order_by('kod')
    depolar = Depo.objects.all().order_by('ad')
    raflar = Raf.objects.none()
    depo_id = None
    if request.method == 'POST' and request.POST.get('depo'):
        try:
            depo_id = int(request.POST.get('depo'))
        except (ValueError, TypeError):
            pass
    if depo_id is None and stok and stok.depo_id:
        depo_id = stok.depo_id
    if depo_id:
        raflar = Raf.objects.filter(depo_id=depo_id).order_by('ad')
    firma_ismi = "Tekmar"
    try:
        ayarlar = GenelAyarlar.get_ayarlar()
        firma_ismi = (ayarlar.firma_ismi or "").strip() or firma_ismi
    except Exception:
        pass
    
    # Ek dosyalar (mevcut yüklenmiş dosyalar)
    ek_dosyalar = []
    if stok and EkDosya is not None:
        ek_dosyalar = stok.ek_dosyalar.all().order_by('-uploaded_at')

    # Fiyat geçmişi (sadece detay görüntüleme modunda)
    fiyat_gecmisi = None
    kullanildigi_urunler = []
    urun_recetesi = None
    if stok:
        fiyat_gecmisi = FiyatGecmisi.objects.filter(
            stok_item=stok,
            degisen_alan='alis_fiyati'
        ).order_by('-tarih')[:50]  # Son 50 kayıt
        
        # Fiyat değişimini hesapla (template için)
        for gecmis in fiyat_gecmisi:
            if gecmis.eski_alis_fiyati is not None and gecmis.yeni_alis_fiyati is not None:
                gecmis.fiyat_farki = gecmis.yeni_alis_fiyati - gecmis.eski_alis_fiyati
            else:
                gecmis.fiyat_farki = None

        # Bu stok kaleminin kullanıldığı ürün reçeteleri
        if ReceteDetay is not None:
            kullanildigi_urunler = (
                ReceteDetay.objects.filter(stok_item=stok)
                .select_related('recete__urun')
                .order_by('recete__urun__stok_kodu', 'recete__versiyon', 'sira')
            )
        if Recete is not None:
            urun_recetesi = (
                Recete.objects.filter(urun=stok)
                .order_by('-aktif', '-created_at', '-id')
                .first()
            )
    
    tamamlanma_durum = None
    tamamlanma_eksik_liste = []
    if stok:
        tamamlanma_durum, tamamlanma_eksik_liste = stok_tamamlanma_detay_for_item(stok)

    maliyet_ctx = _stok_uretim_maliyetleri(stok)

    context = {
        'stok': stok,
        'form': form,
        'tamamlanma_durum': tamamlanma_durum,
        'tamamlanma_eksik_liste': tamamlanma_eksik_liste,
        'birimler': birimler,
        'kategoriler': kategoriler,
        'tedarikciler': tedarikciler,
        'para_birimleri': para_birimleri,
        'depolar': depolar,
        'raflar': raflar,
        'firma_ismi': firma_ismi,
        'fiyat_gecmisi': fiyat_gecmisi,
        'kullanildigi_urunler': kullanildigi_urunler,
        'urun_recetesi': urun_recetesi,
        'ek_dosyalar': ek_dosyalar,
        'is_edit': stok is not None,  # Template'te düzenleme modunu kontrol etmek için
        'is_readonly': is_readonly,  # Template'te readonly modunu kontrol etmek için
        **maliyet_ctx,
    }
    
    return render(request, 'stokapp/stok_ekle.html', context)

def _collect_stok_sil_engelleri(stok):
    """StokItem silinmesini DB düzeyinde engelleyecek PROTECT / üretim emri bağlarını listeler."""
    engeller = []

    sk = SiparisKalemi.objects.filter(stok_item=stok).select_related('siparis')
    n = sk.count()
    if n:
        engeller.append(
            {
                'tip': 'Sipariş Kalemleri',
                'sayi': n,
                'kayitlar': list(sk[:10]),
                'uretim_emirleri': None,
            }
        )

    sa = SatinalmaKalemi.objects.filter(stok_item=stok).select_related('satinalma')
    n = sa.count()
    if n:
        engeller.append(
            {
                'tip': 'Satın Alma Kalemleri',
                'sayi': n,
                'kayitlar': list(sa[:10]),
                'uretim_emirleri': None,
            }
        )

    cmp_qs = Complaint.objects.filter(product=stok).select_related('customer')
    n = cmp_qs.count()
    if n:
        engeller.append(
            {
                'tip': 'Şikayet / Uygunsuzluk',
                'sayi': n,
                'kayitlar': list(cmp_qs[:10]),
                'uretim_emirleri': None,
            }
        )

    eco_qs = EcoChange.objects.filter(product=stok)
    n = eco_qs.count()
    if n:
        engeller.append(
            {
                'tip': 'ECO (Mühendislik Değişikliği)',
                'sayi': n,
                'kayitlar': list(eco_qs[:10]),
                'uretim_emirleri': None,
            }
        )

    cp_qs = ControlPlan.objects.filter(product=stok)
    n = cp_qs.count()
    if n:
        engeller.append(
            {
                'tip': 'Kontrol Planı',
                'sayi': n,
                'kayitlar': list(cp_qs[:10]),
                'uretim_emirleri': None,
            }
        )

    receteler = Recete.objects.filter(urun=stok)
    emirler = UretimEmri.objects.filter(recete__in=receteler).select_related('recete__urun')
    if emirler.exists():
        engeller.append(
            {
                'tip': 'Reçete/Üretim Emri',
                'sayi': receteler.count(),
                'kayitlar': list(receteler[:10]),
                'uretim_emirleri': list(emirler[:15]),
            }
        )

    return engeller


@login_required
def stok_duzenle(request, pk):
    """Stok düzenle - Placeholder"""
    messages.error(request, 'Stok düzenle fonksiyonu henüz implement edilmedi.')
    return redirect('stokapp:stok_listesi')

@login_required
def stok_sil(request, pk):
    stok = get_object_or_404(StokItem, pk=pk)

    if request.method == 'POST':
        engeller = _collect_stok_sil_engelleri(stok)
        if engeller:
            messages.error(request, 'Bu stok bağlı kayıtlar nedeniyle silinemiyor.')
            return render(
                request,
                'stokapp/stok_sil.html',
                {'stok': stok, 'engeller': engeller},
            )
        kod = stok.stok_kodu
        try:
            with transaction.atomic():
                stok.delete()
        except ProtectedError:
            messages.error(
                request,
                'Bu stok veritabanında başka bağlı kayıtlar nedeniyle silinemedi.',
            )
            stok = get_object_or_404(StokItem, pk=pk)
            engeller = _collect_stok_sil_engelleri(stok)
            return render(
                request,
                'stokapp/stok_sil.html',
                {'stok': stok, 'engeller': engeller},
            )
        messages.success(request, f'"{kod}" stoku silindi.')
        return redirect('stokapp:stok_listesi')

    engeller = _collect_stok_sil_engelleri(stok)
    return render(request, 'stokapp/stok_sil.html', {'stok': stok, 'engeller': engeller})


@login_required
@require_http_methods(['POST'])
def stok_ek_dosya_sil(request, pk, dosya_id):
    """Stok ek dosyasını sil."""
    stok = get_object_or_404(StokItem, pk=pk)
    if EkDosya is None:
        messages.error(request, 'Ek dosya modeli bulunamadı.')
        return redirect('stokapp:stok_ekle', pk=pk)
    dosya = get_object_or_404(EkDosya, pk=dosya_id, stok=stok)
    ad = dosya.ad or (dosya.dosya.name.split('/')[-1] if dosya.dosya else 'Dosya')
    try:
        dosya.dosya.delete(save=False)
    except Exception:
        pass
    dosya.delete()
    messages.success(request, f'"{ad}" ek dosyası silindi.')
    return redirect('stokapp:stok_ekle', pk=pk)


@login_required
@require_http_methods(['POST'])
def stok_toplu_sil(request):
    raw_ids = request.POST.getlist('stok_ids')
    if not raw_ids:
        messages.warning(request, 'Silmek için en az bir stok seçmelisiniz.')
        return redirect('stokapp:stok_listesi')

    ids = []
    for x in raw_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids:
        messages.error(request, 'Geçersiz stok seçimi.')
        return redirect('stokapp:stok_listesi')

    silinen = []
    engelli_kodlar = []

    for pk in ids:
        stok = StokItem.objects.filter(pk=pk).first()
        if not stok:
            continue
        engeller = _collect_stok_sil_engelleri(stok)
        if engeller:
            engelli_kodlar.append(stok.stok_kodu)
            continue
        kod = stok.stok_kodu
        try:
            with transaction.atomic():
                stok.delete()
        except ProtectedError:
            engelli_kodlar.append(kod)
            continue
        silinen.append(kod)

    if silinen:
        ozet = ', '.join(silinen[:15])
        if len(silinen) > 15:
            ozet += ' …'
        messages.success(request, f'{len(silinen)} stok silindi: {ozet}')
    if engelli_kodlar:
        ozet = ', '.join(engelli_kodlar[:10])
        if len(engelli_kodlar) > 10:
            ozet += ' …'
        messages.error(
            request,
            f'{len(engelli_kodlar)} stok silinemedi (sipariş, satın alma, üretim emri veya kalite kaydı bağlı olabilir): {ozet}',
        )

    return redirect('stokapp:stok_listesi')

@login_required
def stok_qrcode(request, pk):
    """Stok QR kodu oluştur - Placeholder"""
    if qrcode is None:
        return HttpResponse('QR code library not available', content_type='text/plain')
    try:
        stok = get_object_or_404(StokItem, pk=pk)
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(stok.barkod if stok.barkod else stok.stok_kodu)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        response = HttpResponse(content_type='image/png')
        img.save(response, 'PNG')
        return response
    except:
        return HttpResponse('QR code generation failed', content_type='text/plain')

@login_required
def stok_kopyala(request, pk):
    """Stok kopyala - Kopya_ öneki ile yeni stok oluştur"""
    from django.shortcuts import get_object_or_404
    
    if request.method != 'POST':
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:stok_listesi')
    
    try:
        orijinal_stok = get_object_or_404(StokItem, pk=pk)
        
        # Yeni stok kodu oluştur - "Kopya_" öneki ekle
        yeni_stok_kodu = f"Kopya_{orijinal_stok.stok_kodu}"
        
        # Aynı kod varsa numara ekle
        sayac = 1
        while StokItem.objects.filter(stok_kodu=yeni_stok_kodu).exists():
            yeni_stok_kodu = f"Kopya_{orijinal_stok.stok_kodu}_{sayac}"
            sayac += 1
        
        # Yeni stok kaydı oluştur - tüm alanları kopyala
        yeni_stok = StokItem(
            stok_kodu=yeni_stok_kodu,
            ad=orijinal_stok.ad,
            aciklama=orijinal_stok.aciklama,
            kategori=orijinal_stok.kategori,
            tedarikci=orijinal_stok.tedarikci,
            birim=orijinal_stok.birim,
            barkod='',  # Barkod benzersiz olmalı, boş bırak
            alis_fiyati=orijinal_stok.alis_fiyati,
            alis_para_birimi=orijinal_stok.alis_para_birimi,
            mevcut_miktar=0,  # Kopyada miktar 0 olmalı
            minimum_stok=orijinal_stok.minimum_stok,
            maximum_stok=orijinal_stok.maximum_stok,
            guvenlik_stoku=orijinal_stok.guvenlik_stoku,
            uretim_suresi=orijinal_stok.uretim_suresi,
            uretim_maliyeti=orijinal_stok.uretim_maliyeti,
            satin_alma_fiyati=orijinal_stok.satin_alma_fiyati,
            satis_fiyati=orijinal_stok.satis_fiyati,
            satis_para_birimi=orijinal_stok.satis_para_birimi,
            acilis_miktari=0,  # Kopyada açılış miktarı 0
            stok_takip=orijinal_stok.stok_takip,
            depo=orijinal_stok.depo,
            raf=orijinal_stok.raf,
            urun_tipi=orijinal_stok.urun_tipi,
            urun_rolu=orijinal_stok.urun_rolu,
            tedarikci_kodu=orijinal_stok.tedarikci_kodu,
            stok_tipi=orijinal_stok.stok_tipi,
            arsivli=False,  # Kopya arşivlenmiş olmamalı
            # Fotoğraf ve teknik resim kopyalanmaz (dosya referansları)
        )
        yeni_stok.save()
        
        messages.success(request, f'Stok "{orijinal_stok.stok_kodu}" başarıyla kopyalandı. Yeni stok kodu: "{yeni_stok_kodu}"')
        return redirect('stokapp:stok_ekle', pk=yeni_stok.pk)
        
    except Exception as e:
        messages.error(request, f'Kopyalama sırasında hata oluştu: {str(e)}')
        return redirect('stokapp:stok_listesi')

@login_required
def stok_recete_maliyetleri(request, pk):
    """Stok reçete maliyetleri - Placeholder"""
    return JsonResponse({'error': 'Fonksiyon henüz implement edilmedi.'}, status=404)

# Etiket yazdırma fonksiyonu
@login_required
def stok_etiket_yazdir(request):
    """Seçili stoklar için A4 etiket PDF'i oluştur"""
    if not REPORTLAB_AVAILABLE:
        messages.error(request, 'PDF oluşturma için ReportLab kütüphanesi gerekli.')
        return redirect('stokapp:stok_listesi')
    
    if request.method != 'POST':
        return redirect('stokapp:stok_listesi')
    
    # Seçili stok ID'leri
    stok_ids_str = request.POST.get('stok_ids', '')
    if not stok_ids_str:
        messages.error(request, 'Etiket yazdırmak için en az bir stok seçmelisiniz.')
        return redirect('stokapp:stok_listesi')
    
    stok_ids = [int(id) for id in stok_ids_str.split(',') if id.strip()]
    if not stok_ids:
        messages.error(request, 'Geçerli stok seçilmedi.')
        return redirect('stokapp:stok_listesi')
    
    # Başlangıç pozisyonu
    try:
        baslangic_satir = int(request.POST.get('baslangic_satir', 1))
        baslangic_sutun = int(request.POST.get('baslangic_sutun', 1))
    except ValueError:
        baslangic_satir = 1
        baslangic_sutun = 1
    
    # Geçerli aralık kontrolü
    if not (1 <= baslangic_satir <= 7) or not (1 <= baslangic_sutun <= 2):
        messages.error(request, 'Geçersiz başlangıç pozisyonu.')
        return redirect('stokapp:stok_listesi')
    
    # Stokları getir
    stoklar = StokItem.objects.filter(id__in=stok_ids)
    
    # PDF oluştur
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="stok_etiketleri.pdf"'
    
    # A4 boyutları (mm cinsinden)
    A4_WIDTH_MM = 210 * mm
    A4_HEIGHT_MM = 297 * mm
    
    # Etiket boyutları ve boşluklar (mm)
    SOL_KENAR_BOSLUK = 5 * mm
    UST_KENAR_BOSLUK = 16 * mm
    ETIKET_GENISLIK = 99.1 * mm
    ETIKET_YUKSEKLIK = 38.1 * mm
    SUTUN_ARASI_BOSLUK = 3 * mm
    KULLANILACAK_GENISLIK = 70 * mm  # Ortadan 70mm
    
    # Canvas oluştur
    p = canvas.Canvas(response, pagesize=(A4_WIDTH_MM, A4_HEIGHT_MM))
    
    stok_index = 0
    for satir in range(1, 8):  # 7 satır
        for sutun in range(1, 3):  # 2 sütun
            # Başlangıç pozisyonundan önceki pozisyonları atla
            if satir < baslangic_satir or (satir == baslangic_satir and sutun < baslangic_sutun):
                continue
            
            # Tüm stoklar yazdırıldıysa dur
            if stok_index >= len(stoklar):
                break
            
            stok = stoklar[stok_index]
            
            # Etiket pozisyonu hesapla
            x = SOL_KENAR_BOSLUK + (sutun - 1) * (ETIKET_GENISLIK + SUTUN_ARASI_BOSLUK)
            y_ust = A4_HEIGHT_MM - (UST_KENAR_BOSLUK + (satir - 1) * ETIKET_YUKSEKLIK)
            y_alt = y_ust - ETIKET_YUKSEKLIK
            y_orta = y_ust - (ETIKET_YUKSEKLIK / 2)  # Etiketin dikey ortası
            
            # Etiket içeriği için merkez pozisyonu (70mm genişlik)
            etiket_merkez_x = x + (ETIKET_GENISLIK - KULLANILACAK_GENISLIK) / 2
            icerik_x = etiket_merkez_x
            
            # Etiket 1/3 sol, 2/3 sağ olarak bölünecek
            sol_alan_genislik = KULLANILACAK_GENISLIK / 3  # 1/3 sol taraf
            sag_alan_genislik = KULLANILACAK_GENISLIK * 2 / 3  # 2/3 sağ taraf
            orta_bosluk = 2 * mm  # Sol ve sağ arası küçük boşluk
            
            # Sol tarafta karekod (1/3 alan, dikey ve yatay ortalanmış)
            qr_alan_genislik = sol_alan_genislik - orta_bosluk
            # QR kod boyutunu sol alanın %90'ı ve etiket yüksekliğinin %85'i arasından küçük olanı seç
            qr_boyut = min(qr_alan_genislik * 0.9, ETIKET_YUKSEKLIK * 0.85)
            # Sol alan içinde yatay ortalanmış
            qr_x = icerik_x + (sol_alan_genislik - qr_boyut) / 2
            # Etiket yüksekliğinin tam ortasında (dikey eksende tam ortalanmış)
            qr_y = y_orta - (qr_boyut / 2)
            
            # Karekod oluştur (barkod varsa onu kullan, yoksa stok_kodu)
            barkod_veri = stok.barkod if stok.barkod else stok.stok_kodu
            try:
                qr = qrcode.QRCode(version=1, box_size=10, border=2)
                qr.add_data(barkod_veri)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                
                # QR kodunu BytesIO'ya kaydet
                qr_buffer = BytesIO()
                qr_img.save(qr_buffer, format='PNG')
                qr_buffer.seek(0)
                
                # PDF'e ekle
                p.drawImage(ImageReader(qr_buffer), qr_x, qr_y, 
                          width=qr_boyut, height=qr_boyut, 
                          preserveAspectRatio=True)
            except:
                pass
            
            # Sağ tarafta metin bilgileri (2/3 alan, dikey ortalanmış)
            metin_alan_genislik = sag_alan_genislik - orta_bosluk
            metin_alan_x = icerik_x + sol_alan_genislik + orta_bosluk
            
            # Metin içerikleri
            stok_kodu = str(stok.stok_kodu)[:30]
            ad = str(stok.ad)[:35]
            kategori = str(stok.kategori.ad if stok.kategori else '')[:30]
            min_max_text = f"Min: {stok.minimum_stok}  Max: {stok.maximum_stok if stok.maximum_stok else 'N/A'}"
            
            # Font boyutları ve satır yükseklikleri
            font_boyut_kod = 9
            font_boyut_ad = 8
            font_boyut_diger = 7
            satir_yukseklik = 5.5 * mm
            
            # Metinleri çiz, uzun metinleri alt satıra kaydır
            def drawTextWrapped(text, font_name, font_size, x, y, max_width_mm_value, line_height_mm):
                """Metni maksimum genişlik içinde çiz, gerekirse alt satıra kaydır (Türkçe karakter desteği ile)"""
                p.setFont(font_name, font_size)
                text_str = str(text)
                # max_width_mm_value zaten mm cinsinden bir değer, ReportLab point'e çevir
                # 1 mm ≈ 2.83465 points (72 points/inch, 25.4 mm/inch)
                max_width_points = float(max_width_mm_value) / mm * 72.0 / 25.4
                
                # Satır yüksekliğini point'e çevir
                line_height_points = float(line_height_mm) / mm * 72.0 / 25.4
                
                # Metni kelimelere böl (Türkçe karakterleri koru)
                # Boşluk, tire, virgül, nokta gibi karakterlerde bölebiliriz
                words = re.split(r'(\s+|[-,.])', text_str)
                words = [w for w in words if w]  # Boş stringleri kaldır
                
                lines = []
                current_line = ""
                
                for word in words:
                    # Test satırı oluştur
                    test_line = current_line + word if current_line else word
                    test_width = p.stringWidth(test_line, font_name, font_size)
                    
                    if test_width <= max_width_points or not current_line:
                        # Kelime sığıyor veya ilk kelimeyse, ekle
                        current_line = test_line
                    else:
                        # Kelime sığmıyor, önceki satırı kaydet ve yeni satıra başla
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                # Son satırı ekle
                if current_line:
                    lines.append(current_line)
                
                # Eğer hala tek satırda sığmıyorsa, karakter karakter kır
                if len(lines) == 1 and p.stringWidth(lines[0], font_name, font_size) > max_width_points:
                    lines = []
                    current_line = ""
                    for char in text_str:
                        test_line = current_line + char
                        if p.stringWidth(test_line, font_name, font_size) > max_width_points:
                            if current_line:
                                lines.append(current_line)
                            current_line = char
                        else:
                            current_line = test_line
                    if current_line:
                        lines.append(current_line)
                
                # Satırları çiz
                current_y = y
                for line in lines:
                    p.drawString(x, current_y, line)
                    current_y -= line_height_points
                
                # Kullanılan toplam yüksekliği döndür (mm cinsinden)
                return len(lines) * line_height_points * mm / (72.0 / 25.4)
            
            # Önce tüm metinlerin yüksekliklerini ölç (dikey ortalama için)
            def measureTextWrapped(text, font_name, font_size, max_width_mm_value, line_height_mm):
                """Metnin kaç satır süreceğini ölç (çizmeden)"""
                p.setFont(font_name, font_size)
                text_str = str(text)
                max_width_points = float(max_width_mm_value) / mm * 72.0 / 25.4
                
                words = re.split(r'(\s+|[-,.])', text_str)
                words = [w for w in words if w]
                
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = current_line + word if current_line else word
                    test_width = p.stringWidth(test_line, font_name, font_size)
                    
                    if test_width <= max_width_points or not current_line:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
                
                # Eğer hala tek satırda sığmıyorsa, karakter karakter kır
                if len(lines) == 1 and p.stringWidth(lines[0], font_name, font_size) > max_width_points:
                    lines = []
                    current_line = ""
                    for char in text_str:
                        test_line = current_line + char
                        if p.stringWidth(test_line, font_name, font_size) > max_width_points:
                            if current_line:
                                lines.append(current_line)
                            current_line = char
                        else:
                            current_line = test_line
                    if current_line:
                        lines.append(current_line)
                
                line_height_points = float(line_height_mm) / mm * 72.0 / 25.4
                return len(lines) * line_height_points * mm / (72.0 / 25.4)
            
            satir_yukseklik_mm = satir_yukseklik / mm
            
            # Tüm metinlerin toplam yüksekliğini hesapla
            stok_kodu_yukseklik = measureTextWrapped(stok_kodu, "Helvetica-Bold", font_boyut_kod, metin_alan_genislik, satir_yukseklik_mm)
            stok_adi_yukseklik = measureTextWrapped(ad, "Helvetica", font_boyut_ad, metin_alan_genislik, satir_yukseklik_mm)
            kategori_yukseklik = measureTextWrapped(kategori, "Helvetica", font_boyut_diger, metin_alan_genislik, satir_yukseklik_mm)
            min_max_yukseklik = measureTextWrapped(min_max_text, "Helvetica", font_boyut_diger, metin_alan_genislik, satir_yukseklik_mm)
            
            toplam_metin_yukseklik = stok_kodu_yukseklik + satir_yukseklik + \
                                    stok_adi_yukseklik + satir_yukseklik + \
                                    kategori_yukseklik + satir_yukseklik + \
                                    min_max_yukseklik
            
            # Metinleri dikey olarak ortalama (y_orta'dan başlayarak yukarı ve aşağı dağıt)
            metin_baslangic_y = y_orta + (toplam_metin_yukseklik / 2)
            
            # Stok Kodu (kalın, sol hizalı)
            drawTextWrapped(stok_kodu, "Helvetica-Bold", font_boyut_kod, metin_alan_x, metin_baslangic_y, metin_alan_genislik, satir_yukseklik_mm)
            metin_baslangic_y -= (stok_kodu_yukseklik + satir_yukseklik)
            
            # Stok Adı (sol hizalı)
            drawTextWrapped(ad, "Helvetica", font_boyut_ad, metin_alan_x, metin_baslangic_y, metin_alan_genislik, satir_yukseklik_mm)
            metin_baslangic_y -= (stok_adi_yukseklik + satir_yukseklik)
            
            # Kategori (sol hizalı)
            drawTextWrapped(kategori, "Helvetica", font_boyut_diger, metin_alan_x, metin_baslangic_y, metin_alan_genislik, satir_yukseklik_mm)
            metin_baslangic_y -= (kategori_yukseklik + satir_yukseklik)
            
            # Min ve Max Stok (sol hizalı)
            drawTextWrapped(min_max_text, "Helvetica", font_boyut_diger, metin_alan_x, metin_baslangic_y, metin_alan_genislik, satir_yukseklik_mm)
            
            stok_index += 1
        
        if stok_index >= len(stoklar):
            break
    
    p.showPage()
    p.save()
    
    return response
