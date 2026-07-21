from django.shortcuts import render
from django.db.models import Sum, Count, F, Q, Value, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.db import transaction
from .models import *  # ⭐ Tüm modelleri import et
from django.contrib.auth.decorators import login_required
import pandas as pd
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.urls import reverse
import json
import re
from collections import defaultdict
from decimal import Decimal


_TCMB_KUR_CACHE = {"mono_t": -1e9, "usd": None, "eur": None}
_TCMB_KUR_TTL_SEC = 3600.0
_TCMB_KUR_LAST_FETCH_ATTEMPT = -1e9
_TCMB_KUR_FETCH_COOLDOWN_SEC = 90.0


def _dashboard_tcmb_kurlar():
    """
    TCMB döviz kurları. Bellek önbelleği + kısa timeout; başarılı yanıt 1 saat geçerli.
    Ağ hatasında önceki kur korunur. Hiç kur yokken üst üste istek yapılmaması için kısa bekleme.
    """
    global _TCMB_KUR_CACHE, _TCMB_KUR_LAST_FETCH_ATTEMPT
    import time
    import xml.etree.ElementTree as ET

    import requests

    now = time.monotonic()
    if (now - _TCMB_KUR_CACHE["mono_t"]) < _TCMB_KUR_TTL_SEC:
        return _TCMB_KUR_CACHE["usd"], _TCMB_KUR_CACHE["eur"]
    if (now - _TCMB_KUR_LAST_FETCH_ATTEMPT) < _TCMB_KUR_FETCH_COOLDOWN_SEC:
        return _TCMB_KUR_CACHE["usd"], _TCMB_KUR_CACHE["eur"]

    _TCMB_KUR_LAST_FETCH_ATTEMPT = now
    usd_kur = eur_kur = None
    try:
        response = requests.get(
            "https://www.tcmb.gov.tr/kurlar/today.xml",
            timeout=(0.8, 2.0),
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        root = ET.fromstring(response.text)
        usd_element = root.find(".//Currency[@CurrencyCode='USD']/BanknoteSelling")
        if usd_element is not None and usd_element.text:
            usd_kur = float(usd_element.text.replace(",", "."))
        eur_element = root.find(".//Currency[@CurrencyCode='EUR']/BanknoteSelling")
        if eur_element is not None and eur_element.text:
            eur_kur = float(eur_element.text.replace(",", "."))
        _TCMB_KUR_CACHE.update(mono_t=now, usd=usd_kur, eur=eur_kur)
    except Exception:
        pass
    return _TCMB_KUR_CACHE["usd"], _TCMB_KUR_CACHE["eur"]


def _siparis_numarasi_uretim_emri_aciklamadan(aciklama):
    if not aciklama:
        return None
    m = re.search(r"Sipariş\s+([A-Za-z0-9\-_/]+)\s+için oluşturuldu", aciklama, re.IGNORECASE)
    return m.group(1) if m else None


def _bom_rezerve_by_stok_item():
    """
    Hammadde rezervi: (1) PLANLANDI sipariş iş emirlerinin reçete ihtiyacı
    + (2) ONAYLI siparişte, o sipariş için PLANLANDI sipariş-emirleriyle karşılanmayan ürün miktarına göre reçete ihtiyacı.
    Stok üretimi (production_type=STOCK) emirleri rezerveye dahil edilmez; hammadde yalnızca üretim başlatılınca düşer.
    Üretim başlayınca emir BASLADI olur → (1) düşer; aynı miktar üretim sütununda (URETIM_CIKIS) görünür.
    """
    out = defaultdict(lambda: Decimal("0"))

    emirler_plan = (
        UretimEmri.objects.filter(durum="PLANLANDI", production_type="ORDER")
        .select_related("recete")
        .prefetch_related("recete__detaylar")
    )
    for emir in emirler_plan:
        for detay in emir.recete.detaylar.all():
            if detay.stok_item_id == emir.recete.urun_id:
                continue
            need = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
            out[detay.stok_item_id] += need

    siparis_emir_mik = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    for emir in (
        UretimEmri.objects.filter(durum="PLANLANDI", production_type="ORDER").select_related(
            "recete"
        )
    ):
        sn = _siparis_numarasi_uretim_emri_aciklamadan(emir.aciklama or "")
        if not sn:
            continue
        siparis_emir_mik[sn][emir.recete.urun_id] += Decimal(str(emir.miktar))

    siparisler = Siparis.objects.filter(siparis_durumu="ONAYLANDI").prefetch_related("kalemler")

    urun_ids = set()
    for siparis in siparisler:
        for k in siparis.kalemler.all():
            urun_ids.add(k.stok_item_id)

    recete_by_urun = {}
    for rec in Recete.objects.filter(urun_id__in=urun_ids, aktif=True).prefetch_related("detaylar"):
        recete_by_urun[rec.urun_id] = rec
    urun_rolu_by_id = dict(
        StokItem.objects.filter(id__in=urun_ids).values_list("id", "urun_rolu")
    )

    for siparis in siparisler:
        snum = siparis.siparis_numarasi
        urun_to_sip = defaultdict(lambda: Decimal("0"))
        for k in siparis.kalemler.all():
            urun_to_sip[k.stok_item_id] += Decimal(str(k.miktar))

        emir_by_urun = siparis_emir_mik.get(snum, {})

        for urun_id, sip_toplam in urun_to_sip.items():
            # Rezerveye sadece üretimi yapılan nihai ürünlerin reçete ihtiyacını dahil et.
            if urun_rolu_by_id.get(urun_id) != "NIHAI_URUN":
                continue
            kalan = sip_toplam - emir_by_urun.get(urun_id, Decimal("0"))
            if kalan <= 0:
                continue
            recete = recete_by_urun.get(urun_id)
            if not recete:
                continue
            for detay in recete.detaylar.all():
                # Ürünün kendisini tekrar bileşen gibi rezerve etme (çift sayım engeli).
                if detay.stok_item_id == urun_id:
                    continue
                need = Decimal(str(detay.miktar)) * kalan
                out[detay.stok_item_id] += need

    return dict(out)


def _satinalma_bekleyen_miktar(kalem):
    if kalem.satinalma.teslim_durumu == 'BEKLIYOR':
        return kalem.miktar
    return kalem.miktar - kalem.teslim_alinan_miktar


def _stok_liste_satinalma_linkleri():
    """stok_item_id -> [{id, numara, miktar}] (açık satınalma kalemleri)."""
    from .models import SatinalmaKalemi

    out = defaultdict(list)
    kalemler = SatinalmaKalemi.objects.filter(
        satinalma__teslim_durumu__in=['BEKLIYOR', 'KISMI_TESLIM'],
    ).select_related('satinalma')
    for kalem in kalemler:
        bekleyen = _satinalma_bekleyen_miktar(kalem)
        if bekleyen <= 0:
            continue
        out[kalem.stok_item_id].append({
            'id': kalem.satinalma_id,
            'numara': kalem.satinalma.satinalma_numarasi,
            'miktar': bekleyen,
        })
    return dict(out)


def _stok_liste_uretim_linkleri():
    """Ürün stok_item_id -> [{id, emir_no, miktar}] (BASLADI emirler)."""
    out = defaultdict(list)
    for emir in UretimEmri.objects.filter(durum='BASLADI').select_related('recete'):
        out[emir.recete.urun_id].append({
            'id': emir.id,
            'emir_no': emir.emir_no,
            'miktar': emir.miktar,
        })
    return dict(out)


def _stok_liste_rezerve_linkleri():
    """
    stok_item_id -> [{siparis_id?, siparis_numarasi?, uretim_emri_id?, emir_no?, miktar, kaynak}]
    """
    out = defaultdict(list)

    for kalem in SiparisKalemi.objects.filter(
        siparis__siparis_durumu='ONAYLANDI',
        stok_item_id__isnull=False,
    ).select_related('siparis'):
        out[kalem.stok_item_id].append({
            'siparis_id': kalem.siparis_id,
            'siparis_numarasi': kalem.siparis.siparis_numarasi,
            'miktar': Decimal(str(kalem.miktar)),
            'kaynak': 'siparis_kalem',
        })

    siparis_by_num = {
        s.siparis_numarasi: s
        for s in Siparis.objects.filter(siparis_durumu='ONAYLANDI').only('id', 'siparis_numarasi')
    }

    emirler_plan = (
        UretimEmri.objects.filter(durum='PLANLANDI', production_type='ORDER')
        .select_related('recete')
        .prefetch_related('recete__detaylar')
    )
    for emir in emirler_plan:
        sn = _siparis_numarasi_uretim_emri_aciklamadan(emir.aciklama or '')
        siparis = siparis_by_num.get(sn) if sn else None
        for detay in emir.recete.detaylar.all():
            if detay.stok_item_id == emir.recete.urun_id:
                continue
            need = Decimal(str(detay.miktar)) * Decimal(str(emir.miktar))
            entry = {
                'miktar': need,
                'kaynak': 'planli_emir',
                'uretim_emri_id': emir.id,
                'emir_no': emir.emir_no,
            }
            if siparis:
                entry['siparis_id'] = siparis.id
                entry['siparis_numarasi'] = siparis.siparis_numarasi
            out[detay.stok_item_id].append(entry)

    siparis_emir_mik = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    for emir in emirler_plan:
        sn = _siparis_numarasi_uretim_emri_aciklamadan(emir.aciklama or '')
        if not sn:
            continue
        siparis_emir_mik[sn][emir.recete.urun_id] += Decimal(str(emir.miktar))

    siparisler = Siparis.objects.filter(siparis_durumu='ONAYLANDI').prefetch_related('kalemler')
    urun_ids = set()
    for siparis in siparisler:
        for k in siparis.kalemler.all():
            urun_ids.add(k.stok_item_id)

    recete_by_urun = {}
    for rec in Recete.objects.filter(urun_id__in=urun_ids, aktif=True).prefetch_related('detaylar'):
        recete_by_urun[rec.urun_id] = rec
    urun_rolu_by_id = dict(
        StokItem.objects.filter(id__in=urun_ids).values_list('id', 'urun_rolu')
    )

    for siparis in siparisler:
        snum = siparis.siparis_numarasi
        urun_to_sip = defaultdict(lambda: Decimal('0'))
        for k in siparis.kalemler.all():
            urun_to_sip[k.stok_item_id] += Decimal(str(k.miktar))

        emir_by_urun = siparis_emir_mik.get(snum, {})
        for urun_id, sip_toplam in urun_to_sip.items():
            if urun_rolu_by_id.get(urun_id) != 'NIHAI_URUN':
                continue
            kalan = sip_toplam - emir_by_urun.get(urun_id, Decimal('0'))
            if kalan <= 0:
                continue
            recete = recete_by_urun.get(urun_id)
            if not recete:
                continue
            for detay in recete.detaylar.all():
                if detay.stok_item_id == urun_id:
                    continue
                need = Decimal(str(detay.miktar)) * kalan
                out[detay.stok_item_id].append({
                    'siparis_id': siparis.id,
                    'siparis_numarasi': siparis.siparis_numarasi,
                    'miktar': need,
                    'kaynak': 'recete_ihtiyac',
                })

    return dict(out)


def _birlestir_stok_linkleri(linkler, id_key):
    """Aynı hedef kaydı birleştir (miktarları topla)."""
    birlesik = {}
    for link in linkler:
        hedef_id = link.get(id_key)
        if not hedef_id:
            continue
        if hedef_id not in birlesik:
            birlesik[hedef_id] = dict(link)
            birlesik[hedef_id]['miktar'] = Decimal('0')
        birlesik[hedef_id]['miktar'] += Decimal(str(link['miktar']))
    return list(birlesik.values())


def _birlestir_rezerve_linkleri(linkler):
    """Rezerve kaynaklarını sipariş veya üretim emrine göre birleştir."""
    birlesik = {}
    for link in linkler:
        if link.get('siparis_id'):
            key = ('siparis', link['siparis_id'])
        elif link.get('uretim_emri_id'):
            key = ('emir', link['uretim_emri_id'])
        else:
            continue
        if key not in birlesik:
            birlesik[key] = dict(link)
            birlesik[key]['miktar'] = Decimal('0')
        birlesik[key]['miktar'] += Decimal(str(link['miktar']))
    return sorted(
        birlesik.values(),
        key=lambda x: (x.get('siparis_numarasi') or x.get('emir_no') or ''),
    )


@login_required
def dashboard(request):
    from datetime import datetime, timedelta
    import json
    from django.core.serializers.json import DjangoJSONEncoder
    from django.utils import timezone
    
    toplam_urun_sayisi = StokItem.objects.count()
    # Dashboard tabloları: ilk gösterim 10 satır; genişletmede en fazla bu kadar kayıt
    DASHBOARD_TABLO_ILK = 10
    DASHBOARD_TABLO_MAX = 500

    # Sadece stok takibi yapılan ürünler için kritik stok uyarısı
    kritik_stok_sayisi = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__lte=F('minimum_stok')
    ).count()
    stoksuz_urun_sayisi = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar=0
    ).count()
    
    toplam_stok_agg = StokItem.objects.aggregate(
        total=Sum(
            ExpressionWrapper(
                F("mevcut_miktar") * Coalesce(F("alis_fiyati"), Value(Decimal("0"))),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )
        )
    )
    toplam_stok_degeri = toplam_stok_agg["total"] or Decimal("0")
    
    kritik_stok_qs = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__lte=F('minimum_stok')
    )
    kritik_stoklar_toplam = kritik_stok_qs.count()
    kritik_stoklar = list(
        kritik_stok_qs.order_by('mevcut_miktar')[:DASHBOARD_TABLO_MAX]
    )
    son_hareketler = list(
        StokHareketi.objects.select_related('stok_item').order_by('-tarih')[:DASHBOARD_TABLO_MAX]
    )
    
    # Kategori bazında stok sayıları
    kategori_stoklari = StokItem.objects.values('kategori__ad').annotate(
        urun_sayisi=Count('id'),
        toplam_miktar=Sum('mevcut_miktar')
    )
    kategori_stoklari_list = list(kategori_stoklari)

    kategori_deger_qs = StokItem.objects.values("kategori__ad").annotate(
        deger=Sum(
            ExpressionWrapper(
                F("mevcut_miktar") * Coalesce(F("alis_fiyati"), Value(Decimal("0"))),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )
        )
    )
    kategori_degerleri = [
        {
            "kategori": (row["kategori__ad"] or "Kategori Yok"),
            "deger": round(float(row["deger"] or 0), 2),
        }
        for row in kategori_deger_qs
    ]
    
    # Son 30 günlük hareket grafiği için veri
    son_30_gun = timezone.now() - timedelta(days=30)
    gunluk_hareketler = (
        StokHareketi.objects.filter(tarih__gte=son_30_gun)
        .annotate(gun=TruncDate("tarih"))
        .values("gun")
        .annotate(
            giris=Sum("miktar", filter=Q(hareket_tipi__in=["GIRIS", "URETIM_GIRIS", "URETIM_IADE"])),
            cikis=Sum("miktar", filter=Q(hareket_tipi__in=["CIKIS", "URETIM_CIKIS"])),
        )
        .order_by("gun")
    )
    
    # Stok durumu dağılımı - sadece stok takibi yapılan ürünler
    normal_stok = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__gt=F('minimum_stok')
    ).exclude(
        mevcut_miktar=0
    ).count()
    
    # Kritik stok uyarıları - sadece stok takibi yapılan ürünler
    kritik_stok_listesi = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__lte=F('minimum_stok')
    ).order_by('mevcut_miktar')[:10]  # En kritik 10 ürün
    
    # Yaklaşan sigorta poliçesi uyarıları (1 hafta veya daha az süre kalan)
    bugun = timezone.now().date()
    bir_hafta_sonra = bugun + timedelta(days=7)
    
    yaklasan_sigortalar = Sigorta.objects.filter(
        arsivlendi=False,
        police_bitis_tarihi__gte=bugun,
        police_bitis_tarihi__lte=bir_hafta_sonra
    ).order_by('police_bitis_tarihi')
    
    # Süresi dolmuş ama arşivlenmemiş poliçeler
    suresi_dolan_sigortalar = Sigorta.objects.filter(
        arsivlendi=False,
        police_bitis_tarihi__lt=bugun
    ).order_by('police_bitis_tarihi')
    
    # Araç belgeleri için hatırlatmalar (7 gün öncesinden)
    try:
        from .models import Arac, AracBelgesi, AracBelgeTuru
        uyari_tarihi = bugun + timedelta(days=7)
        
        # 7 gün içinde süresi dolacak araç belgeleri
        yaklasan_arac_belgeler = AracBelgesi.objects.filter(
            arac__aktif=True,
            arsivlendi=False,
            gecerlilik_bitis__isnull=False,
            gecerlilik_bitis__gte=bugun,
            gecerlilik_bitis__lte=uyari_tarihi
        ).exclude(
            belge_turu__in=AracBelgeTuru.objects.filter(
                bitis_tarihi_gerekmez=True
            ).values_list("kod", flat=True)
        ).select_related('arac').order_by('gecerlilik_bitis')
        
        # Süresi dolmuş araç belgeleri
        suresi_dolan_arac_belgeler = AracBelgesi.objects.filter(
            arac__aktif=True,
            arsivlendi=False,
            gecerlilik_bitis__isnull=False,
            gecerlilik_bitis__lt=bugun
        ).exclude(
            belge_turu__in=AracBelgeTuru.objects.filter(
                bitis_tarihi_gerekmez=True
            ).values_list("kod", flat=True)
        ).select_related('arac').order_by('gecerlilik_bitis')
    except ImportError:
        yaklasan_arac_belgeler = []
        suresi_dolan_arac_belgeler = []

    # Personel belgeleri için hatırlatmalar (belge bazlı gün ayarı)
    personel_belge_adaylari = PersonelBelgesi.objects.filter(
        yenileme_gerekli=True,
        yenileme_tarihi__isnull=False,
        personel__aktif=True,
        arsivlendi=False,
    ).select_related("personel").order_by("yenileme_tarihi")

    yaklasan_personel_belgeleri = []
    suresi_dolan_personel_belgeleri = []

    for belge in personel_belge_adaylari:
        if belge.yenileme_tarihi < bugun:
            suresi_dolan_personel_belgeleri.append(belge)
            continue

        hatirlatma_gunu = belge.hatirlatma_gun_once or 0
        if hatirlatma_gunu < 0:
            hatirlatma_gunu = 0
        uyari_baslangic = belge.yenileme_tarihi - timedelta(days=hatirlatma_gunu)
        if uyari_baslangic <= bugun <= belge.yenileme_tarihi:
            yaklasan_personel_belgeleri.append(belge)
    
    # Aylık ödemeler: yaklaşanlar (kayıt bazlı hatırlatma günü)
    try:
        from .models import AylikOdeme

        yaklasan_adaylar = AylikOdeme.objects.filter(
            aktif=True,
            odeme_durumu='BEKLEMEDE',
            odeme_tarihi__gte=bugun,
        ).order_by('odeme_tarihi')
        yaklasan_odemeler = [o for o in yaklasan_adaylar if o.hatirlatma_gecerli_mi()]

        # Gecikmiş ödemeler
        gecikmis_odemeler = AylikOdeme.objects.filter(
            aktif=True,
            odeme_durumu='BEKLEMEDE',
            odeme_tarihi__lt=bugun
        ).order_by('odeme_tarihi')
    except ImportError:
        yaklasan_odemeler = []
        gecikmis_odemeler = []
    
    # Satın alma — teslimat bekleyen; termin bugün / yarın (yeşil) ve geçmiş (kırmızı)
    from django.db.models import Exists, OuterRef

    teslim_bekleyen_kalem_subq = SatinalmaKalemi.objects.filter(
        satinalma=OuterRef("pk"),
        teslim_alinan_miktar__lt=F("miktar"),
    )
    satinalma_teslim_bekleyen_terminli = Satinalma.objects.filter(
        Exists(teslim_bekleyen_kalem_subq),
        arsivlendi=False,
        tamamlanma_tarihi__isnull=False,
    ).select_related("tedarikci")

    yarin = bugun + timedelta(days=1)
    satinalma_termin_yakin_qs = satinalma_teslim_bekleyen_terminli.filter(
        tamamlanma_tarihi__gte=bugun,
        tamamlanma_tarihi__lte=yarin,
    ).order_by("tamamlanma_tarihi", "satinalma_numarasi")
    satinalma_termin_gecmis_qs = satinalma_teslim_bekleyen_terminli.filter(
        tamamlanma_tarihi__lt=bugun,
    ).order_by("tamamlanma_tarihi", "satinalma_numarasi")

    satinalma_termin_yakin_sayisi = satinalma_termin_yakin_qs.count()
    satinalma_termin_gecmis_sayisi = satinalma_termin_gecmis_qs.count()
    satinalma_termin_yakin_ozet = list(satinalma_termin_yakin_qs[:10])
    satinalma_termin_gecmis_ozet = list(satinalma_termin_gecmis_qs[:10])

    # Talep yönetimi — dashboard mini özet
    talep_kapali = ("TAMAMLANDI", "REDDEDILDI", "IPTAL")
    talep_aktif_filt = Q(arsivlendi=False) & ~Q(durum__in=talep_kapali)
    talep_onay_bekleyen_sayisi = Talep.objects.filter(
        talep_aktif_filt, durum__in=("YENI", "INCELEMEDE")
    ).count()
    talep_onay_bekleyen_ozet = list(
        Talep.objects.filter(talep_aktif_filt, durum__in=("YENI", "INCELEMEDE"))
        .select_related("talep_eden")
        .order_by("-talep_tarihi")[:5]
    )
    talep_termin_gun = 7
    talep_termin_son = bugun + timedelta(days=talep_termin_gun)
    talep_termin_filt = talep_aktif_filt & Q(istenen_termin__isnull=False) & Q(
        istenen_termin__lte=talep_termin_son
    )
    talep_termin_dikkat_sayisi = Talep.objects.filter(talep_termin_filt).count()
    talep_termin_dikkat_ozet = list(
        Talep.objects.filter(talep_termin_filt)
        .select_related("talep_eden")
        .order_by("istenen_termin")[:5]
    )

    # TEKORA: aktif/pasif ayarı + mail kaynağından onay bekleyen kayıtlar
    genel_ayarlar = GenelAyarlar.get_ayarlar()
    tekora_aktif = bool(genel_ayarlar.tekora_aktif)
    tekora_mail_qs = ApprovalRequest.objects.filter(
        source=ApprovalRequest.SOURCE_EMAIL,
        status=ApprovalRequest.STATUS_PENDING,
    ).order_by("-created_at")
    tekora_onay_bekleyen_sayisi = tekora_mail_qs.count() if tekora_aktif else 0
    tekora_onay_bekleyen_ozet = list(tekora_mail_qs[:5]) if tekora_aktif else []

    # Günün tarihi
    bugun_tarih = bugun.strftime('%d.%m.%Y')
    
    usd_kur, eur_kur = _dashboard_tcmb_kurlar()
    
    context = {
        'toplam_urun_sayisi': toplam_urun_sayisi,
        'kritik_stok_sayisi': kritik_stok_sayisi,
        'stoksuz_urun_sayisi': stoksuz_urun_sayisi,
        'normal_stok_sayisi': normal_stok,
        'toplam_stok_degeri': round(toplam_stok_degeri, 2),
        'kritik_stoklar': kritik_stoklar,
        'kritik_stoklar_toplam': kritik_stoklar_toplam,
        'dashboard_tablo_ilk': DASHBOARD_TABLO_ILK,
        'dashboard_tablo_max': DASHBOARD_TABLO_MAX,
        'kritik_stok_listesi': kritik_stok_listesi,
        'son_hareketler': son_hareketler,
        'kategori_stoklari': kategori_stoklari_list,
        'kategori_stoklari_json': json.dumps(kategori_stoklari_list, cls=DjangoJSONEncoder),
        'kategori_degerleri_json': json.dumps(kategori_degerleri, cls=DjangoJSONEncoder),
        'gunluk_hareketler_json': json.dumps(list(gunluk_hareketler), cls=DjangoJSONEncoder),
        'yaklasan_sigortalar': yaklasan_sigortalar,
        'suresi_dolan_sigortalar': suresi_dolan_sigortalar,
        'yaklasan_arac_belgeler': yaklasan_arac_belgeler,
        'suresi_dolan_arac_belgeler': suresi_dolan_arac_belgeler,
        'yaklasan_personel_belgeleri': yaklasan_personel_belgeleri,
        'suresi_dolan_personel_belgeleri': suresi_dolan_personel_belgeleri,
        'yaklasan_odemeler': yaklasan_odemeler,
        'gecikmis_odemeler': gecikmis_odemeler,
        'bugun_tarih': bugun_tarih,
        'dashboard_bugun': bugun,
        'dashboard_yarin': yarin,
        'talep_onay_bekleyen_sayisi': talep_onay_bekleyen_sayisi,
        'talep_onay_bekleyen_ozet': talep_onay_bekleyen_ozet,
        'talep_termin_dikkat_sayisi': talep_termin_dikkat_sayisi,
        'talep_termin_dikkat_ozet': talep_termin_dikkat_ozet,
        'talep_termin_gun': talep_termin_gun,
        'usd_kur': usd_kur,
        'eur_kur': eur_kur,
        'tekora_onay_bekleyen_sayisi': tekora_onay_bekleyen_sayisi,
        'tekora_onay_bekleyen_ozet': tekora_onay_bekleyen_ozet,
        'tekora_aktif': tekora_aktif,
        'satinalma_termin_yakin_sayisi': satinalma_termin_yakin_sayisi,
        'satinalma_termin_gecmis_sayisi': satinalma_termin_gecmis_sayisi,
        'satinalma_termin_yakin_ozet': satinalma_termin_yakin_ozet,
        'satinalma_termin_gecmis_ozet': satinalma_termin_gecmis_ozet,
    }
    
    return render(request, 'stokapp/dashboard.html', context)


