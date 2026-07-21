from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import date, timedelta
from django.http import HttpResponse
from django.template.loader import get_template

from .models import OlcuAleti, OlcuAletiTuru, KalibrasyonKaydi
from .forms import OlcuAletiForm, OlcuAletiTuruForm, KalibrasyonKaydiForm

# WeasyPrint lazy import
WEASYPRINT_AVAILABLE = None


@login_required
def olcu_aleti_listesi(request):
    """Ölçü aletleri listesi"""
    search_query = request.GET.get('search', '')
    durum_filter = request.GET.get('durum', '')
    kritiklik_filter = request.GET.get('kritiklik', '')
    kalibrasyon_durum_filter = request.GET.get('kalibrasyon_durum', '')
    
    aletler = OlcuAleti.objects.select_related('alet_turu').all()
    
    if search_query:
        aletler = aletler.filter(
            Q(device_id__icontains=search_query) |
            Q(seri_no__icontains=search_query) |
            Q(marka__icontains=search_query) |
            Q(model__icontains=search_query) |
            Q(alet_turu__ad__icontains=search_query) |
            Q(device_type__icontains=search_query)
        )
    
    # Durum filtresi - yeni status alanını kullan, eski durum alanıyla uyumlu
    if durum_filter:
        if durum_filter in ['active', 'blocked', 'out_of_service']:
            aletler = aletler.filter(status=durum_filter)
        else:
            # Eski durum değerleri için
            aletler = aletler.filter(durum=durum_filter)
    
    if kritiklik_filter:
        aletler = aletler.filter(kritiklik_seviyesi=kritiklik_filter)
    
    # Kalibrasyon durumuna göre filtreleme - next_calibration_date öncelikli
    if kalibrasyon_durum_filter:
        bugun = date.today()
        # next_calibration_date varsa onu kullan, yoksa sonraki_kalibrasyon_tarihi kullan
        if kalibrasyon_durum_filter == 'GECMIS':
            aletler = aletler.filter(
                Q(next_calibration_date__lt=bugun) |
                Q(next_calibration_date__isnull=True, sonraki_kalibrasyon_tarihi__lt=bugun)
            )
        elif kalibrasyon_durum_filter == 'ACIL':
            aletler = aletler.filter(
                Q(next_calibration_date__gte=bugun, next_calibration_date__lte=bugun + timedelta(days=7)) |
                Q(next_calibration_date__isnull=True, sonraki_kalibrasyon_tarihi__gte=bugun, sonraki_kalibrasyon_tarihi__lte=bugun + timedelta(days=7))
            )
        elif kalibrasyon_durum_filter == 'YAKLASIYOR':
            aletler = aletler.filter(
                Q(next_calibration_date__gt=bugun + timedelta(days=7), next_calibration_date__lte=bugun + timedelta(days=30)) |
                Q(next_calibration_date__isnull=True, sonraki_kalibrasyon_tarihi__gt=bugun + timedelta(days=7), sonraki_kalibrasyon_tarihi__lte=bugun + timedelta(days=30))
            )
        elif kalibrasyon_durum_filter == 'SAGLIKLI':
            aletler = aletler.filter(
                Q(next_calibration_date__gt=bugun + timedelta(days=30)) |
                Q(next_calibration_date__isnull=True, sonraki_kalibrasyon_tarihi__gt=bugun + timedelta(days=30))
            )
    
    aletler = aletler.order_by('device_id', 'seri_no')
    
    # Her alet için kalibrasyon durumunu hesapla
    for alet in aletler:
        # next_calibration_date varsa onu kullan, yoksa sonraki_kalibrasyon_tarihi kullan
        cal_date = alet.next_calibration_date or alet.sonraki_kalibrasyon_tarihi
        if cal_date:
            fark = (cal_date - date.today()).days
            if fark < 0:
                alet.kalibrasyon_durumu_calculated = 'GECMIS'
            elif fark <= 7:
                alet.kalibrasyon_durumu_calculated = 'ACIL'
            elif fark <= 30:
                alet.kalibrasyon_durumu_calculated = 'YAKLASIYOR'
            else:
                alet.kalibrasyon_durumu_calculated = 'SAGLIKLI'
        else:
            alet.kalibrasyon_durumu_calculated = 'BILINMIYOR'
    
    context = {
        'aletler': aletler,
        'search_query': search_query,
        'durum_filter': durum_filter,
        'kritiklik_filter': kritiklik_filter,
        'kalibrasyon_durum_filter': kalibrasyon_durum_filter,
    }
    return render(request, 'stokapp/olcu_aleti_listesi.html', context)


