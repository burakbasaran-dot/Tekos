from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta
from .models import Personel, GunlukCalisma, AvansOdeme, PersonelIzin, PersonelBelgesi
from .forms import PersonelForm, GunlukCalismaForm, AvansOdemeForm, PersonelIzinForm, PersonelBelgesiForm


@login_required
def personel_listesi(request):
    """Personel listesi"""
    personeller = Personel.objects.filter(aktif=True).order_by('ad', 'soyad')
    
    # Her personel için özet bilgiler
    personel_bilgileri = []
    for personel in personeller:
        toplam_odenecek = personel.toplam_odenecek_tutar()
        toplam_odenen = personel.toplam_odenen_tutar()
        toplam_avans = personel.toplam_avans()
        kalan_bakiye = personel.kalan_bakiye()
        
        personel_bilgileri.append({
            'personel': personel,
            'toplam_odenecek': toplam_odenecek,
            'toplam_odenen': toplam_odenen,
            'toplam_avans': toplam_avans,
            'kalan_bakiye': kalan_bakiye,
        })
    
    context = {
        'personel_bilgileri': personel_bilgileri,
    }
    return render(request, 'stokapp/personel_listesi.html', context)


@login_required
def gunluk_calisma_listesi(request):
    """Günlük çalışma kayıtları listesi"""
    tarih_baslangic = request.GET.get('tarih_baslangic', '')
    tarih_bitis = request.GET.get('tarih_bitis', '')
    personel_id = request.GET.get('personel', '')
    sort_by = request.GET.get('sort', 'tarih')  # Varsayılan sıralama: tarih
    sort_order = request.GET.get('order', 'desc')  # Varsayılan: azalan
    
    calismalar = GunlukCalisma.objects.all()
    avans_odemeler = AvansOdeme.objects.all()
    
    # Filtreleme
    if tarih_baslangic:
        calismalar = calismalar.filter(tarih__gte=tarih_baslangic)
        avans_odemeler = avans_odemeler.filter(tarih__gte=tarih_baslangic)
    if tarih_bitis:
        calismalar = calismalar.filter(tarih__lte=tarih_bitis)
        avans_odemeler = avans_odemeler.filter(tarih__lte=tarih_bitis)
    if personel_id:
        calismalar = calismalar.filter(personel_id=personel_id)
        avans_odemeler = avans_odemeler.filter(personel_id=personel_id)
    
    # Sıralama
    sort_prefix = '-' if sort_order == 'desc' else ''
    
    # Çalışma kayıtları için sıralama
    if sort_by == 'personel':
        calismalar = calismalar.order_by(f'{sort_prefix}personel__ad', f'{sort_prefix}personel__soyad', '-tarih')
    elif sort_by == 'tarih':
        calismalar = calismalar.order_by(f'{sort_prefix}tarih', 'personel__ad')
    elif sort_by == 'calisma_suresi':
        calismalar = calismalar.order_by(f'{sort_prefix}calisma_suresi', '-tarih')
    elif sort_by == 'saat_ucreti':
        calismalar = calismalar.order_by(f'{sort_prefix}saat_ucreti', '-tarih')
    elif sort_by == 'odenecek':
        calismalar = calismalar.order_by(f'{sort_prefix}odenecek_tutar', '-tarih')
    elif sort_by == 'odeme_durumu':
        calismalar = calismalar.order_by(f'{sort_prefix}odeme_durumu', '-tarih')
    elif sort_by == 'odenen':
        calismalar = calismalar.order_by(f'{sort_prefix}odenen_tutar', '-tarih')
    elif sort_by == 'kalan':
        calismalar = calismalar.order_by(f'{sort_prefix}kalan_bakiye', '-tarih')
    else:
        calismalar = calismalar.order_by('-tarih', 'personel__ad')
    
    # Avans ödemeler için sıralama
    if sort_by == 'personel':
        avans_odemeler = avans_odemeler.order_by(f'{sort_prefix}personel__ad', f'{sort_prefix}personel__soyad', '-tarih')
    elif sort_by == 'tarih':
        avans_odemeler = avans_odemeler.order_by(f'{sort_prefix}tarih', 'personel__ad')
    elif sort_by == 'odenen':
        avans_odemeler = avans_odemeler.order_by(f'{sort_prefix}tutar', '-tarih')
    elif sort_by == 'kalan':
        avans_odemeler = avans_odemeler.order_by(f'{sort_prefix}tutar', '-tarih')
    else:
        avans_odemeler = avans_odemeler.order_by('-tarih', 'personel__ad')
    
    # Özet istatistikler
    toplam_calisma_suresi = calismalar.aggregate(Sum('calisma_suresi'))['calisma_suresi__sum'] or 0
    toplam_odenecek = calismalar.aggregate(Sum('odenecek_tutar'))['odenecek_tutar__sum'] or 0
    toplam_odenen_calisma = calismalar.aggregate(Sum('odenen_tutar'))['odenen_tutar__sum'] or 0
    toplam_avans = avans_odemeler.aggregate(Sum('tutar'))['tutar__sum'] or 0
    # Toplam ödenen: çalışma ödemeleri + avans ödemeleri
    toplam_odenen = toplam_odenen_calisma + toplam_avans
    # Kalan hesaplama: toplam ödenecek - toplam ödenen (avans dahil)
    toplam_kalan = toplam_odenecek - toplam_odenen
    toplam_kalan_abs = abs(float(toplam_kalan))
    toplam_kalan_negatif = toplam_kalan < 0
    
    personeller = Personel.objects.filter(aktif=True).order_by('ad', 'soyad')
    
    context = {
        'calismalar': calismalar,
        'avans_odemeler': avans_odemeler,
        'personeller': personeller,
        'tarih_baslangic': tarih_baslangic,
        'tarih_bitis': tarih_bitis,
        'personel_id': personel_id,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'toplam_calisma_suresi': toplam_calisma_suresi,
        'toplam_odenecek': toplam_odenecek,
        'toplam_odenen': toplam_odenen,
        'toplam_avans': toplam_avans,
        'toplam_kalan': toplam_kalan,
        'toplam_kalan_abs': toplam_kalan_abs,
        'toplam_kalan_negatif': toplam_kalan_negatif,
    }
    return render(request, 'stokapp/gunluk_calisma_listesi.html', context)


