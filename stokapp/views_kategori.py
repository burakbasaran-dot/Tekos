import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from .models import (
    Kategori,
    Tedarikci,
    TedarikciIlgiliKisi,
    Birim,
    StokItem,
    Musteri,
    MusteriIlgiliKisi,
    Siparis,
    Satinalma,
)
from django import forms
from .forms import MusteriForm


def _musteri_ilgililer_kaydet(musteri, raw_json: str) -> None:
    """POST'taki JSON ile ilgili kişileri tamamen yeniden yazar (sırayı korur)."""
    musteri.ilgili_kisiler.all().delete()
    try:
        items = json.loads(raw_json or '[]')
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list):
        items = []
    to_create = []
    order = 0
    for row in items:
        if not isinstance(row, dict):
            continue
        ad = (row.get('ad_soyad') or '').strip()
        if not ad:
            continue
        to_create.append(
            MusteriIlgiliKisi(
                musteri=musteri,
                ad_soyad=ad[:200],
                gorev=(row.get('gorev') or '')[:120],
                telefon=(row.get('telefon') or '')[:40],
                email=(row.get('email') or '').strip()[:254],
                ozel_not=(row.get('ozel_not') or '').strip(),
                sira=order,
            )
        )
        order += 1
    if to_create:
        MusteriIlgiliKisi.objects.bulk_create(to_create)


def _musteri_ilgililer_initial(musteri):
    return [
        {
            'ad_soyad': k.ad_soyad,
            'gorev': k.gorev or '',
            'telefon': k.telefon or '',
            'email': k.email or '',
            'ozel_not': k.ozel_not or '',
        }
        for k in musteri.ilgili_kisiler.all()
    ]


def _ilgililer_json_from_request(request):
    try:
        items = json.loads(request.POST.get('ilgililer') or '[]')
    except json.JSONDecodeError:
        return []
    return items if isinstance(items, list) else []


def _tedarikci_ilgililer_kaydet(tedarikci, raw_json: str) -> None:
    tedarikci.ilgili_kisiler.all().delete()
    try:
        items = json.loads(raw_json or '[]')
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list):
        items = []
    to_create = []
    order = 0
    for row in items:
        if not isinstance(row, dict):
            continue
        ad = (row.get('ad_soyad') or '').strip()
        if not ad:
            continue
        to_create.append(
            TedarikciIlgiliKisi(
                tedarikci=tedarikci,
                ad_soyad=ad[:200],
                gorev=(row.get('gorev') or '')[:120],
                telefon=(row.get('telefon') or '')[:40],
                email=(row.get('email') or '').strip()[:254],
                ozel_not=(row.get('ozel_not') or '').strip(),
                sira=order,
            )
        )
        order += 1
    if to_create:
        TedarikciIlgiliKisi.objects.bulk_create(to_create)


def _tedarikci_ilgililer_initial(tedarikci):
    return [
        {
            'ad_soyad': k.ad_soyad,
            'gorev': k.gorev or '',
            'telefon': k.telefon or '',
            'email': k.email or '',
            'ozel_not': k.ozel_not or '',
        }
        for k in tedarikci.ilgili_kisiler.all()
    ]


class KategoriForm(forms.ModelForm):
    class Meta:
        model = Kategori
        fields = ['ad', 'stok_tipi', 'aciklama']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kategori adı giriniz...'
            }),
            'stok_tipi': forms.Select(attrs={'class': 'form-control'}),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Kategori açıklaması...'
            })
        }


class TedarikciForm(forms.ModelForm):
    kategoriler = forms.ModelMultipleChoiceField(
        queryset=Kategori.objects.all().order_by('ad'),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control',
            'size': 8,
            'style': 'min-height: 160px;',
        }),
        label='Etiketler / Kategoriler',
        help_text='Tedarikçinin tedarik edebildiği kategorileri seçin. Stok kartının kategorisi bu listede ise RFQ önerisinde otomatik düşer.',
    )

    class Meta:
        model = Tedarikci
        fields = ['ad', 'telefon', 'email', 'adres', 'kategoriler']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tedarikçi adı giriniz...'
            }),
            'telefon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Telefon numarası...'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'E-posta adresi...'
            }),
            'adres': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Adres bilgisi...'
            })
        }


