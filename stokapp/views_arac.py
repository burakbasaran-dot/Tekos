import json
import re

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from datetime import date, timedelta
from django import forms
from .models import Arac, AracBelgesi, AracBelgeTuru, AracBelgesiDosya
from .forms import AracForm, AracBelgesiForm


def _arac_belge_form_ekstra_context():
    import json

    kodlar = list(
        AracBelgeTuru.objects.filter(bitis_tarihi_gerekmez=True).values_list("kod", flat=True)
    )
    return {"bitis_tarihi_gerekmez_kodlar_json": json.dumps(kodlar)}


def _arac_belge_dosyalari_isle(belge, request):
    silinen = request.POST.getlist("silinen_dosya")
    if silinen:
        belge.dosyalar.filter(pk__in=silinen).delete()
    for dosya in request.FILES.getlist("belge_dosyalari"):
        if dosya:
            AracBelgesiDosya.objects.create(belge=belge, dosya=dosya)
    belge.sync_belge_pdf()


def _arac_belge_arsivle(belge):
    belge.arsivlendi = True
    belge.arsivlenme_tarihi = timezone.now()
    belge.save(update_fields=["arsivlendi", "arsivlenme_tarihi"])


def _arac_aktif_belgeleri_arsivle(arac, belge_turu, haric_pk=None):
    qs = arac.belgeler.filter(arsivlendi=False, belge_turu=belge_turu)
    if haric_pk:
        qs = qs.exclude(pk=haric_pk)
    now = timezone.now()
    qs.update(arsivlendi=True, arsivlenme_tarihi=now)


def _arac_belge_turu_kod_uret(ad):
    base = slugify(ad, allow_unicode=False).upper().replace("-", "_")
    base = re.sub(r"[^A-Z0-9_]", "", base)[:20]
    if not base:
        base = "TUR"
    kod = base
    i = 1
    while AracBelgeTuru.objects.filter(kod=kod).exists():
        suffix = f"_{i}"
        kod = f"{base[: 20 - len(suffix)]}{suffix}"
        i += 1
    return kod


