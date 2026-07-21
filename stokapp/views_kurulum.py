from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
import json
import os
from .models import (
    KurulumDosyasi,
    KurulumDosyasiArsiv,
    StokItem,
    Istasyon,
    Recete,
    ReceteDetay,
    istasyon_effective_cnc_makine_grubu,
    kurulum_dosyasi_cnc_ekipman_secenekleri,
)
from .forms import KurulumDosyasiForm


def _kurulum_cnc_ekipman_secim_ids(request):
    out = []
    for x in request.POST.getlist("cnc_ekipmanlar"):
        s = str(x).strip()
        if s.isdigit():
            i = int(s)
            if i not in out:
                out.append(i)
    return out


def _kurulum_cnc_secimini_uygula(dosya, request):
    """POST’tan CNC ekipmanlarını okur, istasyona göre doğrular, M2M’yi günceller."""
    ids = _kurulum_cnc_ekipman_secim_ids(request)
    allowed = set(
        kurulum_dosyasi_cnc_ekipman_secenekleri(dosya.istasyon).values_list(
            "pk", flat=True
        )
    )
    chosen = set(ids)
    if not chosen.issubset(allowed):
        invalid = sorted(chosen - allowed)
        return (
            False,
            f"Seçilen CNC ekipmanları bu istasyon için geçerli değil veya pasif. Geçersiz kimlikler: {invalid}",
        )
    dosya.cnc_ekipmanlar.set(ids)
    return True, None


@login_required
def kurulum_dosyalari_listesi(request):
    """Kurulum dosyaları listesi"""
    search_query = request.GET.get('search', '').strip()
    aktif_filter = request.GET.get('aktif', '')
    
    dosyalar = KurulumDosyasi.objects.select_related('urun', 'istasyon').all()
    
    # Arama filtresi
    if search_query:
        dosyalar = dosyalar.filter(
            Q(urun__stok_kodu__icontains=search_query) |
            Q(urun__ad__icontains=search_query) |
            Q(urun_parcasi__icontains=search_query) |
            Q(aciklama__icontains=search_query)
        )
    
    # Aktif/Pasif filtresi
    if aktif_filter == 'aktif':
        dosyalar = dosyalar.filter(aktif=True)
    elif aktif_filter == 'pasif':
        dosyalar = dosyalar.filter(aktif=False)
    
    dosyalar = dosyalar.order_by('urun__stok_kodu', 'urun_parcasi', '-versiyon')
    
    # Pagination
    paginator = Paginator(dosyalar, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'aktif_filter': aktif_filter,
    }
    return render(request, 'stokapp/kurulum_dosyalari_listesi.html', context)


@login_required
@require_http_methods(["GET"])
def kurulum_dosyasi_urun_ara(request):
    """AJAX: Kurulum dosyası için ürün arama"""
    search_query = request.GET.get('q', '').strip()
    
    # Ürün tiplerini getir (sadece ürünler)
    stok_items = StokItem.objects.select_related('kategori').filter(
        Q(stok_tipi='URUN') | Q(kategori__stok_tipi='URUN')
    )
    
    if search_query:
        stok_items = stok_items.filter(
            Q(stok_kodu__icontains=search_query) |
            Q(ad__icontains=search_query)
        )
    
    stok_items = stok_items.order_by('stok_kodu')[:20]
    
    results = []
    for item in stok_items:
        results.append({
            'id': item.pk,
            'stok_kodu': item.stok_kodu,
            'ad': item.ad,
        })
    
    return JsonResponse({'results': results})


@login_required
@require_http_methods(["GET"])
def kurulum_dosyasi_recete_bilesenleri(request, urun_id):
    """AJAX: Seçilen ürünün reçete bileşenlerini getir"""
    try:
        urun = get_object_or_404(StokItem, pk=urun_id)
        
        # Aktif reçeteleri bul (varsayılan olarak en son versiyonu al)
        receteler = Recete.objects.filter(urun=urun, aktif=True).order_by('-versiyon')
        
        if not receteler.exists():
            return JsonResponse({
                'success': False,
                'message': 'Bu ürün için aktif reçete bulunamadı.',
                'bilesenler': []
            })
        
        # En son versiyon reçeteyi al
        recete = receteler.first()
        
        # Reçete bileşenlerini getir
        bilesenler = ReceteDetay.objects.filter(recete=recete).select_related('stok_item').order_by('sira', 'stok_item__stok_kodu')
        
        results = []
        for detay in bilesenler:
            results.append({
                'id': detay.stok_item.pk,
                'stok_kodu': detay.stok_item.stok_kodu,
                'ad': detay.stok_item.ad,
                'miktar': str(detay.miktar),
                'birim': detay.birim,
            })
        
        return JsonResponse({
            'success': True,
            'recete_versiyon': recete.versiyon,
            'bilesenler': results
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Hata: {str(e)}',
            'bilesenler': []
        })


