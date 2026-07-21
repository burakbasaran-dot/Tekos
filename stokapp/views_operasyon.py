from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from .models import Operasyon
from .forms import OperasyonForm


@login_required
def operasyon_listesi(request):
    """Operasyon listesi"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    
    if hepsini_goster:
        operasyonlar = Operasyon.objects.all().order_by('sira', 'ad')
    else:
        operasyonlar = Operasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    
    context = {
        'operasyonlar': operasyonlar,
        'hepsini_goster': hepsini_goster,
    }
    return render(request, 'stokapp/operasyon_listesi.html', context)


@login_required
def operasyon_ekle(request):
    """Yeni operasyon ekle"""
    if request.method == 'POST':
        form = OperasyonForm(request.POST)
        if form.is_valid():
            try:
                operasyon = form.save()
                messages.success(request, f'Operasyon "{operasyon.ad}" başarıyla eklendi.')
                return redirect('stokapp:operasyon_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OperasyonForm()
    
    return render(request, 'stokapp/operasyon_ekle.html', {'form': form})


@login_required
def operasyon_duzenle(request, pk):
    """Operasyon düzenle"""
    operasyon = get_object_or_404(Operasyon, pk=pk)
    
    if request.method == 'POST':
        form = OperasyonForm(request.POST, instance=operasyon)
        if form.is_valid():
            try:
                operasyon = form.save()
                messages.success(request, f'Operasyon "{operasyon.ad}" güncellendi.')
                return redirect('stokapp:operasyon_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = OperasyonForm(instance=operasyon)
    
    context = {
        'form': form,
        'operasyon': operasyon,
    }
    return render(request, 'stokapp/operasyon_duzenle.html', context)


@login_required
def operasyon_sil(request, pk):
    """Operasyon sil"""
    operasyon = get_object_or_404(Operasyon, pk=pk)
    
    if request.method == 'POST':
        try:
            operasyon_adi = operasyon.ad
            operasyon.delete()
            messages.success(request, f'Operasyon "{operasyon_adi}" silindi.')
            return redirect('stokapp:operasyon_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'operasyon': operasyon,
    }
    return render(request, 'stokapp/operasyon_sil.html', context)


@login_required
def operasyon_durum_degistir(request, pk):
    """Operasyon aktif/pasif durumunu değiştir (AJAX)"""
    operasyon = get_object_or_404(Operasyon, pk=pk)
    
    if request.method == 'POST':
        try:
            operasyon.aktif = not operasyon.aktif
            operasyon.save()
            return JsonResponse({
                'success': True,
                'aktif': operasyon.aktif
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})
