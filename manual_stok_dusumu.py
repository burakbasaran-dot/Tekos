#!/usr/bin/env python
"""
UE-7 ve UE-5 üretim emirleri için manuel stok düşüm işlemi
Bu scripti Django shell'de çalıştırmak için:
python manage.py shell < manual_stok_dusumu.py
"""
from django.db import transaction
from decimal import Decimal
from stokapp.models import UretimEmri, StokHareketi

emir_nolari = ['UE-7', 'UE-5']

for emir_no in emir_nolari:
    try:
        emir = UretimEmri.objects.get(emir_no=emir_no)
        print(f"\n{'='*60}")
        print(f"Emir: {emir.emir_no}")
        print(f"Mevcut Durum: {emir.durum}")
        print(f"Ürün: {emir.recete.urun.stok_kodu} - {emir.recete.urun.ad}")
        print(f"Miktar: {emir.miktar}")
        
        # Reçete detaylarını al
        recete_detaylar = emir.recete.detaylar.all()
        print(f"\nReçete Detayları ({recete_detaylar.count()} adet):")
        
        # Mevcut çıkış hareketlerini kontrol et
        mevcut_cikis_hareketleri = StokHareketi.objects.filter(
            uretim_emri=emir,
            hareket_tipi='URETIM_CIKIS'
        ).values_list('stok_item_id', 'miktar')
        
        # Her stok item için toplam çıkış miktarını hesapla
        cikis_dict = {}
        for stok_item_id, miktar in mevcut_cikis_hareketleri:
            cikis_dict[stok_item_id] = cikis_dict.get(stok_item_id, 0) + Decimal(str(miktar))
        
        print(f"Mevcut çıkış hareketleri: {len(mevcut_cikis_hareketleri)} adet")
        
        with transaction.atomic():
            # Her reçete detayı için gerekli miktarı kontrol et ve eksik kalanları düş
            for detay in recete_detaylar:
                gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
                cikis_yapilan_miktar = cikis_dict.get(detay.stok_item_id, Decimal('0'))
                eksik_miktar = gerekli_miktar - cikis_yapilan_miktar
                
                print(f"\n  {detay.stok_item.stok_kodu} ({detay.stok_item.ad}):")
                print(f"    Reçete miktarı: {detay.miktar}")
                print(f"    Gerekli toplam: {gerekli_miktar}")
                print(f"    Daha önce düşülen: {cikis_yapilan_miktar}")
                print(f"    Eksik: {eksik_miktar}")
                print(f"    Mevcut stok: {detay.stok_item.mevcut_miktar}")
                
                # Eksik miktar varsa ve mevcut stokta varsa, stok düşümü yap
                if eksik_miktar > 0:
                    mevcut_stok = Decimal(str(detay.stok_item.mevcut_miktar))
                    dusecek_miktar = min(mevcut_stok, eksik_miktar)
                    
                    if dusecek_miktar > 0:
                        print(f"    ✓ Stok düşümü yapılıyor: {dusecek_miktar}")
                        StokHareketi.objects.create(
                            stok_item=detay.stok_item,
                            hareket_tipi='URETIM_CIKIS',
                            miktar=dusecek_miktar,
                            birim=detay.birim,
                            referans_no=emir.emir_no,
                            uretim_emri=emir,
                            aciklama=f'Üretim emri {emir.emir_no} tamamlandı - manuel stok düşümü (Gerekli: {gerekli_miktar}, Daha önce düşülen: {cikis_yapilan_miktar}, Şimdi düşülen: {dusecek_miktar})',
                            user='Manuel İşlem'
                        )
                        print(f"    ✓ Stok hareketi oluşturuldu")
                    else:
                        print(f"    ✗ Stokta yeterli miktar yok")
                else:
                    print(f"    ✓ Zaten yeterli miktar düşülmüş")
        
        print(f"\n✓ {emir_no} için stok düşüm işlemi tamamlandı")
        
    except UretimEmri.DoesNotExist:
        print(f"\n✗ HATA: {emir_no} kodlu üretim emri bulunamadı")
    except Exception as e:
        print(f"\n✗ HATA ({emir_no}): {str(e)}")
        import traceback
        traceback.print_exc()

print("\n" + "="*60)
print("İşlem tamamlandı!")
