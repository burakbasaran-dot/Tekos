
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from .models import StokItem, EkDosya
try:
    from .models import StokHareketi, Recete, ReceteDetay, ReceteOperasyon, CncProgram
except Exception:
    StokHareketi = None
    Recete = None
    ReceteDetay = None
    ReceteOperasyon = None
    CncProgram = None

@login_required
def stok_detay(request, pk:int):
    stok = get_object_or_404(StokItem, pk=pk)
    hareketler = []
    if StokHareketi is not None:
        hareketler = (StokHareketi.objects
                      .filter(stok_item=stok)
                      .order_by('-tarih')[:100])
    ekler = stok.ek_dosyalar.all() if hasattr(stok, 'ek_dosyalar') else []
    
    # Aktif reçeteyi bul ve maliyetleri hesapla
    ham_madde_maliyeti = Decimal('0')
    operasyonel_maliyetler = Decimal('0')
    toplam_uretim_maliyeti = Decimal('0')
    para_birimi = 'TL'
    para_sembol = '₺'
    
    if Recete is not None:
        # Aktif reçeteyi bul (bu stok için)
        aktif_recete = Recete.objects.filter(urun=stok, aktif=True).first()
        
        if aktif_recete:
            # Reçete bileşenleri toplamını hesapla - Ham Madde Maliyeti
            # Reçete detay sayfasındaki hesaplama mantığı ile aynı
            if ReceteDetay is not None:
                detaylar = ReceteDetay.objects.filter(recete=aktif_recete).select_related('stok_item').all()
                
                for detay in detaylar:
                    birim_fiyat = detay.stok_item.alis_fiyati or Decimal('0')
                    miktar = detay.miktar
                    tutar = miktar * birim_fiyat
                    ham_madde_maliyeti += tutar
                    
                    # İlk bulduğumuz para birimini kullan (basitleştirme için)
                    if para_birimi == 'TL' and detay.stok_item.alis_para_birimi:
                        para_birimi = detay.stok_item.alis_para_birimi or 'TL'
                        para_sembol = '₺' if para_birimi == 'TL' else \
                                     '$' if para_birimi == 'USD' else \
                                     '€' if para_birimi == 'EUR' else \
                                     '£' if para_birimi == 'GBP' else para_birimi
            
            # Operasyonel Maliyetler: Reçete operasyonlarının toplam_maliyet toplamı
            # Reçete detay sayfasındaki hesaplama mantığı ile aynı
            if ReceteOperasyon is not None:
                operasyonlar = ReceteOperasyon.objects.filter(recete=aktif_recete).all()
                for op in operasyonlar:
                    operasyonel_maliyetler += op.toplam_maliyet or Decimal('0')
            
            # Toplam Üretim Maliyeti = Ham Madde Maliyeti + Operasyonel Maliyetler
            toplam_uretim_maliyeti = ham_madde_maliyeti + operasyonel_maliyetler
    
    # CNC Programları getir
    cnc_programlar = []
    if CncProgram is not None:
        cnc_programlar = CncProgram.objects.filter(product=stok, status='active').order_by('-created_at')
    
    ctx = {
        'stok': stok,
        'hareketler': hareketler,
        'ekler': ekler,
        'ham_madde_maliyeti': ham_madde_maliyeti,
        'operasyonel_maliyetler': operasyonel_maliyetler,
        'toplam_uretim_maliyeti': toplam_uretim_maliyeti,
        'para_birimi': para_birimi,
        'para_sembol': para_sembol,
        'cnc_programlar': cnc_programlar,
    }
    return render(request, "stokapp/stok_detay.html", ctx)
