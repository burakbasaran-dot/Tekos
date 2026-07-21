from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from .models import Ekipman
from .forms import EkipmanForm


@login_required
def ekipman_listesi(request):
    """Ekipman listesi - kutucuk görünümü"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    
    if hepsini_goster:
        ekipmanlar = Ekipman.objects.all().order_by('sira', 'ekipman_numarasi')
    else:
        ekipmanlar = Ekipman.objects.filter(aktif=True).order_by('sira', 'ekipman_numarasi')
    
    context = {
        'ekipmanlar': ekipmanlar,
        'hepsini_goster': hepsini_goster,
    }
    return render(request, 'stokapp/ekipman_listesi.html', context)


@login_required
def ekipman_ekle(request):
    """Yeni ekipman ekle"""
    if request.method == 'POST':
        form = EkipmanForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ekipman = form.save(commit=False)
                # Eğer aktif alanı POST'ta yoksa (checkbox işaretlenmemişse) True yap
                if 'aktif' not in request.POST:
                    ekipman.aktif = True
                ekipman.save()
                messages.success(request, f'Ekipman "{ekipman.ad}" başarıyla eklendi.')
                return redirect('stokapp:ekipman_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = EkipmanForm()
        # Varsayılan olarak aktif=True
        form.fields['aktif'].initial = True
    
    return render(request, 'stokapp/ekipman_ekle.html', {'form': form})


@login_required
def ekipman_duzenle(request, pk):
    """Ekipman düzenle"""
    ekipman = get_object_or_404(Ekipman, pk=pk)
    
    if request.method == 'POST':
        form = EkipmanForm(request.POST, request.FILES, instance=ekipman)
        if form.is_valid():
            try:
                ekipman = form.save()
                messages.success(request, f'Ekipman "{ekipman.ad}" güncellendi.')
                return redirect('stokapp:ekipman_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = EkipmanForm(instance=ekipman)
    
    context = {
        'form': form,
        'ekipman': ekipman,
    }
    return render(request, 'stokapp/ekipman_duzenle.html', context)


@login_required
def ekipman_sil(request, pk):
    """Ekipman sil"""
    ekipman = get_object_or_404(Ekipman, pk=pk)
    
    if request.method == 'POST':
        try:
            ekipman_adi = ekipman.ad
            ekipman.delete()
            messages.success(request, f'Ekipman "{ekipman_adi}" silindi.')
            return redirect('stokapp:ekipman_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'ekipman': ekipman,
    }
    return render(request, 'stokapp/ekipman_sil.html', context)


@login_required
def ekipman_durum_degistir(request, pk):
    """Ekipman aktif/pasif durumunu değiştir (AJAX)"""
    ekipman = get_object_or_404(Ekipman, pk=pk)
    
    if request.method == 'POST':
        try:
            ekipman.aktif = not ekipman.aktif
            ekipman.save()
            return JsonResponse({
                'success': True,
                'aktif': ekipman.aktif
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