@login_required
@require_http_methods(["GET"])
def kurulum_dosyasi_cnc_ekipman_secenekleri_api(request):
    """AJAX: Seçilen istasyona göre (ve ortak) CNC ekipman listesi."""
    sid = request.GET.get("istasyon_id", "").strip()
    istasyon = None
    if sid.isdigit():
        istasyon = Istasyon.objects.filter(pk=int(sid)).first()
    qs = kurulum_dosyasi_cnc_ekipman_secenekleri(istasyon)
    items = []
    for e in qs:
        items.append(
            {
                "id": e.pk,
                "label": str(e),
                "scope": e.machine_scope,
                "scope_label": e.get_machine_scope_display(),
            }
        )
    explicit = ""
    effective = ""
    grup_from_name = False
    if istasyon is not None:
        explicit = (getattr(istasyon, "cnc_makine_grubu", None) or "").strip()
        effective = istasyon_effective_cnc_makine_grubu(istasyon)
        grup_from_name = bool(
            explicit not in ("cnc_lathe", "cnc_mill")
            and effective in ("cnc_lathe", "cnc_mill")
        )
    return JsonResponse(
        {
            "success": True,
            "items": items,
            "istasyon_cnc_grubu": explicit,
            "effective_cnc_grubu": effective,
            "grup_from_name": grup_from_name,
        }
    )


@login_required
def kurulum_dosyasi_ekle(request):
    """Yeni kurulum dosyası ekle"""
    if request.method == 'POST':
        form = KurulumDosyasiForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    dosya = form.save()
                    ok, err = _kurulum_cnc_secimini_uygula(dosya, request)
                    if not ok:
                        raise ValueError(err or "CNC ekipman seçimi geçersiz.")
                messages.success(request, f'Kurulum dosyası başarıyla eklendi.')
                return redirect('stokapp:kurulum_dosyalari_listesi')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
    else:
        form = KurulumDosyasiForm()
        form.fields['versiyon'].initial = '1.0'
    
    # İstasyon listesi
    istasyonlar = Istasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    
    if request.method == "POST":
        secili_cnc_json = json.dumps(_kurulum_cnc_ekipman_secim_ids(request))
    else:
        secili_cnc_json = json.dumps([])
    
    context = {
        'form': form,
        'istasyonlar': istasyonlar,
        'secili_cnc_ekipman_ids_json': secili_cnc_json,
    }
    return render(request, 'stokapp/kurulum_dosyasi_ekle.html', context)


@login_required
def kurulum_dosyasi_detay(request, pk):
    """Kurulum dosyası detay sayfası - arşivlenmiş versiyonlar dahil"""
    dosya = get_object_or_404(
        KurulumDosyasi.objects.select_related("urun", "istasyon").prefetch_related(
            "cnc_ekipmanlar"
        ),
        pk=pk,
    )
    
    # Arşivlenmiş versiyonları getir
    arsivlenmis_versiyonlar = KurulumDosyasiArsiv.objects.filter(kurulum_dosyasi=dosya).order_by('-arsiv_tarihi')
    
    context = {
        'dosya': dosya,
        'arsivlenmis_versiyonlar': arsivlenmis_versiyonlar,
    }
    return render(request, 'stokapp/kurulum_dosyasi_detay.html', context)