@login_required
@require_POST
def tekora_aktiflik_toggle(request):
    ayarlar = GenelAyarlar.get_ayarlar()
    if not bool(ayarlar.tekora_aktif):
        return JsonResponse(
            {
                "success": False,
                "tekora_aktif": False,
                "message": "TEKORA şimdilik aktifleştirilemiyor.",
            },
            status=403,
        )
    ayarlar.tekora_aktif = False
    ayarlar.save(update_fields=["tekora_aktif", "updated_at"])
    return JsonResponse(
        {
            "success": True,
            "tekora_aktif": False,
            "message": "TEKORA pasif: mail takibi durduruldu.",
        }
    )

@login_required
def kritik_stok_raporu(request):
    kritik_stoklar = _kritik_stok_raporu_queryset()
    return render(request, 'stokapp/kritik_stok_raporu.html', {'kritik_stoklar': kritik_stoklar})


def _kritik_stok_raporu_queryset():
    from django.db.models import F, ExpressionWrapper, DecimalField

    return StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__lte=F('minimum_stok')
    ).annotate(
        eksik_miktar=ExpressionWrapper(
            F('minimum_stok') - F('mevcut_miktar'),
            output_field=DecimalField(max_digits=10, decimal_places=3)
        )
    ).order_by('mevcut_miktar')

