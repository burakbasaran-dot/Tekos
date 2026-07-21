from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from .models import Sigorta
from .forms import SigortaForm


@login_required
def sigorta_listesi(request):
    """Sigorta poliçe listesi"""
    arsivli = request.GET.get('arsivli', 'false') == 'true'
    
    if arsivli:
        sigortalar = Sigorta.objects.filter(arsivlendi=True).order_by('-police_bitis_tarihi', 'varlik_adi')
        sayfa_basligi = "Arşivlenmiş Sigortalar"
    else:
        sigortalar = Sigorta.objects.filter(arsivlendi=False).order_by('-police_bitis_tarihi', 'varlik_adi')
        sayfa_basligi = "Sigortalar"
    
    # Süresi dolan poliçeleri işaretle
    for sigorta in sigortalar:
        sigorta.suresi_doldu = sigorta.suresi_doldu_mu()
    
    context = {
        'sigortalar': sigortalar,
        'arsivli': arsivli,
        'sayfa_basligi': sayfa_basligi,
    }
    return render(request, 'stokapp/sigorta_listesi.html', context)


@login_required
def sigorta_ekle(request):
    """Yeni sigorta poliçesi ekle"""
    if request.method == 'POST':
        form = SigortaForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                sigorta = form.save()
                messages.success(request, f'Sigorta poliçesi "{sigorta.varlik_adi}" başarıyla eklendi.')
                return redirect('stokapp:sigorta_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = SigortaForm()
    
    return render(request, 'stokapp/sigorta_ekle.html', {'form': form})


@login_required
def sigorta_duzenle(request, pk):
    """Sigorta poliçesi düzenle"""
    sigorta = get_object_or_404(Sigorta, pk=pk)
    
    if request.method == 'POST':
        form = SigortaForm(request.POST, request.FILES, instance=sigorta)
        if form.is_valid():
            try:
                sigorta = form.save()
                messages.success(request, f'Sigorta poliçesi "{sigorta.varlik_adi}" güncellendi.')
                return redirect('stokapp:sigorta_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = SigortaForm(instance=sigorta)
    
    sigorta.suresi_doldu = sigorta.suresi_doldu_mu()
    
    context = {
        'form': form,
        'sigorta': sigorta,
    }
    return render(request, 'stokapp/sigorta_duzenle.html', context)


@login_required
def sigorta_arsivle(request, pk):
    """Sigorta poliçesini arşivle"""
    sigorta = get_object_or_404(Sigorta, pk=pk)
    
    if request.method == 'POST':
        try:
            sigorta.arsivlendi = True
            sigorta.save()
            messages.success(request, f'Sigorta poliçesi "{sigorta.varlik_adi}" arşivlendi.')
            return redirect('stokapp:sigorta_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    sigorta.suresi_doldu = sigorta.suresi_doldu_mu()
    
    context = {
        'sigorta': sigorta,
    }
    return render(request, 'stokapp/sigorta_arsivle.html', context)


@login_required
def sigorta_sil(request, pk):
    """Sigorta poliçesi sil"""
    sigorta = get_object_or_404(Sigorta, pk=pk)
    
    # Arşivli parametresini hem GET hem POST'tan kontrol et
    arsivli = request.GET.get('arsivli', 'false') == 'true' or request.POST.get('arsivli') == 'true'
    
    if request.method == 'POST':
        try:
            sigorta_adi = sigorta.varlik_adi
            police_no = sigorta.police_no
            sigorta.delete()
            messages.success(request, f'Sigorta poliçesi "{sigorta_adi}" (Poliçe No: {police_no}) silindi.')
            # Arşivli sayfadaysa arşivli sayfaya, değilse normal sayfaya yönlendir
            from django.urls import reverse
            if arsivli:
                return redirect(reverse('stokapp:sigorta_listesi') + '?arsivli=true')
            return redirect('stokapp:sigorta_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    sigorta.suresi_doldu = sigorta.suresi_doldu_mu()
    
    context = {
        'sigorta': sigorta,
        'arsivli': arsivli,
    }
    return render(request, 'stokapp/sigorta_sil.html', context)
