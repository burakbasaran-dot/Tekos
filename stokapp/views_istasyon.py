from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from .models import Istasyon
from .forms import IstasyonForm


@login_required
def istasyon_listesi(request):
    """İstasyon listesi - kutucuk görünümü"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    
    if hepsini_goster:
        istasyonlar = Istasyon.objects.all().order_by('sira', 'ad')
    else:
        istasyonlar = Istasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    
    context = {
        'istasyonlar': istasyonlar,
        'hepsini_goster': hepsini_goster,
    }
    return render(request, 'stokapp/istasyon_listesi.html', context)


@login_required
def istasyon_ekle(request):
    """Yeni istasyon ekle"""
    if request.method == 'POST':
        form = IstasyonForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                istasyon = form.save()
                messages.success(request, f'İstasyon "{istasyon.ad}" başarıyla eklendi.')
                return redirect('stokapp:istasyon_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = IstasyonForm()
    
    return render(request, 'stokapp/istasyon_ekle.html', {'form': form})


@login_required
def istasyon_duzenle(request, pk):
    """İstasyon düzenle"""
    istasyon = get_object_or_404(Istasyon, pk=pk)
    
    if request.method == 'POST':
        form = IstasyonForm(request.POST, request.FILES, instance=istasyon)
        if form.is_valid():
            try:
                istasyon = form.save()
                messages.success(request, f'İstasyon "{istasyon.ad}" güncellendi.')
                return redirect('stokapp:istasyon_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = IstasyonForm(instance=istasyon)
    
    context = {
        'form': form,
        'istasyon': istasyon,
    }
    return render(request, 'stokapp/istasyon_duzenle.html', context)


@login_required
def istasyon_sil(request, pk):
    """İstasyon sil"""
    istasyon = get_object_or_404(Istasyon, pk=pk)
    
    if request.method == 'POST':
        try:
            istasyon_adi = istasyon.ad
            istasyon.delete()
            messages.success(request, f'İstasyon "{istasyon_adi}" silindi.')
            return redirect('stokapp:istasyon_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'istasyon': istasyon,
    }
    return render(request, 'stokapp/istasyon_sil.html', context)


@login_required
def istasyon_durum_degistir(request, pk):
    """İstasyon aktif/pasif durumunu değiştir (AJAX)"""
    istasyon = get_object_or_404(Istasyon, pk=pk)
    
    if request.method == 'POST':
        try:
            istasyon.aktif = not istasyon.aktif
            istasyon.save()
            return JsonResponse({
                'success': True,
                'aktif': istasyon.aktif
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})
