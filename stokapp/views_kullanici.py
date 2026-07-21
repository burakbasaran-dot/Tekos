from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from .models import UserProfile
from .forms import KullaniciForm, KullaniciDuzenleForm

@login_required
def kullanici_listesi(request):
    """Kullanıcı listesi"""
    kullanicilar = User.objects.all().order_by('first_name', 'last_name')
    
    # Her kullanıcı için profil bilgisi
    kullanici_bilgileri = []
    for kullanici in kullanicilar:
        try:
            profil = kullanici.profile
            telefon = profil.telefon
        except UserProfile.DoesNotExist:
            telefon = ""
        
        kullanici_bilgileri.append({
            'kullanici': kullanici,
            'telefon': telefon
        })
    
    context = {
        'kullanici_bilgileri': kullanici_bilgileri,
    }
    return render(request, 'stokapp/kullanici_listesi.html', context)


@login_required
def kullanici_ekle(request):
    """Yeni kullanıcı ekle"""
    if request.method == 'POST':
        form = KullaniciForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    # Şifre ayarla
                    user.set_password(form.cleaned_data['password'])
                    user.save()
                    
                    # Profil oluştur
                    telefon = form.cleaned_data.get('telefon', '')
                    UserProfile.objects.create(user=user, telefon=telefon)
                    
                    messages.success(request, f'Kullanıcı "{user.get_full_name()}" başarıyla eklendi.')
                    return redirect('stokapp:kullanici_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KullaniciForm()
    
    return render(request, 'stokapp/kullanici_ekle.html', {'form': form})


@login_required
def kullanici_duzenle(request, pk):
    """Kullanıcı düzenle"""
    user = get_object_or_404(User, pk=pk)
    
    # Profil bilgisi
    try:
        profil = user.profile
        telefon = profil.telefon
    except UserProfile.DoesNotExist:
        profil = None
        telefon = ""
    
    if request.method == 'POST':
        form = KullaniciDuzenleForm(request.POST, instance=user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    
                    # Şifre değiştirildiyse güncelle
                    if form.cleaned_data.get('password'):
                        user.set_password(form.cleaned_data['password'])
                        user.save()
                    
                    # Profil güncelle veya oluştur
                    telefon = form.cleaned_data.get('telefon', '')
                    if profil:
                        profil.telefon = telefon
                        profil.save()
                    else:
                        UserProfile.objects.create(user=user, telefon=telefon)
                    
                    messages.success(request, f'Kullanıcı "{user.get_full_name()}" güncellendi.')
                    return redirect('stokapp:kullanici_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KullaniciDuzenleForm(instance=user, initial={'telefon': telefon})
    
    context = {
        'form': form,
        'kullanici': user,
    }
    return render(request, 'stokapp/kullanici_duzenle.html', context)


@login_required
def kullanici_sil(request, pk):
    """Kullanıcı sil"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        try:
            kullanici_adi = user.get_full_name()
            user.delete()
            messages.success(request, f'Kullanıcı "{kullanici_adi}" silindi.')
            return redirect('stokapp:kullanici_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'kullanici': user,
    }
    return render(request, 'stokapp/kullanici_sil.html', context)


@login_required
def kullanici_sifre_sifirla(request, pk):
    """Kullanıcı şifresini sıfırla"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        yeni_sifre = request.POST.get('yeni_sifre')
        if yeni_sifre:
            user.set_password(yeni_sifre)
            user.save()
            messages.success(request, f'Kullanıcı "{user.get_full_name()}" şifresi sıfırlandı.')
            return redirect('stokapp:kullanici_listesi')
        else:
            messages.error(request, 'Şifre boş olamaz.')
    
    context = {
        'kullanici': user,
    }
    return render(request, 'stokapp/kullanici_sifre_sifirla.html', context)
