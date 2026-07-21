from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.http import FileResponse, Http404
from .models import UretimStandarti, UretimStandartiArsiv
from .forms import UretimStandartiForm, UretimStandartiRevizyonForm


@login_required
def uretim_standarti_listesi(request):
    """Üretim Standart listesi"""
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    search_query = request.GET.get('search', '').strip()
    
    if hepsini_goster:
        standartlar = UretimStandarti.objects.all().order_by('sira', 'kod')
    else:
        standartlar = UretimStandarti.objects.filter(aktif=True).order_by('sira', 'kod')
    
    # Arama filtresi
    if search_query:
        standartlar = standartlar.filter(
            Q(kod__icontains=search_query) |
            Q(ad__icontains=search_query) |
            Q(aciklama__icontains=search_query)
        )
    
    context = {
        'standartlar': standartlar,
        'hepsini_goster': hepsini_goster,
        'search_query': search_query,
    }
    return render(request, 'stokapp/uretim_standarti_listesi.html', context)


@login_required
def uretim_standarti_ekle(request):
    """Yeni üretim standartı ekle"""
    if request.method == 'POST':
        form = UretimStandartiForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                standart = form.save()
                messages.success(request, f'Üretim standartı "{standart.kod}" başarıyla eklendi.')
                return redirect('stokapp:uretim_standarti_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = UretimStandartiForm()
        # Varsayılan olusturma_tarihi bugün
        form.fields['olusturma_tarihi'].initial = timezone.now().date()
    
    return render(request, 'stokapp/uretim_standarti_ekle.html', {'form': form})


@login_required
def uretim_standarti_detay(request, pk):
    """Üretim standart detay sayfası - arşivlenmiş versiyonlar dahil"""
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    # Arşivlenmiş versiyonları getir
    arsivlenmis_versiyonlar = UretimStandartiArsiv.objects.filter(standart=standart).order_by('-revizyon_tarihi')
    
    # Revizyon formu
    revizyon_form = UretimStandartiRevizyonForm()
    
    context = {
        'standart': standart,
        'arsivlenmis_versiyonlar': arsivlenmis_versiyonlar,
        'revizyon_form': revizyon_form,
    }
    return render(request, 'stokapp/uretim_standarti_detay.html', context)


@login_required
def uretim_standarti_duzenle(request, pk):
    """Üretim standart düzenle"""
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    if request.method == 'POST':
        form = UretimStandartiForm(request.POST, request.FILES, instance=standart)
        if form.is_valid():
            try:
                standart = form.save()
                messages.success(request, f'Üretim standartı "{standart.kod}" güncellendi.')
                return redirect('stokapp:uretim_standarti_detay', pk=standart.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = UretimStandartiForm(instance=standart)
    
    context = {
        'form': form,
        'standart': standart,
    }
    return render(request, 'stokapp/uretim_standarti_duzenle.html', context)


@login_required
def uretim_standarti_revizyon_ekle(request, pk):
    """Standart revizyon ekle - önceki versiyonu arşive alır"""
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    if request.method == 'POST':
        form = UretimStandartiRevizyonForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Eğer mevcut PDF ve revizyon bilgileri varsa, önceki versiyonu arşive al
                    if standart.pdf_dosya and (standart.revizyon_tarihi or standart.created_at):
                        arsiv = UretimStandartiArsiv.objects.create(
                            standart=standart,
                            pdf_dosya=standart.pdf_dosya,
                            revizyon_tarihi=standart.revizyon_tarihi or standart.olusturma_tarihi,
                            revizyon_aciklama=standart.revizyon_aciklama or 'İlk versiyon'
                        )
                    
                    # Yeni versiyonu kaydet
                    standart.pdf_dosya = form.cleaned_data['yeni_pdf_dosya']
                    standart.revizyon_tarihi = form.cleaned_data['revizyon_tarihi']
                    standart.revizyon_aciklama = form.cleaned_data['revizyon_aciklama']
                    standart.save()
                    
                messages.success(request, f'Standart "{standart.kod}" başarıyla revize edildi.')
                return redirect('stokapp:uretim_standarti_detay', pk=standart.pk)
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = UretimStandartiRevizyonForm()
        form.fields['revizyon_tarihi'].initial = timezone.now().date()
    
    context = {
        'form': form,
        'standart': standart,
    }
    return render(request, 'stokapp/uretim_standarti_revizyon_ekle.html', context)


@login_required
def uretim_standarti_sil(request, pk):
    """Üretim standart sil"""
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    if request.method == 'POST':
        try:
            standart_kodu = standart.kod
            standart.delete()
            messages.success(request, f'Üretim standartı "{standart_kodu}" silindi.')
            return redirect('stokapp:uretim_standarti_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'standart': standart,
    }
    return render(request, 'stokapp/uretim_standarti_sil.html', context)


@login_required
def uretim_standarti_pdf_indir(request, pk):
    """Standart PDF dosyasını indir"""
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    if not standart.pdf_dosya:
        raise Http404("PDF dosyası bulunamadı.")
    
    try:
        return FileResponse(
            standart.pdf_dosya.open(),
            as_attachment=True,
            filename=standart.pdf_dosya.name.split('/')[-1]
        )
    except Exception as e:
        messages.error(request, f'PDF dosyası açılırken hata oluştu: {str(e)}')
        return redirect('stokapp:uretim_standarti_detay', pk=pk)


@login_required
def uretim_standarti_pdf_sil(request, pk):
    """Standart üzerindeki mevcut PDF dosyasını siler."""
    standart = get_object_or_404(UretimStandarti, pk=pk)

    if request.method != "POST":
        messages.error(request, "Geçersiz istek.")
        return redirect("stokapp:uretim_standarti_duzenle", pk=pk)

    if not standart.pdf_dosya:
        messages.warning(request, "Silinecek PDF dosyası bulunamadı.")
        return redirect("stokapp:uretim_standarti_duzenle", pk=pk)

    try:
        standart.pdf_dosya.delete(save=False)
        standart.pdf_dosya = None
        standart.save(update_fields=["pdf_dosya"])
        messages.success(request, f'"{standart.kod}" için PDF dosyası silindi.')
    except Exception as e:
        messages.error(request, f'PDF silinirken hata oluştu: {str(e)}')

    return redirect("stokapp:uretim_standarti_duzenle", pk=pk)


@login_required
def uretim_standarti_arsiv_pdf_indir(request, pk):
    """Arşivlenmiş standart PDF dosyasını indir"""
    arsiv = get_object_or_404(UretimStandartiArsiv, pk=pk)
    
    if not arsiv.pdf_dosya:
        raise Http404("PDF dosyası bulunamadı.")
    
    try:
        return FileResponse(
            arsiv.pdf_dosya.open(),
            as_attachment=True,
            filename=arsiv.pdf_dosya.name.split('/')[-1]
        )
    except Exception as e:
        messages.error(request, f'PDF dosyası açılırken hata oluştu: {str(e)}')
        return redirect('stokapp:uretim_standarti_detay', pk=arsiv.standart.pk)


@login_required
def uretim_standarti_durum_degistir(request, pk):
    """Üretim standart aktif/pasif durumunu değiştir (AJAX)"""
    from django.http import JsonResponse
    standart = get_object_or_404(UretimStandarti, pk=pk)
    
    if request.method == 'POST':
        try:
            standart.aktif = not standart.aktif
            standart.save()
            return JsonResponse({
                'success': True,
                'aktif': standart.aktif
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

