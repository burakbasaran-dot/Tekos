from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.db.models import Sum, Q, Exists, OuterRef, F, DecimalField, ExpressionWrapper
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from .models import (
    Satinalma,
    SatinalmaKalemi,
    StokItem,
    Tedarikci,
    Depo,
    StokHareketi,
    UretimEmri,
    ReceteDetay,
    FiyatGecmisi,
    SiparisMaliyeti,
    Siparis,
    TeklifTalebi,
    TeklifTalebiKalemi,
)
from .forms import SatinalmaForm, SatinalmaKalemiForm
from .bom_planlama import (
    aktif_recete_id_by_urun,
    build_kapsanan_urun_ids_by_emir,
    uretim_emri_malzeme_satirlari_detayli,
)
from decimal import Decimal
import json
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.conf import settings
from io import BytesIO
import os
import base64
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None
import re
import shutil
from django.core.files.base import ContentFile

# WeasyPrint lazy import - sistem bağımlılıkları olabilir
WEASYPRINT_AVAILABLE = None  # Lazy check

try:
    from xhtml2pdf import pisa
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False


def _satinalma_kalem_efektif_fiyat(kalem):
    """Kalemde teklif fiyatı varsa onu, yoksa birim fiyatı döndür."""
    if kalem.tedarikci_fiyat is not None:
        return Decimal(str(kalem.tedarikci_fiyat))
    return Decimal(str(kalem.birim_fiyat or Decimal("0")))


def _stok_alis_fiyati_guncelle_ve_gecmis(stok_item, yeni_fiyat, para_birimi, aciklama, username):
    """Stok alış fiyatını günceller, değişim varsa fiyat geçmişi kaydı açar."""
    yeni_fiyat = Decimal(str(yeni_fiyat or 0))
    eski_fiyat = Decimal(str(stok_item.alis_fiyati or 0))
    if yeni_fiyat < 0:
        raise ValueError("Negatif fiyat kaydedilemez.")
    if yeni_fiyat == eski_fiyat:
        return False

    FiyatGecmisi.objects.create(
        stok_item=stok_item,
        eski_alis_fiyati=eski_fiyat,
        yeni_alis_fiyati=yeni_fiyat,
        para_birimi=para_birimi or stok_item.alis_para_birimi or "TRY",
        degisen_alan="alis_fiyati",
        aciklama=aciklama,
        user=username or "Sistem",
    )
    stok_item.alis_fiyati = yeni_fiyat
    stok_item.save(update_fields=["alis_fiyati"])
    return True


def _satinalma_toplam_yeniden_hesapla(satinalma):
    toplam = Decimal("0")
    for kalem in SatinalmaKalemi.objects.filter(satinalma=satinalma):
        toplam += Decimal(str(kalem.toplam_fiyat or 0))
    satinalma.toplam = toplam
    satinalma.save(update_fields=["toplam"])


def _siparis_malzeme_maliyetlerini_guncelle(stok_item, yeni_fiyat, para_birimi):
    """
    İlgili stok için oluşmuş sipariş malzeme maliyetlerini teslim/teklif fiyatına günceller.
    """
    yeni_fiyat = Decimal(str(yeni_fiyat or 0))
    if yeni_fiyat < 0:
        return 0

    maliyetler = SiparisMaliyeti.objects.filter(
        maliyet_tipi="MALZEME",
        aciklama__startswith=f"{stok_item.stok_kodu} - ",
    ).exclude(siparis__siparis_durumu="RED")

    guncellenen = 0
    for maliyet in maliyetler:
        if maliyet.birim_fiyat != yeni_fiyat or maliyet.para_birimi != (para_birimi or maliyet.para_birimi):
            maliyet.birim_fiyat = yeni_fiyat
            if para_birimi:
                maliyet.para_birimi = para_birimi
            maliyet.save()
            guncellenen += 1
    return guncellenen


def _resolve_siparis_logo_abs_path(ayarlar=None, sablon=None):
    """
    Sipariş çıktılarında kullanılacak logonun disk path'ini bulur.
    Öncelik: Genel Ayarlar firma logosu > Yazdırma şablonu logosu > assets/TEKMAR_9001_LOGO*
    """
    candidates = []

    if ayarlar and getattr(ayarlar, "firma_logo", None):
        logo_field = ayarlar.firma_logo
        try:
            if hasattr(logo_field, "path") and logo_field.path:
                candidates.append(logo_field.path)
        except Exception:
            pass
        if getattr(logo_field, "name", None):
            candidates.append(os.path.join(settings.MEDIA_ROOT, logo_field.name))

    if sablon and getattr(sablon, "logo_goster", False) and getattr(sablon, "logo_yolu", None):
        logo_field = sablon.logo_yolu
        try:
            if hasattr(logo_field, "path") and logo_field.path:
                candidates.append(logo_field.path)
        except Exception:
            pass
        if getattr(logo_field, "name", None):
            candidates.append(os.path.join(settings.MEDIA_ROOT, logo_field.name))

    assets_dir = os.path.join(settings.BASE_DIR, "assets")
    if os.path.isdir(assets_dir):
        try:
            asset_names = sorted(
                os.listdir(assets_dir),
                key=lambda name: os.path.getmtime(os.path.join(assets_dir, name)),
                reverse=True,
            )
            for fname in asset_names:
                low = fname.lower()
                if not low.startswith("tekmar_9001_logo"):
                    continue
                if not low.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                candidates.append(os.path.join(assets_dir, fname))
        except Exception:
            pass

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _logo_data_uri_from_path(logo_abs_path):
    if not logo_abs_path or not os.path.exists(logo_abs_path):
        return None
    try:
        with open(logo_abs_path, "rb") as logo_file:
            encoded = base64.b64encode(logo_file.read()).decode("ascii")
        ext = os.path.splitext(logo_abs_path)[1].lower()
        mime = "image/png"
        if ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return None


