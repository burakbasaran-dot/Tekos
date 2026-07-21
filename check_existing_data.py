#!/usr/bin/env python
"""
Mevcut ReceteTalimatEkipman kayıtlarını kontrol et ve temizle
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uretim_stok.settings')
django.setup()

from stokapp.models import ReceteTalimatEkipman

# Mevcut kayıtları kontrol et
existing = ReceteTalimatEkipman.objects.all()
count = existing.count()

print(f"Mevcut ReceteTalimatEkipman kayıt sayısı: {count}")

if count > 0:
    print("\nMevcut kayıtlar:")
    for item in existing[:10]:  # İlk 10 tanesini göster
        print(f"  - ID: {item.id}, Talimat: {item.talimat}, Ad: {getattr(item, 'ad', 'N/A')}")
    
    if count > 10:
        print(f"  ... ve {count - 10} kayıt daha")
    
    print("\n⚠️  UYARI: Bu kayıtlar eski model yapısıyla oluşturulmuş (ad ve aciklama alanları var).")
    print("   Yeni model yapısında ekipman ForeignKey kullanılıyor.")
    print("\n   Eğer bu kayıtlar önemli değilse, silinebilirler.")
    print("   Silmek için: python manage.py shell")
    print("   > from stokapp.models import ReceteTalimatEkipman")
    print("   > ReceteTalimatEkipman.objects.all().delete()")
else:
    print("\n✅ Mevcut kayıt yok. Migration sorunsuz yapılabilir.")

