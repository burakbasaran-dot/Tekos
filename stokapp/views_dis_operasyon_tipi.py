"""Ayarlar — dış operasyon tipi (DisOperasyonTipi) yönetimi."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DisOperasyonTipiForm
from .models import DisOperasyonTipi
from .views_recete_dis import _unique_operasyon_kodu


def _dis_tipleri_queryset(hepsini_goster: bool):
    qs = DisOperasyonTipi.objects.filter(ic_dis_tipi='DIS')
    if not hepsini_goster:
        qs = qs.filter(aktif=True)
    return qs.order_by('ad')


@login_required
def dis_operasyon_tipi_listesi(request):
    hepsini_goster = request.GET.get('hepsini_goster', 'false') == 'true'
    return render(request, 'stokapp/dis_operasyon_tipi_listesi.html', {
        'tipler': _dis_tipleri_queryset(hepsini_goster),
        'hepsini_goster': hepsini_goster,
    })


@login_required
def dis_operasyon_tipi_ekle_sayfa(request):
    if request.method == 'POST':
        form = DisOperasyonTipiForm(request.POST)
        if form.is_valid():
            try:
                tip = form.save(commit=False)
                tip.ic_dis_tipi = 'DIS'
                if not tip.operasyon_kodu:
                    tip.operasyon_kodu = _unique_operasyon_kodu(tip.ad)
                tip.save()
                messages.success(request, f'Dış operasyon "{tip.ad}" başarıyla eklendi.')
                return redirect('stokapp:dis_operasyon_tipi_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {e}')
    else:
        form = DisOperasyonTipiForm()
    return render(request, 'stokapp/dis_operasyon_tipi_ekle.html', {'form': form})


@login_required
def dis_operasyon_tipi_duzenle(request, pk):
    tip = get_object_or_404(DisOperasyonTipi, pk=pk, ic_dis_tipi='DIS')
    if request.method == 'POST':
        form = DisOperasyonTipiForm(request.POST, instance=tip)
        if form.is_valid():
            try:
                tip = form.save(commit=False)
                tip.ic_dis_tipi = 'DIS'
                if not tip.operasyon_kodu:
                    tip.operasyon_kodu = _unique_operasyon_kodu(tip.ad)
                tip.save()
                messages.success(request, f'Dış operasyon "{tip.ad}" güncellendi.')
                return redirect('stokapp:dis_operasyon_tipi_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {e}')
    else:
        form = DisOperasyonTipiForm(instance=tip)
    return render(request, 'stokapp/dis_operasyon_tipi_duzenle.html', {'form': form, 'tip': tip})


@login_required
def dis_operasyon_tipi_sil(request, pk):
    tip = get_object_or_404(DisOperasyonTipi, pk=pk, ic_dis_tipi='DIS')
    if request.method == 'POST':
        try:
            ad = tip.ad
            tip.delete()
            messages.success(request, f'Dış operasyon "{ad}" silindi.')
            return redirect('stokapp:dis_operasyon_tipi_listesi')
        except ProtectedError:
            messages.error(
                request,
                'Bu dış operasyon reçete veya dış operasyon kayıtlarında kullanıldığı için silinemez. Pasif yapabilirsiniz.',
            )
        except Exception as e:
            messages.error(request, f'Hata: {e}')
    return render(request, 'stokapp/dis_operasyon_tipi_sil.html', {'tip': tip})


@login_required
def dis_operasyon_tipi_durum_degistir(request, pk):
    tip = get_object_or_404(DisOperasyonTipi, pk=pk, ic_dis_tipi='DIS')
    if request.method == 'POST':
        try:
            tip.aktif = not tip.aktif
            tip.save(update_fields=['aktif'])
            return JsonResponse({'success': True, 'aktif': tip.aktif})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})
