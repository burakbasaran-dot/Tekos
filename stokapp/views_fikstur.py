from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from .models import Fikstur
from .forms import FiksturForm


@login_required
def fikstur_listesi(request):
    """Fikstür listesi - kutucuk görünümü"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    
    if hepsini_goster:
        fiksturler = Fikstur.objects.all().order_by('sira', 'fikstur_numarasi')
    else:
        fiksturler = Fikstur.objects.filter(aktif=True).order_by('sira', 'fikstur_numarasi')
    
    context = {
        'fiksturler': fiksturler,
        'hepsini_goster': hepsini_goster,
    }
    return render(request, 'stokapp/fikstur_listesi.html', context)


@login_required
def fikstur_ekle(request):
    """Yeni fikstür ekle"""
    if request.method == 'POST':
        form = FiksturForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                fikstur = form.save(commit=False)
                # Eğer aktif alanı POST'ta yoksa (checkbox işaretlenmemişse) True yap
                if 'aktif' not in request.POST:
                    fikstur.aktif = True
                fikstur.save()
                messages.success(request, f'Fikstür "{fikstur.ad}" başarıyla eklendi.')
                return redirect('stokapp:fikstur_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = FiksturForm()
        # Varsayılan olarak aktif=True
        form.fields['aktif'].initial = True
    
    return render(request, 'stokapp/fikstur_ekle.html', {'form': form})


@login_required
def fikstur_duzenle(request, pk):
    """Fikstür düzenle"""
    fikstur = get_object_or_404(Fikstur, pk=pk)
    
    if request.method == 'POST':
        form = FiksturForm(request.POST, request.FILES, instance=fikstur)
        if form.is_valid():
            try:
                fikstur = form.save(commit=False)
                # Eğer aktif alanı POST'ta yoksa (checkbox işaretlenmemişse) True yap
                if 'aktif' not in request.POST:
                    fikstur.aktif = True
                fikstur.save()
                messages.success(request, f'Fikstür "{fikstur.ad}" güncellendi.')
                return redirect('stokapp:fikstur_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = FiksturForm(instance=fikstur)
        # Mevcut depo varsa rafları yükle
        if fikstur.depo:
            from .models import Raf
            form.fields['raf'].queryset = Raf.objects.filter(depo=fikstur.depo).order_by('ad')
    
    context = {
        'form': form,
        'fikstur': fikstur,
    }
    return render(request, 'stokapp/fikstur_duzenle.html', context)


@login_required
def fikstur_sil(request, pk):
    """Fikstür sil"""
    fikstur = get_object_or_404(Fikstur, pk=pk)
    
    if request.method == 'POST':
        try:
            fikstur_adi = fikstur.ad
            fikstur.delete()
            messages.success(request, f'Fikstür "{fikstur_adi}" silindi.')
            return redirect('stokapp:fikstur_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'fikstur': fikstur,
    }
    return render(request, 'stokapp/fikstur_sil.html', context)


@login_required
def fikstur_durum_degistir(request, pk):
    """Fikstür aktif/pasif durumunu değiştir (AJAX)"""
    fikstur = get_object_or_404(Fikstur, pk=pk)
    
    if request.method == 'POST':
        try:
            fikstur.aktif = not fikstur.aktif
            fikstur.save()
            return JsonResponse({
                'success': True,
                'aktif': fikstur.aktif
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