@login_required
def stok_hareket_raporu(request):
    hareketler = _stok_hareket_raporu_queryset()
    return render(request, 'stokapp/stok_hareket_raporu.html', {'hareketler': hareketler})


def _stok_hareket_raporu_queryset():
    return StokHareketi.objects.select_related('stok_item').order_by('-tarih')


def _stok_hareket_raporu_satirlari(hareketler):
    from django.utils import timezone

    satirlar = []
    for hareket in hareketler:
        satirlar.append({
            'Tarih': timezone.localtime(hareket.tarih).strftime('%d.%m.%Y %H:%M'),
            'Stok Kodu': hareket.stok_item.stok_kodu,
            'Ürün Adı': hareket.stok_item.ad,
            'Hareket Tipi': hareket.get_hareket_tipi_display(),
            'Miktar': float(hareket.miktar),
            'Birim': hareket.birim,
            'Önceki Stok': float(hareket.onceki_stok),
            'Sonraki Stok': float(hareket.sonraki_stok),
            'Referans No': hareket.referans_no or '',
            'Kullanıcı': hareket.user or '',
            'Açıklama': hareket.aciklama or '',
        })
    return satirlar


@login_required
@never_cache
def stok_hareket_raporu_excel(request):
    """Stok hareket raporu — Excel indir."""
    try:
        hareketler = _stok_hareket_raporu_queryset()
        satirlar = _stok_hareket_raporu_satirlari(hareketler)
        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=[
                'Tarih', 'Stok Kodu', 'Ürün Adı', 'Hareket Tipi', 'Miktar', 'Birim',
                'Önceki Stok', 'Sonraki Stok', 'Referans No', 'Kullanıcı', 'Açıklama',
            ])

        from django.utils import timezone
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="stok_hareket_raporu_{ts}.xlsx"'

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
                    except Exception:
                        pass
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
        return response
    except Exception as e:
        messages.error(request, f'Excel oluşturulamadı: {str(e)}')
        return redirect('stokapp:stok_hareket_raporu')


