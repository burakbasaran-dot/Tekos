from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import StokItem, FiyatGecmisi
from django.db.models import Q


@login_required
def fiyat_gecmisi(request, pk):
    """Stok item'ın fiyat geçmişi"""
    stok_item = get_object_or_404(StokItem, pk=pk)
    gecmisler = FiyatGecmisi.objects.filter(stok_item=stok_item).order_by('-tarih')
    
    context = {
        'stok_item': stok_item,
        'gecmisler': gecmisler,
    }
    return render(request, 'stokapp/fiyat_gecmisi.html', context)


@login_required
def fiyat_gecmisi_listesi(request):
    """Tüm fiyat değişiklikleri listesi"""
    gecmisler = FiyatGecmisi.objects.all().select_related('stok_item').order_by('-tarih')
    
    # Filtreleme
    stok_kodu = request.GET.get('stok_kodu', '')
    if stok_kodu:
        gecmisler = gecmisler.filter(stok_item__stok_kodu__icontains=stok_kodu)
    
    alan = request.GET.get('alan', '')
    if alan:
        gecmisler = gecmisler.filter(degisen_alan=alan)
    
    context = {
        'gecmisler': gecmisler[:100],  # Son 100 kayıt
        'stok_kodu': stok_kodu,
        'alan': alan,
    }
    return render(request, 'stokapp/fiyat_gecmisi_listesi.html', context)