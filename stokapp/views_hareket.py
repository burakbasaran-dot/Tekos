
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from decimal import Decimal, InvalidOperation
import json
import pandas as pd
from .forms import StokHareketForm
from .models import StokHareketi, Birim, StokItem

def _stok_hareket_kaynak_bilgisi(hareket):
    ref = (hareket.referans_no or '').strip()
    aciklama = (hareket.aciklama or '').strip().lower()
    user = (hareket.user or '').strip()
    tip = (hareket.hareket_tipi or '').strip()

    if tip == 'URETIM_IADE':
        return ('Üretim modülü', 'Üretim emri iptal/silme — tüketilen malzeme iadesi')
    if tip in ('URETIM_GIRIS', 'URETIM_CIKIS'):
        return ('Üretim modülü', 'Üretim emri hareketi')
    if tip == 'GIRIS' and (ref.endswith('-SILINDI') or ref.endswith('-IPTAL')):
        return (
            'Üretim modülü',
            'Üretim emri iptal/silme — malzeme iadesi (eski kayıt, Stok Girişi olarak işaretlenmiş)',
        )
    if tip == 'SATIS_STOK':
        return ('Sipariş modülü', 'Siparişten stok düşümü/sevk hareketi')
    if tip == 'SAYIM':
        return ('Stok sayım', 'Sayım düzeltme hareketi')
    if tip == 'TRANSFER' or ref.startswith('TRANSFER-') or 'transfer:' in aciklama:
        return ('Depo transferi', 'Kaynak/ hedef depo arası transfer')
    if tip.startswith('DISOP_'):
        return ('Dış operasyon', 'Dış operasyon sürecinden otomatik hareket')

    if ref.startswith('SAT-') or 'satınalma teslim' in aciklama:
        return ('Satınalma', 'Satınalma teslimatından gelen stok girişi')

    if tip in ('GIRIS', 'CIKIS'):
        if user and user.lower() != 'sistem':
            return ('Manuel işlem', f'Kullanıcı: {user}')
        return ('Manuel/Diğer', 'Kaynak otomatik tespit edilemedi')

    return ('Diğer', 'Kaynak bilgisi bulunamadı')


@login_required
def stok_giris(request):
    preselected_stok = None
    stok_id_raw = (request.GET.get('stok_id') or '').strip()
    if stok_id_raw:
        try:
            preselected_stok = StokItem.objects.filter(pk=int(stok_id_raw)).first()
        except ValueError:
            preselected_stok = None

    if request.method == 'POST':
        form = StokHareketForm(request.POST, hareket_tipi='GIRIS')
        if form.is_valid():
            with transaction.atomic():
                hareket = form.save(commit=False)
                hareket.hareket_tipi = 'GIRIS'
                hareket.user = request.user.username
                hareket.save()
            messages.success(request, 'Stok girişi kaydedildi.')
            return redirect('stokapp:stok_listesi')
    else:
        form = StokHareketForm(hareket_tipi='GIRIS')
        if preselected_stok:
            form.fields['stok_item'].initial = preselected_stok.pk
            if 'birim' in form.fields and not form.fields['birim'].initial:
                form.fields['birim'].initial = preselected_stok.birim or ''
    
    birimler = Birim.objects.all().order_by('ad')
    return render(request, 'stokapp/stok_hareket_form.html', {
        'form': form,
        'baslik': 'Stok Girişi',
        'buton': 'Girişi Kaydet',
        'birimler': birimler,
        'preselected_stok': preselected_stok,
    })

@login_required
def stok_cikis(request):
    preselected_stok = None
    stok_id_raw = (request.GET.get('stok_id') or '').strip()
    if stok_id_raw:
        try:
            preselected_stok = StokItem.objects.filter(pk=int(stok_id_raw)).first()
        except ValueError:
            preselected_stok = None

    if request.method == 'POST':
        form = StokHareketForm(request.POST, hareket_tipi='CIKIS')
        if form.is_valid():
            with transaction.atomic():
                hareket = form.save(commit=False)
                hareket.hareket_tipi = 'CIKIS'
                hareket.user = request.user.username
                hareket.save()
            messages.success(request, 'Stok çıkışı kaydedildi.')
            return redirect('stokapp:stok_listesi')
    else:
        form = StokHareketForm(hareket_tipi='CIKIS')
        if preselected_stok:
            form.fields['stok_item'].initial = preselected_stok.pk
            if 'birim' in form.fields and not form.fields['birim'].initial:
                form.fields['birim'].initial = preselected_stok.birim or ''
    
    birimler = Birim.objects.all().order_by('ad')
    return render(request, 'stokapp/stok_hareket_form.html', {
        'form': form,
        'baslik': 'Stok Çıkışı',
        'buton': 'Çıkışı Kaydet',
        'birimler': birimler,
        'preselected_stok': preselected_stok,
    })


