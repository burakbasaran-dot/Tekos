import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms_arge import ArGeDosyaForm, ArGeProjeForm, ArGeRevizyonForm
from .models import ArGeDosya, ArGeProje, ArGeRevizyon
from .rbac_utils import has_permission


def _beklenen_revizyon_no(proje):
    return ArGeRevizyon.sonraki_revizyon_no(proje)


def _proje_detay_redirect(pk, tab='genel'):
    url = reverse('stokapp:arge_proje_detay', kwargs={'pk': pk})
    if tab and tab != 'genel':
        return redirect(f'{url}?tab={tab}')
    return redirect(url)


@login_required
def arge_proje_listesi(request):
    tab = request.GET.get('tab', 'aktif')
    q = (request.GET.get('q') or '').strip()
    durum = (request.GET.get('durum') or '').strip()

    qs = ArGeProje.objects.select_related('stok_item', 'sorumlu').order_by('-created_at')
    if tab == 'arsiv':
        qs = qs.filter(arsivli=True)
    else:
        qs = qs.filter(arsivli=False)

    if durum:
        qs = qs.filter(durum=durum)
    if q:
        qs = qs.filter(
            Q(proje_kodu__icontains=q)
            | Q(proje_adi__icontains=q)
            | Q(stok_item__stok_kodu__icontains=q)
            | Q(stok_item__ad__icontains=q)
        )

    return render(
        request,
        'stokapp/arge_proje_listesi.html',
        {
            'projeler': qs,
            'tab': tab,
            'q': q,
            'durum': durum,
            'durum_secenekleri': ArGeProje.DURUM_CHOICES,
        },
    )


