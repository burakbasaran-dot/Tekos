from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import ParaBirimi, StokItem
from django import forms


class ParaBirimiForm(forms.ModelForm):
    class Meta:
        model = ParaBirimi
        fields = ['kod', 'ad', 'sembol', 'aktif']
        widgets = {
            'kod': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Para birimi kodu (örn: TL, USD, EUR)...'
            }),
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Para birimi adı (örn: Türk Lirası)...'
            }),
            'sembol': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Para birimi sembolü (örn: ₺, $, €)...'
            }),
            'aktif': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }


@login_required
def para_birimi_listesi(request):
    """Para birimi listesi"""
    # En çok kullanılan para birimlerini otomatik oluştur (eğer yoksa)
    populer_para_birimleri = [
        {'kod': 'TL', 'ad': 'Türk Lirası', 'sembol': '₺'},
        {'kod': 'USD', 'ad': 'Amerikan Doları', 'sembol': '$'},
        {'kod': 'EUR', 'ad': 'Euro', 'sembol': '€'},
        {'kod': 'GBP', 'ad': 'İngiliz Sterlini', 'sembol': '£'},
        {'kod': 'JPY', 'ad': 'Japon Yeni', 'sembol': '¥'},
    ]
    
    for pb in populer_para_birimleri:
        ParaBirimi.objects.get_or_create(
            kod=pb['kod'],
            defaults={
                'ad': pb['ad'],
                'sembol': pb['sembol'],
                'aktif': True
            }
        )
    
    para_birimleri = ParaBirimi.objects.all().order_by('kod')
    
    # Her para birimi için stok sayısı
    para_birimi_bilgileri = []
    for para_birimi in para_birimleri:
        stok_sayisi = StokItem.objects.filter(alis_para_birimi=para_birimi.kod).count()
        para_birimi_bilgileri.append({
            'para_birimi': para_birimi,
            'stok_sayisi': stok_sayisi
        })
    
    context = {
        'para_birimi_bilgileri': para_birimi_bilgileri,
    }
    return render(request, 'stokapp/para_birimi_listesi.html', context)


@login_required
def para_birimi_ekle(request):
    """Yeni para birimi ekle"""
    if request.method == 'POST':
        form = ParaBirimiForm(request.POST)
        if form.is_valid():
            try:
                para_birimi = form.save()
                messages.success(request, f'Para birimi "{para_birimi.ad}" başarıyla eklendi.')
                return redirect('stokapp:para_birimi_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = ParaBirimiForm()
    
    return render(request, 'stokapp/para_birimi_ekle.html', {'form': form})


@login_required
def para_birimi_duzenle(request, pk):
    """Para birimi düzenle"""
    para_birimi = get_object_or_404(ParaBirimi, pk=pk)
    
    if request.method == 'POST':
        form = ParaBirimiForm(request.POST, instance=para_birimi)
        if form.is_valid():
            try:
                para_birimi = form.save()
                messages.success(request, f'Para birimi "{para_birimi.ad}" güncellendi.')
                return redirect('stokapp:para_birimi_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = ParaBirimiForm(instance=para_birimi)
    
    # Bu para birimini kullanan stoklar
    stoklar = StokItem.objects.filter(alis_para_birimi=para_birimi.kod)
    
    context = {
        'form': form,
        'para_birimi': para_birimi,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/para_birimi_duzenle.html', context)


@login_required
def para_birimi_sil(request, pk):
    """Para birimi sil"""
    para_birimi = get_object_or_404(ParaBirimi, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(alis_para_birimi=para_birimi.kod).count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if stok_sayisi > 0:
                    messages.error(request, f'Bu para birimi {stok_sayisi} adet stokta kullanılıyor. Önce stokları başka bir para birimine taşıyın.')
                    return redirect('stokapp:para_birimi_duzenle', pk=pk)
                
                para_birimi_adi = para_birimi.ad
                para_birimi.delete()
                messages.success(request, f'Para birimi "{para_birimi_adi}" silindi.')
                return redirect('stokapp:para_birimi_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:para_birimi_duzenle', pk=pk)
    
    context = {
        'para_birimi': para_birimi,
        'stok_sayisi': stok_sayisi,
    }
    return render(request, 'stokapp/para_birimi_sil.html', context)
