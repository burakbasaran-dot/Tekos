from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Depo, Raf, StokItem
from django import forms


class DepoForm(forms.ModelForm):
    class Meta:
        model = Depo
        fields = ['ad']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Depo adı giriniz...'
            })
        }


class RafForm(forms.ModelForm):
    class Meta:
        model = Raf
        fields = ['depo', 'ad']
        widgets = {
            'depo': forms.Select(attrs={'class': 'form-control'}),
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Raf adı giriniz...'
            })
        }


@login_required
def depo_listesi(request):
    """Depo listesi"""
    depolar = Depo.objects.all().order_by('ad')
    
    # Her depo için raf sayısı ve stok sayısı
    depo_bilgileri = []
    for depo in depolar:
        raf_sayisi = depo.raflar.count()
        stok_sayisi = StokItem.objects.filter(depo=depo).count()
        depo_bilgileri.append({
            'depo': depo,
            'raf_sayisi': raf_sayisi,
            'stok_sayisi': stok_sayisi
        })
    
    context = {
        'depo_bilgileri': depo_bilgileri,
    }
    return render(request, 'stokapp/depo_listesi.html', context)


@login_required
def depo_ekle(request):
    """Yeni depo ekle"""
    if request.method == 'POST':
        form = DepoForm(request.POST)
        if form.is_valid():
            try:
                depo = form.save()
                messages.success(request, f'Depo "{depo.ad}" başarıyla eklendi.')
                return redirect('stokapp:depo_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DepoForm()
    
    return render(request, 'stokapp/depo_ekle.html', {'form': form})


@login_required
def depo_duzenle(request, pk):
    """Depo düzenle"""
    depo = get_object_or_404(Depo, pk=pk)
    
    if request.method == 'POST':
        form = DepoForm(request.POST, instance=depo)
        if form.is_valid():
            try:
                depo = form.save()
                messages.success(request, f'Depo "{depo.ad}" güncellendi.')
                return redirect('stokapp:depo_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = DepoForm(instance=depo)
    
    # Bu depodaki raflar
    raflar = depo.raflar.all().order_by('ad')
    stoklar = StokItem.objects.filter(depo=depo)
    
    context = {
        'form': form,
        'depo': depo,
        'raflar': raflar,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/depo_duzenle.html', context)


@login_required
def depo_sil(request, pk):
    """Depo sil"""
    depo = get_object_or_404(Depo, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(depo=depo).count()
    raf_sayisi = depo.raflar.count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Depodaki stokların depo bilgisini temizle
                StokItem.objects.filter(depo=depo).update(depo=None, raf=None)
                # Depoyu sil (raflar cascade ile silinecek)
                depo_adi = depo.ad
                depo.delete()
                messages.success(request, f'Depo "{depo_adi}" silindi.')
                return redirect('stokapp:depo_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:depo_duzenle', pk=pk)
    
    context = {
        'depo': depo,
        'stok_sayisi': stok_sayisi,
        'raf_sayisi': raf_sayisi,
    }
    return render(request, 'stokapp/depo_sil.html', context)


@login_required
def raf_listesi(request):
    """Raf listesi"""
    raflar = Raf.objects.all().select_related('depo').order_by('depo__ad', 'ad')
    
    # Filtreleme
    depo_id = request.GET.get('depo_id')
    if depo_id:
        raflar = raflar.filter(depo_id=depo_id)
    
    # Her raf için stok sayısı
    raf_bilgileri = []
    for raf in raflar:
        stok_sayisi = StokItem.objects.filter(raf=raf).count()
        raf_bilgileri.append({
            'raf': raf,
            'stok_sayisi': stok_sayisi
        })
    
    depolar = Depo.objects.all().order_by('ad')
    
    context = {
        'raf_bilgileri': raf_bilgileri,
        'depolar': depolar,
        'secili_depo': int(depo_id) if depo_id else None,
    }
    return render(request, 'stokapp/raf_listesi.html', context)


@login_required
def raf_ekle(request):
    """Yeni raf ekle"""
    if request.method == 'POST':
        form = RafForm(request.POST)
        if form.is_valid():
            try:
                raf = form.save()
                messages.success(request, f'Raf "{raf.ad}" başarıyla eklendi.')
                return redirect('stokapp:raf_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = RafForm()
    
    return render(request, 'stokapp/raf_ekle.html', {'form': form})


@login_required
def raf_duzenle(request, pk):
    """Raf düzenle"""
    raf = get_object_or_404(Raf, pk=pk)
    
    if request.method == 'POST':
        form = RafForm(request.POST, instance=raf)
        if form.is_valid():
            try:
                raf = form.save()
                messages.success(request, f'Raf "{raf.ad}" güncellendi.')
                return redirect('stokapp:raf_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = RafForm(instance=raf)
    
    # Bu raftaki stoklar
    stoklar = StokItem.objects.filter(raf=raf)
    
    context = {
        'form': form,
        'raf': raf,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/raf_duzenle.html', context)


@login_required
def raf_sil(request, pk):
    """Raf sil"""
    raf = get_object_or_404(Raf, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(raf=raf).count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Raftaki stokların raf bilgisini temizle
                StokItem.objects.filter(raf=raf).update(raf=None)
                # Rafı sil
                raf_adi = raf.ad
                depo_adi = raf.depo.ad
                raf.delete()
                messages.success(request, f'Raf "{raf_adi}" ({depo_adi} deposu) silindi.')
                return redirect('stokapp:raf_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:raf_duzenle', pk=pk)
    
    context = {
        'raf': raf,
        'stok_sayisi': stok_sayisi,
    }
    return render(request, 'stokapp/raf_sil.html', context)