def dxf_dosyasinda_miktar_guncelle(dxf_dosya_yolu, miktar):
    """DXF/DWG dosyasında 'miktar : ' ifadesinden sonra miktar değerini güncelle"""
    if not EZDXF_AVAILABLE:
        return None, "ezdxf kütüphanesi kurulu değil"
    
    try:
        # DXF dosyasını oku
        try:
            doc = ezdxf.readfile(dxf_dosya_yolu)
        except Exception as e:
            return None, f"DXF dosyası okunamadı: {str(e)}"
        
        # Model space'i al
        msp = doc.modelspace()
        
        # Miktar değeri formatı
        miktar_str = str(float(miktar))
        
        # TEXT ve MTEXT entity'lerini kontrol et
        bulundu = False
        for entity in msp:
            if entity.dxftype() == 'TEXT':
                text = entity.dxf.text
                # "miktar : " ifadesini bul (case insensitive)
                pattern = re.compile(r'(miktar\s*:\s*)([0-9.,]+)?', re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    # Miktarı güncelle
                    yeni_text = pattern.sub(f'\\1{miktar_str}', text)
                    entity.dxf.text = yeni_text
                    bulundu = True
            elif entity.dxftype() == 'MTEXT':
                text = entity.dxf.text
                pattern = re.compile(r'(miktar\s*:\s*)([0-9.,]+)?', re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    yeni_text = pattern.sub(f'\\1{miktar_str}', text)
                    entity.dxf.text = yeni_text
                    bulundu = True
        
        if not bulundu:
            # Eğer "miktar : " bulunamazsa, yeni bir TEXT entity ekle
            try:
                # Varsayılan pozisyon (0, 0, 0) - kullanıcı görünür bir yere ekleyebilir
                msp.add_text(f'miktar : {miktar_str}', dxfattribs={
                    'height': 2.5,
                    'insert': (0, 0, 0)
                })
                bulundu = True
            except Exception as e:
                return None, f"Yeni metin eklenemedi: {str(e)}"
        
        # Güncellenmiş dosyayı BytesIO'ya kaydet
        output = BytesIO()
        try:
            doc.saveas(output)
            output.seek(0)
        except Exception as save_error:
            # ezdxf'in bazı versiyonlarında saveas BytesIO'yu desteklemeyebilir
            # Bu durumda geçici bir dosya kullan
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
                tmp_path = tmp_file.name
                doc.saveas(tmp_path)
            
            with open(tmp_path, 'rb') as f:
                output.write(f.read())
            
            # Geçici dosyayı sil
            try:
                os.unlink(tmp_path)
            except:
                pass
            
            output.seek(0)
        
        return output, None
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"DXF güncelleme hatası: {str(e)}"


@login_required
def satinalma_listesi(request):
    """Satın alma listesi"""
    # Sekme filtresi
    tab = request.GET.get('tab', 'satin_alma')  # Varsayılan: Teslimat Bekleyen
    sort_field = request.GET.get('sort', 'olusturma')
    sort_dir = request.GET.get('dir', 'desc')
    teslim_durumu = request.GET.get('teslim_durumu', '')
    tedarikci_filtre_id = None
    tedarikci_filtre = None
    tedarikci_param = (request.GET.get('tedarikci') or '').strip()
    if tedarikci_param.isdigit():
        tedarikci_filtre = Tedarikci.objects.filter(pk=int(tedarikci_param)).first()
        if tedarikci_filtre:
            tedarikci_filtre_id = tedarikci_filtre.pk
    
    # Tüm kalemleri teslim alınmamış olan satınalmaları bul (en az bir kalem için teslim_alinan_miktar < miktar)
    teslim_bekleyen_kalem_subq = SatinalmaKalemi.objects.filter(
        satinalma=OuterRef('pk'),
        teslim_alinan_miktar__lt=F('miktar')
    )

    satin_alma_qs = Satinalma.objects.filter(Exists(teslim_bekleyen_kalem_subq))
    teslimat_tamamlanan_qs = Satinalma.objects.filter(
        ~Exists(teslim_bekleyen_kalem_subq)
    ).exclude(kalemler__isnull=True)
    fason_siparis_qs = Satinalma.objects.none()  # Şimdilik boş

    if tedarikci_filtre_id:
        satin_alma_qs = satin_alma_qs.filter(tedarikci_id=tedarikci_filtre_id)
        teslimat_tamamlanan_qs = teslimat_tamamlanan_qs.filter(tedarikci_id=tedarikci_filtre_id)
        fason_siparis_qs = fason_siparis_qs.filter(tedarikci_id=tedarikci_filtre_id)

    teslim_bekleyen_kalem_count = SatinalmaKalemi.objects.filter(
        teslim_alinan_miktar__lt=F('miktar')
    ).count()
    if tedarikci_filtre_id:
        teslim_bekleyen_kalem_count = SatinalmaKalemi.objects.filter(
            teslim_alinan_miktar__lt=F('miktar'),
            satinalma__tedarikci_id=tedarikci_filtre_id,
        ).count()

    bekleyen_kalemler_page = None
    satinalmalar_page = None
    rfq_listesi_page = None
    ara_toplam = Decimal('0')
    vergi = Decimal('0')
    toplam = Decimal('0')

    taslak_qs = TeklifTalebi.objects.filter(durum='TASLAK').order_by('-olusturma_tarihi')
    teklif_bekleyen_qs = TeklifTalebi.objects.filter(durum='TEKLIF_BEKLENIYOR').order_by('-olusturma_tarihi')
    degerlendirmede_qs = TeklifTalebi.objects.filter(durum='DEGERLENDIRMEDE').order_by('-olusturma_tarihi')

    if tab == 'taslaklar':
        paginator = Paginator(taslak_qs, 25)
        page = request.GET.get('page', 1)
        rfq_listesi_page = paginator.get_page(page)
    elif tab == 'teklif_bekleyen':
        paginator = Paginator(teklif_bekleyen_qs, 25)
        page = request.GET.get('page', 1)
        rfq_listesi_page = paginator.get_page(page)
    elif tab == 'degerlendirmede':
        paginator = Paginator(degerlendirmede_qs, 25)
        page = request.GET.get('page', 1)
        rfq_listesi_page = paginator.get_page(page)
    elif tab == 'teslim_bekleyen_kalemler':
        bekleyen_qs = (
            SatinalmaKalemi.objects.filter(teslim_alinan_miktar__lt=F('miktar'))
            .select_related('satinalma', 'satinalma__tedarikci', 'stok_item')
            .annotate(
                teslimat_bekleyen_miktar=ExpressionWrapper(
                    F('miktar') - F('teslim_alinan_miktar'),
                    output_field=DecimalField(max_digits=10, decimal_places=3),
                )
            )
            .order_by('satinalma__satinalma_numarasi', 'id')
        )
        if tedarikci_filtre_id:
            bekleyen_qs = bekleyen_qs.filter(satinalma__tedarikci_id=tedarikci_filtre_id)
        paginator = Paginator(bekleyen_qs, 25)
        page = request.GET.get('page', 1)
        bekleyen_kalemler_page = paginator.get_page(page)
    else:
        # Tab'a göre filtreleme
        if tab == 'teslimat_tamamlanan':
            satinalmalar = teslimat_tamamlanan_qs
        elif tab == 'fason_siparis':
            satinalmalar = fason_siparis_qs
        else:  # satin_alma (teslimat bekleyen)
            satinalmalar = satin_alma_qs

        if teslim_durumu:
            satinalmalar = satinalmalar.filter(teslim_durumu=teslim_durumu)

        sortable_fields = {
            'no': 'satinalma_numarasi',
            'tedarikci': 'tedarikci_adi',
            'toplam': 'toplam',
            'olusturma': 'olusturulma_tarihi',
            'tamamlanma': 'tamamlanma_tarihi',
        }
        order_expr = sortable_fields.get(sort_field, 'olusturulma_tarihi')
        if sort_dir == 'desc':
            order_expr = f'-{order_expr}'
        satinalmalar = satinalmalar.order_by(order_expr)

        paginator = Paginator(satinalmalar, 10)
        page = request.GET.get('page', 1)
        satinalmalar_page = paginator.get_page(page)

        ara_toplam = satinalmalar.aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
        vergi = ara_toplam * Decimal('0.20')  # %20 KDV
        toplam = ara_toplam + vergi

    context = {
        'satinalmalar': satinalmalar_page,
        'bekleyen_kalemler': bekleyen_kalemler_page,
        'rfq_listesi': rfq_listesi_page,
        'tab': tab,
        'teslim_durumu': teslim_durumu,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'ara_toplam': ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
        'tedarikci_filtre': tedarikci_filtre,
        'tedarikci_filtre_id': tedarikci_filtre_id,
        'counts': {
            'taslaklar': taslak_qs.count(),
            'teklif_bekleyen': teklif_bekleyen_qs.count(),
            'degerlendirmede': degerlendirmede_qs.count(),
            'teslim_bekleyen_kalemler': teslim_bekleyen_kalem_count,
            'satin_alma': satin_alma_qs.count(),
            'teslimat_tamamlanan': teslimat_tamamlanan_qs.count(),
            'fason_siparis': fason_siparis_qs.count(),
        },
    }
    return render(request, 'stokapp/satinalma_listesi.html', context)

@login_required
def satinalma_ekle(request):
    """Yeni satın alma oluştur"""
    source_siparis_id = request.POST.get('source_siparis') or request.GET.get('source_siparis')
    kaynak_siparis = None
    if source_siparis_id:
        try:
            kaynak_siparis = Siparis.objects.filter(pk=int(source_siparis_id)).first()
        except (TypeError, ValueError):
            kaynak_siparis = None

    if request.method == 'POST':
        form = SatinalmaForm(request.POST)
        kalemler_raw = request.POST.get('kalemler', '[]')
        print(f"DEBUG: kalemler_raw = {kalemler_raw}")
        try:
            kalemler_data = json.loads(kalemler_raw)
            print(f"DEBUG: kalemler_data = {kalemler_data}")
            print(f"DEBUG: kalemler_data type = {type(kalemler_data)}")
            print(f"DEBUG: kalemler_data length = {len(kalemler_data) if isinstance(kalemler_data, list) else 'N/A'}")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")
            kalemler_data = []
        
        print(f"DEBUG: form.is_valid() = {form.is_valid()}")
        print(f"DEBUG: kalemler_data (bool) = {bool(kalemler_data)}")
        
        if form.is_valid() and kalemler_data:
            try:
                with transaction.atomic():
                    satinalma = form.save(commit=False)
                    satinalma.kaynak_siparis = kaynak_siparis
                    # Tedarikçi adını kaydet (form'dan gelen tedarikci_adi_manuel veya tedarikci'den)
                    if not satinalma.tedarikci and form.cleaned_data.get('tedarikci_adi_manuel'):
                        satinalma.tedarikci_adi = form.cleaned_data['tedarikci_adi_manuel']
                    elif satinalma.tedarikci:
                        satinalma.tedarikci_adi = satinalma.tedarikci.ad
                    
                    # Toplam hesapla
                    toplam = Decimal('0')
                    for kalem in kalemler_data:
                        miktar = Decimal(str(kalem['miktar']))
                        birim_fiyat = Decimal(str(kalem['birim_fiyat']))
                        vergi = Decimal(str(kalem.get('vergi_yuzdesi', 20)))
                        kalem_toplam = (miktar * birim_fiyat) * (1 + vergi / 100)
                        toplam += kalem_toplam
                    
                    satinalma.toplam = toplam
                    satinalma.save()
                    
                    # Kalemleri kaydet ve fiyat güncellemesi yap
                    for kalem in kalemler_data:
                        stok_item = StokItem.objects.get(pk=kalem['stok_item'])
                        yeni_fiyat = Decimal(str(kalem['birim_fiyat']))
                        eski_fiyat = stok_item.alis_fiyati or Decimal('0')
                        
                        # Fiyat değişmişse güncelle ve geçmişe kaydet
                        if yeni_fiyat != eski_fiyat:
                            FiyatGecmisi.objects.create(
                                stok_item=stok_item,
                                eski_alis_fiyati=eski_fiyat,
                                yeni_alis_fiyati=yeni_fiyat,
                                para_birimi=stok_item.alis_para_birimi or 'TL',
                                degisen_alan='alis_fiyati',
                                aciklama=f'Satınalma: {satinalma.satinalma_numarasi}',
                                user=request.user.username if request.user.is_authenticated else 'Sistem'
                            )
                            # Stok fiyatını güncelle
                            stok_item.alis_fiyati = yeni_fiyat
                            stok_item.save()
                        
                        SatinalmaKalemi.objects.create(
                            satinalma=satinalma,
                            stok_item=stok_item,
                            miktar=Decimal(str(kalem['miktar'])),
                            birim_fiyat=yeni_fiyat,
                            vergi_yuzdesi=Decimal(str(kalem.get('vergi_yuzdesi', 20))),
                            notlar=kalem.get('notlar', '')
                        )
                    
                    # Planlamadan gelindiyse session'ı açık satın almalarla eşitle
                    planlama_aktif = request.GET.get('planlama') == '1' or request.session.get('planlama_aktif', False)
                    if planlama_aktif:
                        _session_kullanilan_malzemeler_temizle(request)
                        request.session['planlama_aktif'] = False
                        request.session.modified = True
                    
                    messages.success(request, f'Satın alma "{satinalma.satinalma_numarasi}" başarıyla oluşturuldu.')
                    return redirect('stokapp:satinalma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
        else:
            if not form.is_valid():
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
            if not kalemler_data:
                messages.error(request, 'Lütfen en az bir ürün ekleyin ve miktar ile birim fiyat bilgilerini girin.')
            elif not form.is_valid():
                messages.error(request, 'Form hatalarını düzeltin.')
            else:
                messages.error(request, 'Lütfen en az bir ürün ekleyin.')
    else:
        form = SatinalmaForm()
        # Varsayılan değerler
        form.fields['olusturulma_tarihi'].initial = timezone.now().date()
        form.fields['teslim_durumu'].initial = 'BEKLIYOR'
        
        # Varsayılan para birimi - ParaBirimi modelinden ilk aktif olanı al
        from .models import ParaBirimi
        varsayilan_pb = ParaBirimi.objects.filter(aktif=True).first()
        if varsayilan_pb:
            form.fields['para_birimi'].initial = varsayilan_pb.kod
        else:
            form.fields['para_birimi'].initial = 'TRY'
        
        # Otomatik satın alma numarası - Format: TSAT_GGAAYY_NN
        from datetime import date
        today = date.today()
        tarih_format = f"{today.day:02d}{today.month:02d}{str(today.year)[-2:]}"
        
        # Bugün oluşturulan satın almaları say (aynı tarih formatına sahip olanları)
        bugun_baslayan_numaralar = Satinalma.objects.filter(
            satinalma_numarasi__startswith=f'TSAT_{tarih_format}_'
        ).count()
        
        # Sıradaki numara (01, 02, 03, ...)
        sira_no = bugun_baslayan_numaralar + 1
        otomatik_numara = f'TSAT_{tarih_format}_{sira_no:02d}'
        form.fields['satinalma_numarasi'].initial = otomatik_numara
    
    stok_items = StokItem.objects.filter(arsivli=False).order_by('ad')
    tedarikciler = Tedarikci.objects.all().order_by('ad')
    depolar = Depo.objects.all().order_by('ad')
    
    # Planlamadan gelen malzemeleri hazırla
    planlama_malzemeler = []
    if request.GET.get('planlama') == '1':
        # Planlama bilgisini session'a kaydet (POST isteğinde kullanmak için)
        request.session['planlama_aktif'] = True
        request.session.modified = True
        
        # GET parametrelerinden malzemeleri al
        index = 0
        while f'malzeme_{index}' in request.GET:
            stok_item_id = request.GET.get(f'malzeme_{index}')
            miktar = request.GET.get(f'miktar_{index}', '0')
            try:
                stok_item = StokItem.objects.get(pk=stok_item_id)
                planlama_malzemeler.append({
                    'stok_item': stok_item,
                    'miktar': Decimal(str(miktar)),
                    'birim_fiyat': stok_item.alis_fiyati or Decimal('0'),
                    'para_birimi': stok_item.alis_para_birimi or 'TL',
                    'vergi_yuzdesi': Decimal('20'),
                })
            except StokItem.DoesNotExist:
                pass
            index += 1
    
    context = {
        'form': form,
        'stok_items': stok_items,
        'tedarikciler': tedarikciler,
        'depolar': depolar,
        'planlama_malzemeler': planlama_malzemeler,
        'source_siparis_id': kaynak_siparis.pk if kaynak_siparis else '',
    }
    return render(request, 'stokapp/satinalma_ekle.html', context)

@login_required
def satinalma_detay(request, pk):
    """Satın alma detay sayfası"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
    
    # Özet hesaplamaları
    ara_toplam = satinalma.toplam
    vergi = ara_toplam * Decimal('0.20')  # %20 KDV
    toplam = ara_toplam + vergi
    
    context = {
        'satinalma': satinalma,
        'kalemler': kalemler,
        'ara_toplam': ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
    }
    return render(request, 'stokapp/satinalma_detay.html', context)

@login_required
def satinalma_duzenle(request, pk):
    """Satın alma düzenle"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method == 'POST':
        form = SatinalmaForm(request.POST, instance=satinalma)
        kalemler_data = json.loads(request.POST.get('kalemler', '[]'))
        
        if form.is_valid() and kalemler_data:
            try:
                with transaction.atomic():
                    satinalma = form.save(commit=False)
                    # Tedarikçi adını kaydet (form'dan gelen tedarikci_adi_manuel veya tedarikci'den)
                    if not satinalma.tedarikci and form.cleaned_data.get('tedarikci_adi_manuel'):
                        satinalma.tedarikci_adi = form.cleaned_data['tedarikci_adi_manuel']
                    elif satinalma.tedarikci:
                        satinalma.tedarikci_adi = satinalma.tedarikci.ad
                    
                    # Eski kalemleri sil
                    SatinalmaKalemi.objects.filter(satinalma=satinalma).delete()
                    
                    # Toplam hesapla
                    toplam = Decimal('0')
                    for kalem in kalemler_data:
                        miktar = Decimal(str(kalem['miktar']))
                        birim_fiyat = Decimal(str(kalem['birim_fiyat']))
                        vergi = Decimal(str(kalem.get('vergi_yuzdesi', 20)))
                        kalem_toplam = (miktar * birim_fiyat) * (1 + vergi / 100)
                        toplam += kalem_toplam
                    
                    satinalma.toplam = toplam
                    satinalma.save()
                    
                    # Yeni kalemleri kaydet ve fiyat güncellemesi yap
                    for kalem in kalemler_data:
                        stok_item = StokItem.objects.get(pk=kalem['stok_item'])
                        yeni_fiyat = Decimal(str(kalem['birim_fiyat']))
                        eski_fiyat = stok_item.alis_fiyati or Decimal('0')
                        
                        # Fiyat değişmişse güncelle ve geçmişe kaydet
                        if yeni_fiyat != eski_fiyat:
                            FiyatGecmisi.objects.create(
                                stok_item=stok_item,
                                eski_alis_fiyati=eski_fiyat,
                                yeni_alis_fiyati=yeni_fiyat,
                                para_birimi=stok_item.alis_para_birimi or 'TL',
                                degisen_alan='alis_fiyati',
                                aciklama=f'Satınalma Düzenleme: {satinalma.satinalma_numarasi}',
                                user=request.user.username if request.user.is_authenticated else 'Sistem'
                            )
                            # Stok fiyatını güncelle
                            stok_item.alis_fiyati = yeni_fiyat
                            stok_item.save()
                        
                        SatinalmaKalemi.objects.create(
                            satinalma=satinalma,
                            stok_item=stok_item,
                            miktar=Decimal(str(kalem['miktar'])),
                            birim_fiyat=yeni_fiyat,
                            vergi_yuzdesi=Decimal(str(kalem.get('vergi_yuzdesi', 20))),
                            notlar=kalem.get('notlar', '')
                        )

                    _session_kullanilan_malzemeler_temizle(request)

                    messages.success(request, f'Satın alma "{satinalma.satinalma_numarasi}" başarıyla güncellendi.')
                    return redirect('stokapp:satinalma_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
        else:
            messages.error(request, 'Lütfen en az bir ürün ekleyin.')
    else:
        form = SatinalmaForm(instance=satinalma)
    
    stok_items = StokItem.objects.filter(arsivli=False).order_by('ad')
    tedarikciler = Tedarikci.objects.all().order_by('ad')
    depolar = Depo.objects.all().order_by('ad')
    mevcut_kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
    
    context = {
        'form': form,
        'satinalma': satinalma,
        'stok_items': stok_items,
        'tedarikciler': tedarikciler,
        'depolar': depolar,
        'mevcut_kalemler': mevcut_kalemler,
    }
    return render(request, 'stokapp/satinalma_duzenle.html', context)

@login_required
def satinalma_sil(request, pk):
    """Satın alma sil - Eğer teslim edilmişse stok miktarlarını geri al"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                satinalma_numarasi = satinalma.satinalma_numarasi
                
                # Eğer satınalma teslim edilmişse, stok hareketlerini bul ve ters işlemi yap
                if satinalma.teslim_durumu in ['TESLIM_ALINDI', 'KISMI_TESLIM']:
                    # Bu satınalma için oluşturulan tüm stok hareketlerini bul
                    referans_no_pattern = f'SAT-{satinalma_numarasi}'
                    stok_hareketleri = StokHareketi.objects.filter(
                        referans_no=referans_no_pattern,
                        hareket_tipi='GIRIS'
                    )
                    
                    # Her stok hareketi için ters işlemi yap (stok miktarını düş)
                    for hareket in stok_hareketleri:
                        stok_item = hareket.stok_item
                        # Giriş hareketi yapıldıysa, çıkış yaparak geri al
                        if hareket.hareket_tipi == 'GIRIS':
                            # Stok miktarını düş
                            stok_item.mevcut_miktar = max(
                                Decimal('0'), 
                                (stok_item.mevcut_miktar or Decimal('0')) - hareket.miktar
                            )
                            stok_item.save()
                    
                    # Stok hareketlerini sil
                    stok_hareketleri.delete()
                
                # Satınalmayı sil
                satinalma.delete()
                _session_kullanilan_malzemeler_temizle(request)
                messages.success(request, f'Satın alma "{satinalma_numarasi}" başarıyla silindi.')
                return redirect('stokapp:satinalma_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'satinalma': satinalma,
    }
    return render(request, 'stokapp/satinalma_sil.html', context)

@login_required
def satinalma_tamamini_teslim(request, pk):
    """Tüm kalemleri teslim alındı olarak işaretle ve stok güncelle"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method == 'POST' or request.GET.get('confirm') == 'yes':
        try:
            with transaction.atomic():
                # Tüm kalemleri teslim alındı olarak işaretle ve stok güncelle
                kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma)
                
                for kalem in kalemler:
                    # Stok güncelle
                    stok_item = kalem.stok_item
                    if satinalma.lokasyon:
                        # Stok hareketi oluştur
                        StokHareketi.objects.create(
                            stok_item=stok_item,
                            miktar=kalem.miktar,
                            birim=stok_item.birim or 'Adet',
                            hareket_tipi='GIRIS',
                            referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                            depo=satinalma.lokasyon,
                            raf=None  # Raf bilgisi yoksa None
                        )
                        
                        # Stok miktarını güncelle
                        stok_item.miktar = (stok_item.miktar or Decimal('0')) + kalem.miktar
                        stok_item.save()
                
                # Satınalma durumunu güncelle
                satinalma.teslim_durumu = 'TESLIM_ALINDI'
                satinalma.save()
                
                messages.success(request, f'Satın alma "{satinalma.satinalma_numarasi}" tamamen teslim alındı ve stoklar güncellendi.')
                return redirect('stokapp:satinalma_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:satinalma_listesi')
    
    # GET isteği için onay sayfası göster (isteğe bağlı)
    return redirect('stokapp:satinalma_listesi')

@login_required
def satinalma_ksimi_teslim_modal(request, pk):
    """Kısmi teslim modal için kalemleri JSON olarak döndür"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma)
    
    kalemler_data = []
    for kalem in kalemler:
        # Daha önce teslim edilen miktarı hesapla (StokHareketi'nden)
        teslim_edilen = StokHareketi.objects.filter(
            stok_item=kalem.stok_item,
            referans_no=f'SAT-{satinalma.satinalma_numarasi}',
            hareket_tipi='GIRIS'
        ).aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        
        kalan = kalem.miktar - teslim_edilen
        
        kalemler_data.append({
            'id': kalem.id,
            'kod': kalem.stok_item.ad,
            'miktar': str(kalem.miktar),
            'teslim_edilen': str(teslim_edilen),
            'kalan': str(kalan),
            'birim': kalem.stok_item.birim or 'ADET'
        })
    
    return JsonResponse({'kalemler': kalemler_data})

@login_required
def satinalma_ksimi_teslim(request, pk):
    """Kısmi teslim işlemini gerçekleştir"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma)
                toplam_teslim = Decimal('0')
                
                for kalem in kalemler:
                    teslim_miktar_key = f'teslim_miktar_{kalem.id}'
                    teslim_miktar = Decimal(str(request.POST.get(teslim_miktar_key, 0)))
                    
                    if teslim_miktar > 0:
                        # Daha önce teslim edilen miktarı hesapla
                        teslim_edilen = StokHareketi.objects.filter(
                            stok_item=kalem.stok_item,
                            referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                            hareket_tipi='GIRIS'
                        ).aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
                        
                        kalan = kalem.miktar - teslim_edilen
                        
                        # Teslim miktarı kalan miktardan fazla olamaz
                        if teslim_miktar > kalan:
                            teslim_miktar = kalan
                        
                        if teslim_miktar > 0:
                            # Stok hareketi oluştur
                            if satinalma.lokasyon:
                                StokHareketi.objects.create(
                                    stok_item=kalem.stok_item,
                                    miktar=teslim_miktar,
                                    birim=kalem.stok_item.birim or 'Adet',
                                    hareket_tipi='GIRIS',
                                    referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                                    depo=satinalma.lokasyon,
                                    raf=None
                                )
                                
                                # Stok miktarını güncelle
                                kalem.stok_item.miktar = (kalem.stok_item.miktar or Decimal('0')) + teslim_miktar
                                kalem.stok_item.save()
                                
                                toplam_teslim += teslim_miktar
                
                # Satınalma durumunu güncelle
                if toplam_teslim > 0:
                    # Tüm kalemler teslim edildi mi kontrol et
                    tum_teslim_edildi = True
                    for kalem in kalemler:
                        teslim_edilen = StokHareketi.objects.filter(
                            stok_item=kalem.stok_item,
                            referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                            hareket_tipi='GIRIS'
                        ).aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
                        if teslim_edilen < kalem.miktar:
                            tum_teslim_edildi = False
                            break
                    
                    if tum_teslim_edildi:
                        satinalma.teslim_durumu = 'TESLIM_ALINDI'
                    else:
                        satinalma.teslim_durumu = 'KISMI_TESLIM'
                    satinalma.save()
                    
                    messages.success(request, f'{toplam_teslim} birim malzeme teslim alındı ve stoklar güncellendi.')
                else:
                    messages.warning(request, 'Teslim edilecek malzeme bulunamadı.')
                
                return redirect('stokapp:satinalma_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
            return redirect('stokapp:satinalma_listesi')
    
    return redirect('stokapp:satinalma_listesi')

@login_required
def teklif_formu_teknik_resim_isle(request):
    """Teklif formu oluşturulmadan önce teknik resimleri işle"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Sadece POST isteği kabul edilir.'}, status=405)
    
    # Seçilen satın alma ID'leri
    ids_param = request.POST.get('ids', '') or request.GET.get('ids', '')
    if not ids_param:
        return JsonResponse({'success': False, 'error': 'Lütfen en az bir satın alma seçin.'}, status=400)
    
    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids)
        
        if not satinalmalar.exists():
            return JsonResponse({'success': False, 'error': 'Seçilen satın almalar bulunamadı.'}, status=404)
        
        islenen_dosyalar = []
        hatalar = []
        
        with transaction.atomic():
            for satinalma in satinalmalar:
                kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).select_related('stok_item')
                for kalem in kalemler:
                    # Stok item'da teknik resim var mı kontrol et
                    if kalem.stok_item.teknik_resim:
                        teknik_resim_dosyasi = kalem.stok_item.teknik_resim
                        
                        # Dosya yolunu al
                        if hasattr(teknik_resim_dosyasi, 'path') and os.path.exists(teknik_resim_dosyasi.path):
                            teknik_resim_yolu = teknik_resim_dosyasi.path
                        else:
                            teknik_resim_yolu = os.path.join(settings.MEDIA_ROOT, teknik_resim_dosyasi.name)
                            if not os.path.exists(teknik_resim_yolu):
                                hatalar.append(f"{kalem.stok_item.ad}: Teknik resim dosyası bulunamadı")
                                continue
                        
                        # Dosya uzantısını kontrol et
                        dosya_adi = os.path.basename(teknik_resim_yolu)
                        dosya_uzantisi = os.path.splitext(dosya_adi)[1].lower()
                        
                        if dosya_uzantisi in ['.dxf', '.dwg']:
                            # DXF/DWG dosyasını güncelle
                            guncellenmis_dosya, hata = dxf_dosyasinda_miktar_guncelle(teknik_resim_yolu, kalem.miktar)
                            
                            if guncellenmis_dosya and not hata:
                                # Güncellenmiş dosyayı SatinalmaKalemi'ne kaydet
                                orijinal_dosya_adi = os.path.splitext(dosya_adi)[0]
                                yeni_dosya_adi = f"{orijinal_dosya_adi}_miktar_{kalem.miktar}{dosya_uzantisi}"
                                
                                # Eğer daha önce kaydedilmişse sil
                                if kalem.teknik_resim_guncellenmis:
                                    try:
                                        kalem.teknik_resim_guncellenmis.delete(save=False)
                                    except:
                                        pass
                                
                                kalem.teknik_resim_guncellenmis.save(
                                    yeni_dosya_adi,
                                    ContentFile(guncellenmis_dosya.getvalue()),
                                    save=True
                                )
                                
                                islenen_dosyalar.append({
                                    'kalem_id': kalem.id,
                                    'stok_adi': kalem.stok_item.ad,
                                    'dosya_adi': yeni_dosya_adi,
                                    'miktar': str(kalem.miktar)
                                })
                            elif hata:
                                hatalar.append(f"{kalem.stok_item.ad}: {hata}")
        
        return JsonResponse({
            'success': True,
            'islenen_dosyalar': islenen_dosyalar,
            'islenen_sayisi': len(islenen_dosyalar),
            'hatalar': hatalar,
            'hata_sayisi': len(hatalar),
            'message': f'{len(islenen_dosyalar)} teknik resim başarıyla işlendi.' if islenen_dosyalar else 'İşlenecek teknik resim bulunamadı.'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Beklenmeyen hata: {str(e)}'
        }, status=500)


@login_required
def teklif_talep_formu(request):
    """Teklif talep formu oluştur - seçilen satın almalar için"""
    # Seçilen satın alma ID'leri
    ids_param = request.GET.get('ids', '')
    if not ids_param:
        messages.error(request, 'Lütfen en az bir satın alma seçin.')
        return redirect('stokapp:satinalma_listesi')
    
    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids)
        
        if not satinalmalar.exists():
            messages.error(request, 'Seçilen satın almalar bulunamadı.')
            return redirect('stokapp:satinalma_listesi')
        
        # Teklif numarası oluştur - Satın alma numarasındaki TSAT'i TTTF ile değiştir
        from datetime import datetime
        ilk_satinalma = satinalmalar.first()
        if ilk_satinalma and ilk_satinalma.satinalma_numarasi:
            # TSAT_GGAAYY_NN formatındaki TSAT'i TTTF ile değiştir
            teklif_no = ilk_satinalma.satinalma_numarasi.replace('TSAT_', 'TTTF_', 1)
        else:
            # Fallback: Eski format kullanılıyorsa
            teklif_no = f"TTTF-{satinalma_ids[0]}"
        
        # Firma bilgilerini al
        from .models import GenelAyarlar, YazdirmaSablonu
        ayarlar = GenelAyarlar.get_ayarlar()
        
        # YazdirmaSablonu'ndan firma bilgilerini al (varsa)
        sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()
        
        # Tüm kalemleri topla
        tum_kalemler = []
        toplam_birim = Decimal('0')
        toplam_ara_toplam = Decimal('0')
        
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                tum_kalemler.append({
                    'satinalma': satinalma,
                    'kalem': kalem,
                    'urun_adi': kalem.stok_item.ad,
                    'aciklama': kalem.stok_item.aciklama or '',
                    'adet': kalem.miktar,
                    'birim_fiyat': kalem.birim_fiyat,
                    'ara_toplam': kalem.miktar * kalem.birim_fiyat,
                })
                toplam_birim += kalem.miktar
                toplam_ara_toplam += kalem.miktar * kalem.birim_fiyat
        
        # Vergi hesapla (%20 KDV)
        vergi = toplam_ara_toplam * Decimal('0.20')
        toplam = toplam_ara_toplam + vergi
        
        # Tedarikçi bilgisi (ilk satın almanın tedarikçisini al)
        ilk_satinalma = satinalmalar.first()
        tedarikci = None
        if ilk_satinalma.tedarikci:
            tedarikci = ilk_satinalma.tedarikci
        elif ilk_satinalma.tedarikci_adi:
            tedarikci = {'ad': ilk_satinalma.tedarikci_adi}
        
        # Termin tarihi (tamamlanma tarihlerinin en geç olanı)
        termin_tarihi = None
        for satinalma in satinalmalar:
            if satinalma.tamamlanma_tarihi:
                if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                    termin_tarihi = satinalma.tamamlanma_tarihi
        
        context = {
            'teklif_no': teklif_no,
            'satinalmalar': satinalmalar,
            'tedarikci': tedarikci,
            'termin_tarihi': termin_tarihi or datetime.now().date(),
            'kalemler': tum_kalemler,
            'toplam_birim': toplam_birim,
            'toplam_ara_toplam': toplam_ara_toplam,
            'vergi': vergi,
            'toplam': toplam,
            'ayarlar': ayarlar,
            'sablon': sablon,
        }
        
        return render(request, 'stokapp/teklif_talep_formu.html', context)
        
    except Exception as e:
        messages.error(request, f'Hata: {str(e)}')
        return redirect('stokapp:satinalma_listesi')

@login_required
def teklif_talep_formu_pdf(request):
    """Teklif talep formu PDF olarak indir"""
    # Lazy check for WeasyPrint
    global WEASYPRINT_AVAILABLE
    if WEASYPRINT_AVAILABLE is None:
        try:
            from weasyprint import HTML, CSS
            WEASYPRINT_AVAILABLE = True
        except (ImportError, OSError) as e:
            WEASYPRINT_AVAILABLE = False
            ids_param = request.GET.get('ids', '')
            error_msg = 'PDF oluşturma için WeasyPrint kütüphanesi ve sistem bağımlılıkları gerekli. '
            error_msg += 'macOS için: brew install gtk+3 cairo gobject-introspection'
            messages.error(request, error_msg)
            if ids_param:
                return redirect(f"{reverse('stokapp:teklif_talep_formu')}?ids={ids_param}")
            return redirect('stokapp:satinalma_listesi')
    
    if not WEASYPRINT_AVAILABLE:
        ids_param = request.GET.get('ids', '')
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        if ids_param:
            return redirect(f"{reverse('stokapp:teklif_talep_formu')}?ids={ids_param}")
        return redirect('stokapp:satinalma_listesi')
    
    # Seçilen satın alma ID'leri
    ids_param = request.GET.get('ids', '')
    if not ids_param:
        messages.error(request, 'Lütfen en az bir satın alma seçin.')
        return redirect('stokapp:satinalma_listesi')
    
    try:
        import traceback
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids)
        
        if not satinalmalar.exists():
            messages.error(request, 'Seçilen satın almalar bulunamadı.')
            return redirect('stokapp:satinalma_listesi')
        
        # Teklif numarası oluştur - Satın alma numarasındaki TSAT'i TTTF ile değiştir
        from datetime import datetime
        ilk_satinalma = satinalmalar.first()
        if ilk_satinalma and ilk_satinalma.satinalma_numarasi:
            # TSAT_GGAAYY_NN formatındaki TSAT'i TTTF ile değiştir
            teklif_no = ilk_satinalma.satinalma_numarasi.replace('TSAT_', 'TTTF_', 1)
        else:
            # Fallback: Eski format kullanılıyorsa
            teklif_no = f"TTTF-{satinalma_ids[0]}"
        
        # Firma bilgilerini al
        from .models import GenelAyarlar, YazdirmaSablonu
        ayarlar = GenelAyarlar.get_ayarlar()
        
        # YazdirmaSablonu'ndan firma bilgilerini al (varsa)
        sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()
        
        # Eğer sablon PDF Generator API kullanıyorsa, API ile PDF oluştur
        # NOT: Fallback durumunda tekrar API çağrılmasını önlemek için request parametresinde kontrol yapıyoruz
        use_api = sablon and sablon.api_kullan and sablon.api_key and sablon.template_id
        # Eğer URL'de "no_api=1" parametresi varsa, API'yi atla (fallback durumu için)
        skip_api = request.GET.get('no_api') == '1'
        
        if use_api and not skip_api:
            try:
                return teklif_talep_formu_pdf_api(request, sablon, satinalmalar, satinalma_ids)
            except Exception as api_error:
                import traceback
                print(f"PDF Generator API Error: {traceback.format_exc()}")
                # API hatası durumunda normal PDF oluşturma metoduna devam et (API'yi atlamak için no_api parametresi ekle)
                messages.warning(request, f'PDF Generator API hatası, normal PDF oluşturma yöntemi kullanılıyor: {str(api_error)}')
                # Fallback: Normal PDF oluşturma metoduna yönlendir (API'yi atlamak için no_api=1 ekle)
                return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")
        
        # Tüm kalemleri topla
        tum_kalemler = []
        toplam_birim = Decimal('0')
        toplam_ara_toplam = Decimal('0')
        
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                tum_kalemler.append({
                    'satinalma': satinalma,
                    'kalem': kalem,
                    'urun_adi': kalem.stok_item.ad,
                    'aciklama': kalem.stok_item.aciklama or '',
                    'adet': kalem.miktar,
                    'birim_fiyat': kalem.birim_fiyat,
                    'ara_toplam': kalem.miktar * kalem.birim_fiyat,
                })
                toplam_birim += kalem.miktar
                toplam_ara_toplam += kalem.miktar * kalem.birim_fiyat
        
        # Vergi hesapla (%20 KDV)
        vergi = toplam_ara_toplam * Decimal('0.20')
        toplam = toplam_ara_toplam + vergi
        
        # Tedarikçi bilgisi (ilk satın almanın tedarikçisini al)
        ilk_satinalma = satinalmalar.first()
        tedarikci = None
        if ilk_satinalma.tedarikci:
            tedarikci = ilk_satinalma.tedarikci
        elif ilk_satinalma.tedarikci_adi:
            tedarikci = {'ad': ilk_satinalma.tedarikci_adi}
        
        # Termin tarihi (tamamlanma tarihlerinin en geç olanı)
        termin_tarihi = None
        for satinalma in satinalmalar:
            if satinalma.tamamlanma_tarihi:
                if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                    termin_tarihi = satinalma.tamamlanma_tarihi
        
        context = {
            'teklif_no': teklif_no,
            'satinalmalar': satinalmalar,
            'tedarikci': tedarikci,
            'termin_tarihi': termin_tarihi or datetime.now().date(),
            'kalemler': tum_kalemler,
            'toplam_birim': toplam_birim,
            'toplam_ara_toplam': toplam_ara_toplam,
            'vergi': vergi,
            'toplam': toplam,
            'ayarlar': ayarlar,
            'sablon': sablon,
            'for_pdf': True,  # PDF için flag
        }
        
        # Template'i yükle
        template = get_template('stokapp/teklif_talep_formu_pdf.html')
        
        # Logo için absolute path oluştur (WeasyPrint için)
        if sablon and sablon.logo_goster and sablon.logo_yolu:
            from django.conf import settings
            import os
            logo_abs_path = os.path.join(settings.MEDIA_ROOT, sablon.logo_yolu.name)
            if os.path.exists(logo_abs_path):
                # WeasyPrint için absolute path kullan
                context['logo_path'] = logo_abs_path
            else:
                context['logo_path'] = None
        else:
            context['logo_path'] = None
        
        html = template.render(context)
        
        # PDF oluştur - WeasyPrint kullanarak (Türkçe karakter desteği dahil)
        try:
            # WeasyPrint'i lazy import et
            from weasyprint import HTML, CSS
            
            # WeasyPrint ile PDF oluştur
            # HTML objesi oluştur - base_url logo ve diğer asset'ler için gerekli
            base_url = request.build_absolute_uri('/')
            html_obj = HTML(string=html, base_url=base_url)
            
            # CSS stilleri
            css = CSS(string="""
                @page {
                    size: A4;
                    margin: 10mm;
                }
                body {
                    font-family: Arial, sans-serif;
                    font-size: 12px;
                    color: #000;
                    margin: 0;
                    padding: 15px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }
                th, td {
                    border: 1px solid #000;
                    padding: 10px;
                }
                img {
                    max-width: 250px;
                    max-height: 120px;
                }
            """)
            
            # PDF oluştur
            pdf_bytes = html_obj.write_pdf(stylesheets=[css])
            
            # PDF response oluştur
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="teklif_talep_formu_{teklif_no}.pdf"'
            return response
            
        except Exception as pdf_error:
            messages.error(request, f'PDF oluşturma hatası: {str(pdf_error)}')
            import traceback
            print(f"PDF Error: {traceback.format_exc()}")
            return redirect('stokapp:satinalma_listesi')
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"General Error in teklif_talep_formu_pdf: {str(e)}")
        print(f"Traceback: {error_trace}")
        messages.error(request, f'Hata: {str(e)}')
        return redirect('stokapp:satinalma_listesi')

@login_required
def teklif_talep_formu_pdf_api(request, sablon, satinalmalar, satinalma_ids):
    """PDF Generator API kullanarak teklif talep formu PDF'i oluştur"""
    try:
        from datetime import datetime
        from .models import GenelAyarlar
        
        # Teklif numarası oluştur - Satın alma numarasındaki TSAT'i TTTF ile değiştir
        ilk_satinalma = satinalmalar.first()
        if ilk_satinalma and ilk_satinalma.satinalma_numarasi:
            # TSAT_GGAAYY_NN formatındaki TSAT'i TTTF ile değiştir
            teklif_no = ilk_satinalma.satinalma_numarasi.replace('TSAT_', 'TTTF_', 1)
        else:
            # Fallback: Eski format kullanılıyorsa
            teklif_no = f"TTTF-{satinalma_ids[0]}"
        
        # Tüm kalemleri topla
        tum_kalemler = []
        toplam_birim = Decimal('0')
        toplam_ara_toplam = Decimal('0')
        
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                tum_kalemler.append({
                    'urun_adi': kalem.stok_item.ad,
                    'aciklama': kalem.stok_item.aciklama or '',
                    'adet': float(kalem.miktar),
                    'birim_fiyat': '',
                    'ara_toplam': '',
                })
                toplam_birim += kalem.miktar
                toplam_ara_toplam += kalem.miktar * kalem.birim_fiyat
        
        # Tedarikçi bilgisi
        ilk_satinalma = satinalmalar.first()
        tedarikci = None
        tedarikci_ad = None
        
        if ilk_satinalma.tedarikci:
            tedarikci = ilk_satinalma.tedarikci
            tedarikci_ad = tedarikci.ad if hasattr(tedarikci, 'ad') and tedarikci.ad else (tedarikci.unvan if hasattr(tedarikci, 'unvan') and tedarikci.unvan else str(tedarikci))
        elif ilk_satinalma.tedarikci_adi:
            tedarikci_ad = ilk_satinalma.tedarikci_adi
        
        # Termin tarihi
        termin_tarihi = None
        for satinalma in satinalmalar:
            if satinalma.tamamlanma_tarihi:
                if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                    termin_tarihi = satinalma.tamamlanma_tarihi
        
        # API için JSON verisi hazırla - PDF Generator API formatına uygun
        # Adres bilgilerini parse et (adres formatından şehir ve ilçe çıkar)
        firma_adres = sablon.firma_adres if sablon.firma_adres else 'Karadenizliler Mahallesi, Horon Sokak, NO:7, Başiskele / KOCAELİ'
        adres_bolumler = firma_adres.split(',')
        street = ', '.join(adres_bolumler[:-1]).strip() if len(adres_bolumler) > 1 else firma_adres
        sehir_il = adres_bolumler[-1].strip().split(' / ') if ' / ' in adres_bolumler[-1] else ['', adres_bolumler[-1].strip()]
        city = sehir_il[0] if len(sehir_il) > 1 else ''
        province = sehir_il[-1] if len(sehir_il) > 1 else (sehir_il[0] if sehir_il else '')
        
        # Vergi bilgilerini parse et
        vergi_no = sablon.firma_vergi_no if sablon.firma_vergi_no else 'Tepecik / 8360669996'
        vergi_bolumler = vergi_no.split(' / ') if ' / ' in vergi_no else ['', vergi_no]
        tax_office = vergi_bolumler[0] if len(vergi_bolumler) > 1 else ''
        tax_number = vergi_bolumler[-1] if len(vergi_bolumler) > 1 else vergi_no
        
        # Items listesini API formatına çevir
        api_items = []
        for item in tum_kalemler:
            stok_kodu = item['kalem'].stok_item.stok_kodu if item.get('kalem') and item['kalem'].stok_item else ''
            api_items.append({
                'productName': stok_kodu,
                'description': item['urun_adi'] if item['urun_adi'] else None,
                'quantity': float(item['adet']),
                'unitPrice': None,  # Boş bırakılacak
                'subtotal': None    # Boş bırakılacak
            })
        
        # PDF Generator API formatına uygun JSON verisi
        api_data = {
            'quotationNumber': teklif_no,
            'supplier': {
                'name': tedarikci_ad or ''
            },
            'dueDate': (termin_tarihi or datetime.now().date()).strftime('%Y-%m-%d'),
            'deliveryAddress': {
                'companyName': sablon.firma_adi if sablon.firma_adi else 'Tekmar Endüstriyel Makina Otomasyon San. ve Tic. Ltd. Şti.',
                'street': street,
                'city': city,
                'province': province,
                'phone': sablon.firma_telefon if sablon.firma_telefon else '+90 532 488 38 09'
            },
            'billingAddress': {
                'companyName': sablon.firma_adi if sablon.firma_adi else 'Tekmar Endüstriyel Makina Otomasyon San. ve Tic. Ltd. Şti.',
                'street': street,
                'city': city,
                'province': province,
                'taxOffice': tax_office,
                'taxNumber': tax_number
            },
            'items': api_items,
            'totalUnitPrice': str(toplam_birim) if toplam_birim else None,
            'subtotal': None,
            'tax': None,
            'total': None,
            'notes': ''
        }
        
        # Template data'yı birleştir (eğer varsa)
        if sablon.template_data:
            import copy
            merged_data = copy.deepcopy(sablon.template_data)
            # Nested yapıları doğru şekilde birleştir
            if 'supplier' in merged_data and 'supplier' in api_data:
                merged_data['supplier'].update(api_data['supplier'])
                api_data['supplier'] = merged_data['supplier']
            if 'deliveryAddress' in merged_data and 'deliveryAddress' in api_data:
                merged_data['deliveryAddress'].update(api_data['deliveryAddress'])
                api_data['deliveryAddress'] = merged_data['deliveryAddress']
            if 'billingAddress' in merged_data and 'billingAddress' in api_data:
                merged_data['billingAddress'].update(api_data['billingAddress'])
                api_data['billingAddress'] = merged_data['billingAddress']
            # Diğer alanları güncelle
            for key, value in api_data.items():
                if key not in ['supplier', 'deliveryAddress', 'billingAddress']:
                    merged_data[key] = value
            api_data = merged_data
        
        # PDF Generator API'ye istek gönder
        # PDF Generator API endpoint formatı: POST /api/v4/documents/{template_id}
        api_url = f"https://us1.pdfgeneratorapi.com/api/v4/documents/{sablon.template_id}"
        
        headers = {
            'Authorization': f'Bearer {sablon.api_key}',
            'Content-Type': 'application/json',
            'X-Auth-Key': sablon.api_key,
        }
        
        # requests modülü kontrolü
        if not REQUESTS_AVAILABLE or requests is None:
            messages.error(request, 'requests modülü yüklü değil. Lütfen "pip install requests" komutunu çalıştırın.')
            # Fallback: Normal PDF oluşturma metoduna yönlendir
            ids_param = request.GET.get('ids', '')
            return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")
        
        # API request body - direkt data objesini gönder
        response = requests.post(
            api_url,
            json=api_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            # PDF response olarak döner
            pdf_data = response.content
            response_obj = HttpResponse(pdf_data, content_type='application/pdf')
            response_obj['Content-Disposition'] = f'attachment; filename="teklif_talep_formu_{teklif_no}.pdf"'
            return response_obj
        else:
            error_msg = f"API Hatası ({response.status_code}): {response.text}"
            messages.error(request, error_msg)
            # Fallback: Normal PDF oluşturma metoduna yönlendir (API'yi atlamak için no_api=1 ekle)
            ids_param = request.GET.get('ids', '')
            return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")
            
    except (AttributeError, TypeError) as e:
        # requests modülü yüklü değilse veya None ise
        messages.error(request, f'requests modülü hatası: {str(e)}')
        ids_param = request.GET.get('ids', '')
        return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")
    except Exception as e:
        # requests.exceptions.RequestException yerine genel Exception yakalayalım
        if REQUESTS_AVAILABLE and hasattr(requests, 'exceptions'):
            try:
                # requests.exceptions.RequestException kontrolü
                import requests.exceptions
                if isinstance(e, requests.exceptions.RequestException):
                    messages.error(request, f'PDF Generator API bağlantı hatası: {str(e)}')
                else:
                    messages.error(request, f'PDF Generator API hatası: {str(e)}')
            except:
                messages.error(request, f'PDF Generator API hatası: {str(e)}')
        else:
            messages.error(request, f'PDF Generator API hatası: {str(e)}')
        messages.error(request, f'PDF Generator API bağlantı hatası: {str(e)}')
        # Fallback: Normal PDF oluşturma metoduna yönlendir (API'yi atlamak için no_api=1 ekle)
        ids_param = request.GET.get('ids', '')
        return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")
    except Exception as e:
        import traceback
        print(f"PDF Generator API Error: {traceback.format_exc()}")
        messages.error(request, f'PDF Generator API hatası: {str(e)}')
        # Fallback: Normal PDF oluşturma metoduna yönlendir (API'yi atlamak için no_api=1 ekle)
        ids_param = request.GET.get('ids', '')
        return redirect(f"{reverse('stokapp:teklif_talep_formu_pdf')}?ids={ids_param}&no_api=1")

@login_required
def teklif_talep_formu_email(request):
    """Teklif talep formu PDF'ini e-posta ile gönder."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Sadece POST isteği kabul edilir.'}, status=405)

    ids_param = request.GET.get('ids', '')
    if not ids_param:
        return JsonResponse({'success': False, 'error': 'Lütfen en az bir satın alma seçin.'}, status=400)

    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids).select_related('tedarikci')

        if not satinalmalar.exists():
            return JsonResponse({'success': False, 'error': 'Seçilen satın almalar bulunamadı.'}, status=404)

        from .satinalma_mail_send import (
            satinalma_mail_recipient_choices,
            satinalma_mail_normalize_to_allowed,
            send_teklif_talep_formu_mail,
        )

        choices = satinalma_mail_recipient_choices(satinalmalar)
        raw_to = []
        if request.body:
            try:
                payload = json.loads(request.body.decode())
                if isinstance(payload.get('to_emails'), list):
                    raw_to = payload['to_emails']
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                pass

        if raw_to:
            to_emails = satinalma_mail_normalize_to_allowed(raw_to, choices)
        else:
            to_emails = sorted({
                s.tedarikci.email.strip()
                for s in satinalmalar
                if s.tedarikci and s.tedarikci.email and s.tedarikci.email.strip()
            })

        if not to_emails:
            return JsonResponse({
                'success': False,
                'error': 'Gönderilebilir alıcı yok. Tedarikçi firma veya ilgili kişi e-postası ekleyin.',
            }, status=400)

        send_teklif_talep_formu_mail(request, satinalmalar, to_emails)
        return JsonResponse({
            'success': True,
            'message': f'E-posta başarıyla {", ".join(to_emails)} adreslerine gönderildi.',
        })

    except Exception as e:
        import traceback
        print(f"Error: {traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def satinalma_detay_popup(request, pk):
    """Sipariş detayı pop-up için AJAX response"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).select_related('stok_item').order_by('id')
    
    kalemler_data = []
    for kalem in kalemler:
        teslim_bekleyen = kalem.miktar - kalem.teslim_alinan_miktar
        kalemler_data.append({
            'id': kalem.id,
            'stok_kodu': kalem.stok_item.stok_kodu,
            'stok_adi': kalem.stok_item.ad,
            'talep_edilen_miktar': str(kalem.miktar),
            'teslim_alinan_miktar': str(kalem.teslim_alinan_miktar),
            'teslimat_bekleyen_miktar': str(teslim_bekleyen),
            'birim_fiyat': str(kalem.birim_fiyat),
            'efektif_birim_fiyat': str(_satinalma_kalem_efektif_fiyat(kalem)),
            'toplam_fiyat': str(kalem.toplam_fiyat),
            'birim': kalem.stok_item.birim or 'Adet',
            'tedarikci_fiyat': str(kalem.tedarikci_fiyat) if kalem.tedarikci_fiyat else None,
            'teslim_suresi': kalem.teslim_suresi if kalem.teslim_suresi else None,
        })
    
    satinalma_data = {
        'satinalma_numarasi': satinalma.satinalma_numarasi,
        'tedarikci_adi': satinalma.tedarikci_adi or (satinalma.tedarikci.ad if satinalma.tedarikci else ''),
        'olusturulma_tarihi': satinalma.olusturulma_tarihi.strftime('%d.%m.%Y') if satinalma.olusturulma_tarihi else '',
        'tamamlanma_tarihi': satinalma.tamamlanma_tarihi.strftime('%d.%m.%Y') if satinalma.tamamlanma_tarihi else '',
        'toplam': str(satinalma.toplam),
        'para_birimi': satinalma.para_birimi,
        'teslim_durumu': satinalma.get_teslim_durumu_display(),
        'notlar': satinalma.notlar or '',
    }
    
    return JsonResponse({
        'success': True,
        'satinalma': satinalma_data,
        'kalemler': kalemler_data,
    })


@login_required
def satinalma_items_api(request, pk):
    """Satınalma tooltip'i için kalemleri döndürür."""
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    satinalma = get_object_or_404(Satinalma, pk=pk)
    kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).select_related("stok_item").order_by("id")
    items = []
    for kalem in kalemler:
        stok = kalem.stok_item
        items.append({
            "code": stok.stok_kodu if stok else "-",
            "name": stok.ad if stok else "-",
            "quantity": str(kalem.miktar),
            "unit": stok.birim if stok else "",
        })
    return JsonResponse({"success": True, "items": items})


@login_required
def satinalma_kismi_teslimat(request, pk):
    """Kısmi teslimat işlemi"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek'}, status=400)
    
    try:
        with transaction.atomic():
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).select_related('stok_item')
            kalemler_json = json.loads(request.POST.get('kalemler', '[]'))
            
            toplam_teslim = Decimal('0')
            
            for kalem_data in kalemler_json:
                kalem_id = kalem_data.get('kalem_id')
                teslim_alinan_miktar = Decimal(str(kalem_data.get('teslim_alinan_miktar', 0)))
                birim_fiyat_raw = kalem_data.get('birim_fiyat')
                
                if teslim_alinan_miktar <= 0:
                    continue
                
                try:
                    kalem = kalemler.get(id=kalem_id)
                except SatinalmaKalemi.DoesNotExist:
                    continue
                
                # Validasyon
                kalan_miktar = kalem.miktar - kalem.teslim_alinan_miktar
                if teslim_alinan_miktar > kalan_miktar:
                    return JsonResponse({
                        'success': False,
                        'error': f'{kalem.stok_item.ad} için teslim alınan miktar ({teslim_alinan_miktar}) kalan miktardan ({kalan_miktar}) fazla olamaz.'
                    }, status=400)
                
                # Fiyat önceliği: teslimat ekranında girilen fiyat > teklif fiyatı > mevcut birim fiyat
                if birim_fiyat_raw in (None, "", "null"):
                    birim_fiyat = _satinalma_kalem_efektif_fiyat(kalem)
                else:
                    birim_fiyat = Decimal(str(birim_fiyat_raw))
                    if birim_fiyat < 0:
                        return JsonResponse({
                            'success': False,
                            'error': f'{kalem.stok_item.ad} için birim fiyat negatif olamaz.'
                        }, status=400)

                if kalem.birim_fiyat != birim_fiyat:
                    kalem.birim_fiyat = birim_fiyat
                # Teslimatta kullanılan net fiyatı teklif fiyatına da yansıt
                kalem.tedarikci_fiyat = birim_fiyat
                kalem.save()  # save() metodu toplam_fiyat'ı otomatik hesaplar

                # Sistem alış fiyatını güncelle + fiyat geçmişi oluştur
                _stok_alis_fiyati_guncelle_ve_gecmis(
                    stok_item=kalem.stok_item,
                    yeni_fiyat=birim_fiyat,
                    para_birimi=satinalma.para_birimi,
                    aciklama=f'Satınalma kısmi teslim: {satinalma.satinalma_numarasi}',
                    username=request.user.username if request.user.is_authenticated else 'Sistem',
                )
                _siparis_malzeme_maliyetlerini_guncelle(
                    stok_item=kalem.stok_item,
                    yeni_fiyat=birim_fiyat,
                    para_birimi=satinalma.para_birimi,
                )
                
                # Teslim alınan miktarı güncelle
                kalem.teslim_alinan_miktar += teslim_alinan_miktar
                kalem.save()
                
                # Stok hareketi oluştur (StokHareketi.save() otomatik olarak stok miktarını günceller)
                stok_item = kalem.stok_item
                StokHareketi.objects.create(
                    stok_item=stok_item,
                    hareket_tipi='GIRIS',
                    miktar=teslim_alinan_miktar,
                    birim=stok_item.birim or 'Adet',
                    referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                    depo=satinalma.lokasyon,
                    raf=None,
                    aciklama=f'Satınalma Teslimi: {satinalma.satinalma_numarasi}',
                    user=request.user.username if request.user.is_authenticated else 'Sistem'
                )
                
                toplam_teslim += teslim_alinan_miktar
            
            # Tüm kalemlerin teslim edilip edilmediğini kontrol et
            tum_teslim_edildi = True
            for kalem in kalemler:
                if kalem.teslim_alinan_miktar < kalem.miktar:
                    tum_teslim_edildi = False
                    break
            
            if toplam_teslim > 0:
                # Satınalma durumunu güncelle
                if tum_teslim_edildi:
                    satinalma.teslim_durumu = 'TESLIM_ALINDI'
                else:
                    satinalma.teslim_durumu = 'KISMI_TESLIM'
                satinalma.save()
                _satinalma_toplam_yeniden_hesapla(satinalma)
                
                return JsonResponse({
                    'success': True,
                    'message': f'{toplam_teslim} birim malzeme teslim alındı.',
                    'teslim_durumu': satinalma.get_teslim_durumu_display()
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Teslim edilecek malzeme bulunamadı.'
                }, status=400)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Hata: {str(e)}'
        }, status=400)


@login_required
def satinalma_tam_teslimat(request, pk):
    """Tam teslimat işlemi"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek'}, status=400)
    
    try:
        with transaction.atomic():
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).select_related('stok_item')
            
            for kalem in kalemler:
                # Kalan miktarı hesapla
                kalan_miktar = kalem.miktar - kalem.teslim_alinan_miktar
                
                if kalan_miktar > 0:
                    efektif_fiyat = _satinalma_kalem_efektif_fiyat(kalem)
                    if kalem.birim_fiyat != efektif_fiyat or kalem.tedarikci_fiyat != efektif_fiyat:
                        kalem.birim_fiyat = efektif_fiyat
                        kalem.tedarikci_fiyat = efektif_fiyat

                    # Teslim alınan miktarı güncelle
                    kalem.teslim_alinan_miktar = kalem.miktar
                    kalem.save()

                    # Sistem alış fiyatını güncelle + fiyat geçmişi oluştur
                    _stok_alis_fiyati_guncelle_ve_gecmis(
                        stok_item=kalem.stok_item,
                        yeni_fiyat=efektif_fiyat,
                        para_birimi=satinalma.para_birimi,
                        aciklama=f'Satınalma tam teslim: {satinalma.satinalma_numarasi}',
                        username=request.user.username if request.user.is_authenticated else 'Sistem',
                    )
                    _siparis_malzeme_maliyetlerini_guncelle(
                        stok_item=kalem.stok_item,
                        yeni_fiyat=efektif_fiyat,
                        para_birimi=satinalma.para_birimi,
                    )
                    
                    # Stok hareketi oluştur (StokHareketi.save() otomatik olarak stok miktarını günceller)
                    stok_item = kalem.stok_item
                    StokHareketi.objects.create(
                        stok_item=stok_item,
                        hareket_tipi='GIRIS',
                        miktar=kalan_miktar,
                        birim=stok_item.birim or 'Adet',
                        referans_no=f'SAT-{satinalma.satinalma_numarasi}',
                        depo=satinalma.lokasyon,
                        raf=None,
                        aciklama=f'Satınalma Teslimi: {satinalma.satinalma_numarasi}',
                        user=request.user.username if request.user.is_authenticated else 'Sistem'
                    )
            
            # Satınalma durumunu ve arşiv durumunu güncelle
            satinalma.teslim_durumu = 'TESLIM_ALINDI'
            satinalma.arsivlendi = True
            satinalma.save()
            _satinalma_toplam_yeniden_hesapla(satinalma)
            
            return JsonResponse({
                'success': True,
                'message': 'Tüm malzemeler teslim alındı. Satınalma "Teslimatı Tamamlanan Siparişler" sekmesine taşındı.'
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Hata: {str(e)}'
        }, status=400)



def _acik_satinalma_stok_item_ids():
    """Teslimi bekleyen satın almalardaki stok kalemleri (planlamadan hariç tutulur)."""
    return set(
        SatinalmaKalemi.objects.filter(
            satinalma__teslim_durumu__in=['BEKLIYOR', 'KISMI_TESLIM'],
        )
        .values_list('stok_item_id', flat=True)
        .distinct()
    )


def _session_kullanilan_malzemeler_temizle(request):
    """Session'daki eski planlama kayıtlarını açık satın almalarla eşitle."""
    acik_ids = {str(sid) for sid in _acik_satinalma_stok_item_ids()}
    session_list = request.session.get('kullanilan_malzemeler', [])
    if not isinstance(session_list, list):
        session_list = []
    temiz = [sid for sid in session_list if sid in acik_ids]
    if temiz != session_list:
        request.session['kullanilan_malzemeler'] = temiz
        request.session.modified = True


def _uretim_malzemesi_planla_verileri(request):
    """Planlanacak üretim malzemelerini hesaplar (liste ve PDF için ortak)."""
    _session_kullanilan_malzemeler_temizle(request)

    # Yalnızca gerçekten açık satın alma siparişlerindeki kalemler hariç tutulur.
    # Session'dan silinen / düzenlenen satın alma kalemleri planlamaya geri döner.
    kullanilan_malzemeler = {str(sid) for sid in _acik_satinalma_stok_item_ids()}

    uretim_emirleri = list(
        UretimEmri.objects.filter(
            durum__in=['PLANLANDI', 'BASLADI']
        ).select_related('recete', 'recete__urun', 'ust_uretim_emri')
    )

    kapsanan_urun_by_emir = build_kapsanan_urun_ids_by_emir(uretim_emirleri)
    recete_id_by_urun = aktif_recete_id_by_urun()

    basladi_emir_ids = [emir.id for emir in uretim_emirleri if emir.durum == 'BASLADI']
    cikis_by_emir_stok = {}
    if basladi_emir_ids:
        for row in (
            StokHareketi.objects.filter(
                uretim_emri_id__in=basladi_emir_ids,
                hareket_tipi='URETIM_CIKIS',
            )
            .values('uretim_emri_id', 'stok_item_id')
            .annotate(total=Sum('miktar'))
        ):
            cikis_by_emir_stok[(row['uretim_emri_id'], row['stok_item_id'])] = Decimal(str(row['total']))

    malzemeler = {}

    for emir in uretim_emirleri:
        if emir.durum == 'PLANLANDI' and emir.production_type == 'STOCK':
            continue

        kapsanan_urun_ids = kapsanan_urun_by_emir.get(emir.id, frozenset())
        malzeme_detay = uretim_emri_malzeme_satirlari_detayli(
            emir,
            kapsanan_urun_ids,
            recete_id_by_urun,
            cikis_by_emir_stok,
        )

        for stok_item_id, info in malzeme_detay.items():
            kalan_ihtiyac = info['kalan']
            toplam_ihtiyac = info['toplam']
            dusulen = info['dusulen']
            birim = info['birim']

            if str(stok_item_id) in kullanilan_malzemeler:
                continue

            if stok_item_id not in malzemeler:
                stok_item = StokItem.objects.get(pk=stok_item_id)
                mevcut_miktar = stok_item.mevcut_miktar
                if mevcut_miktar is None:
                    mevcut_miktar = Decimal('0')
                else:
                    mevcut_miktar = Decimal(str(mevcut_miktar))

                malzemeler[stok_item_id] = {
                    'stok_item': stok_item,
                    'kullanilacak_miktar': Decimal('0'),  # kalan ihtiyaç (satınalma için)
                    'toplam_ihtiyac': Decimal('0'),
                    'dusulen_miktar': Decimal('0'),
                    'mevcut_miktar': mevcut_miktar,
                    'min_stok': Decimal(str(stok_item.minimum_stok or 0)),
                    'max_stok': Decimal(str(stok_item.maximum_stok or 0)) if stok_item.maximum_stok is not None else None,
                    'birim': birim,
                    'emir_no_list': [],
                    'emir_link_list': [],
                }

            malzemeler[stok_item_id]['toplam_ihtiyac'] += toplam_ihtiyac
            malzemeler[stok_item_id]['dusulen_miktar'] += dusulen
            if kalan_ihtiyac > 0:
                malzemeler[stok_item_id]['kullanilacak_miktar'] += kalan_ihtiyac
            if emir.emir_no not in malzemeler[stok_item_id]['emir_no_list']:
                malzemeler[stok_item_id]['emir_no_list'].append(emir.emir_no)
            if not any(link['id'] == emir.id for link in malzemeler[stok_item_id]['emir_link_list']):
                malzemeler[stok_item_id]['emir_link_list'].append({
                    'id': emir.id,
                    'emir_no': emir.emir_no,
                    'miktar': emir.miktar,
                    'durum': emir.durum,
                })

    planlanacak_malzemeler = []
    for data in malzemeler.values():
        mevcut = Decimal(str(data['mevcut_miktar']))
        kullanilacak = Decimal(str(data['kullanilacak_miktar']))
        toplam_ihtiyac = Decimal(str(data.get('toplam_ihtiyac') or 0))
        dusulen_miktar = Decimal(str(data.get('dusulen_miktar') or 0))
        kalan_stok = mevcut - kullanilacak
        min_stok = Decimal(str(data['min_stok']))
        max_stok = data['max_stok']
        if max_stok is None or Decimal(str(max_stok)) <= 0:
            hedef_stok = min_stok
        else:
            hedef_stok = Decimal(str(max_stok))

        # Üretim ihtiyacı karşılanmış olsa bile (BASLADI + stok düşümü) minimum altındaysa listele
        if kalan_stok < min_stok or mevcut < kullanilacak:
            satin_alma_oneri = hedef_stok - kalan_stok
            if satin_alma_oneri < 0:
                satin_alma_oneri = Decimal('0')
            planlanacak_malzemeler.append({
                'stok_item': data['stok_item'],
                'kullanilacak_miktar': kullanilacak,
                'toplam_ihtiyac': toplam_ihtiyac,
                'dusulen_miktar': dusulen_miktar,
                'mevcut_miktar': mevcut,
                'kalan_stok': kalan_stok,
                'min_stok': min_stok,
                'max_stok': max_stok,
                'eksik_miktar': satin_alma_oneri,
                'birim': data['birim'],
                'emir_no_list': data['emir_no_list'],
                'emir_link_list': data.get('emir_link_list', []),
            })

    if planlanacak_malzemeler:
        plan_stok_ids = [m['stok_item'].pk for m in planlanacak_malzemeler]
        rfq_acik_durumlar = ('TASLAK', 'TEKLIF_BEKLENIYOR', 'DEGERLENDIRMEDE')
        rfq_nolar_by_stok = {}
        seen_stok_rfq = set()
        for row in (
            TeklifTalebiKalemi.objects.filter(
                stok_item_id__in=plan_stok_ids,
                rfq__durum__in=rfq_acik_durumlar,
            )
            .values('stok_item_id', 'rfq_id', 'rfq__rfq_no')
            .order_by('-rfq_id')
        ):
            sid = row['stok_item_id']
            rid = row['rfq_id']
            rno = row['rfq__rfq_no'] or ''
            key = (sid, rid)
            if key in seen_stok_rfq:
                continue
            seen_stok_rfq.add(key)
            rfq_nolar_by_stok.setdefault(sid, []).append(rno)
        for m in planlanacak_malzemeler:
            m['rfq_acik_nolar'] = rfq_nolar_by_stok.get(m['stok_item'].pk, [])

    return planlanacak_malzemeler


@login_required
@never_cache
def uretim_malzemesi_planla(request):
    """Üretim emirlerinden yetersiz malzemeleri listele ve satınalma planla"""
    if request.GET.get('yenile') == '1':
        request.session['kullanilan_malzemeler'] = []
        request.session.modified = True
        messages.info(request, 'Liste güncellendi.')
        return redirect('stokapp:uretim_malzemesi_planla')

    planlanacak_malzemeler = _uretim_malzemesi_planla_verileri(request)

    try:
        pdf_url = reverse('stokapp:uretim_malzemesi_planla_pdf')
    except Exception:
        pdf_url = '/stok/satinalma/uretim-malzemesi-planla/pdf/'

    context = {
        'malzemeler': planlanacak_malzemeler,
        'pdf_url': pdf_url,
        'son_guncelleme': timezone.localtime(timezone.now()),
    }
    response = render(request, 'stokapp/uretim_malzemesi_planla.html', context)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


@login_required
@never_cache
def uretim_malzemesi_planla_pdf(request):
    """Üretim malzemesi planı — yatay PDF çıktı."""
    global WEASYPRINT_AVAILABLE
    if WEASYPRINT_AVAILABLE is None:
        try:
            from weasyprint import HTML, CSS  # noqa: F401
            WEASYPRINT_AVAILABLE = True
        except ImportError:
            WEASYPRINT_AVAILABLE = False

    if not WEASYPRINT_AVAILABLE:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:uretim_malzemesi_planla')

    from weasyprint import HTML, CSS

    malzemeler = _uretim_malzemesi_planla_verileri(request)
    olusturma_tarihi = timezone.localtime(timezone.now())

    template = get_template('stokapp/uretim_malzemesi_planla_pdf.html')
    html = template.render({
        'malzemeler': malzemeler,
        'olusturma_tarihi': olusturma_tarihi,
        'kalem_sayisi': len(malzemeler),
    })

    css = CSS(string="""
        @page {
            size: A4 landscape;
            margin: 10mm;
        }
        body {
            font-family: 'DejaVu Sans', Arial, sans-serif;
            font-size: 8pt;
            color: #111827;
        }
        h1 {
            font-size: 14pt;
            margin: 0 0 4px 0;
        }
        .meta {
            color: #6b7280;
            font-size: 8pt;
            margin-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: #f3f4f6;
            border: 1px solid #d1d5db;
            padding: 5px 4px;
            text-align: left;
            font-size: 7.5pt;
        }
        td {
            border: 1px solid #e5e7eb;
            padding: 4px;
            vertical-align: top;
        }
        .num { text-align: right; white-space: nowrap; }
        .eksik { color: #dc2626; font-weight: bold; }
        .rfq {
            display: inline-block;
            font-size: 6.5pt;
            color: #92400e;
            background: #fef3c7;
            padding: 1px 4px;
            border-radius: 3px;
        }
        .empty {
            text-align: center;
            color: #6b7280;
            padding: 24px;
        }
    """)

    try:
        pdf_bytes = HTML(
            string=html,
            base_url=request.build_absolute_uri('/'),
        ).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:uretim_malzemesi_planla')

    filename = f"uretim_malzemesi_plani_{olusturma_tarihi.strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def teklif_girisi(request, pk):
    """Teklif girişi - tedarikçiden gelen fiyat ve teslim süresi bilgilerini güncelle"""
    satinalma = get_object_or_404(Satinalma, pk=pk)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek'}, status=400)
    
    try:
        with transaction.atomic():
            kalemler_json = json.loads(request.POST.get('kalemler', '[]'))
            
            for kalem_data in kalemler_json:
                kalem_id = kalem_data.get('kalem_id')
                tedarikci_fiyat = kalem_data.get('tedarikci_fiyat')
                teslim_suresi = kalem_data.get('teslim_suresi')
                
                try:
                    kalem = SatinalmaKalemi.objects.get(pk=kalem_id, satinalma=satinalma)
                    
                    if tedarikci_fiyat is not None:
                        yeni_fiyat = Decimal(str(tedarikci_fiyat)) if tedarikci_fiyat else None
                        if yeni_fiyat is not None:
                            if yeni_fiyat < 0:
                                return JsonResponse({
                                    'success': False,
                                    'error': f'{kalem.stok_item.ad} için teklif fiyatı negatif olamaz.'
                                }, status=400)
                            kalem.tedarikci_fiyat = yeni_fiyat
                            # Teklif girişi fiyatı satınalma kaleminin birim fiyatını da günceller
                            kalem.birim_fiyat = yeni_fiyat
                            _stok_alis_fiyati_guncelle_ve_gecmis(
                                stok_item=kalem.stok_item,
                                yeni_fiyat=yeni_fiyat,
                                para_birimi=satinalma.para_birimi,
                                aciklama=f'Teklif girişi: {satinalma.satinalma_numarasi}',
                                username=request.user.username if request.user.is_authenticated else 'Sistem',
                            )
                            _siparis_malzeme_maliyetlerini_guncelle(
                                stok_item=kalem.stok_item,
                                yeni_fiyat=yeni_fiyat,
                                para_birimi=satinalma.para_birimi,
                            )
                        else:
                            kalem.tedarikci_fiyat = None
                    if teslim_suresi is not None:
                        kalem.teslim_suresi = int(teslim_suresi) if teslim_suresi else None
                    
                    kalem.save()
                except SatinalmaKalemi.DoesNotExist:
                    continue

            _satinalma_toplam_yeniden_hesapla(satinalma)
            
            return JsonResponse({
                'success': True,
                'message': 'Teklif bilgileri başarıyla kaydedildi.'
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Hata: {str(e)}'
        }, status=400)


@login_required
def siparis_formu(request):
    """Sipariş formu HTML sayfası - teklif formu gibi ama başlık farklı, fiyatlar görünecek"""
    # Seçilen satın alma ID'leri
    ids_param = request.GET.get('ids', '')
    if not ids_param:
        messages.error(request, 'Lütfen en az bir satın alma seçin.')
        return redirect('stokapp:satinalma_listesi')
    
    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids)
        
        if not satinalmalar.exists():
            messages.error(request, 'Seçilen satın almalar bulunamadı.')
            return redirect('stokapp:satinalma_listesi')
        
        from .models import GenelAyarlar, YazdirmaSablonu
        ayarlar = GenelAyarlar.get_ayarlar()
        sablon = YazdirmaSablonu.objects.filter(tip='SIPARIS', aktif=True).first()
        
        # Tüm kalemleri topla
        tum_kalemler = []
        toplam_birim = Decimal('0')
        toplam_ara_toplam = Decimal('0')
        
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                # Tedarikçi fiyatı varsa onu kullan, yoksa birim_fiyat'ı kullan
                fiyat = kalem.tedarikci_fiyat if kalem.tedarikci_fiyat else kalem.birim_fiyat
                tum_kalemler.append({
                    'satinalma': satinalma,
                    'kalem': kalem,
                    'urun_adi': kalem.stok_item.ad,
                    'aciklama': kalem.stok_item.aciklama or '',
                    'adet': kalem.miktar,
                    'birim_fiyat': fiyat,
                    'ara_toplam': kalem.miktar * fiyat,
                    'teslim_suresi': kalem.teslim_suresi,
                })
                toplam_birim += kalem.miktar
                toplam_ara_toplam += kalem.miktar * fiyat
        
        vergi = toplam_ara_toplam * Decimal('0.20')
        toplam = toplam_ara_toplam + vergi
        
        termin_tarihi = None
        for satinalma in satinalmalar:
            if satinalma.tamamlanma_tarihi:
                if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                    termin_tarihi = satinalma.tamamlanma_tarihi
        
        # Sipariş numarası oluştur
        ilk_satinalma = satinalmalar.first()
        siparis_no = ilk_satinalma.satinalma_numarasi if ilk_satinalma else f"SIP-{satinalma_ids[0]}"
        para_birimi = ilk_satinalma.para_birimi if ilk_satinalma else 'TRY'
        
        tekmar_logo_data_uri = _logo_data_uri_from_path(
            _resolve_siparis_logo_abs_path(ayarlar=ayarlar, sablon=sablon)
        )

        context = {
            'siparis_no': siparis_no,
            'satinalmalar': satinalmalar,
            'tedarikci': ilk_satinalma.tedarikci if ilk_satinalma.tedarikci else None,
            'tedarikci_adi': ilk_satinalma.tedarikci_adi or (ilk_satinalma.tedarikci.ad if ilk_satinalma.tedarikci else ''),
            'termin_tarihi': termin_tarihi or timezone.now().date(),
            'kalemler': tum_kalemler,
            'toplam_birim': toplam_birim,
            'toplam_ara_toplam': toplam_ara_toplam,
            'vergi': vergi,
            'toplam': toplam,
            'para_birimi': para_birimi,
            'ayarlar': ayarlar,
            'sablon': sablon,
            'tekmar_logo_data_uri': tekmar_logo_data_uri,
        }
        
        return render(request, 'stokapp/siparis_formu.html', context)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"General Error in siparis_formu: {str(e)}")
        print(f"Traceback: {error_trace}")
        messages.error(request, f'Hata: {str(e)}')
        return redirect('stokapp:satinalma_listesi')


@login_required
def siparis_formu_pdf(request):
    """Sipariş formu PDF olarak indir - teklif formu gibi ama başlık farklı, fiyatlar görünecek"""
    # Seçilen satın alma ID'leri
    ids_param = request.GET.get('ids', '')
    if not ids_param:
        messages.error(request, 'Lütfen en az bir satın alma seçin.')
        return redirect('stokapp:satinalma_listesi')
    
    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids)
        
        if not satinalmalar.exists():
            messages.error(request, 'Seçilen satın almalar bulunamadı.')
            return redirect('stokapp:satinalma_listesi')
        
        from .models import GenelAyarlar, YazdirmaSablonu
        ayarlar = GenelAyarlar.get_ayarlar()
        sablon = YazdirmaSablonu.objects.filter(tip='SIPARIS', aktif=True).first()
        # Eğer SIPARIS tipinde sablon yoksa, TEKLIF_TALEBI tipindeki sablonu kullan (görsel olarak aynı)
        if not sablon:
            sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()
        
        # Tüm kalemleri topla
        tum_kalemler = []
        toplam_birim = Decimal('0')
        toplam_ara_toplam = Decimal('0')
        
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                # Tedarikçi fiyatı varsa onu kullan, yoksa birim_fiyat'ı kullan
                fiyat = kalem.tedarikci_fiyat if kalem.tedarikci_fiyat else kalem.birim_fiyat
                tum_kalemler.append({
                    'satinalma': satinalma,
                    'kalem': kalem,
                    'urun_adi': kalem.stok_item.ad,
                    'aciklama': kalem.stok_item.aciklama or '',
                    'adet': kalem.miktar,
                    'birim_fiyat': fiyat,
                    'ara_toplam': kalem.miktar * fiyat,
                    'teslim_suresi': kalem.teslim_suresi,
                })
                toplam_birim += kalem.miktar
                toplam_ara_toplam += kalem.miktar * fiyat
        
        vergi = toplam_ara_toplam * Decimal('0.20')
        toplam = toplam_ara_toplam + vergi
        
        termin_tarihi = None
        for satinalma in satinalmalar:
            if satinalma.tamamlanma_tarihi:
                if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                    termin_tarihi = satinalma.tamamlanma_tarihi
        
        # Sipariş numarası oluştur
        ilk_satinalma = satinalmalar.first()
        siparis_no = ilk_satinalma.satinalma_numarasi if ilk_satinalma else f"SIP-{satinalma_ids[0]}"
        para_birimi = ilk_satinalma.para_birimi if ilk_satinalma else 'TRY'
        
        context = {
            'siparis_no': siparis_no,
            'satinalmalar': satinalmalar,
            'tedarikci': ilk_satinalma.tedarikci if ilk_satinalma.tedarikci else None,
            'tedarikci_adi': ilk_satinalma.tedarikci_adi or (ilk_satinalma.tedarikci.ad if ilk_satinalma.tedarikci else ''),
            'termin_tarihi': termin_tarihi or timezone.now().date(),
            'kalemler': tum_kalemler,
            'toplam_birim': toplam_birim,
            'toplam_ara_toplam': toplam_ara_toplam,
            'vergi': vergi,
            'toplam': toplam,
            'para_birimi': para_birimi,
            'ayarlar': ayarlar,
            'sablon': sablon,
            'for_pdf': True,
        }
        
        template = get_template('stokapp/siparis_formu_pdf.html')
        
        context['logo_path'] = _resolve_siparis_logo_abs_path(ayarlar=ayarlar, sablon=sablon)
        
        html_content = template.render(context)
        
        # WeasyPrint ile PDF oluştur
        try:
            from weasyprint import HTML
            pdf_file = BytesIO()
            HTML(string=html_content, base_url=request.build_absolute_uri('/')).write_pdf(pdf_file)
            pdf_file.seek(0)
            
            response = HttpResponse(pdf_file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="siparis_formu_{siparis_no}.pdf"'
            return response
        except ImportError:
            messages.error(request, 'WeasyPrint kütüphanesi bulunamadı. PDF oluşturulamadı.')
            return redirect('stokapp:satinalma_listesi')
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"General Error in siparis_formu_pdf: {str(e)}")
        print(f"Traceback: {error_trace}")
        messages.error(request, f'Hata: {str(e)}')
        return redirect('stokapp:satinalma_listesi')


