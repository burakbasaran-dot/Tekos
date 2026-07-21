"""
Skala Suite entegrasyon view fonksiyonları
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from .models import SkalaSuiteEntegrasyon

try:
    from .skala_integration import SkalaSuiteIntegration, REQUESTS_AVAILABLE
    import pandas as pd
    SKALA_AVAILABLE = REQUESTS_AVAILABLE
except ImportError as e:
    SKALA_AVAILABLE = False
    SkalaSuiteIntegration = None
    pd = None

from io import BytesIO


@login_required
def skala_entegrasyon(request):
    """
    Skala Suite entegrasyon ana sayfası
    """
    entegrasyon = SkalaSuiteEntegrasyon.get_ayarlar()
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        aktif = request.POST.get('aktif') == 'on'
        
        if email and password:
            entegrasyon.email = email
            entegrasyon.password = password
            entegrasyon.aktif = aktif
            entegrasyon.save()
            messages.success(request, 'Skala Suite ayarları başarıyla kaydedildi.')
            return redirect('stokapp:skala_entegrasyon')
        else:
            messages.error(request, 'E-posta ve şifre gereklidir.')
    
    context = {
        'entegrasyon': entegrasyon,
    }
    return render(request, 'stokapp/skala_entegrasyon.html', context)


@login_required
def skala_stok_export(request):
    """
    Skala Suite'den stok verilerini çek ve Excel olarak indir
    """
    entegrasyon = SkalaSuiteEntegrasyon.get_ayarlar()
    
    if not entegrasyon.aktif or not entegrasyon.email or not entegrasyon.password:
        messages.error(request, 'Skala Suite entegrasyonu aktif değil veya ayarlar eksik.')
        return redirect('stokapp:skala_entegrasyon')
    
    try:
        # Skala Suite'e bağlan
        skala = SkalaSuiteIntegration(entegrasyon.email, entegrasyon.password)
        
        # Stok verilerini çek
        stock_df = skala.fetch_stock_data()
        
        if stock_df is None or stock_df.empty:
            messages.warning(request, 'Skala Suite\'den stok verisi çekilemedi. Lütfen bağlantıyı kontrol edin.')
            return redirect('stokapp:skala_entegrasyon')
        
        # Excel'e dönüştür
        excel_output = skala.export_to_excel(stock_df=stock_df)
        
        # Son senkronizasyon zamanını güncelle
        entegrasyon.son_stok_senkronizasyon = timezone.now()
        entegrasyon.save()
        
        # HTTP response olarak döndür
        response = HttpResponse(
            excel_output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="skala_stok_export.xlsx"'
        
        messages.success(request, f'{len(stock_df)} adet stok kaydı başarıyla export edildi.')
        return response
        
    except Exception as e:
        messages.error(request, f'Skala Suite stok export hatası: {str(e)}')
        return redirect('stokapp:skala_entegrasyon')


@login_required
def skala_cari_export(request):
    """
    Skala Suite'den cari verilerini çek ve Excel olarak indir
    """
    entegrasyon = SkalaSuiteEntegrasyon.get_ayarlar()
    
    if not entegrasyon.aktif or not entegrasyon.email or not entegrasyon.password:
        messages.error(request, 'Skala Suite entegrasyonu aktif değil veya ayarlar eksik.')
        return redirect('stokapp:skala_entegrasyon')
    
    try:
        # Skala Suite'e bağlan
        skala = SkalaSuiteIntegration(entegrasyon.email, entegrasyon.password)
        
        # Cari verilerini çek
        cari_df = skala.fetch_cari_data()
        
        if cari_df is None or cari_df.empty:
            messages.warning(request, 'Skala Suite\'den cari verisi çekilemedi. Lütfen bağlantıyı kontrol edin.')
            return redirect('stokapp:skala_entegrasyon')
        
        # Excel'e dönüştür
        excel_output = skala.export_to_excel(cari_df=cari_df)
        
        # Son senkronizasyon zamanını güncelle
        entegrasyon.son_cari_senkronizasyon = timezone.now()
        entegrasyon.save()
        
        # HTTP response olarak döndür
        response = HttpResponse(
            excel_output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="skala_cari_export.xlsx"'
        
        messages.success(request, f'{len(cari_df)} adet cari kaydı başarıyla export edildi.')
        return response
        
    except Exception as e:
        messages.error(request, f'Skala Suite cari export hatası: {str(e)}')
        return redirect('stokapp:skala_entegrasyon')


@login_required
def skala_recete_export(request):
    """
    Skala Suite'den reçete verilerini çek ve Excel olarak indir
    """
    entegrasyon = SkalaSuiteEntegrasyon.get_ayarlar()
    
    if not entegrasyon.aktif or not entegrasyon.email or not entegrasyon.password:
        messages.error(request, 'Skala Suite entegrasyonu aktif değil veya ayarlar eksik.')
        return redirect('stokapp:skala_entegrasyon')
    
    try:
        # Skala Suite'e bağlan
        skala = SkalaSuiteIntegration(entegrasyon.email, entegrasyon.password)
        
        # Reçete verilerini çek
        recete_df = skala.fetch_recete_data()
        
        if recete_df is None or recete_df.empty:
            messages.warning(request, 'Skala Suite\'den reçete verisi çekilemedi. Lütfen bağlantıyı kontrol edin.')
            return redirect('stokapp:skala_entegrasyon')
        
        # Excel'e dönüştür
        excel_output = skala.export_to_excel(recete_df=recete_df)
        
        # Son senkronizasyon zamanını güncelle
        entegrasyon.son_recete_senkronizasyon = timezone.now()
        entegrasyon.save()
        
        # HTTP response olarak döndür
        response = HttpResponse(
            excel_output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="skala_recete_export.xlsx"'
        
        messages.success(request, f'{len(recete_df)} adet reçete kaydı başarıyla export edildi.')
        return response
        
    except Exception as e:
        messages.error(request, f'Skala Suite reçete export hatası: {str(e)}')
        return redirect('stokapp:skala_entegrasyon')