@login_required
@never_cache
def stok_hareket_raporu_pdf(request):
    """Stok hareket raporu — PDF indir."""
    from django.template.loader import get_template
    from django.utils import timezone

    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:stok_hareket_raporu')

    hareketler = _stok_hareket_raporu_queryset()
    olusturma_tarihi = timezone.localtime(timezone.now())
    template = get_template('stokapp/stok_hareket_raporu_pdf.html')
    html = template.render({
        'hareketler': hareketler,
        'olusturma_tarihi': olusturma_tarihi,
        'kayit_sayisi': hareketler.count(),
    })

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
        return redirect('stokapp:stok_hareket_raporu')

    filename = f'stok_hareket_raporu_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _stok_queryset_annotate_uretim_miktar(queryset):
    """BASLADI durumundaki üretim emirlerinde, ürün bazında üretim miktarı toplamı."""
    from django.db.models import Sum, OuterRef, Subquery, DecimalField, Value
    from django.db.models.functions import Coalesce

    dec3 = DecimalField(max_digits=14, decimal_places=3)
    subq = (
        UretimEmri.objects.filter(
            recete__urun_id=OuterRef('pk'),
            durum='BASLADI',
        )
        .order_by()
        .values('recete__urun_id')
        .annotate(_t=Sum('miktar'))
        .values('_t')[:1]
    )
    return queryset.annotate(
        uretim_miktar_goster=Coalesce(
            Subquery(subq, output_field=dec3),
            Value(0, output_field=dec3),
            output_field=dec3,
        )
    )


