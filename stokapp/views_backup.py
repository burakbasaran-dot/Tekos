from django.shortcuts import render
from django.db.models import Sum, Count, F
from .models import StokItem, StokHareketi, Kategori
from django.contrib.auth.decorators import login_required
import pandas as pd
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages

@login_required
def dashboard(request):
    # Stok özet istatistikleri
    toplam_urun_sayisi = StokItem.objects.count()
    kritik_stok_sayisi = StokItem.objects.filter(mevcut_miktar__lte=F('minimum_stok')).count()
    stoksuz_urun_sayisi = StokItem.objects.filter(mevcut_miktar=0).count()
    
    # Toplam stok değeri (basit hesaplama)
    toplam_stok_degeri = sum(
        item.mevcut_miktar * item.alis_fiyati 
        for item in StokItem.objects.all()
    )
    
    # Kritik stok listesi
    kritik_stoklar = StokItem.objects.filter(mevcut_miktar__lte=F('minimum_stok')).order_by('mevcut_miktar')
    
    # Son hareketler
    son_hareketler = StokHareketi.objects.all().order_by('-tarih')[:10]
    
    # Kategori bazlı stok sayıları
    kategori_stoklari = StokItem.objects.values('kategori__ad').annotate(
        urun_sayisi=Count('id'),
        toplam_miktar=Sum('mevcut_miktar')
    )
    
    context = {
        'toplam_urun_sayisi': toplam_urun_sayisi,
        'kritik_stok_sayisi': kritik_stok_sayisi,
        'stoksuz_urun_sayisi': stoksuz_urun_sayisi,
        'toplam_stok_degeri': round(toplam_stok_degeri, 2),
        'kritik_stoklar': kritik_stoklar,
        'son_hareketler': son_hareketler,
        'kategori_stoklari': kategori_stoklari,
    }
    
    return render(request, 'stokapp/dashboard.html', context)

@login_required
def kritik_stok_raporu(request):
    kritik_stoklar = StokItem.objects.filter(mevcut_miktar__lte=F('minimum_stok')).order_by('mevcut_miktar')
    return render(request, 'stokapp/kritik_stok_raporu.html', {'kritik_stoklar': kritik_stoklar})

@login_required
def stok_hareket_raporu(request):
    hareketler = StokHareketi.objects.all().order_by('-tarih')
    return render(request, 'stokapp/stok_hareket_raporu.html', {'hareketler': hareketler})

@login_required
def stok_listesi(request):
    stok_items = StokItem.objects.all().order_by('stok_kodu')
    return render(request, 'stokapp/stok_listesi.html', {'stok_items': stok_items})

# EXCEL FONKSİYONLARI
@login_required
def excel_import_page(request):
    return render(request, 'stokapp/excel_import.html')

@login_required
def export_stok_listesi(request):
    try:
        # Stok verilerini al
        stok_items = StokItem.objects.all().values(
            'stok_kodu', 'ad', 'kategori__ad', 'kategori__stok_tipi',
            'birim', 'mevcut_miktar', 'minimum_stok', 'alis_fiyati', 
            'alis_para_birimi', 'barkod', 'aciklama'
        )
        
        # DataFrame oluştur
        df = pd.DataFrame(list(stok_items))
        
        # Sütun isimlerini düzenle
        df.columns = ['Stok Kodu', 'Ürün Adı', 'Kategori', 'Stok Tipi', 
                     'Birim', 'Mevcut Miktar', 'Min. Stok', 'Alış Fiyatı',
                     'Para Birimi', 'Barkod', 'Açıklama']
        
        # Excel dosyası oluştur
        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="stok_listesi.xlsx"'
        
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Stok Listesi', index=False)
            
            # Auto-fit columns
            worksheet = writer.sheets['Stok Listesi']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        return response
        
    except Exception as e:
        messages.error(request, f'Export hatası: {str(e)}')
        return redirect('stokapp:stok_listesi')

@login_required
def export_stok_hareketleri(request):
    try:
        hareketler = StokHareketi.objects.all().values(
            'stok_item__stok_kodu', 'stok_item__ad', 'hareket_tipi',
            'miktar', 'birim', 'referans_no', 'tarih', 'user', 'aciklama'
        )
        
        df = pd.DataFrame(list(hareketler))
        df.columns = ['Stok Kodu', 'Ürün Adı', 'Hareket Tipi', 'Miktar',
                     'Birim', 'Referans No', 'Tarih', 'Kullanıcı', 'Açıklama']
        
        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="stok_hareketleri.xlsx"'
        
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Stok Hareketleri', index=False)
            
            worksheet = writer.sheets['Stok Hareketleri']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        return response
        
    except Exception as e:
        messages.error(request, f'Export hatası: {str(e)}')
        return redirect('stokapp:dashboard')

@login_required
def import_stok_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            
            # Excel dosyasını oku
            df = pd.read_excel(excel_file)
            
            # Sütun kontrolü
            required_columns = ['Stok Kodu', 'Ürün Adı', 'Kategori', 'Birim']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                messages.error(request, f'Eksik sütunlar: {", ".join(missing_columns)}')
                return redirect('stokapp:excel_import_page')
            
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                try:
                    # Kategoriyi bul veya oluştur
                    kategori, created = Kategori.objects.get_or_create(
                        ad=row['Kategori'],
                        defaults={'stok_tipi': 'HAM_MADDE'}
                    )
                    
                    # StokItem oluştur veya güncelle
                    stok_item, created = StokItem.objects.update_or_create(
                        stok_kodu=row['Stok Kodu'],
                        defaults={
                            'ad': row['Ürün Adı'],
                            'kategori': kategori,
                            'birim': row.get('Birim', 'Adet'),
                            'mevcut_miktar': row.get('Mevcut Miktar', 0),
                            'minimum_stok': row.get('Min. Stok', 0),
                            'alis_fiyati': row.get('Alış Fiyatı', 0),
                            'alis_para_birimi': row.get('Para Birimi', 'TL'),
                            'barkod': row.get('Barkod', ''),
                            'aciklama': row.get('Açıklama', '')
                        }
                    )
                    
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    print(f"Satır {index + 2} hatası: {str(e)}")
            
            messages.success(request, f'{success_count} kayıt başarıyla import edildi. {error_count} hata.')
            return redirect('stokapp:stok_listesi')
            
        except Exception as e:
            messages.error(request, f'Import hatası: {str(e)}')
            return redirect('stokapp:excel_import_page')
    
    return redirect('stokapp:excel_import_page')

@login_required
def download_template(request):
    # Örnek template oluştur
    template_data = {
        'Stok Kodu': ['ORNEK-001', 'ORNEK-002'],
        'Ürün Adı': ['Örnek Ürün 1', 'Örnek Ürün 2'],
        'Kategori': ['Ham Madde', 'Yarı Mamül'],
        'Birim': ['Adet', 'Kg'],
        'Mevcut Miktar': [100, 50],
        'Min. Stok': [10, 5],
        'Alış Fiyatı': [25.50, 15.75],
        'Para Birimi': ['TL', 'USD'],
        'Barkod': ['123456789', '987654321'],
        'Açıklama': ['Örnek açıklama 1', 'Örnek açıklama 2']
    }
    
    df = pd.DataFrame(template_data)
    
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="stok_import_template.xlsx"'
    
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Template', index=False)
        
        worksheet = writer.sheets['Template']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    return response