@login_required
def kurulum_dosyasi_duzenle(request, pk):
    """Kurulum dosyası düzenle"""
    dosya = get_object_or_404(KurulumDosyasi, pk=pk)
    eski_versiyon = dosya.versiyon
    eski_pdf_dosya = dosya.pdf_dosya
    
    if request.method == 'POST':
        form = KurulumDosyasiForm(request.POST, request.FILES, instance=dosya)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Versiyon değiştiyse eski dosyayı arşive al
                    yeni_versiyon = form.cleaned_data['versiyon']
                    yeni_pdf_dosya = form.cleaned_data.get('pdf_dosya')
                    
                    # Versiyon değiştiyse eski dosyayı arşive al
                    if yeni_versiyon != eski_versiyon and eski_pdf_dosya:
                        # Eski versiyonu arşive al
                        KurulumDosyasiArsiv.objects.create(
                            kurulum_dosyasi=dosya,
                            pdf_dosya=eski_pdf_dosya,
                            versiyon=eski_versiyon,
                            aciklama=f'Versiyon {eski_versiyon} → {yeni_versiyon} güncellemesi nedeniyle arşivlendi.'
                        )
                    
                    # Dosyayı kaydet (yeni PDF yoksa mevcut dosya korunur)
                    dosya = form.save(commit=False)
                    if not yeni_pdf_dosya:
                        dosya.pdf_dosya = eski_pdf_dosya
                    dosya.save()
                    ok, err = _kurulum_cnc_secimini_uygula(dosya, request)
                    if not ok:
                        raise ValueError(err or "CNC ekipman seçimi geçersiz.")
                    
                messages.success(request, f'Kurulum dosyası güncellendi.')
                return redirect('stokapp:kurulum_dosyasi_detay', pk=dosya.pk)
            except ValueError as e:
                messages.error(request, str(e))
                dosya.refresh_from_db()
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
                dosya.refresh_from_db()
    else:
        form = KurulumDosyasiForm(instance=dosya)
    
    # İstasyon listesi
    istasyonlar = Istasyon.objects.filter(aktif=True).order_by('sira', 'ad')
    
    if request.method == "POST":
        secili_cnc_json = json.dumps(_kurulum_cnc_ekipman_secim_ids(request))
    else:
        secili_cnc_json = json.dumps(
            list(dosya.cnc_ekipmanlar.values_list("pk", flat=True))
        )
    
    context = {
        'form': form,
        'dosya': dosya,
        'istasyonlar': istasyonlar,
        'secili_cnc_ekipman_ids_json': secili_cnc_json,
    }
    return render(request, 'stokapp/kurulum_dosyasi_duzenle.html', context)


@login_required
def kurulum_dosyasi_sil(request, pk):
    """Kurulum dosyası sil"""
    dosya = get_object_or_404(KurulumDosyasi, pk=pk)
    
    if request.method == 'POST':
        try:
            urun_adi = f"{dosya.urun.stok_kodu} - {dosya.urun_parcasi}"
            dosya.delete()
            messages.success(request, f'Kurulum dosyası "{urun_adi}" silindi.')
            return redirect('stokapp:kurulum_dosyalari_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'dosya': dosya,
    }
    return render(request, 'stokapp/kurulum_dosyasi_sil.html', context)


@login_required
def kurulum_dosyasi_pdf_indir(request, pk):
    """Kurulum dosyası PDF'ini indir"""
    dosya = get_object_or_404(KurulumDosyasi, pk=pk)
    
    if not dosya.pdf_dosya:
        raise Http404("PDF dosyası bulunamadı.")
    
    try:
        return FileResponse(
            dosya.pdf_dosya.open(),
            as_attachment=True,
            filename=os.path.basename(dosya.pdf_dosya.name)
        )
    except Exception as e:
        messages.error(request, f'PDF dosyası açılırken hata oluştu: {str(e)}')
        return redirect('stokapp:kurulum_dosyasi_detay', pk=pk)


@login_required
def kurulum_dosyasi_arsiv_pdf_indir(request, pk):
    """Arşivlenmiş kurulum dosyası PDF'ini indir"""
    arsiv = get_object_or_404(KurulumDosyasiArsiv, pk=pk)
    
    if not arsiv.pdf_dosya:
        raise Http404("PDF dosyası bulunamadı.")
    
    try:
        return FileResponse(
            arsiv.pdf_dosya.open(),
            as_attachment=True,
            filename=os.path.basename(arsiv.pdf_dosya.name)
        )
    except Exception as e:
        messages.error(request, f'PDF dosyası açılırken hata oluştu: {str(e)}')
        return redirect('stokapp:kurulum_dosyasi_detay', pk=arsiv.kurulum_dosyasi.pk)


@login_required
def kurulum_dosyasi_arsiv_listesi(request, pk):
    """Kurulum dosyasının arşivlenmiş versiyonları"""
    dosya = get_object_or_404(KurulumDosyasi, pk=pk)
    arsivlenmis_versiyonlar = KurulumDosyasiArsiv.objects.filter(kurulum_dosyasi=dosya).order_by('-arsiv_tarihi')
    
    context = {
        'dosya': dosya,
        'arsivlenmis_versiyonlar': arsivlenmis_versiyonlar,
    }
    return render(request, 'stokapp/kurulum_dosyasi_arsiv_listesi.html', context)