@login_required
def olcu_aleti_ekle(request):
    """Yeni ölçü aleti ekle"""
    if request.method == 'POST':
        form = OlcuAletiForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                alet = form.save(commit=False)
                # Eğer aktif alanı POST'ta yoksa (checkbox işaretlenmemişse) True yap
                if 'aktif' not in request.POST:
                    alet.aktif = True
                
                # Device ID yoksa otomatik oluştur
                if not alet.device_id and alet.seri_no:
                    counter = 1
                    device_id = alet.seri_no
                    while OlcuAleti.objects.filter(device_id=device_id).exclude(pk=alet.pk if alet.pk else None).exists():
                        device_id = f"{alet.seri_no}_{counter}"
                        counter += 1
                    alet.device_id = device_id
                
                # Periyoda göre sonraki kalibrasyon tarihini hesapla (model save metodunda otomatik yapılıyor)
                # Burada sadece gerekli alanları senkronize ediyoruz
                cal_date = alet.last_calibration_date or alet.son_kalibrasyon_tarihi
                if cal_date:
                    alet.last_calibration_date = cal_date
                    if not alet.son_kalibrasyon_tarihi:
                        alet.son_kalibrasyon_tarihi = cal_date
                
                alet.save()
                messages.success(request, f'Ölçü aleti "{alet.seri_no}" başarıyla eklendi.')
                return redirect('stokapp:olcu_aleti_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OlcuAletiForm()
        # Varsayılan olarak aktif=True
        form.fields['aktif'].initial = True
    
    # Alet türlerini, istasyonları ve personelleri context'e ekle
    from .models import Istasyon, Personel
    # Mevcut kullanım yerlerini al (benzersiz değerler)
    kullanim_yerleri = OlcuAleti.objects.exclude(kullanim_yeri='').values_list('kullanim_yeri', flat=True).distinct()
    # Mevcut markaları al (benzersiz değerler)
    markalar = OlcuAleti.objects.exclude(marka='').values_list('marka', flat=True).distinct()
    
    context = {
        'form': form,
        'alet_turleri': OlcuAletiTuru.objects.filter(aktif=True).order_by('sira', 'ad'),
        'istasyonlar': Istasyon.objects.filter(aktif=True).order_by('sira', 'ad'),
        'personeller': Personel.objects.filter(aktif=True).order_by('ad', 'soyad'),
        'kullanim_yerleri': kullanim_yerleri,
        'markalar': markalar,
    }
    return render(request, 'stokapp/olcu_aleti_ekle.html', context)


@login_required
def olcu_aleti_duzenle(request, pk):
    """Ölçü aleti düzenle"""
    alet = get_object_or_404(OlcuAleti, pk=pk)
    
    if request.method == 'POST':
        form = OlcuAletiForm(request.POST, request.FILES, instance=alet)
        if form.is_valid():
            try:
                alet = form.save(commit=False)
                # Eğer aktif alanı POST'ta yoksa (checkbox işaretlenmemişse) True yap
                if 'aktif' not in request.POST:
                    alet.aktif = True
                
                # Device ID yoksa otomatik oluştur
                if not alet.device_id and alet.seri_no:
                    counter = 1
                    device_id = alet.seri_no
                    while OlcuAleti.objects.filter(device_id=device_id).exclude(pk=alet.pk).exists():
                        device_id = f"{alet.seri_no}_{counter}"
                        counter += 1
                    alet.device_id = device_id
                
                # Kalibrasyon tarihlerini senkronize et
                cal_date = alet.last_calibration_date or alet.son_kalibrasyon_tarihi
                if cal_date:
                    alet.last_calibration_date = cal_date
                    if not alet.son_kalibrasyon_tarihi:
                        alet.son_kalibrasyon_tarihi = cal_date
                
                # Sonraki kalibrasyon tarihini senkronize et
                next_date = alet.next_calibration_date or alet.sonraki_kalibrasyon_tarihi
                if next_date:
                    alet.next_calibration_date = next_date
                    if not alet.sonraki_kalibrasyon_tarihi:
                        alet.sonraki_kalibrasyon_tarihi = next_date
                
                alet.save()
                messages.success(request, f'Ölçü aleti "{alet.seri_no}" güncellendi.')
                return redirect('stokapp:olcu_aleti_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OlcuAletiForm(instance=alet)
    
    # Alet türlerini, istasyonları ve personelleri context'e ekle
    from .models import Istasyon, Personel
    # Mevcut kullanım yerlerini al (benzersiz değerler)
    kullanim_yerleri = OlcuAleti.objects.exclude(kullanim_yeri='').values_list('kullanim_yeri', flat=True).distinct()
    # Mevcut markaları al (benzersiz değerler)
    markalar = OlcuAleti.objects.exclude(marka='').values_list('marka', flat=True).distinct()
    
    context = {
        'form': form,
        'alet': alet,
        'alet_turleri': OlcuAletiTuru.objects.filter(aktif=True).order_by('sira', 'ad'),
        'istasyonlar': Istasyon.objects.filter(aktif=True).order_by('sira', 'ad'),
        'personeller': Personel.objects.filter(aktif=True).order_by('ad', 'soyad'),
        'kullanim_yerleri': kullanim_yerleri,
        'markalar': markalar,
    }
    return render(request, 'stokapp/olcu_aleti_duzenle.html', context)


@login_required
def olcu_aleti_sil(request, pk):
    """Ölçü aleti sil"""
    alet = get_object_or_404(OlcuAleti, pk=pk)
    
    if request.method == 'POST':
        try:
            seri_no = alet.seri_no
            alet.delete()
            messages.success(request, f'Ölçü aleti "{seri_no}" silindi.')
            return redirect('stokapp:olcu_aleti_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    return render(request, 'stokapp/olcu_aleti_sil.html', {'alet': alet})


@login_required
def olcu_aleti_durum_degistir(request, pk):
    """Ölçü aleti aktif/pasif durumunu değiştir"""
    alet = get_object_or_404(OlcuAleti, pk=pk)
    alet.aktif = not alet.aktif
    alet.save()
    messages.success(request, f'Ölçü aleti durumu {"aktif" if alet.aktif else "pasif"} olarak değiştirildi.')
    return redirect('stokapp:olcu_aleti_listesi')


# Alet Türü Yönetimi

@login_required
def olcu_aleti_turu_listesi(request):
    """Ölçü aleti türleri listesi"""
    # Varsayılan alet türlerini oluştur (eğer yoksa)
    default_turler = [
        'Kumpas', 'Mikrometre', 'Mihengir', 'Mastar', 
        'Yük Hücresi', 'Tork Anahtarı', 'CMM', 
        'Delik Mikrometresi', 'Komparatör'
    ]
    for idx, tur_adi in enumerate(default_turler):
        OlcuAletiTuru.objects.get_or_create(ad=tur_adi, defaults={'sira': idx + 1, 'aktif': True})
    
    turler = OlcuAletiTuru.objects.all().order_by('sira', 'ad')
    return render(request, 'stokapp/olcu_aleti_turu_listesi.html', {'turler': turler})


@login_required
def olcu_aleti_turu_ekle(request):
    """Yeni ölçü aleti türü ekle"""
    if request.method == 'POST':
        form = OlcuAletiTuruForm(request.POST)
        if form.is_valid():
            try:
                tur = form.save(commit=False)
                if 'aktif' not in request.POST:
                    tur.aktif = True
                tur.save()
                messages.success(request, f'Alet türü "{tur.ad}" başarıyla eklendi.')
                return redirect('stokapp:olcu_aleti_turu_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OlcuAletiTuruForm()
        form.fields['aktif'].initial = True
    
    return render(request, 'stokapp/olcu_aleti_turu_ekle.html', {'form': form})


@login_required
def olcu_aleti_turu_duzenle(request, pk):
    """Ölçü aleti türü düzenle"""
    tur = get_object_or_404(OlcuAletiTuru, pk=pk)
    
    if request.method == 'POST':
        form = OlcuAletiTuruForm(request.POST, instance=tur)
        if form.is_valid():
            try:
                tur = form.save(commit=False)
                if 'aktif' not in request.POST:
                    tur.aktif = True
                tur.save()
                messages.success(request, f'Alet türü "{tur.ad}" güncellendi.')
                return redirect('stokapp:olcu_aleti_turu_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OlcuAletiTuruForm(instance=tur)
    
    return render(request, 'stokapp/olcu_aleti_turu_duzenle.html', {'form': form, 'tur': tur})


@login_required
def olcu_aleti_turu_sil(request, pk):
    """Ölçü aleti türü sil"""
    tur = get_object_or_404(OlcuAletiTuru, pk=pk)
    
    if request.method == 'POST':
        try:
            ad = tur.ad
            tur.delete()
            messages.success(request, f'Alet türü "{ad}" silindi.')
            return redirect('stokapp:olcu_aleti_turu_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    return render(request, 'stokapp/olcu_aleti_turu_sil.html', {'tur': tur})


# Kalibrasyon Yönetimi

@login_required
def kalibrasyon_ekle(request, alet_id):
    """Yeni kalibrasyon kaydı ekle"""
    alet = get_object_or_404(OlcuAleti, pk=alet_id)
    
    if request.method == 'POST':
        form = KalibrasyonKaydiForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                kalibrasyon = form.save(commit=False)
                kalibrasyon.olcu_aleti = alet
                kalibrasyon.save()  # Bu save, alet'in son kalibrasyon tarihini güncelleyecek
                messages.success(request, f'Kalibrasyon kaydı başarıyla eklendi.')
                return redirect('stokapp:olcu_aleti_duzenle', pk=alet.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KalibrasyonKaydiForm()
    
    return render(request, 'stokapp/kalibrasyon_ekle.html', {
        'form': form,
        'alet': alet,
        'kalibrasyonlar': alet.kalibrasyonlar.all().order_by('-kalibrasyon_tarihi')[:10]
    })


@login_required
def olcu_aleti_dashboard(request):
    """Ölçü aletleri dashboard - uyarı sistemi"""
    bugun = date.today()
    
    # Tüm aktif ölçü aletleri
    aletler = OlcuAleti.objects.filter(aktif=True).select_related('alet_turu').order_by('sonraki_kalibrasyon_tarihi')
    
    # Durumlara göre kategorize et
    saglikli = []
    yaklasiyor = []
    acil = []
    gecmis = []
    bilinmiyor = []
    
    for alet in aletler:
        durum = alet.kalibrasyon_durumu()
        if durum == 'SAGLIKLI':
            saglikli.append(alet)
        elif durum == 'YAKLASIYOR':
            yaklasiyor.append(alet)
        elif durum == 'ACIL':
            acil.append(alet)
        elif durum == 'GECMIS':
            gecmis.append(alet)
        else:
            bilinmiyor.append(alet)
    
    context = {
        'saglikli': saglikli,
        'yaklasiyor': yaklasiyor,
        'acil': acil,
        'gecmis': gecmis,
        'bilinmiyor': bilinmiyor,
        'toplam': len(aletler),
    }
    return render(request, 'stokapp/olcu_aleti_dashboard.html', context)


@login_required
def olcu_aleti_export_pdf(request):
    """Ölçü aletleri listesini PDF olarak dışa aktar"""
    global WEASYPRINT_AVAILABLE
    
    # WeasyPrint kontrolü
    if WEASYPRINT_AVAILABLE is None:
        try:
            from weasyprint import HTML, CSS
            WEASYPRINT_AVAILABLE = True
        except ImportError:
            WEASYPRINT_AVAILABLE = False
    
    if not WEASYPRINT_AVAILABLE:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:olcu_aleti_listesi')
    
    from weasyprint import HTML, CSS
    
    # Tüm ölçü aletlerini al
    aletler = OlcuAleti.objects.select_related('alet_turu').order_by('device_id', 'seri_no')
    
    # Her alet için kalibrasyon durumunu hesapla
    for alet in aletler:
        cal_date = alet.next_calibration_date or alet.sonraki_kalibrasyon_tarihi
        if cal_date:
            fark = (cal_date - date.today()).days
            if fark < 0:
                alet.kalibrasyon_durumu_calculated = 'GECMIS'
            elif fark <= 7:
                alet.kalibrasyon_durumu_calculated = 'ACIL'
            elif fark <= 30:
                alet.kalibrasyon_durumu_calculated = 'YAKLASIYOR'
            else:
                alet.kalibrasyon_durumu_calculated = 'SAGLIKLI'
        else:
            alet.kalibrasyon_durumu_calculated = 'BILINMIYOR'
    
    context = {
        'aletler': aletler,
        'olusturma_tarihi': date.today(),
    }
    
    # Template'i yükle
    template = get_template('stokapp/olcu_aleti_export_pdf.html')
    html = template.render(context)
    
    # PDF oluştur
    try:
        base_url = request.build_absolute_uri('/')
        html_obj = HTML(string=html, base_url=base_url)
        
        css = CSS(string="""
            @page {
                size: A4 landscape;
                margin: 10mm;
            }
            body {
                font-family: 'DejaVu Sans', Arial, sans-serif;
                font-size: 9pt;
            }
            h1 {
                text-align: center;
                color: #1f2937;
                margin-bottom: 20px;
                font-size: 18pt;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }
            th {
                background-color: #3b82f6;
                color: white;
                padding: 8px;
                text-align: left;
                border: 1px solid #2563eb;
                font-weight: bold;
                font-size: 8pt;
            }
            td {
                padding: 6px;
                border: 1px solid #d1d5db;
                font-size: 8pt;
            }
            tr:nth-child(even) {
                background-color: #f9fafb;
            }
            .status-active { color: #22c55e; font-weight: bold; }
            .status-blocked { color: #ef4444; font-weight: bold; }
            .status-out-of-service { color: #6b7280; font-weight: bold; }
            .kalibrasyon-saglikli { color: #22c55e; }
            .kalibrasyon-yaklasiyor { color: #eab308; }
            .kalibrasyon-acil { color: #f97316; }
            .kalibrasyon-gecmis { color: #ef4444; font-weight: bold; }
        """)
        
        pdf_file = html_obj.write_pdf(stylesheets=[css])
        
        # HTTP Response olarak döndür
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="olcu_aletleri_listesi_{date.today().strftime("%Y%m%d")}.pdf"'
        return response
        
    except Exception as e:
        messages.error(request, f'PDF oluşturulurken hata oluştu: {str(e)}')
        return redirect('stokapp:olcu_aleti_listesi')