class BirimForm(forms.ModelForm):
    class Meta:
        model = Birim
        fields = ['ad']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Birim adı giriniz (örn: Adet, Kg, Litre)...'
            })
        }


# KATEGORİ VIEW'LARI
@login_required
def kategori_listesi(request):
    """Kategori listesi"""
    kategoriler = Kategori.objects.all().order_by('stok_tipi', 'ad')
    
    # Her kategori için stok sayısı
    kategori_bilgileri = []
    for kategori in kategoriler:
        stok_sayisi = StokItem.objects.filter(kategori=kategori).count()
        kategori_bilgileri.append({
            'kategori': kategori,
            'stok_sayisi': stok_sayisi
        })
    
    context = {
        'kategori_bilgileri': kategori_bilgileri,
    }
    return render(request, 'stokapp/kategori_listesi.html', context)


@login_required
def kategori_ekle(request):
    """Yeni kategori ekle"""
    if request.method == 'POST':
        form = KategoriForm(request.POST)
        if form.is_valid():
            try:
                kategori = form.save()
                messages.success(request, f'Kategori "{kategori.ad}" başarıyla eklendi.')
                return redirect('stokapp:kategori_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KategoriForm()
    
    return render(request, 'stokapp/kategori_ekle.html', {'form': form})


@login_required
def kategori_duzenle(request, pk):
    """Kategori düzenle"""
    kategori = get_object_or_404(Kategori, pk=pk)
    
    if request.method == 'POST':
        form = KategoriForm(request.POST, instance=kategori)
        if form.is_valid():
            try:
                kategori = form.save()
                messages.success(request, f'Kategori "{kategori.ad}" güncellendi.')
                return redirect('stokapp:kategori_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KategoriForm(instance=kategori)
    
    # Bu kategorideki stoklar
    stoklar = StokItem.objects.filter(kategori=kategori)
    
    context = {
        'form': form,
        'kategori': kategori,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/kategori_duzenle.html', context)


@login_required
def kategori_sil(request, pk):
    """Kategori sil"""
    kategori = get_object_or_404(Kategori, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(kategori=kategori).count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Kategorideki stokların kategori bilgisini temizle (veya başka bir kategoriye taşı)
                # Burada silmek yerine uyarı veriyoruz
                if stok_sayisi > 0:
                    messages.error(request, f'Bu kategoride {stok_sayisi} adet stok bulunuyor. Önce stokları başka bir kategoriye taşıyın.')
                    return redirect('stokapp:kategori_duzenle', pk=pk)
                
                kategori_adi = kategori.ad
                kategori.delete()
                messages.success(request, f'Kategori "{kategori_adi}" silindi.')
                return redirect('stokapp:kategori_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:kategori_duzenle', pk=pk)
    
    context = {
        'kategori': kategori,
        'stok_sayisi': stok_sayisi,
    }
    return render(request, 'stokapp/kategori_sil.html', context)


# TEDARİKÇİ VIEW'LARI
@login_required
def tedarikci_listesi(request):
    """Tedarikçi listesi"""
    sort_field = request.GET.get('sort', 'ad')
    sort_dir = request.GET.get('dir', 'asc')
    tedarikciler = Tedarikci.objects.all().prefetch_related('kategoriler')
    
    tedarikci_ids = list(tedarikciler.values_list('id', flat=True))
    satinalma_sayilari = {
        row['tedarikci_id']: row
        for row in Satinalma.objects.filter(tedarikci_id__in=tedarikci_ids)
        .values('tedarikci_id')
        .annotate(
            acik_satinalma_sayisi=Count('id', filter=Q(teslim_durumu__in=['BEKLIYOR', 'KISMI_TESLIM'])),
            kapali_satinalma_sayisi=Count('id', filter=Q(teslim_durumu='TESLIM_ALINDI')),
        )
    }

    # Her tedarikçi için stok ve satınalma sayıları
    tedarikci_bilgileri = []
    for tedarikci in tedarikciler:
        stok_sayisi = StokItem.objects.filter(tedarikci=tedarikci).count()
        satinalma_bilgi = satinalma_sayilari.get(tedarikci.id, {})
        tedarikci_bilgileri.append({
            'tedarikci': tedarikci,
            'stok_sayisi': stok_sayisi,
            'acik_satinalma_sayisi': satinalma_bilgi.get('acik_satinalma_sayisi', 0),
            'kapali_satinalma_sayisi': satinalma_bilgi.get('kapali_satinalma_sayisi', 0),
        })

    reverse = sort_dir == 'desc'
    if sort_field == 'stok_sayisi':
        tedarikci_bilgileri.sort(key=lambda x: x['stok_sayisi'], reverse=reverse)
    elif sort_field == 'acik_satinalma_sayisi':
        tedarikci_bilgileri.sort(key=lambda x: x['acik_satinalma_sayisi'], reverse=reverse)
    elif sort_field == 'kapali_satinalma_sayisi':
        tedarikci_bilgileri.sort(key=lambda x: x['kapali_satinalma_sayisi'], reverse=reverse)
    elif sort_field == 'created_at':
        tedarikci_bilgileri.sort(
            key=lambda x: x['tedarikci'].created_at or timezone.datetime.min,
            reverse=reverse,
        )
    else:
        tedarikci_bilgileri.sort(key=lambda x: (x['tedarikci'].ad or '').lower(), reverse=reverse)
    
    context = {
        'tedarikci_bilgileri': tedarikci_bilgileri,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
    }
    return render(request, 'stokapp/tedarikci_listesi.html', context)


@login_required
def tedarikci_ekle(request):
    """Yeni tedarikçi ekle"""
    ilgililer_initial = []
    if request.method == 'POST':
        form = TedarikciForm(request.POST)
        ilgililer_initial = _ilgililer_json_from_request(request)
        if form.is_valid():
            try:
                with transaction.atomic():
                    tedarikci = form.save()
                    _tedarikci_ilgililer_kaydet(tedarikci, request.POST.get('ilgililer', '[]'))
                messages.success(request, f'Tedarikçi "{tedarikci.ad}" başarıyla eklendi.')
                return redirect('stokapp:tedarikci_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = TedarikciForm()

    return render(
        request,
        'stokapp/tedarikci_ekle.html',
        {'form': form, 'ilgililer_initial': ilgililer_initial},
    )


@login_required
def tedarikci_duzenle(request, pk):
    """Tedarikçi düzenle"""
    tedarikci = get_object_or_404(Tedarikci, pk=pk)
    ilgililer_initial = _tedarikci_ilgililer_initial(tedarikci)

    if request.method == 'POST':
        form = TedarikciForm(request.POST, instance=tedarikci)
        ilgililer_initial = _ilgililer_json_from_request(request)
        if form.is_valid():
            try:
                with transaction.atomic():
                    tedarikci = form.save()
                    _tedarikci_ilgililer_kaydet(tedarikci, request.POST.get('ilgililer', '[]'))
                messages.success(request, f'Tedarikçi "{tedarikci.ad}" güncellendi.')
                return redirect('stokapp:tedarikci_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = TedarikciForm(instance=tedarikci)

    stoklar = StokItem.objects.filter(tedarikci=tedarikci)

    context = {
        'form': form,
        'tedarikci': tedarikci,
        'stoklar': stoklar,
        'ilgililer_initial': ilgililer_initial,
    }
    return render(request, 'stokapp/tedarikci_duzenle.html', context)


@login_required
def tedarikci_stoklari(request, pk):
    """Tedarikçiye ait stokları listele"""
    tedarikci = get_object_or_404(Tedarikci, pk=pk)
    stoklar = StokItem.objects.filter(tedarikci=tedarikci, arsivli=False).order_by('stok_kodu')
    
    context = {
        'tedarikci': tedarikci,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/tedarikci_stoklari.html', context)


@login_required
def tedarikci_sil(request, pk):
    """Tedarikçi sil"""
    tedarikci = get_object_or_404(Tedarikci, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(tedarikci=tedarikci).count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Tedarikçideki stokların tedarikçi bilgisini temizle
                StokItem.objects.filter(tedarikci=tedarikci).update(tedarikci=None)
                tedarikci_adi = tedarikci.ad
                tedarikci.delete()
                messages.success(request, f'Tedarikçi "{tedarikci_adi}" silindi.')
                return redirect('stokapp:tedarikci_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:tedarikci_duzenle', pk=pk)
    
    context = {
        'tedarikci': tedarikci,
        'stok_sayisi': stok_sayisi,
    }
    return render(request, 'stokapp/tedarikci_sil.html', context)


# BİRİM VIEW'LARI
@login_required
def birim_listesi(request):
    """Birim listesi"""
    birimler = Birim.objects.all().order_by('ad')
    
    # Her birim için stok sayısı
    birim_bilgileri = []
    for birim in birimler:
        stok_sayisi = StokItem.objects.filter(birim=birim.ad).count()
        birim_bilgileri.append({
            'birim': birim,
            'stok_sayisi': stok_sayisi
        })
    
    context = {
        'birim_bilgileri': birim_bilgileri,
    }
    return render(request, 'stokapp/birim_listesi.html', context)


@login_required
def birim_ekle(request):
    """Yeni birim ekle"""
    if request.method == 'POST':
        form = BirimForm(request.POST)
        if form.is_valid():
            try:
                birim = form.save()
                messages.success(request, f'Birim "{birim.ad}" başarıyla eklendi.')
                return redirect('stokapp:birim_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = BirimForm()
    
    return render(request, 'stokapp/birim_ekle.html', {'form': form})


@login_required
def birim_duzenle(request, pk):
    """Birim düzenle"""
    birim = get_object_or_404(Birim, pk=pk)
    
    if request.method == 'POST':
        form = BirimForm(request.POST, instance=birim)
        if form.is_valid():
            try:
                birim = form.save()
                messages.success(request, f'Birim "{birim.ad}" güncellendi.')
                return redirect('stokapp:birim_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = BirimForm(instance=birim)
    
    # Bu birimi kullanan stoklar
    stoklar = StokItem.objects.filter(birim=birim.ad)
    
    context = {
        'form': form,
        'birim': birim,
        'stoklar': stoklar,
    }
    return render(request, 'stokapp/birim_duzenle.html', context)


@login_required
def birim_sil(request, pk):
    """Birim sil"""
    birim = get_object_or_404(Birim, pk=pk)
    
    # Kontroller
    stok_sayisi = StokItem.objects.filter(birim=birim.ad).count()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Birimi kullanan stokların birim bilgisini temizle (veya başka bir birime taşı)
                if stok_sayisi > 0:
                    messages.error(request, f'Bu birim {stok_sayisi} adet stokta kullanılıyor. Önce stokları başka bir birime taşıyın.')
                    return redirect('stokapp:birim_duzenle', pk=pk)
                
                birim_adi = birim.ad
                birim.delete()
                messages.success(request, f'Birim "{birim_adi}" silindi.')
                return redirect('stokapp:birim_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:birim_duzenle', pk=pk)
    
    context = {
        'birim': birim,
        'stok_sayisi': stok_sayisi,
    }
    return render(request, 'stokapp/birim_sil.html', context)


@login_required
def musteri_listesi(request):
    """Müşteri listesi"""
    sort_field = request.GET.get('sort', 'ad')
    sort_dir = request.GET.get('dir', 'asc')
    musteriler = Musteri.objects.all().order_by('ad')

    musteri_bilgileri = []
    for musteri in musteriler:
        siparis_qs = Siparis.objects.filter(
            Q(musteri=musteri) | Q(musteri_adi=musteri.ad)
        )
        siparis_sayisi = siparis_qs.count()
        acik_siparis_sayisi = siparis_qs.exclude(siparis_durumu='TESLIM_EDILDI').count()
        kapali_siparis_sayisi = siparis_qs.filter(siparis_durumu='TESLIM_EDILDI').count()
        musteri_bilgileri.append({
            'musteri': musteri,
            'siparis_sayisi': siparis_sayisi,
            'acik_siparis_sayisi': acik_siparis_sayisi,
            'kapali_siparis_sayisi': kapali_siparis_sayisi,
        })

    reverse = sort_dir == 'desc'
    if sort_field == 'siparis_sayisi':
        musteri_bilgileri.sort(key=lambda x: x['siparis_sayisi'], reverse=reverse)
    elif sort_field == 'acik_siparis_sayisi':
        musteri_bilgileri.sort(key=lambda x: x['acik_siparis_sayisi'], reverse=reverse)
    elif sort_field == 'kapali_siparis_sayisi':
        musteri_bilgileri.sort(key=lambda x: x['kapali_siparis_sayisi'], reverse=reverse)
    elif sort_field == 'telefon':
        musteri_bilgileri.sort(
            key=lambda x: (x['musteri'].telefon or '').lower(),
            reverse=reverse,
        )
    elif sort_field == 'email':
        musteri_bilgileri.sort(
            key=lambda x: (x['musteri'].email or '').lower(),
            reverse=reverse,
        )
    elif sort_field == 'created_at':
        musteri_bilgileri.sort(
            key=lambda x: x['musteri'].created_at or timezone.datetime.min,
            reverse=reverse,
        )
    else:
        musteri_bilgileri.sort(
            key=lambda x: (x['musteri'].ad or '').lower(),
            reverse=reverse,
        )

    context = {
        'musteri_bilgileri': musteri_bilgileri,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
    }
    return render(request, 'stokapp/musteri_listesi.html', context)


@login_required
def musteri_siparisleri(request, pk):
    """Müşteriye ait siparişleri listele"""
    musteri = get_object_or_404(Musteri, pk=pk)
    
    # Filtre: açık (TESLIM_EDILDI olmayan) veya kapalı (TESLIM_EDILDI)
    durum_filtre = request.GET.get('durum', 'acik')  # Varsayılan: açık
    
    # Müşteriye ait siparişleri getir (ForeignKey veya musteri_adi ile)
    siparisler = Siparis.objects.filter(
        Q(musteri=musteri) | Q(musteri_adi=musteri.ad)
    )
    
    # Durum filtresini uygula
    if durum_filtre == 'kapali':
        siparisler = siparisler.filter(siparis_durumu='TESLIM_EDILDI')
    else:  # açık
        siparisler = siparisler.exclude(siparis_durumu='TESLIM_EDILDI')
    
    siparisler = siparisler.order_by('-olusturulma_tarihi')
    
    context = {
        'musteri': musteri,
        'siparisler': siparisler,
        'durum_filtre': durum_filtre,
    }
    return render(request, 'stokapp/musteri_siparisleri.html', context)


@login_required
def musteri_ekle(request):
    """Yeni müşteri ekle"""
    ilgililer_initial = []
    if request.method == 'POST':
        form = MusteriForm(request.POST)
        ilgililer_initial = _ilgililer_json_from_request(request)
        if form.is_valid():
            try:
                with transaction.atomic():
                    musteri = form.save()
                    _musteri_ilgililer_kaydet(musteri, request.POST.get('ilgililer', '[]'))
                messages.success(request, f'Müşteri "{musteri.ad}" başarıyla eklendi.')
                return redirect('stokapp:musteri_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = MusteriForm()

    return render(
        request,
        'stokapp/musteri_ekle.html',
        {'form': form, 'ilgililer_initial': ilgililer_initial},
    )


@login_required
def musteri_duzenle(request, pk):
    """Müşteri düzenle"""
    musteri = get_object_or_404(Musteri, pk=pk)
    ilgililer_initial = _musteri_ilgililer_initial(musteri)

    if request.method == 'POST':
        form = MusteriForm(request.POST, instance=musteri)
        ilgililer_initial = _ilgililer_json_from_request(request)
        if form.is_valid():
            try:
                with transaction.atomic():
                    musteri = form.save()
                    _musteri_ilgililer_kaydet(musteri, request.POST.get('ilgililer', '[]'))
                messages.success(request, f'Müşteri "{musteri.ad}" güncellendi.')
                return redirect('stokapp:musteri_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = MusteriForm(instance=musteri)

    context = {
        'form': form,
        'musteri': musteri,
        'ilgililer_initial': ilgililer_initial,
    }
    return render(request, 'stokapp/musteri_duzenle.html', context)


@login_required
def musteri_sil(request, pk):
    """Müşteri sil"""
    musteri = get_object_or_404(Musteri, pk=pk)
    
    if request.method == 'POST':
        try:
            musteri_adi = musteri.ad
            musteri.delete()
            messages.success(request, f'Müşteri "{musteri_adi}" silindi.')
            return redirect('stokapp:musteri_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'musteri': musteri,
    }
    return render(request, 'stokapp/musteri_sil.html', context)