@login_required
def siparis_formu_email(request):
    """Sipariş formu PDF'ini e-posta ile gönder."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Sadece POST isteği kabul edilir.'}, status=405)

    ids_param = request.GET.get('ids', '')
    if not ids_param:
        return JsonResponse({'success': False, 'error': 'Lütfen en az bir satın alma seçin.'}, status=400)

    try:
        satinalma_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
        satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids).select_related('tedarikci')

        if not satinalmalar.exists():
            return JsonResponse({'success': False, 'error': 'Seçilen satın almalar bulunamadı.'}, status=404)

        from .satinalma_mail_send import (
            satinalma_mail_recipient_choices,
            satinalma_mail_normalize_to_allowed,
            send_siparis_formu_mail,
        )

        choices = satinalma_mail_recipient_choices(satinalmalar)
        raw_to = []
        if request.body:
            try:
                payload = json.loads(request.body.decode())
                if isinstance(payload.get('to_emails'), list):
                    raw_to = payload['to_emails']
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                pass

        if raw_to:
            to_emails = satinalma_mail_normalize_to_allowed(raw_to, choices)
        else:
            to_emails = sorted({
                s.tedarikci.email.strip()
                for s in satinalmalar
                if s.tedarikci and s.tedarikci.email and s.tedarikci.email.strip()
            })

        if not to_emails:
            return JsonResponse({
                'success': False,
                'error': 'Gönderilebilir alıcı yok. Tedarikçi firma veya ilgili kişi e-postası ekleyin.',
            }, status=400)

        send_siparis_formu_mail(request, satinalmalar, to_emails)
        return JsonResponse({
            'success': True,
            'message': f'Sipariş formu {", ".join(to_emails)} adreslerine başarıyla gönderildi.',
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


SATINALMA_MAIL_WIZARD_SESSION_KEY = 'satinalma_mail_gonder_wizard'


def _satinalma_mail_form_url(kind: str, ids_param: str):
    if kind == 'teklif':
        return f"{reverse('stokapp:teklif_talep_formu')}?ids={ids_param}"
    return f"{reverse('stokapp:siparis_formu')}?ids={ids_param}"


@login_required
def satinalma_mail_alici_sec(request):
    """Teklif / sipariş maili için tedarikçi ilgili kişilerinden alıcı seçimi."""
    kind = (request.GET.get('kind') or request.POST.get('kind') or '').strip()
    ids_param = (request.GET.get('ids') or request.POST.get('ids') or '').strip()
    rfq_param = (request.GET.get('rfq') or request.POST.get('rfq') or '').strip()
    if kind not in ('teklif', 'siparis') or not ids_param:
        messages.error(request, 'Geçersiz istek.')
        return redirect('stokapp:satinalma_listesi')

    try:
        satinalma_ids = [int(x.strip()) for x in ids_param.split(',') if x.strip()]
    except ValueError:
        messages.error(request, 'Geçersiz satın alma listesi.')
        return redirect('stokapp:satinalma_listesi')

    satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids).select_related('tedarikci')
    if not satinalmalar.exists():
        messages.error(request, 'Satın almalar bulunamadı.')
        return redirect('stokapp:satinalma_listesi')

    from .satinalma_mail_send import (
        satinalma_mail_recipient_choices,
        satinalma_mail_emails_from_keys,
        satinalma_mail_labels_from_keys,
    )

    choices = satinalma_mail_recipient_choices(satinalmalar)
    if not choices:
        messages.error(
            request,
            'Gönderilebilir e-posta yok. Tedarikçi kartında firma e-postası veya ilgili kişi e-postası ekleyin.',
        )
        return redirect('stokapp:satinalma_listesi')

    if request.method == 'POST':
        selected = request.POST.getlist('recipient_key')
        emails = satinalma_mail_emails_from_keys(choices, selected)
        if not emails:
            messages.error(request, 'En az bir alıcı seçin.')
            return render(
                request,
                'stokapp/satinalma_mail_alici_sec.html',
                {
                    'kind': kind,
                    'ids_param': ids_param,
                    'choices': choices,
                    'satinalmalar': satinalmalar,
                    'geri_url': _satinalma_mail_form_url(kind, ids_param),
                    'rfq_param': rfq_param,
                },
            )
        labels = satinalma_mail_labels_from_keys(choices, selected)
        request.session[SATINALMA_MAIL_WIZARD_SESSION_KEY] = {
            'kind': kind,
            'ids': ids_param,
            'emails': emails,
            'labels': labels,
            'uid': request.user.pk,
            'rfq': rfq_param,
        }
        return redirect('stokapp:satinalma_mail_onay')

    return render(
        request,
        'stokapp/satinalma_mail_alici_sec.html',
        {
            'kind': kind,
            'ids_param': ids_param,
            'choices': choices,
            'satinalmalar': satinalmalar,
            'geri_url': _satinalma_mail_form_url(kind, ids_param),
            'rfq_param': rfq_param,
        },
    )


@login_required
def satinalma_mail_onay(request):
    """Mail göndermeden önce alıcı özeti; «Maili gönder» ile gönderilir."""
    data = request.session.get(SATINALMA_MAIL_WIZARD_SESSION_KEY)
    if not data or data.get('uid') != request.user.pk:
        messages.error(request, 'Oturum süresi doldu. Lütfen alıcı seçimini yeniden yapın.')
        return redirect('stokapp:satinalma_listesi')

    kind = data['kind']
    ids_param = data['ids']
    emails = list(data['emails'])
    labels = list(data['labels'])

    try:
        satinalma_ids = [int(x.strip()) for x in ids_param.split(',') if x.strip()]
    except ValueError:
        del request.session[SATINALMA_MAIL_WIZARD_SESSION_KEY]
        messages.error(request, 'Geçersiz oturum verisi.')
        return redirect('stokapp:satinalma_listesi')

    satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids).select_related('tedarikci')
    if not satinalmalar.exists():
        del request.session[SATINALMA_MAIL_WIZARD_SESSION_KEY]
        messages.error(request, 'Satın almalar bulunamadı.')
        return redirect('stokapp:satinalma_listesi')

    from .satinalma_mail_send import (
        satinalma_mail_recipient_choices,
        satinalma_mail_normalize_to_allowed,
        send_teklif_talep_formu_mail,
        send_siparis_formu_mail,
    )

    choices = satinalma_mail_recipient_choices(satinalmalar)
    allowed = satinalma_mail_normalize_to_allowed(emails, choices)

    ctx = {
        'kind': kind,
        'ids_param': ids_param,
        'emails': allowed if allowed else emails,
        'labels': labels,
        'emails_invalid': not allowed,
        'geri_url': reverse('stokapp:satinalma_mail_alici_sec') + f'?kind={kind}&ids={ids_param}',
        'form_url': _satinalma_mail_form_url(kind, ids_param),
    }

    if request.method == 'POST':
        if not allowed:
            del request.session[SATINALMA_MAIL_WIZARD_SESSION_KEY]
            messages.error(request, 'Seçilen adresler artık geçerli değil. Lütfen yeniden seçin.')
            return redirect(f"{reverse('stokapp:satinalma_mail_alici_sec')}?kind={kind}&ids={ids_param}")

        try:
            if kind == 'teklif':
                send_teklif_talep_formu_mail(request, satinalmalar, allowed)
            else:
                send_siparis_formu_mail(request, satinalmalar, allowed)
        except Exception as exc:
            messages.error(request, str(exc))
            return render(request, 'stokapp/satinalma_mail_onay.html', ctx)

        rfq_id_str = (data.get('rfq') or '').strip()
        del request.session[SATINALMA_MAIL_WIZARD_SESSION_KEY]
        messages.success(request, f'E-posta gönderildi: {", ".join(allowed)}')

        # RFQ wizard zinciri varsa: bu siparişi kalan listesinden düşür ve overview'e dön
        if rfq_id_str:
            try:
                from .views_rfq import SATINALMA_RFQ_MAIL_WIZARD_KEY
                state = request.session.get(SATINALMA_RFQ_MAIL_WIZARD_KEY) or {}
                if str(state.get('rfq_id')) == rfq_id_str:
                    kalan = [x for x in state.get('kalan_ids', []) if x not in satinalma_ids]
                    state['kalan_ids'] = kalan
                    request.session[SATINALMA_RFQ_MAIL_WIZARD_KEY] = state
                    request.session.modified = True
                    if not kalan:
                        request.session.pop(SATINALMA_RFQ_MAIL_WIZARD_KEY, None)
                        return redirect('stokapp:satinalma_listesi')
                    return redirect('stokapp:rfq_siparis_mail_secimi', pk=int(rfq_id_str))
            except Exception:
                pass

        return redirect(_satinalma_mail_form_url(kind, ids_param))

    return render(request, 'stokapp/satinalma_mail_onay.html', ctx)