@login_required
def stok_toplu_hareket(request):
    """Seçili stoklar için toplu giriş/çıkış kaydı oluşturur."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek.'}, status=405)

    hareket_tipi = (request.POST.get('hareket_tipi') or '').strip().upper()
    if hareket_tipi not in ('GIRIS', 'CIKIS'):
        return JsonResponse({'success': False, 'error': 'Geçersiz hareket tipi.'}, status=400)

    stok_ids_raw = (request.POST.get('stok_ids') or '').strip()
    if not stok_ids_raw:
        return JsonResponse({'success': False, 'error': 'En az bir stok seçmelisiniz.'}, status=400)

    try:
        stok_ids = []
        seen = set()
        for x in stok_ids_raw.split(','):
            x = x.strip()
            if not x:
                continue
            sid = int(x)
            if sid in seen:
                continue
            seen.add(sid)
            stok_ids.append(sid)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Geçersiz stok seçimi.'}, status=400)

    miktarlar_raw = request.POST.get('miktarlar') or '{}'
    try:
        miktarlar_map = json.loads(miktarlar_raw)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Geçersiz miktar verisi.'}, status=400)

    referans_no = (request.POST.get('referans_no') or '').strip()
    aciklama = (request.POST.get('aciklama') or '').strip()
    user_name = request.user.username if request.user.is_authenticated else 'Sistem'

    try:
        with transaction.atomic():
            stok_qs = StokItem.objects.select_for_update().filter(pk__in=stok_ids)
            stok_map = {s.pk: s for s in stok_qs}
            eksik_ids = [sid for sid in stok_ids if sid not in stok_map]
            if eksik_ids:
                return JsonResponse({'success': False, 'error': 'Seçilen stoklardan bazıları bulunamadı.'}, status=400)

            kayit_sayisi = 0
            for sid in stok_ids:
                raw_miktar = miktarlar_map.get(str(sid), miktarlar_map.get(sid))
                if raw_miktar in (None, ''):
                    continue
                try:
                    miktar = Decimal(str(raw_miktar).replace(',', '.'))
                except (InvalidOperation, ValueError, TypeError):
                    return JsonResponse({'success': False, 'error': 'Miktar formatı geçersiz.'}, status=400)
                if miktar <= 0:
                    continue

                stok = stok_map[sid]
                StokHareketi.objects.create(
                    stok_item=stok,
                    hareket_tipi=hareket_tipi,
                    miktar=miktar,
                    birim=stok.birim or 'Adet',
                    referans_no=referans_no,
                    aciklama=aciklama,
                    user=user_name,
                )
                kayit_sayisi += 1

            if kayit_sayisi == 0:
                return JsonResponse({'success': False, 'error': 'En az bir stok için 0\'dan büyük miktar girin.'}, status=400)

        tip_text = 'giriş' if hareket_tipi == 'GIRIS' else 'çıkış'
        return JsonResponse({'success': True, 'message': f'{kayit_sayisi} stok için toplu {tip_text} kaydı oluşturuldu.'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

def _stok_hareket_listesi_queryset(request):
    hareketler = StokHareketi.objects.select_related('stok_item').all().order_by('-tarih')

    stok_ids_raw = (request.GET.get('stok_ids') or '').strip()
    if stok_ids_raw:
        try:
            stok_ids = [int(x) for x in stok_ids_raw.split(',') if str(x).strip()]
        except ValueError:
            stok_ids = []
        if stok_ids:
            hareketler = hareketler.filter(stok_item_id__in=stok_ids)

    search = request.GET.get('search', '')
    if search:
        hareketler = hareketler.filter(
            stok_item__stok_kodu__icontains=search
        ) | hareketler.filter(
            stok_item__ad__icontains=search
        ) | hareketler.filter(
            referans_no__icontains=search
        )

    hareket_tipi = request.GET.get('hareket_tipi', '')
    if hareket_tipi:
        hareketler = hareketler.filter(hareket_tipi=hareket_tipi)
    return hareketler


@login_required
def stok_hareket_listesi(request):
    """Stok hareketlerini listele"""
    hareketler = _stok_hareket_listesi_queryset(request)
    search = request.GET.get('search', '')
    hareket_tipi = request.GET.get('hareket_tipi', '')
    stok_ids = request.GET.get('stok_ids', '')
    
    # Sayfalama
    paginator = Paginator(hareketler, 50)
    page = request.GET.get('page', 1)
    hareketler_page = paginator.get_page(page)
    for hareket in hareketler_page.object_list:
        kaynak, detay = _stok_hareket_kaynak_bilgisi(hareket)
        hareket.kaynak_baslik = kaynak
        hareket.kaynak_detay = detay
    
    return render(request, 'stokapp/stok_hareket_listesi.html', {
        'hareketler': hareketler_page,
        'search': search,
        'hareket_tipi': hareket_tipi,
        'stok_ids': stok_ids,
        'hareket_tipleri': StokHareketi.HAREKET_TIPLERI,
    })


@login_required
@never_cache
def stok_hareket_listesi_export_excel(request):
    try:
        hareketler = _stok_hareket_listesi_queryset(request)
        satirlar = []
        for h in hareketler:
            satirlar.append({
                'Tarih': h.tarih.strftime('%d.%m.%Y %H:%M') if h.tarih else '',
                'Stok Kodu': h.stok_item.stok_kodu if h.stok_item else '',
                'Ürün Adı': h.stok_item.ad if h.stok_item else '',
                'Hareket Tipi': h.get_hareket_tipi_display(),
                'Miktar': float(h.miktar or 0),
                'Birim': h.birim,
                'Önceki Stok': float(h.onceki_stok or 0),
                'Sonraki Stok': float(h.sonraki_stok or 0),
                'Referans': h.referans_no or '',
                'Açıklama': h.aciklama or '',
            })

        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=[
                'Tarih', 'Stok Kodu', 'Ürün Adı', 'Hareket Tipi', 'Miktar',
                'Birim', 'Önceki Stok', 'Sonraki Stok', 'Referans', 'Açıklama',
            ])

        from django.utils import timezone
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="stok_hareket_listesi_{ts}.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Hareketler', index=False)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:stok_hareket_listesi')


@login_required
@never_cache
def stok_hareket_listesi_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:stok_hareket_listesi')

    from django.utils import timezone

    hareketler = list(_stok_hareket_listesi_queryset(request)[:1200])
    olusturma_tarihi = timezone.localtime(timezone.now())
    html_rows = []
    for h in hareketler:
        html_rows.append(
            f"""
            <tr>
                <td>{h.tarih.strftime('%d.%m.%Y %H:%M') if h.tarih else '-'}</td>
                <td>{h.stok_item.stok_kodu if h.stok_item else '-'}</td>
                <td>{h.stok_item.ad if h.stok_item else '-'}</td>
                <td>{h.get_hareket_tipi_display()}</td>
                <td class="num">{h.miktar or 0}</td>
                <td>{h.birim or ''}</td>
                <td>{h.referans_no or ''}</td>
            </tr>
            """
        )
    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Stok Hareket Listesi</h1>
      <div class="meta">Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(hareketler)}</div>
      <table>
        <thead><tr><th>Tarih</th><th>Stok Kodu</th><th>Ürün</th><th>Tip</th><th>Miktar</th><th>Birim</th><th>Referans</th></tr></thead>
        <tbody>{''.join(html_rows) if html_rows else '<tr><td colspan="7" class="empty">Kayıt yok.</td></tr>'}</tbody>
      </table>
    </body></html>
    """
    css = CSS(string="""
        @page { size: A4 landscape; margin: 10mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8pt; color: #111827; }
        h1 { font-size: 14pt; margin: 0 0 4px 0; }
        .meta { color: #6b7280; font-size: 8pt; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f3f4f6; border: 1px solid #d1d5db; padding: 5px 4px; text-align: left; font-size: 7.5pt; }
        td { border: 1px solid #e5e7eb; padding: 4px; vertical-align: top; font-size: 7.5pt; }
        .num { text-align: right; white-space: nowrap; }
        .empty { text-align: center; color: #6b7280; padding: 24px; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:stok_hareket_listesi')

    filename = f'stok_hareket_listesi_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def stok_hareket_duzenle(request, pk):
    """Stok hareketini düzenle"""
    hareket = get_object_or_404(StokHareketi, pk=pk)
    
    if request.method == 'POST':
        form = StokHareketForm(request.POST, instance=hareket, hareket_tipi=hareket.hareket_tipi, is_edit=True)
        if form.is_valid():
            with transaction.atomic():
                # Eski değerleri geri al
                eski_miktar = hareket.miktar
                eski_tip = hareket.hareket_tipi
                
                # Yeni değerler
                yeni_miktar = form.cleaned_data['miktar']
                yeni_tip = form.cleaned_data.get('hareket_tipi', eski_tip)
                
                # Stok miktarını düzelt
                stok_item = hareket.stok_item
                
                # Eski hareketi geri al
                if eski_tip in ['GIRIS', 'URETIM_GIRIS', 'URETIM_IADE']:
                    stok_item.mevcut_miktar -= eski_miktar
                elif eski_tip in ['CIKIS', 'URETIM_CIKIS', 'SATIS_STOK']:
                    stok_item.mevcut_miktar += eski_miktar
                elif eski_tip == 'SAYIM':
                    stok_item.mevcut_miktar -= eski_miktar
                
                # Yeni hareketi uygula
                if yeni_tip in ['GIRIS', 'URETIM_GIRIS', 'URETIM_IADE']:
                    stok_item.mevcut_miktar += yeni_miktar
                elif yeni_tip in ['CIKIS', 'URETIM_CIKIS', 'SATIS_STOK']:
                    stok_item.mevcut_miktar -= yeni_miktar
                elif yeni_tip == 'SAYIM':
                    stok_item.mevcut_miktar += yeni_miktar
                
                stok_item.save()
                
                # Hareketi kaydet
                hareket = form.save(commit=False)
                hareket.stok_item = stok_item  # Disabled alan için manuel set
                hareket.hareket_tipi = yeni_tip
                # Önceki stok = şu anki stok - yeni hareket miktarı
                if yeni_tip in ['GIRIS', 'URETIM_GIRIS', 'URETIM_IADE']:
                    hareket.onceki_stok = stok_item.mevcut_miktar - yeni_miktar
                elif yeni_tip in ['CIKIS', 'URETIM_CIKIS', 'SATIS_STOK']:
                    hareket.onceki_stok = stok_item.mevcut_miktar + yeni_miktar
                elif yeni_tip == 'SAYIM':
                    hareket.onceki_stok = stok_item.mevcut_miktar - yeni_miktar
                else:
                    hareket.onceki_stok = stok_item.mevcut_miktar
                hareket.sonraki_stok = stok_item.mevcut_miktar
                hareket.save()
                
            messages.success(request, 'Stok hareketi güncellendi.')
            return redirect('stokapp:stok_hareket_listesi')
    else:
        form = StokHareketForm(instance=hareket, hareket_tipi=hareket.hareket_tipi, is_edit=True)
    
    birimler = Birim.objects.all().order_by('ad')
    return render(request, 'stokapp/stok_hareket_form.html', {
        'form': form,
        'baslik': f'Stok Hareketi Düzenle - {hareket.stok_item.stok_kodu}',
        'buton': 'Güncelle',
        'birimler': birimler,
        'hareket': hareket,
    })

@login_required
def stok_hareket_sil(request, pk):
    """Stok hareketini sil"""
    hareket = get_object_or_404(StokHareketi, pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            # Stok miktarını geri al
            stok_item = hareket.stok_item
            
            if hareket.hareket_tipi in ['GIRIS', 'URETIM_GIRIS', 'URETIM_IADE']:
                stok_item.mevcut_miktar -= hareket.miktar
            elif hareket.hareket_tipi in ['CIKIS', 'URETIM_CIKIS', 'SATIS_STOK']:
                stok_item.mevcut_miktar += hareket.miktar
            elif hareket.hareket_tipi == 'SAYIM':
                stok_item.mevcut_miktar -= hareket.miktar
            
            stok_item.save()
            
            # Hareketi sil
            hareket.delete()
        
        messages.success(request, 'Stok hareketi silindi.')
        return redirect('stokapp:stok_hareket_listesi')
    
    return render(request, 'stokapp/stok_hareket_sil.html', {
        'hareket': hareket,
    })