def _stok_listesi_filtered_data(request):
    stok_tipi = request.GET.get('tip', 'TUMU')
    sort_field = request.GET.get('sort', 'stok_kodu')
    sort_dir = request.GET.get('dir', 'asc')
    hide_zero_mevcut = request.GET.get('hide_zero_mevcut') in ['1', 'true', 'on']
    hide_zero_sipariste = request.GET.get('hide_zero_sipariste') in ['1', 'true', 'on']
    hide_zero_rezerve = request.GET.get('hide_zero_rezerve') in ['1', 'true', 'on']
    hide_all_zero_values = request.GET.get('hide_all_zero_values') in ['1', 'true', 'on']
    eksi_stok = request.GET.get('eksi_stok') in ['1', 'true', 'on']

    stok_items = _stok_queryset_annotate_uretim_miktar(
        StokItem.objects.all().select_related('kategori')
    ).order_by('stok_kodu')

    sortable_db_fields = {
        'stok_kodu': 'stok_kodu',
        'ad': 'ad',
        'kategori': 'kategori__ad',
        'mevcut': 'mevcut_miktar',
        'uretim': 'uretim_miktar_goster',
        'min': 'minimum_stok',
        'alis': 'alis_fiyati',
        'tarih': 'created_at',
    }
    if sort_field in sortable_db_fields:
        order_expr = sortable_db_fields[sort_field]
        if sort_dir == 'desc':
            order_expr = f'-{order_expr}'
        stok_items = stok_items.order_by(order_expr)

    rezerve_map = {
        row['stok_item_id']: (row['toplam'] or Decimal('0'))
        for row in SiparisKalemi.objects.filter(
            siparis__siparis_durumu='ONAYLANDI'
        ).values('stok_item_id').annotate(toplam=Sum('miktar'))
    }
    bom_rezerve_map = _bom_rezerve_by_stok_item()
    satinalma_link_map = _stok_liste_satinalma_linkleri()
    uretim_link_map = _stok_liste_uretim_linkleri()
    rezerve_link_map = _stok_liste_rezerve_linkleri()

    tum_stok_items_with_data = []
    for item in stok_items:
        satinalma_linkleri = _birlestir_stok_linkleri(
            satinalma_link_map.get(item.id, []), 'id'
        )
        siparis_miktari = sum(
            (link['miktar'] for link in satinalma_linkleri), Decimal('0')
        )

        rezerve_miktari = rezerve_map.get(item.id, Decimal('0')) + bom_rezerve_map.get(
            item.id, Decimal('0')
        )
        rezerve_linkleri = _birlestir_rezerve_linkleri(
            rezerve_link_map.get(item.id, [])
        )
        uretim_linkleri = uretim_link_map.get(item.id, [])
        uretim_goster = getattr(item, 'uretim_miktar_goster', None)
        if uretim_goster is None:
            uretim_goster = Decimal('0')
        else:
            uretim_goster = Decimal(str(uretim_goster))

        mevcut_d = item.mevcut_miktar if item.mevcut_miktar is not None else Decimal('0')
        if eksi_stok and not (mevcut_d < Decimal('0')):
            continue
        if hide_zero_mevcut and (item.mevcut_miktar or Decimal('0')) == Decimal('0'):
            continue
        if hide_zero_sipariste and siparis_miktari == Decimal('0'):
            continue
        if hide_zero_rezerve and rezerve_miktari == Decimal('0'):
            continue
        if hide_all_zero_values:
            if (
                (item.mevcut_miktar or Decimal('0')) == Decimal('0')
                and siparis_miktari == Decimal('0')
                and rezerve_miktari == Decimal('0')
                and uretim_goster == Decimal('0')
            ):
                continue

        tum_stok_items_with_data.append({
            'item': item,
            'siparis_miktari': siparis_miktari,
            'rezerve_miktari': rezerve_miktari,
            'uretim_miktari': uretim_goster,
            'satinalma_linkleri': satinalma_linkleri,
            'rezerve_linkleri': rezerve_linkleri,
            'uretim_linkleri': uretim_linkleri,
        })

    tab_counts = {
        'TUMU': len(tum_stok_items_with_data),
        'URUN': 0,
        'YARI_MAMUL': 0,
        'HAM_MADDE': 0,
    }
    for row in tum_stok_items_with_data:
        tip = (getattr(row['item'].kategori, 'stok_tipi', None) or '').upper()
        if tip in tab_counts:
            tab_counts[tip] += 1

    if stok_tipi != 'TUMU':
        stok_items_with_data = [
            row for row in tum_stok_items_with_data
            if (getattr(row['item'].kategori, 'stok_tipi', None) or '').upper() == stok_tipi
        ]
    else:
        stok_items_with_data = tum_stok_items_with_data

    if sort_field in ['sipariste', 'rezerve']:
        reverse = sort_dir == 'desc'
        if sort_field == 'sipariste':
            stok_items_with_data.sort(key=lambda x: x['siparis_miktari'], reverse=reverse)
        else:
            stok_items_with_data.sort(key=lambda x: x['rezerve_miktari'], reverse=reverse)

    return {
        'stok_items_data': stok_items_with_data,
        'aktif_tip': stok_tipi,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'hide_zero_mevcut': hide_zero_mevcut,
        'hide_zero_sipariste': hide_zero_sipariste,
        'hide_zero_rezerve': hide_zero_rezerve,
        'hide_all_zero_values': hide_all_zero_values,
        'eksi_stok': eksi_stok,
        'tab_counts': tab_counts,
    }