@login_required
def arge_proje_ekle(request):
    if request.method == 'POST':
        form = ArGeProjeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    proje = form.save(commit=False)
                    if not proje.proje_kodu:
                        proje.proje_kodu = ArGeProje.uret_sonraki_proje_kodu()
                    proje.save()
                messages.success(request, f'Proje "{proje.proje_kodu}" oluşturuldu.')
                return redirect('stokapp:arge_proje_detay', pk=proje.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ArGeProjeForm(
            initial={
                'proje_kodu': ArGeProje.uret_sonraki_proje_kodu(),
                'baslangic_tarihi': timezone.now().date(),
            }
        )
    return render(request, 'stokapp/arge_proje_form.html', {'form': form, 'baslik': 'Yeni Ar-Ge projesi'})


@login_required
def arge_proje_duzenle(request, pk):
    proje = get_object_or_404(ArGeProje, pk=pk)
    if request.method == 'POST':
        form = ArGeProjeForm(request.POST, instance=proje)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Proje güncellendi.')
                return redirect('stokapp:arge_proje_detay', pk=proje.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ArGeProjeForm(instance=proje)
    return render(
        request,
        'stokapp/arge_proje_form.html',
        {'form': form, 'baslik': f'Proje düzenle: {proje.proje_kodu}', 'proje': proje},
    )


@login_required
@require_POST
def arge_proje_arsivle(request, pk):
    proje = get_object_or_404(ArGeProje, pk=pk)
    proje.arsivli = not proje.arsivli
    proje.save(update_fields=['arsivli', 'updated_at'])
    messages.success(
        request, 'Proje arşivlendi.' if proje.arsivli else 'Proje arşivden çıkarıldı.'
    )
    return redirect('stokapp:arge_proje_detay', pk=proje.pk)


@login_required
def arge_proje_detay(request, pk):
    proje = get_object_or_404(
        ArGeProje.objects.select_related('stok_item', 'sorumlu'),
        pk=pk,
    )
    tab = (request.GET.get('tab') or 'genel').lower()
    allowed = {
        'genel',
        'revizyonlar',
        'prototipler',
        'testler',
        'dosyalar',
        'maliyet',
        'kararlar',
        'seri',
    }
    if tab not in allowed:
        tab = 'genel'

    revizyonlar = proje.revizyonlar.all().order_by('id')
    dosyalar = proje.dosyalar.all().order_by('-uploaded_at')

    dosya_form = None
    can_dosya_ekle = request.user.is_superuser or has_permission(request.user, 'arge.ekle')
    if tab == 'dosyalar' and can_dosya_ekle:
        dosya_form = ArGeDosyaForm()

    checklist_items = [
        ('Teknik resim hazır', proje.teknik_resim_hazir),
        ('CAD hazır', proje.cad_hazir),
        ('Malzeme tanımlı', proje.malzeme_tanimli),
        ('Operasyon tanımlı', proje.operasyon_tanimli),
        ('Maliyet hesaplandı', proje.maliyet_hesaplandi),
        ('Kontrol planı hazır', proje.kontrol_plani_hazir),
        ('Paketleme hazır', proje.paketleme_hazir),
        ('Stok kodu var', proje.stok_kodu_var),
        ('Satış fiyatı belirlendi', proje.satis_fiyati_belirlendi),
    ]

    return render(
        request,
        'stokapp/arge_proje_detay.html',
        {
            'proje': proje,
            'tab': tab,
            'revizyonlar': revizyonlar,
            'dosyalar': dosyalar,
            'dosya_form': dosya_form,
            'checklist_ok': proje.seri_uretime_checklist_tamam(),
            'checklist_items': checklist_items,
        },
    )


@login_required
def arge_revizyon_listesi(request):
    proje_id = request.GET.get('proje')
    qs = ArGeRevizyon.objects.select_related('proje', 'proje__stok_item').order_by('-tarih', '-id')
    if proje_id:
        qs = qs.filter(proje_id=proje_id)
    return render(
        request,
        'stokapp/arge_revizyon_listesi.html',
        {'revizyonlar': qs, 'proje_id': proje_id},
    )


@login_required
def arge_revizyon_ekle(request, proje_pk):
    proje = get_object_or_404(ArGeProje, pk=proje_pk)
    beklenen = _beklenen_revizyon_no(proje)
    if request.method == 'POST':
        form = ArGeRevizyonForm(request.POST, request.FILES)
        if form.is_valid():
            rno = (form.cleaned_data.get('revizyon_no') or '').strip().upper()
            if rno != beklenen:
                form.add_error(
                    'revizyon_no',
                    f'Sıradaki revizyon numarası {beklenen} olmalıdır (sıralı R0, R1, …).',
                )
            else:
                rev = form.save(commit=False)
                rev.proje = proje
                try:
                    rev.save()
                    messages.success(request, f'{rev.revizyon_no} kaydedildi.')
                    return _proje_detay_redirect(proje.pk, 'revizyonlar')
                except Exception as e:
                    messages.error(request, str(e))
    else:
        form = ArGeRevizyonForm(initial={'revizyon_no': beklenen, 'onceki_durum': proje.durum})
    return render(
        request,
        'stokapp/arge_revizyon_form.html',
        {'form': form, 'proje': proje, 'beklenen_rev': beklenen, 'baslik': 'Yeni revizyon'},
    )


@login_required
def arge_revizyon_duzenle(request, pk):
    rev = get_object_or_404(ArGeRevizyon.objects.select_related('proje'), pk=pk)
    proje = rev.proje
    if request.method == 'POST':
        form = ArGeRevizyonForm(request.POST, request.FILES, instance=rev)
        if form.is_valid():
            rno = (form.cleaned_data.get('revizyon_no') or '').strip().upper()
            if rno != rev.revizyon_no:
                form.add_error('revizyon_no', 'Mevcut revizyon numarası değiştirilemez.')
            else:
                try:
                    form.save()
                    messages.success(request, 'Revizyon güncellendi.')
                    return _proje_detay_redirect(proje.pk, 'revizyonlar')
                except Exception as e:
                    messages.error(request, str(e))
    else:
        form = ArGeRevizyonForm(instance=rev)
    return render(
        request,
        'stokapp/arge_revizyon_form.html',
        {
            'form': form,
            'proje': proje,
            'revizyon': rev,
            'baslik': f'Revizyon düzenle: {rev.revizyon_no}',
        },
    )


@login_required
@require_POST
def arge_revizyon_sil(request, pk):
    rev = get_object_or_404(ArGeRevizyon, pk=pk)
    pid = rev.proje_id
    rev.delete()
    messages.success(request, 'Revizyon silindi.')
    return _proje_detay_redirect(pid, 'revizyonlar')


@login_required
@require_POST
def arge_dosya_sil(request, pk):
    dosya = get_object_or_404(ArGeDosya, pk=pk)
    pid = dosya.proje_id
    if dosya.dosya:
        try:
            if os.path.isfile(dosya.dosya.path):
                os.remove(dosya.dosya.path)
        except Exception:
            pass
    dosya.delete()
    messages.success(request, 'Dosya kaldırıldı.')
    return _proje_detay_redirect(pid, 'dosyalar')


@login_required
def arge_dosya_ekle(request, pk):
    proje = get_object_or_404(ArGeProje, pk=pk)
    if request.method == 'POST':
        form = ArGeDosyaForm(request.POST, request.FILES)
        if form.is_valid():
            d = form.save(commit=False)
            d.proje = proje
            d.save()
            messages.success(request, 'Dosya yüklendi.')
            return _proje_detay_redirect(proje.pk, 'dosyalar')
        messages.error(request, 'Dosya yüklenemedi; formu kontrol edin.')
        return render(
            request,
            'stokapp/arge_dosya_ekle.html',
            {'form': form, 'proje': proje},
        )
    return redirect('stokapp:arge_proje_detay', pk=pk)


@login_required
def arge_dosya_indir(request, pk):
    dosya = get_object_or_404(ArGeDosya, pk=pk)
    if not dosya.dosya:
        raise Http404()
    try:
        return FileResponse(
            dosya.dosya.open('rb'),
            as_attachment=True,
            filename=os.path.basename(dosya.dosya.name),
        )
    except Exception:
        raise Http404()


@login_required
def arge_dosya_listesi(request):
    proje_id = request.GET.get('proje')
    qs = ArGeDosya.objects.select_related('proje', 'proje__stok_item').order_by('-uploaded_at')
    if proje_id:
        qs = qs.filter(proje_id=proje_id)
    return render(
        request,
        'stokapp/arge_dosya_listesi.html',
        {'dosyalar': qs, 'proje_id': proje_id},
    )


@login_required
def arge_asama_yakinda(request):
    modul = (request.GET.get('m') or '').strip() or 'arge'
    etiketler = {
        'prototip': 'Prototip / Demo Üretimler',
        'test': 'Test ve Kontroller',
        'maliyet': 'Maliyet Takibi',
        'karar': 'Kararlar',
    }
    return render(
        request,
        'stokapp/arge_asama_yakinda.html',
        {'modul_etiket': etiketler.get(modul, 'Ar-Ge'), 'modul_kod': modul},
    )
