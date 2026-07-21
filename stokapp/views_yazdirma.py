from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import YazdirmaSablonu


@login_required
def yazdirma_sablonlari_listesi(request):
    """Yazdırma şablonları listesi"""
    sablonlar = YazdirmaSablonu.objects.all().order_by('tip')
    
    # Eğer şablon yoksa varsayılan şablonları oluştur
    if not sablonlar.exists():
        with transaction.atomic():
            for tip_kod, tip_ad in YazdirmaSablonu.SABLON_TIPLERI:
                YazdirmaSablonu.objects.get_or_create(
                    tip=tip_kod,
                    defaults={
                        'baslik_metni': tip_ad,
                        'firma_adi': 'Firma Adı',
                        'firma_adres': 'Firma Adresi',
                        'firma_telefon': '0212 123 45 67',
                        'firma_email': 'info@firma.com',
                        'firma_vergi_no': '1234567890',
                        'alt_bilgi_metni': 'Teşekkür ederiz.',
                    }
                )
        sablonlar = YazdirmaSablonu.objects.all().order_by('tip')
    
    return render(request, 'stokapp/yazdirma_sablonlari_listesi.html', {
        'sablonlar': sablonlar,
    })


@login_required
def yazdirma_sablonu_duzenle(request, pk):
    """Yazdırma şablonu düzenle"""
    sablon = get_object_or_404(YazdirmaSablonu, pk=pk)
    
    if request.method == 'POST':
        # API ile düzenleme modu kontrolü
        api_kullan = request.POST.get('api_kullan') == 'on'
        sablon.api_kullan = api_kullan
        
        if api_kullan:
            # API ayarları
            sablon.api_key = request.POST.get('api_key', '')
            sablon.template_id = request.POST.get('template_id', '')
            sablon.editor_url = request.POST.get('editor_url', '')
            
            # Template data JSON olarak kaydet
            if 'template_data' in request.POST:
                try:
                    sablon.template_data = json.loads(request.POST.get('template_data', '{}'))
                except:
                    sablon.template_data = {}
        else:
            # Normal form verilerini al
            sablon.logo_goster = request.POST.get('logo_goster') == 'on'
            sablon.logo_pozisyon = request.POST.get('logo_pozisyon', 'SOL')
            sablon.logo_genislik = int(request.POST.get('logo_genislik', 150) or 150)
            sablon.logo_yukseklik = int(request.POST.get('logo_yukseklik', 80) or 80)
            
            sablon.baslik_metni = request.POST.get('baslik_metni', '')
            sablon.baslik_font_boyutu = int(request.POST.get('baslik_font_boyutu', 24) or 24)
            sablon.baslik_font_rengi = request.POST.get('baslik_font_rengi', '#000000')
            sablon.baslik_kalin = request.POST.get('baslik_kalin') == 'on'
            sablon.baslik_pozisyon = request.POST.get('baslik_pozisyon', 'ORTA')
            
            sablon.tarih_goster = request.POST.get('tarih_goster') == 'on'
            sablon.tarih_format = request.POST.get('tarih_format', '%d.%m.%Y')
            sablon.tarih_pozisyon = request.POST.get('tarih_pozisyon', 'SAG')
            
            sablon.firma_adi = request.POST.get('firma_adi', '')
            sablon.firma_adres = request.POST.get('firma_adres', '')
            sablon.firma_telefon = request.POST.get('firma_telefon', '')
            sablon.firma_email = request.POST.get('firma_email', '')
            sablon.firma_vergi_no = request.POST.get('firma_vergi_no', '')
            
            sablon.alt_bilgi_goster = request.POST.get('alt_bilgi_goster') == 'on'
            sablon.alt_bilgi_metni = request.POST.get('alt_bilgi_metni', '')
            
            sablon.sayfa_kenar_bosluk = int(request.POST.get('sayfa_kenar_bosluk', 20) or 20)
            sablon.font_ailesi = request.POST.get('font_ailesi', 'Arial')
            sablon.varsayilan_font_boyutu = int(request.POST.get('varsayilan_font_boyutu', 12) or 12)
            
            sablon.ozel_css = request.POST.get('ozel_css', '')
            sablon.ozel_html = request.POST.get('ozel_html', '')
            
            # Logo dosyası yükleme
            if 'logo_yolu' in request.FILES:
                sablon.logo_yolu = request.FILES['logo_yolu']
        
        sablon.save()
        
        messages.success(request, f'{sablon.get_tip_display()} şablonu başarıyla güncellendi.')
        return redirect('stokapp:yazdirma_sablonlari_listesi')
    
    return render(request, 'stokapp/yazdirma_sablonu_duzenle.html', {
        'sablon': sablon,
    })


@login_required
@require_http_methods(["POST"])
def yazdirma_sablonu_api_save(request, pk):
    """API'den gelen şablon verilerini kaydet"""
    sablon = get_object_or_404(YazdirmaSablonu, pk=pk)
    
    try:
        data = json.loads(request.body)
        sablon.template_data = data.get('template_data', {})
        sablon.template_id = data.get('template_id', sablon.template_id)
        sablon.save()
        
        return JsonResponse({'success': True, 'message': 'Şablon başarıyla kaydedildi.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def yazdirma_sablonu_onizleme(request, pk):
    """Şablon önizlemesi"""
    sablon = get_object_or_404(YazdirmaSablonu, pk=pk)
    
    # Örnek veri ile önizleme
    ornek_veri = {
        'baslik': sablon.baslik_metni or sablon.get_tip_display(),
        'tarih': '01.01.2024',
        'numara': 'TEK-2024-001',
        'musteri': 'Örnek Müşteri',
    }
    
    return render(request, 'stokapp/yazdirma_sablonu_onizleme.html', {
        'sablon': sablon,
        'ornek_veri': ornek_veri,
    })

