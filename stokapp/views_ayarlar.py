from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.core.mail import EmailMultiAlternatives
from datetime import timedelta, datetime
import os
import json
import zipfile
import shutil
import tempfile
from pathlib import Path
from .models import GenelAyarlar, HataLog, YazdirmaSablonu, GelistirmeTalebi
from .forms import GenelAyarlarForm, GelistirmeTalepForm
from .nav_visibility import NAV_KEY_AYARLAR_GELISTIRME, hidden_nav_access_required

_gelistirme_nav_guard = hidden_nav_access_required(NAV_KEY_AYARLAR_GELISTIRME)

@login_required
def genel_ayarlar(request):
    """Genel ayarlar sayfası"""
    from .mail_config import apply_mail_settings

    ayarlar = GenelAyarlar.get_ayarlar()
    apply_mail_settings(ayarlar)
    
    if request.method == 'POST':
        form = GenelAyarlarForm(request.POST, request.FILES, instance=ayarlar)
        if form.is_valid():
            try:
                ayarlar = form.save()
                apply_mail_settings(ayarlar)
                messages.success(request, 'Ayarlar başarıyla kaydedildi.')
                return redirect('stokapp:genel_ayarlar')
            except Exception as e:
                messages.error(request, f'Ayarlar kaydedilirken hata oluştu: {str(e)}')
        else:
            messages.error(request, 'Lütfen form hatalarını düzeltin.')
    else:
        form = GenelAyarlarForm(instance=ayarlar)
    
    context = {
        'form': form,
        'ayarlar': ayarlar,
    }
    return render(request, 'stokapp/genel_ayarlar.html', context)