@login_required
@require_POST
def api_arac_belge_turu_ekle(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Geçersiz JSON"}, status=400)

    ad = (payload.get("ad") or "").strip()
    if not ad:
        return JsonResponse({"ok": False, "error": "Belge türü adı boş olamaz"}, status=400)

    mevcut = AracBelgeTuru.objects.filter(ad__iexact=ad).first()
    if mevcut:
        return JsonResponse({"ok": True, "kod": mevcut.kod, "ad": mevcut.ad})

    kod = _arac_belge_turu_kod_uret(ad)
    max_sira = AracBelgeTuru.objects.order_by("-sira").values_list("sira", flat=True).first() or 0
    ad_lower = ad.lower()
    bitis_gerekmez = "hasar" in ad_lower or "tescil" in ad_lower
    tur = AracBelgeTuru.objects.create(
        kod=kod, ad=ad, sira=max_sira + 1, bitis_tarihi_gerekmez=bitis_gerekmez
    )
    return JsonResponse({"ok": True, "kod": tur.kod, "ad": tur.ad})


@login_required
def arac_listesi(request):
    """Araç listesi"""
    aktif = request.GET.get('aktif', '1')
    search = request.GET.get('search', '')
    
    araclar = Arac.objects.all()
    
    # Filtreleme
    if aktif == '1':
        araclar = araclar.filter(aktif=True)
    elif aktif == '0':
        araclar = araclar.filter(aktif=False)
    
    # Arama
    if search:
        araclar = araclar.filter(
            Q(plaka__icontains=search) |
            Q(marka__icontains=search) |
            Q(model__icontains=search)
        )
    
    # Sayfalama
    paginator = Paginator(araclar.order_by('plaka'), 12)
    page = request.GET.get('page', 1)
    araclar_page = paginator.get_page(page)
    
    context = {
        'araclar': araclar_page,
        'aktif': aktif,
        'search': search,
    }
    return render(request, 'stokapp/arac_listesi.html', context)


@login_required
def arac_ekle(request):
    """Yeni araç ekle"""
    if request.method == 'POST':
        form = AracForm(request.POST, request.FILES)
        if form.is_valid():
            arac = form.save()
            messages.success(request, f'Araç "{arac.plaka}" başarıyla eklendi.')
            return redirect('stokapp:arac_detay', pk=arac.pk)
    else:
        form = AracForm()
        form.fields['aktif'].initial = True
    
    context = {
        'form': form,
        'is_edit': False,
    }
    return render(request, 'stokapp/arac_ekle.html', context)


@login_required
def arac_duzenle(request, pk):
    """Araç düzenle"""
    arac = get_object_or_404(Arac, pk=pk)
    
    if request.method == 'POST':
        form = AracForm(request.POST, request.FILES, instance=arac)
        if form.is_valid():
            arac = form.save()
            messages.success(request, f'Araç "{arac.plaka}" başarıyla güncellendi.')
            return redirect('stokapp:arac_detay', pk=arac.pk)
    else:
        form = AracForm(instance=arac)
    
    context = {
        'form': form,
        'arac': arac,
        'is_edit': True,
    }
    return render(request, 'stokapp/arac_ekle.html', context)


@login_required
def arac_detay(request, pk):
    """Araç detay sayfası"""
    arac = get_object_or_404(Arac, pk=pk)
    arsivli = request.GET.get("arsivli", "false") == "true"

    belgeler = (
        arac.belgeler.filter(arsivlendi=arsivli)
        .prefetch_related("dosyalar")
        .order_by("-gecerlilik_bitis", "-created_at")
    )
    
    # Hatırlatma gereken belgeler (7 gün kala) — sadece güncel belgeler
    bugun = date.today()
    uyari_tarihi = bugun + timedelta(days=7)
    
    hatirlatma_belgeler = []
    suresi_dolan_belgeler = []
    
    if not arsivli:
        for belge in belgeler:
            if not belge.gecerlilik_bitis:
                continue
            if belge.gecerlilik_bitis < bugun:
                suresi_dolan_belgeler.append(belge)
            elif belge.gecerlilik_bitis <= uyari_tarihi:
                hatirlatma_belgeler.append(belge)
    
    context = {
        'arac': arac,
        'belgeler': belgeler,
        'arsivli': arsivli,
        'hatirlatma_belgeler': hatirlatma_belgeler,
        'suresi_dolan_belgeler': suresi_dolan_belgeler,
    }
    return render(request, 'stokapp/arac_detay.html', context)


@login_required
def arac_sil(request, pk):
    """Araç sil"""
    arac = get_object_or_404(Arac, pk=pk)
    
    if request.method == 'POST':
        plaka = arac.plaka
        arac.delete()
        messages.success(request, f'Araç "{plaka}" başarıyla silindi.')
        return redirect('stokapp:arac_listesi')
    
    context = {
        'arac': arac,
    }
    return render(request, 'stokapp/arac_sil.html', context)


@login_required
def arac_belgesi_ekle(request, arac_pk):
    """Araç belgesi ekle"""
    arac = get_object_or_404(Arac, pk=arac_pk)
    
    if request.method == 'POST':
        form = AracBelgesiForm(request.POST, request.FILES)
        if form.is_valid():
            belge = form.save(commit=False)
            belge.arac = arac
            _arac_aktif_belgeleri_arsivle(arac, belge.belge_turu)
            belge.save()
            _arac_belge_dosyalari_isle(belge, request)
            messages.success(request, f'Belge "{belge.get_belge_turu_display()}" başarıyla eklendi.')
            return redirect('stokapp:arac_detay', pk=arac.pk)
    else:
        form = AracBelgesiForm()
        form.fields['arac'].initial = arac
        form.fields['arac'].widget = forms.HiddenInput()
    
    context = {
        'form': form,
        'arac': arac,
        'is_edit': False,
        **_arac_belge_form_ekstra_context(),
    }
    return render(request, 'stokapp/arac_belgesi_ekle.html', context)


@login_required
def arac_belgesi_duzenle(request, pk):
    """Araç belgesi düzenle"""
    belge = get_object_or_404(AracBelgesi, pk=pk, arsivlendi=False)
    arac = belge.arac
    
    if request.method == 'POST':
        form = AracBelgesiForm(request.POST, request.FILES, instance=belge)
        if form.is_valid():
            belge = form.save()
            _arac_belge_dosyalari_isle(belge, request)
            messages.success(request, f'Belge "{belge.get_belge_turu_display()}" başarıyla güncellendi.')
            return redirect('stokapp:arac_detay', pk=arac.pk)
    else:
        form = AracBelgesiForm(instance=belge)
        form.fields['arac'].widget = forms.HiddenInput()
    
    context = {
        'form': form,
        'belge': belge,
        'arac': arac,
        'is_edit': True,
        **_arac_belge_form_ekstra_context(),
    }
    return render(request, 'stokapp/arac_belgesi_ekle.html', context)


@login_required
def arac_belgesi_guncelle(request, pk):
    """Mevcut belgeyi arşivleyip yeni sürüm oluşturur."""
    eski_belge = get_object_or_404(AracBelgesi, pk=pk, arsivlendi=False)
    arac = eski_belge.arac

    if request.method == "POST":
        post_data = request.POST.copy()
        post_data["belge_turu"] = eski_belge.belge_turu
        post_data["arac"] = str(arac.pk)
        form = AracBelgesiForm(post_data, request.FILES)
        if form.is_valid():
            _arac_belge_arsivle(eski_belge)
            yeni_belge = form.save(commit=False)
            yeni_belge.arac = arac
            yeni_belge.belge_turu = eski_belge.belge_turu
            yeni_belge.onceki_belge = eski_belge
            yeni_belge.save()
            _arac_belge_dosyalari_isle(yeni_belge, request)
            messages.success(
                request,
                f'"{yeni_belge.get_belge_turu_display()}" belgesi güncellendi. Eski sürüm arşive alındı.',
            )
            return redirect("stokapp:arac_detay", pk=arac.pk)
    else:
        form = AracBelgesiForm(
            initial={
                "arac": arac,
                "belge_turu": eski_belge.belge_turu,
                "gecerlilik_baslangic": eski_belge.gecerlilik_baslangic,
                "gecerlilik_bitis": eski_belge.gecerlilik_bitis,
                "belge_no": eski_belge.belge_no,
                "aciklama": eski_belge.aciklama,
            }
        )
        form.fields["arac"].widget = forms.HiddenInput()

    context = {
        "form": form,
        "arac": arac,
        "belge": eski_belge,
        "is_edit": False,
        "is_guncelle": True,
        **_arac_belge_form_ekstra_context(),
    }
    return render(request, "stokapp/arac_belgesi_ekle.html", context)


@login_required
def arac_belgesi_sil(request, pk):
    """Araç belgesi sil"""
    belge = get_object_or_404(AracBelgesi, pk=pk)
    arac = belge.arac
    
    if request.method == 'POST':
        belge_turu = belge.get_belge_turu_display()
        belge.delete()
        messages.success(request, f'Belge "{belge_turu}" başarıyla silindi.')
        return redirect('stokapp:arac_detay', pk=arac.pk)
    
    context = {
        'belge': belge,
        'arac': arac,
    }
    return render(request, 'stokapp/arac_belgesi_sil.html', context)