@login_required
def personel_ekle(request):
    """Yeni personel ekle"""
    if request.method == 'POST':
        form = PersonelForm(request.POST)
        if form.is_valid():
            try:
                personel = form.save()
                messages.success(request, f'Personel "{personel.ad} {personel.soyad}" başarıyla eklendi.')
                return redirect('stokapp:personel_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = PersonelForm()
    
    return render(request, 'stokapp/personel_ekle.html', {'form': form})


@login_required
def personel_duzenle(request, pk):
    """Personel düzenle"""
    personel = get_object_or_404(Personel, pk=pk)
    
    if request.method == 'POST':
        form = PersonelForm(request.POST, instance=personel)
        if form.is_valid():
            try:
                personel = form.save()
                messages.success(request, f'Personel "{personel.ad} {personel.soyad}" güncellendi.')
                return redirect('stokapp:personel_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = PersonelForm(instance=personel)
    
    context = {
        'form': form,
        'personel': personel,
    }
    return render(request, 'stokapp/personel_duzenle.html', context)


@login_required
def personel_detay(request, pk):
    """Personel detay görüntüleme"""
    personel = get_object_or_404(Personel, pk=pk, aktif=True)
    belgeler = personel.belgeler.order_by("yenileme_tarihi", "-created_at")

    context = {
        "personel": personel,
        "belgeler": belgeler,
    }
    return render(request, "stokapp/personel_detay.html", context)


@login_required
def personel_belgeleri(request, pk):
    """Personel belge listesi"""
    personel = get_object_or_404(Personel, pk=pk, aktif=True)
    arsivli = request.GET.get("arsivli", "false") == "true"

    belgeler = personel.belgeler.filter(arsivlendi=arsivli).order_by("yenileme_tarihi", "-created_at")
    context = {
        "personel": personel,
        "belgeler": belgeler,
        "arsivli": arsivli,
    }
    return render(request, "stokapp/personel_belgeleri.html", context)


@login_required
def personel_belgesi_ekle(request, pk):
    personel = get_object_or_404(Personel, pk=pk, aktif=True)
    if request.method == "POST":
        form = PersonelBelgesiForm(request.POST, request.FILES)
        if "personel" in form.fields:
            form.fields["personel"].required = False
        if form.is_valid():
            belge = form.save(commit=False)
            belge.personel = personel
            belge.save()
            messages.success(request, "Personel belgesi eklendi.")
            return redirect("stokapp:personel_belgeleri", pk=personel.pk)
        messages.error(request, "Belge eklenemedi. Alanlari kontrol edin.")
    else:
        form = PersonelBelgesiForm(initial={"personel": personel})
        if "personel" in form.fields:
            form.fields["personel"].required = False
            form.fields["personel"].widget.attrs["disabled"] = True

    return render(request, "stokapp/personel_belgesi_form.html", {"form": form, "personel": personel, "is_edit": False})


@login_required
def personel_belgesi_duzenle(request, pk):
    belge = get_object_or_404(PersonelBelgesi, pk=pk)
    personel = belge.personel
    if request.method == "POST":
        form = PersonelBelgesiForm(request.POST, request.FILES, instance=belge)
        if "personel" in form.fields:
            form.fields["personel"].required = False
        if form.is_valid():
            belge = form.save(commit=False)
            belge.personel = personel
            belge.save()
            messages.success(request, "Personel belgesi guncellendi.")
            return redirect("stokapp:personel_belgeleri", pk=personel.pk)
    else:
        form = PersonelBelgesiForm(instance=belge)
        if "personel" in form.fields:
            form.fields["personel"].required = False
            form.fields["personel"].widget.attrs["disabled"] = True
    return render(request, "stokapp/personel_belgesi_form.html", {"form": form, "personel": personel, "is_edit": True, "belge": belge})


@login_required
def personel_belgesi_arsivle(request, pk):
    belge = get_object_or_404(PersonelBelgesi, pk=pk)
    personel = belge.personel
    if request.method == "POST":
        belge.arsivlendi = True
        belge.save()
        messages.success(request, "Belge arsivlendi.")
        return redirect("stokapp:personel_belgeleri", pk=personel.pk)
    return render(request, "stokapp/personel_belgesi_arsivle.html", {"belge": belge, "personel": personel})


@login_required
def personel_belgesi_sil(request, pk):
    belge = get_object_or_404(PersonelBelgesi, pk=pk)
    personel = belge.personel
    arsivli = request.GET.get("arsivli", "false") == "true" or request.POST.get("arsivli") == "true"
    if request.method == "POST":
        belge.delete()
        messages.success(request, "Belge silindi.")
        if arsivli:
            return redirect(reverse("stokapp:personel_belgeleri", kwargs={"pk": personel.pk}) + "?arsivli=true")
        return redirect("stokapp:personel_belgeleri", pk=personel.pk)
    return render(request, "stokapp/personel_belgesi_sil.html", {"belge": belge, "personel": personel, "arsivli": arsivli})


@login_required
def gunluk_calisma_ekle(request):
    """Yeni günlük çalışma kaydı ekle"""
    if request.method == 'POST':
        form = GunlukCalismaForm(request.POST)
        if form.is_valid():
            try:
                calisma = form.save()
                messages.success(request, f'Günlük çalışma kaydı başarıyla eklendi.')
                return redirect('stokapp:gunluk_calisma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
        else:
            # Form hatalarını göster
            # Non-field errors (genel hatalar)
            for error in form.non_field_errors():
                messages.error(request, f'{error}')
            # Field-specific errors
            for field, errors in form.errors.items():
                if field in form.fields:
                    for error in errors:
                        messages.error(request, f'{form.fields[field].label}: {error}')
                else:
                    # Field form'da yoksa direkt hata mesajını göster
                    for error in errors:
                        messages.error(request, f'{error}')
    else:
        form = GunlukCalismaForm()
        # Varsayılan tarih bugün
        form.fields['tarih'].initial = timezone.now().date()
    
    return render(request, 'stokapp/gunluk_calisma_ekle.html', {'form': form})


@login_required
def gunluk_calisma_duzenle(request, pk):
    """Günlük çalışma kaydı düzenle"""
    calisma = get_object_or_404(GunlukCalisma, pk=pk)
    
    if request.method == 'POST':
        form = GunlukCalismaForm(request.POST, instance=calisma)
        if form.is_valid():
            try:
                calisma = form.save()
                messages.success(request, f'Günlük çalışma kaydı güncellendi.')
                return redirect('stokapp:gunluk_calisma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = GunlukCalismaForm(instance=calisma)
    
    context = {
        'form': form,
        'calisma': calisma,
    }
    return render(request, 'stokapp/gunluk_calisma_duzenle.html', context)


@login_required
def gunluk_calisma_sil(request, pk):
    """Günlük çalışma kaydı sil"""
    calisma = get_object_or_404(GunlukCalisma, pk=pk)
    
    if request.method == 'POST':
        try:
            calisma.delete()
            messages.success(request, 'Günlük çalışma kaydı silindi.')
            return redirect('stokapp:gunluk_calisma_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'calisma': calisma,
    }
    return render(request, 'stokapp/gunluk_calisma_sil.html', context)


@login_required
def avans_odeme_ekle(request):
    """Yeni avans ödeme ekle"""
    if request.method == 'POST':
        form = AvansOdemeForm(request.POST)
        if form.is_valid():
            try:
                avans = form.save()
                messages.success(request, f'Avans ödeme kaydı başarıyla eklendi.')
                return redirect('stokapp:gunluk_calisma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = AvansOdemeForm()
        form.fields['tarih'].initial = timezone.now().date()
    
    return render(request, 'stokapp/avans_odeme_ekle.html', {'form': form})


@login_required
def avans_odeme_duzenle(request, pk):
    """Avans ödeme düzenle"""
    avans = get_object_or_404(AvansOdeme, pk=pk)
    
    if request.method == 'POST':
        form = AvansOdemeForm(request.POST, instance=avans)
        if form.is_valid():
            try:
                avans = form.save()
                messages.success(request, f'Avans ödeme kaydı güncellendi.')
                return redirect('stokapp:gunluk_calisma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = AvansOdemeForm(instance=avans)
    
    context = {
        'form': form,
        'avans': avans,
    }
    return render(request, 'stokapp/avans_odeme_duzenle.html', context)


@login_required
def avans_odeme_sil(request, pk):
    """Avans ödeme sil"""
    avans = get_object_or_404(AvansOdeme, pk=pk)
    
    if request.method == 'POST':
        try:
            avans.delete()
            messages.success(request, 'Avans ödeme kaydı silindi.')
            return redirect('stokapp:gunluk_calisma_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'avans': avans,
    }
    return render(request, 'stokapp/avans_odeme_sil.html', context)


@login_required
def personel_izin_listesi(request):
    """Personel izin kayıtları listesi ve yeni kayıt ekleme"""
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    izinler_qs = PersonelIzin.objects.select_related("personel").order_by("-baslangic_zamani")
    personel_id = request.GET.get("personel", "").strip()
    tarih_baslangic = request.GET.get("tarih_baslangic", "").strip()
    tarih_bitis = request.GET.get("tarih_bitis", "").strip()

    filtered = izinler_qs
    if personel_id:
        try:
            filtered = filtered.filter(personel_id=int(personel_id))
        except ValueError:
            pass
    if tarih_baslangic:
        filtered = filtered.filter(baslangic_zamani__date__gte=tarih_baslangic)
    if tarih_bitis:
        filtered = filtered.filter(baslangic_zamani__date__lte=tarih_bitis)

    toplam_kayit = filtered.count()
    aktif_izin_sayisi = filtered.filter(
        baslangic_zamani__lte=now, bitis_zamani__gte=now
    ).count()
    yaklasan_bitis_sayisi = filtered.filter(
        bitis_zamani__gte=now,
        bitis_zamani__lte=now + timedelta(days=7),
    ).count()

    if request.method == "POST":
        form = PersonelIzinForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Personel izin kaydı eklendi.")
            return redirect("stokapp:personel_izin_listesi")
        messages.error(request, "İzin kaydı eklenemedi. Lütfen alanları kontrol edin.")
    else:
        form = PersonelIzinForm()

    personeller = Personel.objects.filter(aktif=True).order_by("ad", "soyad")
    return render(request, "stokapp/personel_izin_listesi.html", {
        "izinler": filtered[:500],
        "personeller": personeller,
        "personel_id": personel_id,
        "tarih_baslangic": tarih_baslangic,
        "tarih_bitis": tarih_bitis,
        "form": form,
        "toplam_kayit": toplam_kayit,
        "aktif_izin_sayisi": aktif_izin_sayisi,
        "yaklasan_bitis_sayisi": yaklasan_bitis_sayisi,
    })


@login_required
def personel_izin_duzenle(request, pk):
    izin = get_object_or_404(PersonelIzin, pk=pk)
    if request.method == "POST":
        form = PersonelIzinForm(request.POST, instance=izin)
        if form.is_valid():
            form.save()
            messages.success(request, "İzin kaydı güncellendi.")
            return redirect("stokapp:personel_izin_listesi")
    else:
        form = PersonelIzinForm(instance=izin)
    return render(request, "stokapp/personel_izin_duzenle.html", {"form": form, "izin": izin})


@login_required
def personel_izin_sil(request, pk):
    izin = get_object_or_404(PersonelIzin, pk=pk)
    if request.method == "POST":
        izin.delete()
        messages.success(request, "İzin kaydı silindi.")
        return redirect("stokapp:personel_izin_listesi")
    return render(request, "stokapp/personel_izin_sil.html", {"izin": izin})