@login_required
def stok_listesi(request):
    return render(request, 'stokapp/stok_listesi.html', _stok_listesi_filtered_data(request))


@login_required
@never_cache
def stok_listesi_export_excel(request):
    try:
        data = _stok_listesi_filtered_data(request)
        satirlar = []
        for row in data['stok_items_data']:
            item = row['item']
            satirlar.append({
                'Stok Kodu': item.stok_kodu,
                'Ürün Adı': item.ad,
                'Kategori': item.kategori.ad if item.kategori else '',
                'Birim': item.birim,
                'Mevcut Miktar': float(item.mevcut_miktar or 0),
                'Üretimde': float(row['uretim_miktari'] or 0),
                'Siparişte': float(row['siparis_miktari'] or 0),
                'Rezerve': float(row['rezerve_miktari'] or 0),
                'Min. Stok': float(item.minimum_stok or 0),
                'Alış Fiyatı': float(item.alis_fiyati or 0),
                'Para Birimi': item.alis_para_birimi or '',
            })
        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=[
                'Stok Kodu', 'Ürün Adı', 'Kategori', 'Birim', 'Mevcut Miktar', 'Üretimde',
                'Siparişte', 'Rezerve', 'Min. Stok', 'Alış Fiyatı', 'Para Birimi',
            ])

        from django.utils import timezone
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="stok_listesi_{ts}.xlsx"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Stok Listesi', index=False)
            worksheet = writer.sheets['Stok Listesi']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:stok_listesi')


@login_required
@never_cache
def stok_listesi_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:stok_listesi')

    from django.utils import timezone

    data = _stok_listesi_filtered_data(request)
    olusturma_tarihi = timezone.localtime(timezone.now())
    html_rows = []
    for row in data['stok_items_data'][:1000]:
        item = row['item']
        html_rows.append(
            f"""
            <tr>
                <td>{item.stok_kodu}</td>
                <td>{item.ad}</td>
                <td>{item.kategori.ad if item.kategori else '-'}</td>
                <td class="num">{item.mevcut_miktar or 0}</td>
                <td class="num">{row['uretim_miktari'] or 0}</td>
                <td class="num">{row['siparis_miktari'] or 0}</td>
                <td class="num">{row['rezerve_miktari'] or 0}</td>
                <td class="num">{item.minimum_stok or 0}</td>
                <td>{item.birim}</td>
            </tr>
            """
        )

    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Stok Listesi</h1>
      <div class="meta">Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(data['stok_items_data'])}</div>
      <table>
        <thead>
          <tr><th>Stok Kodu</th><th>Ürün</th><th>Kategori</th><th>Mevcut</th><th>Üretimde</th><th>Siparişte</th><th>Rezerve</th><th>Min</th><th>Birim</th></tr>
        </thead>
        <tbody>{''.join(html_rows) if html_rows else '<tr><td colspan="9" class="empty">Kayıt bulunamadı.</td></tr>'}</tbody>
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
        return redirect('stokapp:stok_listesi')

    filename = f'stok_listesi_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@never_cache