@login_required
def genel_ayarlar_cc_test_mail(request):
    """Genel ayarlardaki CC adresi için test maili gönderir."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek.'}, status=405)

    kind = (request.POST.get('kind') or '').strip()
    raw_email = (request.POST.get('email') or '').strip()
    if kind not in ('musteri', 'satinalma'):
        return JsonResponse({'success': False, 'error': 'Geçersiz test türü.'}, status=400)

    if kind == 'musteri':
        fallback = GenelAyarlar.get_musteri_mail_cc_adresi()
        subject = 'Test Maili — Müşteri Gönderimleri CC'
        body = (
            'Bu bir test e-postasıdır.\n\n'
            'Ayarlar > Genel Ayarlar > Müşteri Gönderimleri CC alanı test edilmiştir.'
        )
    else:
        fallback = GenelAyarlar.get_satinalma_mail_cc_adresi()
        subject = 'Test Maili — Satınalma Gönderimleri CC'
        body = (
            'Bu bir test e-postasıdır.\n\n'
            'Ayarlar > Genel Ayarlar > Satınalma Gönderimleri CC alanı test edilmiştir.'
        )

    email = raw_email or fallback
    if not email:
        return JsonResponse({'success': False, 'error': 'Test için bir e-posta adresi gerekli.'}, status=400)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or None
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[email],
        )
        msg.send(fail_silently=False)
        return JsonResponse({'success': True, 'message': f'Test maili gönderildi: {email}'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def genel_ayarlar_smtp_test_mail(request):
    """Genel ayarlardaki SMTP yapılandırması ile test maili gönderir."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek.'}, status=405)

    from .mail_config import apply_mail_settings

    raw_email = (request.POST.get('email') or '').strip()
    ayarlar = GenelAyarlar.get_ayarlar()
    apply_mail_settings(ayarlar)

    email = raw_email or (ayarlar.default_from_email or '').strip() or (ayarlar.smtp_username or '').strip()
    if not email:
        return JsonResponse({'success': False, 'error': 'Test için bir alıcı e-posta adresi gerekli.'}, status=400)

    from_email = ayarlar.default_from_email or ayarlar.smtp_username or None
    try:
        msg = EmailMultiAlternatives(
            subject='Test Maili — SMTP Ayarları',
            body=(
                'Bu bir test e-postasıdır.\n\n'
                'Ayarlar > Genel Ayarlar > SMTP bölümü test edilmiştir.'
            ),
            from_email=from_email,
            to=[email],
        )
        msg.send(fail_silently=False)
        return JsonResponse({'success': True, 'message': f'SMTP test maili gönderildi: {email}'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def genel_ayarlar_imap_test(request):
    """Genel ayarlardaki IMAP yapılandırması ile bağlantı testi."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek.'}, status=405)

    from .mail_config import apply_mail_settings
    from .services.imap_mail_reader import test_imap_connection

    apply_mail_settings(GenelAyarlar.get_ayarlar())
    try:
        result = test_imap_connection()
        return JsonResponse({'success': True, 'message': result.get('message', 'IMAP bağlantısı başarılı.'), 'details': result})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


YAPIM_ASAMASINDA_ETIKETLER = {
    'mobil': 'Mobil Uygulama',
    'abonelik': 'Abonelik',
    'tum-verileri-sil': 'Tüm Verileri Sil',
}


@login_required
def yapim_asamasinda(request, modul=''):
    baslik = YAPIM_ASAMASINDA_ETIKETLER.get(modul, 'Bu özellik')
    return render(request, 'stokapp/yapim_asamasinda.html', {
        'baslik': baslik,
        'modul_slug': modul,
    })


@login_required
def veri_yedekleme(request):
    """Veri yedekleme ve geri yükleme sayfası"""
    return render(request, 'stokapp/veri_yedekleme.html')


@login_required
def hata_raporlari(request):
    """Hata raporları listesi"""
    # Filtreleme parametreleri
    seviye_filter = request.GET.get('seviye', '')
    cozuldu_filter = request.GET.get('cozuldu', '')
    tarih_filter = request.GET.get('tarih', '')
    search_query = request.GET.get('search', '')
    
    # QuerySet başlat
    hatalar = HataLog.objects.all().select_related('kullanici').order_by('-created_at')
    
    # Seviye filtresi
    if seviye_filter:
        hatalar = hatalar.filter(seviye=seviye_filter)
    
    # Çözüldü filtresi
    if cozuldu_filter == '1':
        hatalar = hatalar.filter(cozuldu=True)
    elif cozuldu_filter == '0':
        hatalar = hatalar.filter(cozuldu=False)
    
    # Tarih filtresi
    if tarih_filter == 'bugun':
        bugun = timezone.now().date()
        hatalar = hatalar.filter(created_at__date=bugun)
    elif tarih_filter == 'hafta':
        bir_hafta_once = timezone.now() - timedelta(days=7)
        hatalar = hatalar.filter(created_at__gte=bir_hafta_once)
    elif tarih_filter == 'ay':
        bir_ay_once = timezone.now() - timedelta(days=30)
        hatalar = hatalar.filter(created_at__gte=bir_ay_once)
    
    # Arama
    if search_query:
        hatalar = hatalar.filter(mesaj__icontains=search_query)
    
    # Sayfalama
    paginator = Paginator(hatalar, 50)  # Sayfa başına 50 kayıt
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # İstatistikler
    toplam_hata = HataLog.objects.filter(seviye='ERROR').count()
    toplam_uyari = HataLog.objects.filter(seviye='WARNING').count()
    cozulmemis_hata = HataLog.objects.filter(seviye='ERROR', cozuldu=False).count()
    
    context = {
        'page_obj': page_obj,
        'hatalar': page_obj,
        'seviye_filter': seviye_filter,
        'cozuldu_filter': cozuldu_filter,
        'tarih_filter': tarih_filter,
        'search_query': search_query,
        'toplam_hata': toplam_hata,
        'toplam_uyari': toplam_uyari,
        'cozulmemis_hata': cozulmemis_hata,
    }
    
    return render(request, 'stokapp/hata_raporlari.html', context)


@login_required
def hata_raporu_coz(request, pk):
    """Hata raporunu çözüldü olarak işaretle"""
    hata = get_object_or_404(HataLog, pk=pk)
    
    if request.method == 'POST':
        cozum_notu = request.POST.get('cozum_notu', '')
        hata.cozuldu = True
        hata.cozum_notu = cozum_notu
        hata.save()
        messages.success(request, 'Hata raporu çözüldü olarak işaretlendi.')
        return redirect('stokapp:hata_raporlari')
    
    return redirect('stokapp:hata_raporlari')


@login_required
def hata_raporu_sil(request, pk):
    """Hata raporunu sil"""
    hata = get_object_or_404(HataLog, pk=pk)
    
    if request.method == 'POST':
        hata.delete()
        messages.success(request, 'Hata raporu silindi.')
        return redirect('stokapp:hata_raporlari')
    
    return redirect('stokapp:hata_raporlari')


@login_required
@_gelistirme_nav_guard
def gelistirme_talep_listesi(request):
    """Geliştirme talepleri listesi"""
    durum_filter = request.GET.get('durum', '')
    talepler = GelistirmeTalebi.objects.all().order_by('-created_at')
    if durum_filter:
        talepler = talepler.filter(durum=durum_filter)

    context = {
        'talepler': talepler,
        'durum_filter': durum_filter,
    }
    return render(request, 'stokapp/gelistirme_talep_listesi.html', context)


@login_required
@_gelistirme_nav_guard
def gelistirme_talep_ekle(request):
    """Yeni geliştirme talebi"""
    if request.method == 'POST':
        form = GelistirmeTalepForm(request.POST)
        if form.is_valid():
            talep = form.save(commit=False)
            talep.durum = 'ACIK'
            talep.save()
            messages.success(request, 'Geliştirme talebi oluşturuldu.')
            return redirect('stokapp:gelistirme_talep_listesi')
        messages.error(request, 'Lütfen form hatalarını düzeltin.')
    else:
        form = GelistirmeTalepForm()

    return render(request, 'stokapp/gelistirme_talep_form.html', {
        'form': form,
        'form_title': 'Yeni Geliştirme Talebi'
    })


@login_required
@_gelistirme_nav_guard
def gelistirme_talep_duzenle(request, pk):
    """Geliştirme talebi düzenle"""
    talep = get_object_or_404(GelistirmeTalebi, pk=pk)
    if request.method == 'POST':
        form = GelistirmeTalepForm(request.POST, instance=talep)
        if form.is_valid():
            form.save()
            messages.success(request, 'Geliştirme talebi güncellendi.')
            return redirect('stokapp:gelistirme_talep_listesi')
        messages.error(request, 'Lütfen form hatalarını düzeltin.')
    else:
        form = GelistirmeTalepForm(instance=talep)

    return render(request, 'stokapp/gelistirme_talep_form.html', {
        'form': form,
        'form_title': 'Geliştirme Talebi Düzenle'
    })


@login_required
@_gelistirme_nav_guard
def gelistirme_talep_kapat(request, pk):
    """Geliştirme talebini tamamlandı olarak kapat"""
    talep = get_object_or_404(GelistirmeTalebi, pk=pk)
    if request.method == 'POST':
        tamamlanma_str = request.POST.get('tamamlanma_zamani') or ''
        tamamlanma_dt = parse_datetime(tamamlanma_str) if tamamlanma_str else None
        if tamamlanma_dt and timezone.is_naive(tamamlanma_dt):
            tamamlanma_dt = timezone.make_aware(tamamlanma_dt)
        if not tamamlanma_dt:
            tamamlanma_dt = timezone.now()

        talep.durum = 'TAMAMLANDI'
        talep.tamamlanma_zamani = tamamlanma_dt
        talep.save(update_fields=['durum', 'tamamlanma_zamani'])
        messages.success(request, 'Geliştirme talebi tamamlandı olarak kapatıldı.')
        return redirect('stokapp:gelistirme_talep_listesi')

    default_dt = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')
    return render(request, 'stokapp/gelistirme_talep_kapat.html', {
        'talep': talep,
        'default_dt': default_dt,
    })


@login_required
def yedekle_altyapi(request):
    """Program alt yapısını yedekle - Ayarlar, şablonlar, yapılandırmalar (veri yok)"""
    if request.method != 'POST':
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:veri_yedekleme')
    
    try:
        # Geçici dizin oluştur
        temp_dir = tempfile.mkdtemp()
        
        backup_data = {
            'backup_type': 'altyapi',
            'backup_date': datetime.now().isoformat(),
            'created_by': request.user.username if request.user.is_authenticated else 'System',
        }
        
        # Alt yapı modellerini yedekle (veri içermez, sadece yapılandırma)
        altyapi_models = {
            'genel_ayarlar': [],
            'yazdirma_sablonlari': [],
            'para_birimleri': [],
            'birimler': [],
            'depolar': [],
            'istasyonlar': [],
            'operasyonlar': [],
            'ekipmanlar': [],
            'fiksturlar': [],
            'olcu_aleti_turleri': [],
        }
        
        # GenelAyarlar
        from .models import GenelAyarlar, YazdirmaSablonu, ParaBirimi, Birim, Depo, Istasyon, Operasyon, Ekipman, Fikstur, OlcuAletiTuru
        
        ayarlar = GenelAyarlar.get_ayarlar()
        if ayarlar:
            altyapi_models['genel_ayarlar'] = [{
                'firma_ismi': ayarlar.firma_ismi or '',
                'telefon': ayarlar.telefon or '',
                'email': ayarlar.email or '',
                'musteri_mail_cc_adresi': ayarlar.musteri_mail_cc_adresi or '',
                'satinalma_mail_cc_adresi': ayarlar.satinalma_mail_cc_adresi or '',
                'para_birimi': ayarlar.para_birimi or 'TRY',
                'on_tanimli_satis_lokasyonu_id': ayarlar.on_tanimli_satis_lokasyonu_id,
                'on_tanimli_satin_alma_lokasyonu_id': ayarlar.on_tanimli_satin_alma_lokasyonu_id,
                'on_tanimli_uretim_lokasyonu_id': ayarlar.on_tanimli_uretim_lokasyonu_id,
                'varsayilan_satis_teslimat_suresi': str(ayarlar.varsayilan_satis_teslimat_suresi) if ayarlar.varsayilan_satis_teslimat_suresi else '',
                'varsayilan_satin_alma_teslimat_suresi': str(ayarlar.varsayilan_satin_alma_teslimat_suresi) if ayarlar.varsayilan_satin_alma_teslimat_suresi else '',
                'varsayilan_uretim_suresi': str(ayarlar.varsayilan_uretim_suresi) if ayarlar.varsayilan_uretim_suresi else '',
                'satis_irsaliyesi_oneki': ayarlar.satis_irsaliyesi_oneki or '',
                'satin_alma_irsaliyesi_oneki': ayarlar.satin_alma_irsaliyesi_oneki or '',
                'is_emri_oneki': ayarlar.is_emri_oneki or '',
            }]
        
        # YazdirmaSablonu
        sablonlar = YazdirmaSablonu.objects.all()
        altyapi_models['yazdirma_sablonlari'] = [{
            'ad': s.ad,
            'tip': s.tip,
            'icerik': s.icerik,
        } for s in sablonlar]
        
        # ParaBirimi
        para_birimleri = ParaBirimi.objects.all()
        altyapi_models['para_birimleri'] = [{
            'kod': pb.kod,
            'ad': pb.ad,
            'sembol': pb.sembol,
            'aktif': pb.aktif,
        } for pb in para_birimleri]
        
        # Birim
        birimler = Birim.objects.all()
        altyapi_models['birimler'] = [{
            'ad': b.ad,
        } for b in birimler]
        
        # Depo
        depolar = Depo.objects.all()
        altyapi_models['depolar'] = [{
            'ad': d.ad,
            'aciklama': d.aciklama or '',
        } for d in depolar]
        
        # Istasyon
        istasyonlar = Istasyon.objects.all()
        altyapi_models['istasyonlar'] = [{
            'ad': i.ad,
            'aciklama': i.aciklama or '',
        } for i in istasyonlar]
        
        # Operasyon
        operasyonlar = Operasyon.objects.all()
        altyapi_models['operasyonlar'] = [{
            'ad': o.ad,
            'aciklama': o.aciklama or '',
        } for o in operasyonlar]
        
        # Ekipman
        ekipmanlar = Ekipman.objects.all()
        altyapi_models['ekipmanlar'] = [{
            'ad': e.ad,
            'aciklama': e.aciklama or '',
        } for e in ekipmanlar]
        
        # Fikstur
        fiksturlar = Fikstur.objects.all()
        altyapi_models['fiksturlar'] = [{
            'ad': f.ad,
            'aciklama': f.aciklama or '',
        } for f in fiksturlar]
        
        # OlcuAletiTuru
        olcu_aleti_turleri = OlcuAletiTuru.objects.all()
        altyapi_models['olcu_aleti_turleri'] = [{
            'ad': o.ad,
            'aciklama': o.aciklama or '',
        } for o in olcu_aleti_turleri]
        
        backup_data['data'] = altyapi_models
        
        # JSON dosyasına yaz
        json_file = os.path.join(temp_dir, 'altyapi_backup.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        # ZIP dosyası oluştur
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f'altyapi_yedek_{timestamp}.zip'
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(json_file, 'altyapi_backup.json')
        
        # ZIP dosyasını oku ve response olarak döndür
        with open(zip_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        
        # Geçici dosyaları temizle
        shutil.rmtree(temp_dir)
        
        messages.success(request, 'Program alt yapısı başarıyla yedeklendi.')
        return response
        
    except Exception as e:
        messages.error(request, f'Yedekleme sırasında hata oluştu: {str(e)}')
        return redirect('stokapp:veri_yedekleme')


@login_required
def yedekle_veriler(request):
    """Program verilerini yedekle - Tüm veritabanı verileri"""
    if request.method != 'POST':
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:veri_yedekleme')
    
    try:
        from django.core import serializers
        from .models import (
            StokItem, StokHareketi, Satinalma, SatinalmaKalemi, Siparis, SiparisKalemi,
            Recete, ReceteDetay, ReceteOperasyon, UretimEmri, UretimAsamasi,
            Cari, Musteri, Tedarikci, Kategori, FiyatGecmisi,
            GunlukCalisma, AvansOdeme, Personel, AylikOdeme,
            Sigorta, Arac, AracBelgesi, BankaHesabi, KrediKarti,
            OlcuAleti, KalibrasyonKaydi, UretimStandarti, KurulumDosyasi
        )
        
        # Geçici dizin oluştur
        temp_dir = tempfile.mkdtemp()
        
        backup_data = {
            'backup_type': 'veriler',
            'backup_date': datetime.now().isoformat(),
            'created_by': request.user.username if request.user.is_authenticated else 'System',
            'data': {}
        }
        
        # Tüm veri modellerini yedekle
        models_to_backup = [
            ('stok_items', StokItem),
            ('stok_hareketleri', StokHareketi),
            ('satinalmalar', Satinalma),
            ('satinalma_kalemleri', SatinalmaKalemi),
            ('siparisler', Siparis),
            ('siparis_kalemleri', SiparisKalemi),
            ('receteler', Recete),
            ('recete_detaylar', ReceteDetay),
            ('recete_operasyonlar', ReceteOperasyon),
            ('uretim_emirleri', UretimEmri),
            ('uretim_asamalari', UretimAsamasi),
            ('cariler', Cari),
            ('musteriler', Musteri),
            ('tedarikciler', Tedarikci),
            ('kategoriler', Kategori),
            ('fiyat_gecmisi', FiyatGecmisi),
            ('gunluk_calismalar', GunlukCalisma),
            ('avans_odemeler', AvansOdeme),
            ('personel', Personel),
            ('sigortalar', Sigorta),
            ('olcu_aletleri', OlcuAleti),
            ('kalibrasyon_kayitlari', KalibrasyonKaydi),
            ('uretim_standartlari', UretimStandarti),
            ('kurulum_dosyalari', KurulumDosyasi),
        ]
        
        # AylikOdeme varsa ekle
        try:
            from .models import AylikOdeme
            models_to_backup.append(('aylik_odemeler', AylikOdeme))
        except:
            pass
        
        # Her modeli JSON formatında serialize et
        for model_name, model_class in models_to_backup:
            try:
                queryset = model_class.objects.all()
                serialized_data = serializers.serialize('json', queryset, ensure_ascii=False)
                backup_data['data'][model_name] = json.loads(serialized_data)
            except Exception as e:
                backup_data['data'][model_name] = {'error': str(e)}
        
        # JSON dosyasına yaz
        json_file = os.path.join(temp_dir, 'veriler_backup.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        # ZIP dosyası oluştur
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f'veriler_yedek_{timestamp}.zip'
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(json_file, 'veriler_backup.json')
            
            # MEDIA dosyalarını da ekle (varsa)
            media_root = getattr(settings, 'MEDIA_ROOT', None)
            if media_root and os.path.exists(media_root):
                for root, dirs, files in os.walk(media_root):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, media_root)
                        zipf.write(file_path, f'media/{arcname}')
        
        # ZIP dosyasını oku ve response olarak döndür
        with open(zip_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        
        # Geçici dosyaları temizle
        shutil.rmtree(temp_dir)
        
        messages.success(request, 'Program verileri başarıyla yedeklendi.')
        return response
        
    except Exception as e:
        messages.error(request, f'Veri yedekleme sırasında hata oluştu: {str(e)}')
        return redirect('stokapp:veri_yedekleme')


@login_required
def geri_yukle_altyapi(request):
    """Program alt yapısını geri yükle - Sıfır veri ile"""
    if request.method != 'POST':
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:veri_yedekleme')
    
    if 'backup_file' not in request.FILES:
        messages.error(request, 'Lütfen bir yedek dosyası seçin.')
        return redirect('stokapp:veri_yedekleme')
    
    try:
        from .models import GenelAyarlar, YazdirmaSablonu, ParaBirimi, Birim, Depo, Istasyon, Operasyon, Ekipman, Fikstur, OlcuAletiTuru
        
        backup_file = request.FILES['backup_file']
        
        # Geçici dizine kaydet
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, backup_file.name)
        
        with open(temp_file, 'wb+') as f:
            for chunk in backup_file.chunks():
                f.write(chunk)
        
        # ZIP dosyasını aç
        with zipfile.ZipFile(temp_file, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        # JSON dosyasını oku
        json_file = os.path.join(temp_dir, 'altyapi_backup.json')
        if not os.path.exists(json_file):
            messages.error(request, 'Yedek dosyası geçersiz format.')
            shutil.rmtree(temp_dir)
            return redirect('stokapp:veri_yedekleme')
        
        with open(json_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        if backup_data.get('backup_type') != 'altyapi':
            messages.error(request, 'Bu dosya bir alt yapı yedeği değil.')
            shutil.rmtree(temp_dir)
            return redirect('stokapp:veri_yedekleme')
        
        # Transaction içinde geri yükle
        with transaction.atomic():
            data = backup_data.get('data', {})
            
            # ParaBirimi geri yükle
            if 'para_birimleri' in data:
                ParaBirimi.objects.all().delete()
                for pb_data in data['para_birimleri']:
                    ParaBirimi.objects.create(**pb_data)
            
            # Birim geri yükle
            if 'birimler' in data:
                Birim.objects.all().delete()
                for b_data in data['birimler']:
                    Birim.objects.create(**b_data)
            
            # Depo geri yükle
            if 'depolar' in data:
                Depo.objects.all().delete()
                for d_data in data['depolar']:
                    Depo.objects.create(**d_data)
            
            # Istasyon geri yükle
            if 'istasyonlar' in data:
                Istasyon.objects.all().delete()
                for i_data in data['istasyonlar']:
                    Istasyon.objects.create(**i_data)
            
            # Operasyon geri yükle
            if 'operasyonlar' in data:
                Operasyon.objects.all().delete()
                for o_data in data['operasyonlar']:
                    Operasyon.objects.create(**o_data)
            
            # Ekipman geri yükle
            if 'ekipmanlar' in data:
                Ekipman.objects.all().delete()
                for e_data in data['ekipmanlar']:
                    Ekipman.objects.create(**e_data)
            
            # Fikstur geri yükle
            if 'fiksturlar' in data:
                Fikstur.objects.all().delete()
                for f_data in data['fiksturlar']:
                    Fikstur.objects.create(**f_data)
            
            # OlcuAletiTuru geri yükle
            if 'olcu_aleti_turleri' in data:
                OlcuAletiTuru.objects.all().delete()
                for o_data in data['olcu_aleti_turleri']:
                    OlcuAletiTuru.objects.create(**o_data)
            
            # YazdirmaSablonu geri yükle
            if 'yazdirma_sablonlari' in data:
                YazdirmaSablonu.objects.all().delete()
                for s_data in data['yazdirma_sablonlari']:
                    YazdirmaSablonu.objects.create(**s_data)
            
            # GenelAyarlar geri yükle
            if 'genel_ayarlar' in data and data['genel_ayarlar']:
                ayar_data = data['genel_ayarlar'][0]
                ayarlar = GenelAyarlar.get_ayarlar()
                for key, value in ayar_data.items():
                    if hasattr(ayarlar, key):
                        setattr(ayarlar, key, value)
                ayarlar.save()
        
        # Geçici dosyaları temizle
        shutil.rmtree(temp_dir)
        
        messages.success(request, 'Program alt yapısı başarıyla geri yüklendi.')
        return redirect('stokapp:veri_yedekleme')
        
    except Exception as e:
        messages.error(request, f'Alt yapı geri yükleme sırasında hata oluştu: {str(e)}')
        return redirect('stokapp:veri_yedekleme')


@login_required
def geri_yukle_veriler(request):
    """Program verilerini geri yükle"""
    if request.method != 'POST':
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:veri_yedekleme')
    
    if 'backup_file' not in request.FILES:
        messages.error(request, 'Lütfen bir yedek dosyası seçin.')
        return redirect('stokapp:veri_yedekleme')
    
    try:
        from django.core import serializers
        from .models import (
            StokItem, StokHareketi, Satinalma, SatinalmaKalemi, Siparis, SiparisKalemi,
            Recete, ReceteDetay, ReceteOperasyon, UretimEmri, UretimAsamasi,
            Cari, Musteri, Tedarikci, Kategori, FiyatGecmisi,
            GunlukCalisma, AvansOdeme, Personel,
            Sigorta, Arac, AracBelgesi, BankaHesabi, KrediKarti,
            OlcuAleti, KalibrasyonKaydi, UretimStandarti, KurulumDosyasi
        )
        
        backup_file = request.FILES['backup_file']
        
        # Geçici dizine kaydet
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, backup_file.name)
        
        with open(temp_file, 'wb+') as f:
            for chunk in backup_file.chunks():
                f.write(chunk)
        
        # ZIP dosyasını aç
        with zipfile.ZipFile(temp_file, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        # JSON dosyasını oku
        json_file = os.path.join(temp_dir, 'veriler_backup.json')
        if not os.path.exists(json_file):
            messages.error(request, 'Yedek dosyası geçersiz format.')
            shutil.rmtree(temp_dir)
            return redirect('stokapp:veri_yedekleme')
        
        with open(json_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        if backup_data.get('backup_type') != 'veriler':
            messages.error(request, 'Bu dosya bir veri yedeği değil.')
            shutil.rmtree(temp_dir)
            return redirect('stokapp:veri_yedekleme')
        
        # Model mapping
        model_mapping = {
            'stok_items': StokItem,
            'stok_hareketleri': StokHareketi,
            'satinalmalar': Satinalma,
            'satinalma_kalemleri': SatinalmaKalemi,
            'siparisler': Siparis,
            'siparis_kalemleri': SiparisKalemi,
            'receteler': Recete,
            'recete_detaylar': ReceteDetay,
            'recete_operasyonlar': ReceteOperasyon,
            'uretim_emirleri': UretimEmri,
            'uretim_asamalari': UretimAsamasi,
            'cariler': Cari,
            'musteriler': Musteri,
            'tedarikciler': Tedarikci,
            'kategoriler': Kategori,
            'fiyat_gecmisi': FiyatGecmisi,
            'gunluk_calismalar': GunlukCalisma,
            'avans_odemeler': AvansOdeme,
            'personel': Personel,
            'sigortalar': Sigorta,
            'olcu_aletleri': OlcuAleti,
            'kalibrasyon_kayitlari': KalibrasyonKaydi,
            'uretim_standartlari': UretimStandarti,
            'kurulum_dosyalari': KurulumDosyasi,
        }
        
        # AylikOdeme varsa ekle
        try:
            from .models import AylikOdeme
            model_mapping['aylik_odemeler'] = AylikOdeme
        except:
            pass
        
        # Transaction içinde geri yükle
        with transaction.atomic():
            data = backup_data.get('data', {})
            
            # Tüm modelleri temizle (ForeignKey ilişkilerine dikkat ederek)
            # Önce child modelleri, sonra parent modelleri sil
            
            # Child modelleri sil
            StokHareketi.objects.all().delete()
            SatinalmaKalemi.objects.all().delete()
            SiparisKalemi.objects.all().delete()
            ReceteDetay.objects.all().delete()
            ReceteOperasyon.objects.all().delete()
            UretimAsamasi.objects.all().delete()
            FiyatGecmisi.objects.all().delete()
            GunlukCalisma.objects.all().delete()
            AvansOdeme.objects.all().delete()
            KalibrasyonKaydi.objects.all().delete()
            
            # Parent modelleri sil
            StokItem.objects.all().delete()
            Satinalma.objects.all().delete()
            Siparis.objects.all().delete()
            Recete.objects.all().delete()
            UretimEmri.objects.all().delete()
            Cari.objects.all().delete()
            Musteri.objects.all().delete()
            Tedarikci.objects.all().delete()
            Kategori.objects.all().delete()
            Personel.objects.all().delete()
            Sigorta.objects.all().delete()
            OlcuAleti.objects.all().delete()
            UretimStandarti.objects.all().delete()
            KurulumDosyasi.objects.all().delete()
            
            try:
                AylikOdeme.objects.all().delete()
            except:
                pass
            
            # Verileri geri yükle
            for model_name, model_class in model_mapping.items():
                if model_name in data and not isinstance(data[model_name], dict):
                    serialized_json = json.dumps(data[model_name])
                    objects = serializers.deserialize('json', serialized_json)
                    for obj in objects:
                        obj.save()
            
            # MEDIA dosyalarını geri yükle (varsa)
            media_backup_dir = os.path.join(temp_dir, 'media')
            if os.path.exists(media_backup_dir):
                media_root = getattr(settings, 'MEDIA_ROOT', None)
                if media_root:
                    if os.path.exists(media_root):
                        shutil.rmtree(media_root)
                    os.makedirs(media_root, exist_ok=True)
                    for root, dirs, files in os.walk(media_backup_dir):
                        for file in files:
                            src = os.path.join(root, file)
                            dst = os.path.join(media_root, os.path.relpath(src, media_backup_dir))
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
        
        # Geçici dosyaları temizle
        shutil.rmtree(temp_dir)
        
        messages.success(request, 'Program verileri başarıyla geri yüklendi.')
        return redirect('stokapp:veri_yedekleme')
        
    except Exception as e:
        messages.error(request, f'Veri geri yükleme sırasında hata oluştu: {str(e)}')
        import traceback
        traceback.print_exc()
        return redirect('stokapp:veri_yedekleme')