def kritik_stok_raporu_excel(request):
    try:
        kritik_stoklar = _kritik_stok_raporu_queryset()
        satirlar = [{
            'Stok Kodu': item.stok_kodu,
            'Ürün Adı': item.ad,
            'Kategori': item.kategori.ad if item.kategori else '',
            'Mevcut Stok': float(item.mevcut_miktar or 0),
            'Minimum Stok': float(item.minimum_stok or 0),
            'Eksik Miktar': float(item.eksik_miktar or 0),
            'Birim': item.birim,
        } for item in kritik_stoklar]
        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=['Stok Kodu', 'Ürün Adı', 'Kategori', 'Mevcut Stok', 'Minimum Stok', 'Eksik Miktar', 'Birim'])

        from django.utils import timezone
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="kritik_stok_raporu_{ts}.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Kritik Stok', index=False)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:kritik_stok_raporu')


@login_required
@never_cache
def kritik_stok_raporu_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:kritik_stok_raporu')

    from django.utils import timezone

    kritik_stoklar = list(_kritik_stok_raporu_queryset()[:1000])
    olusturma_tarihi = timezone.localtime(timezone.now())
    html_rows = []
    for item in kritik_stoklar:
        html_rows.append(
            f"""
            <tr>
                <td>{item.stok_kodu}</td>
                <td>{item.ad}</td>
                <td>{item.kategori.ad if item.kategori else '-'}</td>
                <td class="num">{item.mevcut_miktar or 0}</td>
                <td class="num">{item.minimum_stok or 0}</td>
                <td class="num">{item.eksik_miktar or 0}</td>
                <td>{item.birim}</td>
            </tr>
            """
        )

    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Kritik Stok Raporu</h1>
      <div class="meta">Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(kritik_stoklar)}</div>
      <table>
        <thead><tr><th>Stok Kodu</th><th>Ürün</th><th>Kategori</th><th>Mevcut</th><th>Minimum</th><th>Eksik</th><th>Birim</th></tr></thead>
        <tbody>{''.join(html_rows) if html_rows else '<tr><td colspan="7" class="empty">Kayıt bulunamadı.</td></tr>'}</tbody>
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
        return redirect('stokapp:kritik_stok_raporu')

    filename = f'kritik_stok_raporu_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _next_uretim_emri_no():
    son_emir = UretimEmri.objects.order_by('-id').first()
    if son_emir:
        try:
            num = int((son_emir.emir_no or '').replace('UE-', '')) + 1
        except (ValueError, TypeError):
            num = 1
    else:
        num = 1

    emir_no = f'UE-{num}'
    while UretimEmri.objects.filter(emir_no=emir_no).exists():
        num += 1
        emir_no = f'UE-{num}'
    return emir_no


@login_required
def stok_hizli_uretim_olustur(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Geçersiz istek yöntemi.'}, status=405)

    stok_id = request.POST.get('stok_id')
    miktar_raw = request.POST.get('miktar')
    termin_raw = (request.POST.get('termin_tarihi') or '').strip()
    oncelik = (request.POST.get('oncelik') or '').strip()
    aciklama = (request.POST.get('aciklama') or '').strip()

    if not stok_id:
        return JsonResponse({'success': False, 'error': 'Ürün seçilmedi.'}, status=400)

    try:
        stok_item = StokItem.objects.get(pk=int(stok_id))
    except (ValueError, TypeError, StokItem.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Ürün bulunamadı.'}, status=404)

    try:
        from decimal import Decimal
        miktar = Decimal(str(miktar_raw or '0'))
    except Exception:
        return JsonResponse({'success': False, 'error': 'Geçerli bir üretim adedi giriniz.'}, status=400)

    if miktar <= 0:
        return JsonResponse({'success': False, 'error': 'Üretim adedi 0\'dan büyük olmalı.'}, status=400)

    recete = Recete.objects.filter(urun=stok_item, aktif=True).first()
    if not recete:
        return JsonResponse({'success': False, 'error': 'Bu ürün için reçete tanımlı değil.'}, status=400)

    operasyonlar = recete.operasyonlar.select_related('operasyon', 'recete_detay').order_by(
        'recete_detay__sira', 'recete_detay_id', 'sira', 'id',
    )
    if not operasyonlar.exists():
        return JsonResponse({'success': False, 'error': 'Bu reçete için operasyon adımı bulunamadı.'}, status=400)

    from datetime import datetime, timedelta
    from django.utils import timezone

    planlanan_baslama = timezone.now()
    if termin_raw:
        try:
            termin_date = datetime.strptime(termin_raw, '%Y-%m-%d').date()
            planlanan_bitis = timezone.make_aware(datetime.combine(termin_date, datetime.max.time()))
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Termin tarihi formatı geçersiz.'}, status=400)
    else:
        planlanan_bitis = planlanan_baslama + timedelta(days=30)

    if planlanan_bitis <= planlanan_baslama:
        planlanan_bitis = planlanan_baslama + timedelta(days=1)

    info_parts = ['Stok için hızlı üretim emri']
    if oncelik:
        info_parts.append(f'Öncelik: {oncelik}')
    if aciklama:
        info_parts.append(aciklama)
    aciklama_text = ' | '.join(info_parts)

    with transaction.atomic():
        uretim_emri = UretimEmri.objects.create(
            emir_no=_next_uretim_emri_no(),
            recete=recete,
            miktar=miktar,
            production_type='STOCK',
            durum='PLANLANDI',
            planlanan_baslama=planlanan_baslama,
            planlanan_bitis=planlanan_bitis,
            aciklama=aciklama_text,
        )

        for idx, operasyon in enumerate(operasyonlar, start=1):
            UretimAsamasi.objects.create(
                uretim_emri=uretim_emri,
                recete_detay=operasyon.recete_detay,
                recete_operasyon=operasyon,
                ad=operasyon.operasyon.ad,
                sira=idx,
                planlanan_sure=operasyon.sure_dakika,
                durum='BEKLIYOR',
            )

    return JsonResponse({
        'success': True,
        'emir_no': uretim_emri.emir_no,
        'message': f'{stok_item.stok_kodu} için hızlı üretim emri oluşturuldu.',
        'detay_url': reverse('stokapp:uretim_emri_detay', args=[uretim_emri.id]),
        'planlama_url': reverse('stokapp:uretim_planlama'),
    })

# EXCEL FONKSİYONLARI
@login_required
def excel_import_page(request):
    return render(request, 'stokapp/excel_import.html')

@login_required
def export_stok_listesi(request):
    try:
        stok_items = _stok_queryset_annotate_uretim_miktar(StokItem.objects.all()).values(
                'stok_kodu',
                'ad',
                'kategori__ad',
                'kategori__stok_tipi',
                'birim',
                'mevcut_miktar',
                'uretim_miktar_goster',
                'minimum_stok',
                'alis_fiyati',
                'alis_para_birimi',
                'barkod',
                'aciklama',
            )

        df = pd.DataFrame(list(stok_items))
        df.columns = [
            'Stok Kodu',
            'Ürün Adı',
            'Kategori',
            'Stok Tipi',
            'Birim',
            'Mevcut Miktar',
            'Üretimde',
            'Min. Stok',
            'Alış Fiyatı',
            'Para Birimi',
            'Barkod',
            'Açıklama',
        ]
        
        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="stok_listesi.xlsx"'
        
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Stok Listesi', index=False)
            
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
    """Geriye dönük uyumluluk — rapor sayfasındaki Excel indirmeye yönlendir."""
    return stok_hareket_raporu_excel(request)

@login_required
def import_stok_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            df = pd.read_excel(excel_file)
            
            required_columns = ['Stok Kodu', 'Ürün Adı', 'Kategori', 'Birim']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                messages.error(request, f'Eksik sütunlar: {", ".join(missing_columns)}')
                return redirect('stokapp:excel_import_page')
            
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                try:
                    kategori, created = Kategori.objects.get_or_create(
                        ad=row['Kategori'],
                        defaults={'stok_tipi': 'HAM_MADDE'}
                    )
                    
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
            
            messages.success(request, f'{success_count} kayıt başarıyla import edildi. {error_count} hata.')
            return redirect('stokapp:stok_listesi')
            
        except Exception as e:
            messages.error(request, f'Import hatası: {str(e)}')
            return redirect('stokapp:excel_import_page')
    
    return redirect('stokapp:excel_import_page')

@login_required
def download_template(request):
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

# BARKOD FONKSİYONLARI
@login_required
def barkod_sorgula(request):
    if request.method == 'GET' and 'barkod' in request.GET:
        barkod = request.GET['barkod']
        try:
            stok_item = StokItem.objects.get(barkod=barkod)
            return JsonResponse({
                'success': True,
                'stok_kodu': stok_item.stok_kodu,
                'ad': stok_item.ad,
                'mevcut_miktar': float(stok_item.mevcut_miktar),
                'birim': stok_item.birim,
                'kategori': stok_item.kategori.ad if stok_item.kategori else ''
            })
        except StokItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Barkod bulunamadı'})
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

@login_required
def barkod_olustur(request, stok_kodu):
    try:
        stok_item = StokItem.objects.get(stok_kodu=stok_kodu)
        if not stok_item.barkod:
            import hashlib
            barkod = hashlib.md5(stok_kodu.encode()).hexdigest()[:10].upper()
            stok_item.barkod = barkod
            stok_item.save()
            return JsonResponse({'success': True, 'barkod': barkod})
        else:
            return JsonResponse({'success': True, 'barkod': stok_item.barkod})
    except StokItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Stok kartı bulunamadı'})

@login_required
def barkod_arayuzu(request):
    return render(request, 'stokapp/barkod_arayuzu.html')

@login_required
def ana_sayfa(request):
    """Ana sayfa - Sistem genel bakış"""
    # İstatistikler
    toplam_stok_item = StokItem.objects.count()
    toplam_uretim_emri = UretimEmri.objects.count()
    toplam_tedarikci = Cari.objects.filter(cari_tipi='TEDARIKCI', aktif=True).count()
    
    # Son eklenenler
    son_stoklar = StokItem.objects.all().order_by('-created_at')[:5]
    son_uretim_emirleri = UretimEmri.objects.all().order_by('-created_at')[:5]
    
    # Kritik stoklar - sadece stok takibi yapılan ürünler
    kritik_stoklar = StokItem.objects.filter(
        stok_takip=True,
        mevcut_miktar__lte=F('minimum_stok')
    )[:5]
    
    context = {
        'toplam_stok_item': toplam_stok_item,
        'toplam_uretim_emri': toplam_uretim_emri,
        'toplam_tedarikci': toplam_tedarikci,
        'son_stoklar': son_stoklar,
        'son_uretim_emirleri': son_uretim_emirleri,
        'kritik_stoklar': kritik_stoklar,
    }
    return render(request, 'stokapp/ana_sayfa.html', context)

# CARİLER MODÜLÜ
@login_required
def cariler_liste(request):
    """Cariler listesi"""
    cariler = Cari.objects.all().order_by('unvan')
    
    # Filtreleme
    cari_tipi = request.GET.get('tip', '')
    if cari_tipi:
        cariler = cariler.filter(cari_tipi=cari_tipi)
    
    context = {
        'cariler': cariler,
        'cari_tipi': cari_tipi,
    }
    return render(request, 'stokapp/cariler_liste.html', context)

@login_required
def cari_ekle(request):
    """Yeni cari ekleme"""
    if request.method == 'POST':
        try:
            # Form verilerini al
            cari_kodu = request.POST.get('cari_kodu')
            unvan = request.POST.get('unvan')
            cari_tipi = request.POST.get('cari_tipi')
            vergi_dairesi = request.POST.get('vergi_dairesi')
            vergi_no = request.POST.get('vergi_no')
            telefon = request.POST.get('telefon')
            email = request.POST.get('email')
            adres = request.POST.get('adres')
            
            # Yeni cari oluştur
            cari = Cari(
                cari_kodu=cari_kodu,
                unvan=unvan,
                cari_tipi=cari_tipi,
                vergi_dairesi=vergi_dairesi,
                vergi_no=vergi_no,
                telefon=telefon,
                email=email,
                adres=adres
            )
            cari.save()
            
            messages.success(request, f'{unvan} carisi başarıyla eklendi.')
            return redirect('stokapp:cariler_liste')
            
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    return render(request, 'stokapp/cari_ekle.html')

@login_required
def cari_duzenle(request, cari_id):
    """Cari düzenleme"""
    try:
        cari = Cari.objects.get(id=cari_id)
        
        if request.method == 'POST':
            cari.unvan = request.POST.get('unvan')
            cari.cari_tipi = request.POST.get('cari_tipi')
            cari.vergi_dairesi = request.POST.get('vergi_dairesi')
            cari.vergi_no = request.POST.get('vergi_no')
            cari.telefon = request.POST.get('telefon')
            cari.email = request.POST.get('email')
            cari.adres = request.POST.get('adres')
            cari.aktif = request.POST.get('aktif') == 'on'
            cari.save()
            
            messages.success(request, f'{cari.unvan} carisi güncellendi.')
            return redirect('stokapp:cariler_liste')
        
        context = {'cari': cari}
        return render(request, 'stokapp/cari_duzenle.html', context)
        
    except Cari.DoesNotExist:
        messages.error(request, 'Cari bulunamadı.')
        return redirect('stokapp:cariler_liste')