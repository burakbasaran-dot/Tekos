from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from collections import defaultdict

from django.db.models import Prefetch, Sum, Q
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.contrib.staticfiles import finders
from email.mime.image import MIMEImage
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.cache import never_cache
import os
import base64
from datetime import timedelta, datetime
from .models import Siparis, SiparisKalemi, SiparisMaliyeti, StokItem, Musteri, Recete, UretimEmri, UretimAsamasi, ReceteDetay, ReceteOperasyon, StokHareketi, SatinalmaKalemi, Satinalma, TeklifTalebi, GenelAyarlar
from .forms import SiparisForm, SiparisKalemiForm, SiparisMaliyetiForm
from .views_uretim import uretim_emri_baslat_execute
from .uretim_emri_service import create_uretim_emri_with_stages
from .bom_planlama import create_alt_uretim_emirleri
from .views import _dashboard_tcmb_kurlar
from decimal import Decimal
import json
from urllib.parse import urlencode
from typing import Optional


SIPARIS_ONAY_MAIL_SESSION_KEY = 'siparis_onay_mail_wizard'


def _siparis_onay_mail_preview_context(request, siparis):
    """Sipariş onay e-postası HTML/text şablonları için bağlam (önizleme; CID başlangıçta boş)."""
    kalemler = SiparisKalemi.objects.filter(siparis=siparis).order_by('id')
    ara_toplam = siparis.toplam
    vergi = ara_toplam * Decimal('0.20')
    toplam = ara_toplam + vergi

    tekos_logo_url = static('stokapp/images/tekos-logo.png')
    tekmar_logo_data_uri = None
    tekmar_logo_path_candidates = [
        os.path.join(settings.BASE_DIR, "assets", "TEKMAR_9001_LOGO-706d99ca-b4cf-4e19-b1b2-417aeff36663.png"),
        "/Users/burakbasaran/.cursor/projects/Users-burakbasaran-uretim-stok/assets/TEKMAR_9001_LOGO-706d99ca-b4cf-4e19-b1b2-417aeff36663.png",
    ]
    tekmar_logo_path = next((p for p in tekmar_logo_path_candidates if p and os.path.exists(p)), None)
    if tekmar_logo_path:
        try:
            with open(tekmar_logo_path, "rb") as logo_file:
                encoded = base64.b64encode(logo_file.read()).decode("ascii")
            tekmar_logo_data_uri = f"data:image/png;base64,{encoded}"
        except Exception:
            tekmar_logo_data_uri = None

    return {
        'siparis': siparis,
        'kalemler': kalemler,
        'ara_toplam': ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
        'tekos_logo_cid': None,
        'tekos_logo_url': tekos_logo_url,
        'tekmar_logo_cid': None,
        'tekmar_logo_data_uri': tekmar_logo_data_uri,
        '_tekmar_logo_path': tekmar_logo_path,
    }


def _siparis_onay_mail_send(request, siparis, to_emails):
    """Müşteri onay teyit mailini gönderir (şablon ve ek yapısı siparis_onayla ile aynı)."""
    if not to_emails:
        raise ValueError('En az bir alıcı gerekli.')

    ctx = _siparis_onay_mail_preview_context(request, siparis)
    tekmar_logo_path = ctx.pop('_tekmar_logo_path', None)

    subject = f"Siparişiniz işleme alınmıştır - {siparis.siparis_numarasi}"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or None
    to_email = list(to_emails)
    auto_cc = GenelAyarlar.get_musteri_mail_cc_adresi()
    cc_email = [auto_cc] if auto_cc and auto_cc.lower() not in {str(e).strip().lower() for e in to_email} else []

    tekos_logo_path = finders.find('stokapp/images/tekos-logo.png')
    img = None
    if tekos_logo_path:
        try:
            with open(tekos_logo_path, 'rb') as img_file:
                img = MIMEImage(img_file.read())
            img.add_header('Content-ID', '<tekos_logo>')
            img.add_header('Content-Disposition', 'inline', filename='tekos-logo.png')
            ctx['tekos_logo_cid'] = 'tekos_logo'
        except Exception:
            img = None

    tekmar_img = None
    if tekmar_logo_path:
        try:
            with open(tekmar_logo_path, "rb") as logo_file:
                tekmar_img = MIMEImage(logo_file.read())
            tekmar_img.add_header('Content-ID', '<tekmar_logo>')
            tekmar_img.add_header('Content-Disposition', 'inline', filename='tekmar-logo.png')
            ctx['tekmar_logo_cid'] = 'tekmar_logo'
        except Exception:
            tekmar_img = None

    email = EmailMultiAlternatives(
        subject,
        render_to_string('stokapp/emails/siparis_onay_email.txt', ctx),
        from_email,
        to_email,
        cc=cc_email,
    )
    email.attach_alternative(render_to_string('stokapp/emails/siparis_onay_email.html', ctx), "text/html")
    if img:
        email.attach(img)
    if tekmar_img:
        email.attach(tekmar_img)
    email.send()


def _siparis_onay_mail_template_vars(request, siparis):
    raw = _siparis_onay_mail_preview_context(request, siparis)
    return {k: v for k, v in raw.items() if not str(k).startswith('_')}


class SiparisUretimBaslatHatasi(Exception):
    """Siparişten iş emri oluşturma + otomatik başlatma sırasında iptal (transaction rollback)."""

    def __init__(self, message):
        self.message = message
        super().__init__(message)


@login_required
def siparis_items_api(request, pk):
    """Sipariş tooltip'i için kalemleri döndürür."""
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    items = []
    for kalem in SiparisKalemi.objects.filter(siparis=siparis).select_related("stok_item"):
        urun_adi = kalem.stok_item.ad if kalem.stok_item else "-"
        aciklama = (kalem.aciklama or "").strip()
        if aciklama:
            urun_adi = aciklama
        items.append({
            "code": kalem.stok_item.stok_kodu if kalem.stok_item else "-",
            "name": urun_adi,
            "quantity": str(kalem.miktar),
            "unit": kalem.stok_item.birim if kalem.stok_item else "",
        })
    return JsonResponse({"success": True, "items": items})


def _siparis_kalem_toplam_map(siparis):
    toplam_map = {}
    for kalem in SiparisKalemi.objects.filter(siparis=siparis).select_related("stok_item"):
        toplam_map[kalem.stok_item_id] = toplam_map.get(kalem.stok_item_id, Decimal("0")) + Decimal(str(kalem.miktar))
    return toplam_map


def _siparis_stoktan_dusulen_map(siparis):
    return {
        row["stok_item_id"]: (row["toplam"] or Decimal("0"))
        for row in StokHareketi.objects.filter(
            referans_no=siparis.siparis_numarasi,
            hareket_tipi="SATIS_STOK",
        ).values("stok_item_id").annotate(toplam=Sum("miktar"))
    }


def _basladi_uretim_miktar_map(urun_ids):
    if not urun_ids:
        return {}
    return {
        row["recete__urun_id"]: Decimal(str(row["toplam"] or 0))
        for row in UretimEmri.objects.filter(
            durum="BASLADI",
            recete__urun_id__in=urun_ids,
        ).values("recete__urun_id").annotate(toplam=Sum("miktar"))
    }


def _basladi_uretim_detay_map(urun_ids):
    if not urun_ids:
        return {}
    out = defaultdict(list)
    for emir in (
        UretimEmri.objects.filter(
            durum="BASLADI",
            recete__urun_id__in=urun_ids,
        )
        .select_related("recete__urun")
        .order_by("emir_no", "id")
    ):
        out[emir.recete.urun_id].append(
            {
                "id": emir.id,
                "emir_no": emir.emir_no,
                "miktar": str(Decimal(str(emir.miktar))),
            }
        )
    return dict(out)


def _siparis_kalan_teslim_miktari_map(siparis):
    siparis_toplam_map = _siparis_kalem_toplam_map(siparis)
    stoktan_dusulen_map = _siparis_stoktan_dusulen_map(siparis)
    kalan = {}
    for stok_item_id, siparis_miktari in siparis_toplam_map.items():
        daha_once_stoktan = stoktan_dusulen_map.get(stok_item_id, Decimal("0"))
        kalan_teslim = siparis_miktari - daha_once_stoktan
        if kalan_teslim > 0:
            kalan[stok_item_id] = kalan_teslim
    return kalan


def _siparis_stoktan_teslime_hazir_mi(siparis):
    kalan_map = _siparis_kalan_teslim_miktari_map(siparis)
    if not kalan_map:
        return True
    stok_map = {
        row["id"]: Decimal(str(row["mevcut_miktar"] or 0))
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "mevcut_miktar")
    }
    for stok_item_id, gerekli in kalan_map.items():
        if stok_map.get(stok_item_id, Decimal("0")) < gerekli:
            return False
    return True


def _siparis_teslimat_bekleyen_qs():
    """Üretimi tamamlanmış / stoktan sevk, henüz teslim edilmemiş siparişler."""
    return (
        Siparis.objects.exclude(siparis_durumu__in=["TESLIM_EDILDI", "RED"])
        .filter(uretim_durumu__in=["TAMAMLANDI", "STOKTAN_SEVK"])
    )


def _siparis_tedarik_aksiyon_bilgisi(siparis):
    """
    Onaylı siparişte kalan teslim miktarına göre Al-Sat kalemler için
    satın alma / RFQ prefill querystring üretir.
    """
    kalan_map = _siparis_kalan_teslim_miktari_map(siparis)
    if not kalan_map:
        return {
            "has_al_sat_items": False,
            "has_uretim_items": False,
            "satinalma_query": "",
            "rfq_query": "",
        }

    stok_rows = {
        row["id"]: row["urun_rolu"] or "AL_SAT"
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "urun_rolu")
    }

    al_sat_items = []
    has_uretim_items = False
    for stok_item_id, miktar in kalan_map.items():
        rol = (stok_rows.get(stok_item_id) or "AL_SAT").upper()
        if rol == "AL_SAT":
            al_sat_items.append((stok_item_id, miktar))
        else:
            has_uretim_items = True

    if not al_sat_items:
        return {
            "has_al_sat_items": False,
            "has_uretim_items": has_uretim_items,
            "satinalma_query": "",
            "rfq_query": "",
        }

    params = {"planlama": "1", "source_siparis": str(siparis.pk)}
    for idx, (stok_item_id, miktar) in enumerate(al_sat_items):
        params[f"malzeme_{idx}"] = str(stok_item_id)
        params[f"miktar_{idx}"] = str(Decimal(str(miktar)))

    query = urlencode(params)
    return {
        "has_al_sat_items": True,
        "has_uretim_items": has_uretim_items,
        "satinalma_query": query,
        "rfq_query": query,
    }


def _siparis_al_sat_kalan_map(siparis):
    """Onaylı siparişte kalan teslim miktarından yalnızca AL_SAT kalemleri döndür."""
    kalan_map = _siparis_kalan_teslim_miktari_map(siparis)
    if not kalan_map:
        return {}
    stok_rows = {
        row["id"]: (row["urun_rolu"] or "AL_SAT").upper()
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "urun_rolu")
    }
    out = {}
    for stok_item_id, miktar in kalan_map.items():
        if stok_rows.get(stok_item_id) == "AL_SAT" and Decimal(str(miktar)) > 0:
            out[stok_item_id] = Decimal(str(miktar))
    return out


def _bagli_satinalma_otomatik_eslestir(siparis):
    """
    Eski kayıtlarda kaynak_siparis boş kalmış olabilir.
    Siparişin AL_SAT kalan haritası ile birebir eşleşen tek açık satınalmayı bulursa bağlar.
    """
    hedef_map = _siparis_al_sat_kalan_map(siparis)
    if not hedef_map:
        return None

    stok_ids = list(hedef_map.keys())
    adaylar = (
        Satinalma.objects.filter(
            kaynak_siparis__isnull=True,
            teslim_durumu__in=["BEKLIYOR", "KISMI_TESLIM"],
            kalemler__stok_item_id__in=stok_ids,
        )
        .distinct()
        .order_by("-created_at", "-id")
    )

    eslesenler = []
    for sat in adaylar:
        sat_map = {
            row["stok_item_id"]: Decimal(str(row["toplam"] or 0))
            for row in (
                SatinalmaKalemi.objects.filter(satinalma=sat)
                .values("stok_item_id")
                .annotate(toplam=Sum("miktar"))
            )
        }
        if sat_map == hedef_map:
            eslesenler.append(sat)

    if len(eslesenler) != 1:
        return None

    eslesen = eslesenler[0]
    eslesen.kaynak_siparis = siparis
    eslesen.save(update_fields=["kaynak_siparis"])
    return eslesen


def _siparis_referans_karsilanan_stok_batch(siparis_numaralari):
    """Sipariş referansına göre stok kalemi bazında SATIS_STOK + teslim CIKIS toplamı."""
    if not siparis_numaralari:
        return {}
    rows = (
        StokHareketi.objects.filter(
            referans_no__in=siparis_numaralari,
            hareket_tipi__in=["SATIS_STOK", "CIKIS"],
            stok_item__isnull=False,
        )
        .values("referans_no", "stok_item_id")
        .annotate(toplam=Sum("miktar"))
    )
    out = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    for row in rows:
        out[row["referans_no"]][row["stok_item_id"]] += Decimal(str(row["toplam"] or 0))
    return out


def _build_acik_siparis_kalem_rows():
    """
    Teslim edilmemiş / reddedilmemiş siparişlerde, satır bazında kalan miktar.
    Karşılanan = siparişe bağlı stok hareketleri (FIFO) + mevcut stokla karşılanabilir miktar.
    Stoksuz (serbest) satırlar sipariş açıkken tamamı açık kabul edilir.
    """
    qs = (
        Siparis.objects.exclude(siparis_durumu__in=["TESLIM_EDILDI", "RED"])
        .select_related("musteri")
        .prefetch_related(
            Prefetch(
                "kalemler",
                SiparisKalemi.objects.select_related("stok_item").order_by("id"),
            )
        )
        .order_by("-olusturulma_tarihi", "-id")
    )
    siparis_list = list(qs)
    batch = _siparis_referans_karsilanan_stok_batch([s.siparis_numarasi for s in siparis_list])
    stok_mevcut_pool = {}
    rows = []
    for siparis in siparis_list:
        ref_map = {
            k: Decimal(str(v)) for k, v in batch.get(siparis.siparis_numarasi, {}).items()
        }
        for kalem in siparis.kalemler.all():
            talep = Decimal(str(kalem.miktar))
            if not kalem.stok_item_id:
                birim = "ADET"
                karsilanan = Decimal("0")
                bekleyen = talep
            else:
                birim = (kalem.stok_item.birim or "ADET") if kalem.stok_item else "ADET"
                sid = kalem.stok_item_id
                hareket_havuzu = ref_map.get(sid, Decimal("0"))
                karsilanan_hareket = min(talep, hareket_havuzu)
                ref_map[sid] = hareket_havuzu - karsilanan_hareket

                if sid not in stok_mevcut_pool:
                    stok_mevcut_pool[sid] = Decimal(str(kalem.stok_item.mevcut_miktar or 0))
                stok_kalan = stok_mevcut_pool[sid]
                kalan_ihtiyac = talep - karsilanan_hareket
                stoktan_karsilanabilir = (
                    min(kalan_ihtiyac, stok_kalan) if kalan_ihtiyac > 0 else Decimal("0")
                )
                stok_mevcut_pool[sid] = stok_kalan - stoktan_karsilanabilir

                karsilanan = karsilanan_hareket + stoktan_karsilanabilir
                bekleyen = talep - karsilanan
            if bekleyen <= 0:
                continue
            rows.append(
                {
                    "kalem": kalem,
                    "siparis": siparis,
                    "talep": talep,
                    "karsilanan": karsilanan,
                    "bekleyen": bekleyen,
                    "birim": birim,
                }
            )
    return rows


def _build_teslimat_bekleyen_kalem_rows():
    """
    Üretimi tamamlanmış / stoktan sevk, henüz teslim edilmemiş siparişlerde
    satır bazında kalan teslim miktarı.
    """
    qs = (
        _siparis_teslimat_bekleyen_qs()
        .select_related("musteri")
        .prefetch_related(
            Prefetch(
                "kalemler",
                SiparisKalemi.objects.select_related("stok_item").order_by("id"),
            )
        )
        .order_by("-olusturulma_tarihi", "-id")
    )
    rows = []
    for siparis in qs:
        stoktan_dusulen_map = {
            sid: Decimal(str(miktar))
            for sid, miktar in _siparis_stoktan_dusulen_map(siparis).items()
        }
        havuz = dict(stoktan_dusulen_map)
        for kalem in siparis.kalemler.all():
            talep = Decimal(str(kalem.miktar))
            if not kalem.stok_item_id:
                birim = "ADET"
                stoktan_dusulen = Decimal("0")
                bekleyen = talep
            else:
                birim = (kalem.stok_item.birim or "ADET") if kalem.stok_item else "ADET"
                sid = kalem.stok_item_id
                havuz_miktar = havuz.get(sid, Decimal("0"))
                stoktan_dusulen = min(talep, havuz_miktar)
                havuz[sid] = havuz_miktar - stoktan_dusulen
                bekleyen = talep - stoktan_dusulen
            rows.append(
                {
                    "kalem": kalem,
                    "siparis": siparis,
                    "talep": talep,
                    "stoktan_dusulen": stoktan_dusulen,
                    "bekleyen": bekleyen,
                    "birim": birim,
                }
            )
    return rows


def _malzeme_birim_fiyat_bul(stok_item):
    """
    Sipariş maliyeti için birim fiyat:
    1) Teslim alınmış satınalmalardaki efektif fiyat
    2) Stok kartı alış fiyatı (fallback)
    """
    son_teslim = (
        SatinalmaKalemi.objects.filter(
            stok_item=stok_item,
            satinalma__teslim_durumu__in=["KISMI_TESLIM", "TESLIM_ALINDI"],
        )
        .select_related("satinalma")
        .order_by("-satinalma__updated_at", "-id")
        .first()
    )
    if son_teslim:
        fiyat = son_teslim.tedarikci_fiyat if son_teslim.tedarikci_fiyat is not None else son_teslim.birim_fiyat
        if fiyat is not None:
            return Decimal(str(fiyat)), son_teslim.satinalma.para_birimi or "TRY"
    return Decimal(str(stok_item.alis_fiyati or 0)), stok_item.alis_para_birimi or "TRY"


def _siparis_uretim_emri_olustur_core(siparis, miktar_override_by_item=None, auto_start_username=None):
    kalemler = SiparisKalemi.objects.filter(siparis=siparis)
    if not kalemler.exists():
        return {"ok": False, "error": "Bu siparişte ürün bulunmuyor."}

    olusturulan_emirler = []
    recete_bulunamayanlar = []
    baslat_uyarilari = []

    siparis_emir_aciklama = f"Sipariş {siparis.siparis_numarasi} için oluşturuldu"
    if miktar_override_by_item is None:
        mevcut_siparis_emirleri = UretimEmri.objects.filter(
            aciklama__icontains=siparis_emir_aciklama,
            production_type="ORDER",
        )
        planlandi_emirler = list(
            mevcut_siparis_emirleri.filter(durum="PLANLANDI").order_by("id")
        )
        if planlandi_emirler:
            if not auto_start_username:
                return {
                    "ok": False,
                    "error": "Mevcut planlı iş emirlerini başlatmak için kullanıcı bilgisi gerekli.",
                    "olusturulan_emirler": [],
                    "recete_bulunamayanlar": [],
                    "baslat_uyarilari": [],
                }
            with transaction.atomic():
                for emir in planlandi_emirler:
                    ex = uretim_emri_baslat_execute(emir, auto_start_username)
                    if not ex["ok"]:
                        raise SiparisUretimBaslatHatasi(
                            ex.get("error") or "Üretim emri başlatılamadı."
                        )
                    baslat_uyarilari.extend(ex.get("warnings") or [])
                    olusturulan_emirler.append(emir.emir_no)
                siparis.uretim_durumu = "DEVAM_EDIYOR"
                siparis.save(update_fields=["uretim_durumu"])
            return {
                "ok": True,
                "olusturulan_emirler": olusturulan_emirler,
                "recete_bulunamayanlar": [],
                "baslat_uyarilari": baslat_uyarilari,
            }
        if mevcut_siparis_emirleri.filter(durum="BASLADI").exists():
            return {
                "ok": False,
                "error": "Bu sipariş için üretim zaten başlatılmış. İş emirleri listesinden tamamlayabilirsiniz.",
                "olusturulan_emirler": [],
                "recete_bulunamayanlar": [],
                "baslat_uyarilari": [],
            }
        if mevcut_siparis_emirleri.exists():
            return {
                "ok": False,
                "error": (
                    "Bu siparişe bağlı iş emirleri var; başlatılacak PLANLANDI emir yok "
                    "(tamamlanmış veya iptal olabilir). İş emirleri listesinden kontrol edin."
                ),
                "olusturulan_emirler": [],
                "recete_bulunamayanlar": [],
                "baslat_uyarilari": [],
            }

    with transaction.atomic():
        for kalem in kalemler:
            recete = Recete.objects.filter(urun=kalem.stok_item, aktif=True).first()
            if not recete:
                recete_bulunamayanlar.append(kalem.stok_item.ad)
                continue

            # Üretilecek miktar
            if miktar_override_by_item is not None:
                # Kalan miktar üret: yalnızca eksik listesindeki ürünler; stoktan karşılananlar atlanır
                if kalem.stok_item_id not in miktar_override_by_item:
                    continue
                uretilecek_miktar = Decimal(str(miktar_override_by_item[kalem.stok_item_id]))
            else:
                uretilecek_miktar = Decimal(str(kalem.miktar))
            if uretilecek_miktar <= 0:
                continue

            if siparis.tamamlanma_tarihi:
                planlanan_baslama = timezone.make_aware(datetime.combine(siparis.olusturulma_tarihi, datetime.min.time()))
                planlanan_bitis = timezone.make_aware(datetime.combine(siparis.tamamlanma_tarihi, datetime.max.time()))
            else:
                planlanan_baslama = timezone.now()
                planlanan_bitis = timezone.now() + timedelta(days=30)

            uretim_emri = create_uretim_emri_with_stages(
                recete=recete,
                miktar=uretilecek_miktar,
                planlanan_baslama=planlanan_baslama,
                planlanan_bitis=planlanan_bitis,
                aciklama=siparis_emir_aciklama,
                production_type="ORDER",
                ust_uretim_emri=None,
                alt_emir_otomatik=False,
            )

            alt_aciklama = (
                f"Sipariş {siparis.siparis_numarasi} — ana emir {uretim_emri.emir_no} için otomatik ara ürün"
            )
            alt_emirler = create_alt_uretim_emirleri(
                uretim_emri,
                planlanan_baslama=planlanan_baslama,
                planlanan_bitis=planlanan_bitis,
                aciklama=alt_aciklama,
                production_type="ORDER",
            )

            for ae in alt_emirler:
                olusturulan_emirler.append(ae.emir_no)
            olusturulan_emirler.append(uretim_emri.emir_no)

            # Sipariş maliyetleri yalnızca ana ürün emrine (malzeme + operasyon)
            from datetime import date

            kayit_tarihi = date.today()
            recete_detaylar = ReceteDetay.objects.filter(recete=recete)
            for detay in recete_detaylar:
                gerekli_miktar = detay.miktar * uretilecek_miktar
                birim_fiyat, para_birimi = _malzeme_birim_fiyat_bul(detay.stok_item)
                SiparisMaliyeti.objects.create(
                    siparis=siparis,
                    maliyet_tipi="MALZEME",
                    aciklama=f"{detay.stok_item.stok_kodu} - {detay.stok_item.ad}",
                    miktar=gerekli_miktar,
                    birim_fiyat=birim_fiyat,
                    para_birimi=para_birimi,
                    birim=detay.birim,
                    kayit_tarihi=kayit_tarihi,
                    aciklama_detay=f"Recete: {recete.urun.stok_kodu}, Üretim Emri: {uretim_emri.emir_no}",
                )

            recete_operasyonlar = ReceteOperasyon.objects.filter(recete=recete)
            for operasyon in recete_operasyonlar:
                birim_maliyet = operasyon.toplam_maliyet if operasyon.toplam_maliyet else Decimal("0")
                SiparisMaliyeti.objects.create(
                    siparis=siparis,
                    maliyet_tipi="OPERASYON",
                    aciklama=operasyon.operasyon.ad,
                    miktar=uretilecek_miktar,
                    birim_fiyat=birim_maliyet,
                    para_birimi="TRY",
                    birim="Adet",
                    kayit_tarihi=kayit_tarihi,
                    aciklama_detay=f"Recete: {recete.urun.stok_kodu}, Süre: {operasyon.sure_dakika} dakika, Maliyet/Saat: {operasyon.maliyet} TRY",
                )

            if auto_start_username:
                for ae in alt_emirler:
                    ex = uretim_emri_baslat_execute(ae, auto_start_username)
                    if not ex["ok"]:
                        raise SiparisUretimBaslatHatasi(ex.get("error") or "Üretim emri başlatılamadı.")
                    baslat_uyarilari.extend(ex.get("warnings") or [])
                ex = uretim_emri_baslat_execute(uretim_emri, auto_start_username)
                if not ex["ok"]:
                    raise SiparisUretimBaslatHatasi(ex.get("error") or "Üretim emri başlatılamadı.")
                baslat_uyarilari.extend(ex.get("warnings") or [])

        if olusturulan_emirler:
            siparis.uretim_durumu = "DEVAM_EDIYOR"
            siparis.save(update_fields=["uretim_durumu"])

    return {
        "ok": True,
        "olusturulan_emirler": olusturulan_emirler,
        "recete_bulunamayanlar": recete_bulunamayanlar,
        "baslat_uyarilari": baslat_uyarilari,
    }


def _hesapla_stok_durumu(siparis):
    kalemler = SiparisKalemi.objects.filter(siparis=siparis).select_related('stok_item')
    if not kalemler.exists():
        return 'STOKTA_YOK'
    yeterli = all(kalem.stok_item.mevcut_miktar >= kalem.miktar for kalem in kalemler)
    return 'STOKTA_VAR' if yeterli else 'STOKTA_YOK'


SIPARIS_KDV_ORANI = Decimal("0.20")


def _siparis_para_birimi_toplamlari(siparis_qs):
    """Filtrelenmiş sipariş queryset'inde para birimine göre ara toplam (KDV hariç) tutarlar."""
    tl_tutar = eur_tutar = usd_tutar = Decimal("0")
    for row in siparis_qs.values("para_birimi").annotate(t=Sum("toplam")):
        pb = (row["para_birimi"] or "").upper().strip()
        amount = Decimal(str(row["t"] or 0))
        if pb in ("TL", "TRY"):
            tl_tutar += amount
        elif pb == "EUR":
            eur_tutar += amount
        elif pb == "USD":
            usd_tutar += amount
    return tl_tutar, eur_tutar, usd_tutar


def _siparis_ozet_kdv_toplam(tutar):
    kdv = tutar * SIPARIS_KDV_ORANI
    return kdv, tutar + kdv


def _hesapla_hammadde_durumu(siparis):
    kalemler = SiparisKalemi.objects.filter(siparis=siparis).select_related('stok_item')
    if not kalemler.exists():
        return 'STOKTA_YOK'

    # Stok yetersiz olsa bile açık satınalma ile karşılanabiliyorsa
    # "Stokta Var" yerine ara durum dönmek için işaretleyici.
    tedarik_bekleniyor = False

    for kalem in kalemler:
        urun_rolu = (getattr(kalem.stok_item, 'urun_rolu', '') or 'AL_SAT').upper()
        if urun_rolu == 'AL_SAT':
            gerekli_miktar = Decimal(str(kalem.miktar))
            mevcut_miktar = Decimal(str(kalem.stok_item.mevcut_miktar or 0))
            if mevcut_miktar >= gerekli_miktar:
                continue
            eksik_miktar = gerekli_miktar - mevcut_miktar
            teslim_agg = SatinalmaKalemi.objects.filter(
                stok_item=kalem.stok_item,
                satinalma__teslim_durumu__in=['BEKLIYOR', 'KISMI_TESLIM'],
            ).aggregate(
                toplam_miktar=Sum('miktar'),
                teslim_alinan=Sum('teslim_alinan_miktar'),
            )
            toplam_miktar = Decimal(str(teslim_agg.get('toplam_miktar') or 0))
            teslim_alinan = Decimal(str(teslim_agg.get('teslim_alinan') or 0))
            acik_satinalma_miktari = max(Decimal('0'), toplam_miktar - teslim_alinan)
            if acik_satinalma_miktari >= eksik_miktar:
                tedarik_bekleniyor = True
                continue
            return 'STOKTA_YOK'

        recete = Recete.objects.filter(urun=kalem.stok_item, aktif=True).first()
        if not recete:
            return 'STOKTA_YOK'

        recete_detaylar = ReceteDetay.objects.filter(recete=recete).select_related('stok_item')
        for detay in recete_detaylar:
            gerekli_miktar = Decimal(str(detay.miktar)) * Decimal(str(kalem.miktar))
            mevcut_miktar = Decimal(str(detay.stok_item.mevcut_miktar or 0))
            if mevcut_miktar >= gerekli_miktar:
                continue

            eksik_miktar = gerekli_miktar - mevcut_miktar
            teslim_agg = SatinalmaKalemi.objects.filter(
                stok_item=detay.stok_item,
                satinalma__teslim_durumu__in=['BEKLIYOR', 'KISMI_TESLIM'],
            ).aggregate(
                toplam_miktar=Sum('miktar'),
                teslim_alinan=Sum('teslim_alinan_miktar'),
            )
            toplam_miktar = Decimal(str(teslim_agg.get('toplam_miktar') or 0))
            teslim_alinan = Decimal(str(teslim_agg.get('teslim_alinan') or 0))
            acik_satinalma_miktari = max(Decimal('0'), toplam_miktar - teslim_alinan)

            if acik_satinalma_miktari >= eksik_miktar:
                tedarik_bekleniyor = True
                continue
            return 'STOKTA_YOK'

    if tedarik_bekleniyor:
        return 'KISMI_STOK'
    return 'STOKTA_VAR'


@login_required
def siparis_listesi(request):
    """Sipariş listesi"""
    # Sekme filtresi
    tab = request.GET.get('tab', 'onaylandi')  # Varsayılan: Onaylandı

    acik_siparis_kalemleri_page = None
    acik_kalem_rows = None
    teslimat_bekleyen_kalemleri_page = None
    teslimat_bekleyen_kalem_rows = None
    if tab == 'acik_siparis_kalemleri':
        acik_kalem_rows = _build_acik_siparis_kalem_rows()
        paginator_acik = Paginator(acik_kalem_rows, 25)
        acik_siparis_kalemleri_page = paginator_acik.get_page(request.GET.get('page', 1))
        siparisler = Siparis.objects.none()
    elif tab == 'teslimat_bekleyen_kalemleri':
        teslimat_bekleyen_kalem_rows = _build_teslimat_bekleyen_kalem_rows()
        paginator_tb = Paginator(teslimat_bekleyen_kalem_rows, 25)
        teslimat_bekleyen_kalemleri_page = paginator_tb.get_page(request.GET.get('page', 1))
        siparisler = Siparis.objects.none()
    elif tab == 'onay_bekliyor':
        siparisler = Siparis.objects.filter(siparis_durumu='ONAY_BEKLIYOR')
    elif tab == 'onaylandi':
        siparisler = Siparis.objects.filter(siparis_durumu='ONAYLANDI')
    elif tab == 'teslimat_bekleyen':
        siparisler = _siparis_teslimat_bekleyen_qs()
    elif tab == 'teslim_edildi':
        siparisler = Siparis.objects.filter(siparis_durumu='TESLIM_EDILDI')
    elif tab == 'red':
        siparisler = Siparis.objects.filter(siparis_durumu='RED')
    else:  # detayli_liste
        siparisler = Siparis.objects.all()

    if acik_kalem_rows is None:
        acik_kalem_rows = _build_acik_siparis_kalem_rows()
    if teslimat_bekleyen_kalem_rows is None:
        teslimat_bekleyen_kalem_rows = _build_teslimat_bekleyen_kalem_rows()

    # Sipariş durumlarını iş kurallarına göre güncelle
    for siparis in siparisler:
        yeni_stok_durumu = _hesapla_stok_durumu(siparis)
        yeni_hammadde_durumu = _hesapla_hammadde_durumu(siparis)
        ilgili_emirler = UretimEmri.objects.filter(
            aciklama__icontains=f'Sipariş {siparis.siparis_numarasi} için oluşturuldu'
        )

        if ilgili_emirler.exists() and not ilgili_emirler.exclude(durum='TAMAMLANDI').exists():
            yeni_uretim_durumu = 'TAMAMLANDI'
        elif ilgili_emirler.filter(durum='BASLADI').exists():
            yeni_uretim_durumu = 'DEVAM_EDIYOR'
        elif ilgili_emirler.exists():
            # Emir kaydı var ama hiçbiri BASLADI değil (ör. hepsi PLANLANDI) — üretim fiilen başlamadı
            if siparis.uretim_durumu == 'STOKTAN_SEVK':
                yeni_uretim_durumu = 'STOKTAN_SEVK'
            else:
                yeni_uretim_durumu = 'BEKLEMEDE'
        else:
            # Stoktan sevk seçilmiş siparişlerde üretim durumu korunur
            if siparis.uretim_durumu == 'STOKTAN_SEVK':
                yeni_uretim_durumu = 'STOKTAN_SEVK'
            elif siparis.uretim_durumu == 'DEVAM_EDIYOR':
                # Harici/önceden başlayan üretimden karşılama seçildiyse,
                # stok teslime yetecek seviyeye geldiğinde sevke hazır kabul et.
                yeni_uretim_durumu = 'TAMAMLANDI' if _siparis_stoktan_teslime_hazir_mi(siparis) else 'DEVAM_EDIYOR'
            else:
                yeni_uretim_durumu = 'BEKLEMEDE'

        guncellenecek_alanlar = []
        if siparis.stok_durumu != yeni_stok_durumu:
            siparis.stok_durumu = yeni_stok_durumu
            guncellenecek_alanlar.append('stok_durumu')
        if siparis.hammadde_durumu != yeni_hammadde_durumu:
            siparis.hammadde_durumu = yeni_hammadde_durumu
            guncellenecek_alanlar.append('hammadde_durumu')
        if siparis.uretim_durumu != yeni_uretim_durumu:
            siparis.uretim_durumu = yeni_uretim_durumu
            guncellenecek_alanlar.append('uretim_durumu')

        if guncellenecek_alanlar:
            siparis.save(update_fields=guncellenecek_alanlar)
    
    # Filtreler
    stok_durumu = request.GET.get('stok_durumu', '')
    hammadde_durumu = request.GET.get('hammadde_durumu', '')
    uretim_durumu = request.GET.get('uretim_durumu', '')
    teslimat_durumu = request.GET.get('teslimat_durumu', '')
    fatura_durumu = request.GET.get('fatura_durumu', '')
    
    if stok_durumu:
        siparisler = siparisler.filter(stok_durumu=stok_durumu)
    if hammadde_durumu:
        siparisler = siparisler.filter(hammadde_durumu=hammadde_durumu)
    if uretim_durumu:
        siparisler = siparisler.filter(uretim_durumu=uretim_durumu)
    if teslimat_durumu:
        siparisler = siparisler.filter(teslimat_durumu=teslimat_durumu)
    if fatura_durumu:
        siparisler = siparisler.filter(fatura_durumu=fatura_durumu)

    siparisler = siparisler.select_related('musteri', 'kaynak_teklif')
    
    # Sayfalama
    paginator = Paginator(siparisler, 10)
    page = request.GET.get('page', 1)
    siparisler_page = paginator.get_page(page)

    for siparis in siparisler_page.object_list:
        aksiyon = _siparis_tedarik_aksiyon_bilgisi(siparis)
        siparis.has_al_sat_items = aksiyon["has_al_sat_items"]
        siparis.has_uretim_items = aksiyon["has_uretim_items"]
        siparis.al_satinalma_query = aksiyon["satinalma_query"]
        siparis.al_rfq_query = aksiyon["rfq_query"]
        siparis.linked_satinalma_id = None
        siparis.linked_satinalma_no = ""
        siparis.linked_rfq_id = None
        siparis.linked_rfq_no = ""
        siparis.ek_dosya_url = ""
        if siparis.siparis_mektubu:
            try:
                siparis.ek_dosya_url = siparis.siparis_mektubu.url
            except Exception:
                siparis.ek_dosya_url = ""
        elif getattr(siparis, "kaynak_teklif", None) and siparis.kaynak_teklif.siparis_mektubu:
            try:
                siparis.ek_dosya_url = siparis.kaynak_teklif.siparis_mektubu.url
            except Exception:
                siparis.ek_dosya_url = ""

    order_ids = [siparis.id for siparis in siparisler_page.object_list]
    satinalma_by_order = {}
    if order_ids:
        for row in (
            Satinalma.objects.filter(kaynak_siparis_id__in=order_ids)
            .order_by("-created_at", "-id")
            .values("kaynak_siparis_id", "id", "satinalma_numarasi")
        ):
            sid = row["kaynak_siparis_id"]
            if sid in satinalma_by_order:
                continue
            satinalma_by_order[sid] = row

    rfq_by_order = {}
    if order_ids:
        for row in (
            TeklifTalebi.objects.filter(kaynak_siparis_id__in=order_ids)
            .order_by("-created_at", "-id")
            .values("kaynak_siparis_id", "id", "rfq_no")
        ):
            sid = row["kaynak_siparis_id"]
            if sid in rfq_by_order:
                continue
            rfq_by_order[sid] = row

    for siparis in siparisler_page.object_list:
        sat_row = satinalma_by_order.get(siparis.id)
        if sat_row:
            siparis.linked_satinalma_id = sat_row["id"]
            siparis.linked_satinalma_no = sat_row["satinalma_numarasi"] or ""
        else:
            auto_sat = _bagli_satinalma_otomatik_eslestir(siparis)
            if auto_sat:
                siparis.linked_satinalma_id = auto_sat.id
                siparis.linked_satinalma_no = auto_sat.satinalma_numarasi or ""
        rfq_row = rfq_by_order.get(siparis.id)
        if rfq_row:
            siparis.linked_rfq_id = rfq_row["id"]
            siparis.linked_rfq_no = rfq_row["rfq_no"] or ""
        siparis.show_decision_button = (
            tab == "onaylandi"
            and siparis.uretim_durumu == "BEKLEMEDE"
            and (siparis.has_uretim_items or siparis.has_al_sat_items)
            and not siparis.linked_satinalma_id
            and not siparis.linked_rfq_id
        )
    
    siparis_tl_tutar = siparis_eur_tutar = siparis_usd_tutar = Decimal("0")
    siparis_tl_kdv = siparis_eur_kdv = siparis_usd_kdv = Decimal("0")
    siparis_tl_toplam = siparis_eur_toplam = siparis_usd_toplam = Decimal("0")
    siparis_genel_tl_tutar = siparis_genel_tl_kdv = siparis_genel_tl_toplam = None
    usd_kur = eur_kur = None
    if tab not in ("acik_siparis_kalemleri", "teslimat_bekleyen_kalemleri"):
        siparis_tl_tutar, siparis_eur_tutar, siparis_usd_tutar = _siparis_para_birimi_toplamlari(
            siparisler
        )
        siparis_tl_kdv, siparis_tl_toplam = _siparis_ozet_kdv_toplam(siparis_tl_tutar)
        siparis_eur_kdv, siparis_eur_toplam = _siparis_ozet_kdv_toplam(siparis_eur_tutar)
        siparis_usd_kdv, siparis_usd_toplam = _siparis_ozet_kdv_toplam(siparis_usd_tutar)
        usd_kur, eur_kur = _dashboard_tcmb_kurlar()
        siparis_genel_tl_tutar = siparis_tl_tutar
        siparis_genel_tl_kdv = siparis_tl_kdv
        if eur_kur:
            eur_kur_dec = Decimal(str(eur_kur))
            siparis_genel_tl_tutar += siparis_eur_tutar * eur_kur_dec
            siparis_genel_tl_kdv += siparis_eur_kdv * eur_kur_dec
        if usd_kur:
            usd_kur_dec = Decimal(str(usd_kur))
            siparis_genel_tl_tutar += siparis_usd_tutar * usd_kur_dec
            siparis_genel_tl_kdv += siparis_usd_kdv * usd_kur_dec
        siparis_genel_tl_toplam = siparis_genel_tl_tutar + siparis_genel_tl_kdv

    counts = {
        'onay_bekliyor': Siparis.objects.filter(siparis_durumu='ONAY_BEKLIYOR').count(),
        'onaylandi': Siparis.objects.filter(siparis_durumu='ONAYLANDI').count(),
        'teslimat_bekleyen': _siparis_teslimat_bekleyen_qs().count(),
        'teslimat_bekleyen_kalemleri': len(teslimat_bekleyen_kalem_rows),
        'teslim_edildi': Siparis.objects.filter(siparis_durumu='TESLIM_EDILDI').count(),
        'red': Siparis.objects.filter(siparis_durumu='RED').count(),
        'detayli_liste': Siparis.objects.count(),
        'acik_siparis_kalemleri': len(acik_kalem_rows),
    }

    context = {
        'siparisler': siparisler_page,
        'acik_siparis_kalemleri': acik_siparis_kalemleri_page,
        'teslimat_bekleyen_kalemleri': teslimat_bekleyen_kalemleri_page,
        'tab': tab,
        'stok_durumu': stok_durumu,
        'hammadde_durumu': hammadde_durumu,
        'uretim_durumu': uretim_durumu,
        'teslimat_durumu': teslimat_durumu,
        'fatura_durumu': fatura_durumu,
        'siparis_tl_tutar': siparis_tl_tutar,
        'siparis_tl_kdv': siparis_tl_kdv,
        'siparis_tl_toplam': siparis_tl_toplam,
        'siparis_eur_tutar': siparis_eur_tutar,
        'siparis_eur_kdv': siparis_eur_kdv,
        'siparis_eur_toplam': siparis_eur_toplam,
        'siparis_usd_tutar': siparis_usd_tutar,
        'siparis_usd_kdv': siparis_usd_kdv,
        'siparis_usd_toplam': siparis_usd_toplam,
        'siparis_genel_tl_tutar': siparis_genel_tl_tutar,
        'siparis_genel_tl_kdv': siparis_genel_tl_kdv,
        'siparis_genel_tl_toplam': siparis_genel_tl_toplam,
        'usd_kur': usd_kur,
        'eur_kur': eur_kur,
        'counts': counts,
    }
    return render(request, 'stokapp/siparis_listesi.html', context)

@login_required
def siparis_ekle(request):
    """Yeni sipariş oluştur"""
    if request.method == 'POST':
        form = SiparisForm(request.POST, request.FILES)
        kalemler_data = json.loads(request.POST.get('kalemler', '[]'))
        
        if form.is_valid() and kalemler_data:
            try:
                with transaction.atomic():
                    siparis = form.save(commit=False)
                    # Müşteri adını kaydet
                    if siparis.musteri:
                        siparis.musteri_adi = siparis.musteri.ad
                    # Toplam hesapla
                    toplam = Decimal('0')
                    for kalem in kalemler_data:
                        miktar = Decimal(str(kalem['miktar']))
                        birim_fiyat = Decimal(str(kalem['birim_fiyat']))
                        indirim = Decimal(str(kalem.get('indirim_yuzdesi', 0)))
                        kalem_toplam = (miktar * birim_fiyat) * (1 - indirim / 100)
                        toplam += kalem_toplam
                    
                    siparis.toplam = toplam
                    siparis.save()
                    
                    # Kalemleri kaydet
                    for kalem in kalemler_data:
                        stok_item = StokItem.objects.get(pk=kalem['stok_item'])
                        SiparisKalemi.objects.create(
                            siparis=siparis,
                            stok_item=stok_item,
                            miktar=Decimal(str(kalem['miktar'])),
                            birim_fiyat=Decimal(str(kalem['birim_fiyat'])),
                            indirim_yuzdesi=Decimal(str(kalem.get('indirim_yuzdesi', 0))),
                            aciklama=kalem.get('aciklama', '')
                        )
                    
                    messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" başarıyla oluşturuldu.')
                    return redirect('stokapp:siparis_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
        else:
            messages.error(request, 'Lütfen en az bir ürün ekleyin.')
    else:
        form = SiparisForm()
        # Varsayılan değerler
        form.fields['olusturulma_tarihi'].initial = timezone.now().date()
        form.fields['siparis_durumu'].initial = 'ONAY_BEKLIYOR'
        
        # Varsayılan para birimi - ParaBirimi modelinden ilk aktif olanı al
        from .models import ParaBirimi
        varsayilan_pb = ParaBirimi.objects.filter(aktif=True).first()
        if varsayilan_pb:
            form.fields['para_birimi'].initial = varsayilan_pb.kod
        else:
            form.fields['para_birimi'].initial = 'USD'
        
        # Otomatik sipariş numarası
        son_siparis = Siparis.objects.order_by('-id').first()
        if son_siparis:
            try:
                num = int(son_siparis.siparis_numarasi.replace('SO-', '')) + 1
            except:
                num = 1
        else:
            num = 1
        form.fields['siparis_numarasi'].initial = f'SO-{num}'
    
    stok_items = StokItem.objects.all().order_by('ad')
    # Debug için birim bilgilerini kontrol et
    for item in stok_items:
        print(f"Stok: {item.ad}, Birim: {item.birim}, Birim Type: {type(item.birim)}")
    musteriler = Musteri.objects.all().order_by('ad')
    
    context = {
        'form': form,
        'stok_items': stok_items,
        'musteriler': musteriler,
    }
    return render(request, 'stokapp/siparis_ekle.html', context)

@login_required
def siparis_detay(request, pk):
    """Sipariş detay sayfası"""
    siparis = get_object_or_404(Siparis.objects.select_related('kaynak_teklif'), pk=pk)
    kalemler = SiparisKalemi.objects.filter(siparis=siparis).order_by('id')
    
    # Özet hesaplamaları
    ara_toplam = siparis.toplam
    vergi = ara_toplam * Decimal('0.20')  # %20 KDV
    toplam = ara_toplam + vergi
    
    tekos_logo_url = static('stokapp/images/tekos-logo.png')
    context = {
        'siparis': siparis,
        'kalemler': kalemler,
        'ara_toplam': ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
        'tekos_logo_cid': None,
        'tekos_logo_url': tekos_logo_url,
    }
    return render(request, 'stokapp/siparis_detay.html', context)

@login_required
def siparis_duzenle(request, pk):
    """Sipariş düzenle"""
    siparis = get_object_or_404(Siparis, pk=pk)
    
    if request.method == 'POST':
        form = SiparisForm(request.POST, request.FILES, instance=siparis)
        kalemler_str = request.POST.get('kalemler', '[]')
        try:
            kalemler_data = json.loads(kalemler_str) if kalemler_str else []
        except json.JSONDecodeError:
            kalemler_data = []
        
        if form.is_valid() and kalemler_data:
            try:
                with transaction.atomic():
                    siparis = form.save(commit=False)
                    # Müşteri adını kaydet
                    if siparis.musteri:
                        siparis.musteri_adi = siparis.musteri.ad
                    
                    # Eski kalemleri sil
                    SiparisKalemi.objects.filter(siparis=siparis).delete()
                    
                    # Toplam hesapla
                    toplam = Decimal('0')
                    for kalem in kalemler_data:
                        miktar = Decimal(str(kalem['miktar']))
                        birim_fiyat = Decimal(str(kalem['birim_fiyat']))
                        indirim = Decimal(str(kalem.get('indirim_yuzdesi', 0)))
                        kalem_toplam = (miktar * birim_fiyat) * (1 - indirim / 100)
                        toplam += kalem_toplam
                    
                    siparis.toplam = toplam
                    siparis.save()
                    
                    # Yeni kalemleri kaydet
                    for kalem in kalemler_data:
                        stok_item = StokItem.objects.get(pk=kalem['stok_item'])
                        SiparisKalemi.objects.create(
                            siparis=siparis,
                            stok_item=stok_item,
                            miktar=Decimal(str(kalem['miktar'])),
                            birim_fiyat=Decimal(str(kalem['birim_fiyat'])),
                            indirim_yuzdesi=Decimal(str(kalem.get('indirim_yuzdesi', 0))),
                            aciklama=kalem.get('aciklama', '')
                        )
                    
                    messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" başarıyla güncellendi.')
                    return redirect('stokapp:siparis_listesi')
            except Exception as e:
                messages.error(request, f'Hata: {str(e)}')
        else:
            messages.error(request, 'Lütfen en az bir ürün ekleyin.')
    else:
        form = SiparisForm(instance=siparis)
    
    stok_items = StokItem.objects.all().order_by('ad')
    musteriler = Musteri.objects.all().order_by('ad')
    mevcut_kalemler = SiparisKalemi.objects.filter(siparis=siparis).order_by('id')
    
    context = {
        'form': form,
        'siparis': siparis,
        'stok_items': stok_items,
        'musteriler': musteriler,
        'mevcut_kalemler': mevcut_kalemler,
    }
    return render(request, 'stokapp/siparis_duzenle.html', context)

@login_required
def siparis_sil(request, pk):
    """Sipariş sil"""
    siparis = get_object_or_404(Siparis, pk=pk)
    
    if request.method == 'POST':
        try:
            siparis_numarasi = siparis.siparis_numarasi
            siparis.delete()
            messages.success(request, f'Sipariş "{siparis_numarasi}" başarıyla silindi.')
            return redirect('stokapp:siparis_listesi')
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    
    context = {
        'siparis': siparis,
    }
    return render(request, 'stokapp/siparis_sil.html', context)

@login_required
def siparis_uretim_emri_olustur(request, pk):
    """Sipariş için üretim emri oluştur"""
    siparis = get_object_or_404(Siparis, pk=pk)
    
    # Sadece onaylanmış siparişler için üretim emri oluşturulabilir
    if siparis.siparis_durumu != 'ONAYLANDI':
        messages.error(request, 'Sadece onaylanmış siparişler için üretim emri oluşturulabilir.')
        return redirect('stokapp:siparis_listesi')
    
    try:
        result = _siparis_uretim_emri_olustur_core(siparis, auto_start_username=request.user.username)
        if not result.get("ok"):
            messages.error(request, result.get("error") or "Üretim emri oluşturulamadı.")
            return redirect('stokapp:siparis_listesi')

        if result.get("olusturulan_emirler"):
            messages.success(
                request,
                f'{len(result["olusturulan_emirler"])} adet üretim emri oluşturuldu ve başlatıldı: {", ".join(result["olusturulan_emirler"])}'
            )
        else:
            messages.error(request, "Üretim emri oluşturulamadı.")
        for uyari in result.get("baslat_uyarilari") or []:
            messages.warning(request, uyari)
        if result.get("recete_bulunamayanlar"):
            messages.warning(
                request,
                f'Şu ürünler için recete bulunamadı, üretim emri oluşturulmadı: {", ".join(result["recete_bulunamayanlar"])}'
            )
    except SiparisUretimBaslatHatasi as e:
        messages.error(request, e.message)
        return redirect('stokapp:siparis_listesi')
    except Exception as e:
        messages.error(request, f'Üretim emri oluşturulurken hata oluştu: {str(e)}')
        return redirect('stokapp:siparis_listesi')
    
    return redirect('stokapp:siparis_listesi')


@login_required
def start_production_from_order(request, pk):
    """Sipariş için stok kontrolü ve karar verisi döndür"""
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    kalemler = list(SiparisKalemi.objects.filter(siparis=siparis).select_related("stok_item"))
    if not kalemler:
        return JsonResponse({"success": False, "error": "Siparişte ürün bulunmuyor."}, status=400)
    # Aynı ürün birden fazla satırda olabilir; ürün bazında birleştir.
    item_map = {}
    for kalem in kalemler:
        key = kalem.stok_item_id
        if key not in item_map:
            item_map[key] = {
                "product_id": kalem.stok_item_id,
                "product_name": kalem.stok_item.ad,
                "product_code": kalem.stok_item.stok_kodu,
                "unit": kalem.stok_item.birim,
                "order_quantity": Decimal("0"),
                "stock": Decimal(str(kalem.stok_item.mevcut_miktar or 0)),
            }
        item_map[key]["order_quantity"] += Decimal(str(kalem.miktar))

    items = []
    all_enough = True
    any_stock_positive = False
    any_missing = False
    for data in item_map.values():
        order_quantity = data["order_quantity"]
        stock_quantity = data["stock"]
        in_production_quantity = data.get("in_production", Decimal("0"))
        effective_quantity = stock_quantity + in_production_quantity
        missing = order_quantity - stock_quantity
        if missing < 0:
            missing = Decimal("0")
        if stock_quantity < order_quantity:
            all_enough = False
        if stock_quantity > 0:
            any_stock_positive = True
        if missing > 0:
            any_missing = True
        items.append({
            "product_id": data["product_id"],
            "product_name": data["product_name"],
            "product_code": data["product_code"],
            "unit": data["unit"],
            "order_quantity": str(order_quantity),
            "stock": str(stock_quantity),
            "in_production": str(in_production_quantity),
            "effective_stock": str(effective_quantity),
            "missing_quantity": str(missing),
        })

    urun_ids = [row["product_id"] for row in items]
    basladi_map = _basladi_uretim_miktar_map(urun_ids)
    basladi_detay_map = _basladi_uretim_detay_map(urun_ids)
    rol_map = {
        row["id"]: (row["urun_rolu"] or "AL_SAT").upper()
        for row in StokItem.objects.filter(id__in=urun_ids).values("id", "urun_rolu")
    }
    enough_with_production = True
    has_in_production = False
    for row in items:
        in_prod = basladi_map.get(row["product_id"], Decimal("0"))
        order_q = Decimal(str(row["order_quantity"]))
        stock_q = Decimal(str(row["stock"]))
        effective = stock_q + in_prod
        row["in_production"] = str(in_prod)
        row["effective_stock"] = str(effective)
        row["in_production_orders"] = basladi_detay_map.get(row["product_id"], [])
        row["urun_rolu"] = rol_map.get(row["product_id"], "AL_SAT")
        if row["urun_rolu"] == "AL_SAT":
            row["suggested_action"] = None
            row["available_actions"] = []
            row["decision_enabled"] = False
            row["default_produce_qty"] = str(order_q)
        else:
            suggested, available, default_produce_qty = _siparis_kalem_karar_aksiyonlari(
                order_q, stock_q, in_prod
            )
            row["suggested_action"] = suggested
            row["available_actions"] = available
            row["decision_enabled"] = True
            row["default_produce_qty"] = str(default_produce_qty)
        if in_prod > 0:
            has_in_production = True
        if effective < order_q:
            enough_with_production = False

    if all_enough:
        check_type = "enough_stock"
    elif enough_with_production and has_in_production:
        check_type = "enough_in_production"
    elif any_stock_positive and any_missing:
        check_type = "partial_stock"
    else:
        check_type = "no_stock"

    return JsonResponse({
        "success": True,
        "type": check_type,
        "order_id": siparis.id,
        "item_count": len(items),
        "items": items,
        "apply_url": reverse("stokapp:apply_siparis_kalem_kararlari", kwargs={"pk": siparis.id}),
    })


def _siparis_kalem_karar_aksiyonlari(order_q, stock_q, in_prod_q):
    """Kalem için önerilen ve seçilebilir karşılama aksiyonları."""
    order_q = Decimal(str(order_q or 0))
    stock_q = Decimal(str(stock_q or 0))
    in_prod_q = Decimal(str(in_prod_q or 0))
    effective = stock_q + in_prod_q

    actions = []
    if stock_q >= order_q:
        actions.append({"value": "from_stock", "label": "Stoktan"})
        actions.append({"value": "produce_full", "label": "Yeni üret"})
        suggested = "from_stock"
        default_produce_qty = order_q
    elif effective >= order_q and in_prod_q > 0:
        actions.append({"value": "from_inproduction", "label": "Üretimden karşıla"})
        if stock_q > 0:
            actions.append({"value": "produce_remaining", "label": "Kalanı üret"})
        actions.append({"value": "produce_full", "label": "Yeni üret"})
        suggested = "from_inproduction"
        default_produce_qty = max(Decimal("0"), order_q - stock_q)
    elif stock_q > 0:
        actions.append({"value": "produce_remaining", "label": "Kalanı üret"})
        actions.append({"value": "produce_full", "label": "Yeni üret"})
        suggested = "produce_remaining"
        default_produce_qty = max(Decimal("0"), order_q - stock_q)
    else:
        actions.append({"value": "produce_full", "label": "Yeni üret"})
        suggested = "produce_full"
        default_produce_qty = order_q
    return suggested, actions, default_produce_qty


def _stok_uretim_emirleri_olustur(siparis, miktar_by_item, auto_start_username=None):
    """Sipariş üstü fazla miktar için STOCK tipi üretim emirleri oluşturur."""
    olusturulan = []
    uyarilar = []
    if not miktar_by_item:
        return {"ok": True, "olusturulan_emirler": [], "baslat_uyarilari": []}

    if siparis.tamamlanma_tarihi:
        planlanan_baslama = timezone.make_aware(
            datetime.combine(siparis.olusturulma_tarihi, datetime.min.time())
        )
        planlanan_bitis = timezone.make_aware(
            datetime.combine(siparis.tamamlanma_tarihi, datetime.max.time())
        )
    else:
        planlanan_baslama = timezone.now()
        planlanan_bitis = timezone.now() + timedelta(days=30)

    for stok_item_id, miktar in miktar_by_item.items():
        miktar = Decimal(str(miktar or 0))
        if miktar <= 0:
            continue
        stok_item = StokItem.objects.filter(pk=stok_item_id).first()
        if not stok_item:
            return {"ok": False, "error": f"Stok kartı bulunamadı: {stok_item_id}"}
        recete = Recete.objects.filter(urun=stok_item, aktif=True).first()
        if not recete:
            return {
                "ok": False,
                "error": f"{stok_item.stok_kodu} için aktif reçete bulunamadı (stok üretimi).",
            }

        aciklama = (
            f"Sipariş {siparis.siparis_numarasi} — fazla miktar stok üretimi "
            f"({stok_item.stok_kodu})"
        )
        uretim_emri = create_uretim_emri_with_stages(
            recete=recete,
            miktar=miktar,
            planlanan_baslama=planlanan_baslama,
            planlanan_bitis=planlanan_bitis,
            aciklama=aciklama,
            production_type="STOCK",
            ust_uretim_emri=None,
            alt_emir_otomatik=False,
        )
        alt_emirler = create_alt_uretim_emirleri(
            uretim_emri,
            planlanan_baslama=planlanan_baslama,
            planlanan_bitis=planlanan_bitis,
            aciklama=f"{aciklama} — otomatik ara ürün",
            production_type="STOCK",
        )
        for ae in alt_emirler:
            olusturulan.append(ae.emir_no)
        olusturulan.append(uretim_emri.emir_no)

        if auto_start_username:
            for ae in alt_emirler:
                ex = uretim_emri_baslat_execute(ae, auto_start_username)
                if not ex["ok"]:
                    raise SiparisUretimBaslatHatasi(ex.get("error") or "Stok üretim emri başlatılamadı.")
                uyarilar.extend(ex.get("warnings") or [])
            ex = uretim_emri_baslat_execute(uretim_emri, auto_start_username)
            if not ex["ok"]:
                raise SiparisUretimBaslatHatasi(ex.get("error") or "Stok üretim emri başlatılamadı.")
            uyarilar.extend(ex.get("warnings") or [])

    return {"ok": True, "olusturulan_emirler": olusturulan, "baslat_uyarilari": uyarilar}


def _split_siparis_stok_uretim_miktari(order_need, produce_qty):
    """
    Üretilecek miktarı sipariş + stok üretimi olarak böler.
    order_need: sipariş için gereken üretim
    produce_qty: kullanıcının girdiği toplam üretim
    """
    order_need = Decimal(str(order_need or 0))
    produce_qty = Decimal(str(produce_qty or 0))
    if produce_qty <= 0:
        return Decimal("0"), Decimal("0")
    if produce_qty <= order_need:
        return produce_qty, Decimal("0")
    return order_need, produce_qty - order_need


@login_required
def apply_siparis_kalem_kararlari(request, pk):
    """
    Sipariş karar modalında kalem bazlı karma karar uygular.
    Body: {"decisions": [{"product_id": 1, "action": "from_inproduction"}, ...]}
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)

    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    try:
        payload = json.loads(request.body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Geçersiz JSON gövdesi."}, status=400)

    decisions_raw = payload.get("decisions") or []
    if not isinstance(decisions_raw, list) or not decisions_raw:
        return JsonResponse({"success": False, "error": "En az bir kalem kararı gerekli."}, status=400)

    valid_actions = {"from_stock", "from_inproduction", "produce_remaining", "produce_full"}
    decisions = {}
    produce_qty_map = {}
    for row in decisions_raw:
        if not isinstance(row, dict):
            continue
        try:
            product_id = int(row.get("product_id"))
        except (TypeError, ValueError):
            continue
        action = (row.get("action") or "").strip()
        if action not in valid_actions:
            return JsonResponse(
                {"success": False, "error": f"Geçersiz aksiyon: {action or '-'}"},
                status=400,
            )
        decisions[product_id] = action
        raw_qty = row.get("produce_qty", None)
        if raw_qty is not None and str(raw_qty).strip() != "":
            try:
                produce_qty_map[product_id] = Decimal(str(raw_qty).replace(",", "."))
            except Exception:
                return JsonResponse(
                    {"success": False, "error": f"Geçersiz üretilecek miktar (ürün {product_id})."},
                    status=400,
                )
            if produce_qty_map[product_id] < 0:
                return JsonResponse(
                    {"success": False, "error": f"Üretilecek miktar negatif olamaz (ürün {product_id})."},
                    status=400,
                )

    if not decisions:
        return JsonResponse({"success": False, "error": "Geçerli kalem kararı bulunamadı."}, status=400)

    kalan_map = _siparis_kalan_teslim_miktari_map(siparis)
    if not kalan_map:
        siparis.uretim_durumu = "TAMAMLANDI"
        siparis.save(update_fields=["uretim_durumu"])
        return JsonResponse({"success": True, "message": "Sipariş zaten teslime hazır."})

    # Karar verilmeyen ürünler için varsayılan seçim (öneri)
    stok_map = {
        row["id"]: Decimal(str(row["mevcut_miktar"] or 0))
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "mevcut_miktar")
    }
    basladi_map = _basladi_uretim_miktar_map(list(kalan_map.keys()))
    rol_map = {
        row["id"]: (row["urun_rolu"] or "AL_SAT").upper()
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "urun_rolu")
    }

    for product_id, gerekli in kalan_map.items():
        if rol_map.get(product_id) == "AL_SAT":
            continue
        if product_id in decisions:
            continue
        suggested, _, default_qty = _siparis_kalem_karar_aksiyonlari(
            gerekli,
            stok_map.get(product_id, Decimal("0")),
            basladi_map.get(product_id, Decimal("0")),
        )
        decisions[product_id] = suggested
        produce_qty_map.setdefault(product_id, default_qty)

    stock_fulfill_ids = []
    wait_production_ids = []
    order_uretim_map = {}
    stock_uretim_map = {}
    ozet = {
        "stoktan": 0,
        "uretimden": 0,
        "siparis_uret": 0,
        "stok_uret": 0,
    }

    with transaction.atomic():
        # Güncel stok kilidi
        locked_stock = {
            item.id: item
            for item in StokItem.objects.select_for_update().filter(id__in=list(kalan_map.keys()))
        }
        basladi_now = _basladi_uretim_miktar_map(list(kalan_map.keys()))

        for product_id, gerekli in kalan_map.items():
            if rol_map.get(product_id) == "AL_SAT":
                continue
            action = decisions.get(product_id)
            if not action:
                continue
            item = locked_stock.get(product_id)
            if not item:
                return JsonResponse({"success": False, "error": f"Stok kartı bulunamadı: {product_id}"}, status=400)

            stock_q = Decimal(str(item.mevcut_miktar or 0))
            in_prod_q = basladi_now.get(product_id, Decimal("0"))

            if action == "from_stock":
                if stock_q < gerekli:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"{item.stok_kodu} için stok yetersiz. Mevcut: {stock_q}, Gerekli: {gerekli}",
                        },
                        status=400,
                    )
                StokHareketi.objects.create(
                    stok_item=item,
                    hareket_tipi="SATIS_STOK",
                    miktar=gerekli,
                    birim=item.birim,
                    referans_no=siparis.siparis_numarasi,
                    aciklama=f"Sipariş {siparis.siparis_numarasi} kalem bazlı stoktan karşılama",
                    user=request.user.username,
                )
                stock_fulfill_ids.append(product_id)
                ozet["stoktan"] += 1

            elif action == "from_inproduction":
                if (stock_q + in_prod_q) < gerekli:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": (
                                f"{item.stok_kodu} için stok+üretimde toplamı yetersiz. "
                                f"Mevcut: {stock_q}, Üretimde: {in_prod_q}, Gerekli: {gerekli}"
                            ),
                        },
                        status=400,
                    )
                wait_production_ids.append(product_id)
                ozet["uretimden"] += 1

            elif action == "produce_remaining":
                stoktan = min(stock_q, gerekli)
                eksik = gerekli - stoktan
                if stoktan > 0:
                    StokHareketi.objects.create(
                        stok_item=item,
                        hareket_tipi="SATIS_STOK",
                        miktar=stoktan,
                        birim=item.birim,
                        referans_no=siparis.siparis_numarasi,
                        aciklama=f"Sipariş {siparis.siparis_numarasi} kalem bazlı kısmi stok karşılama",
                        user=request.user.username,
                    )
                if eksik <= 0:
                    stock_fulfill_ids.append(product_id)
                    ozet["stoktan"] += 1
                else:
                    produce_qty = produce_qty_map.get(product_id)
                    if produce_qty is None:
                        produce_qty = eksik
                    if produce_qty <= 0:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": f"{item.stok_kodu} için üretilecek miktar 0'dan büyük olmalı.",
                            },
                            status=400,
                        )
                    order_qty, stock_qty = _split_siparis_stok_uretim_miktari(eksik, produce_qty)
                    if order_qty > 0:
                        order_uretim_map[product_id] = order_qty
                        ozet["siparis_uret"] += 1
                    if stock_qty > 0:
                        stock_uretim_map[product_id] = stock_qty
                        ozet["stok_uret"] += 1

            elif action == "produce_full":
                produce_qty = produce_qty_map.get(product_id)
                if produce_qty is None:
                    produce_qty = gerekli
                if produce_qty <= 0:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"{item.stok_kodu} için üretilecek miktar 0'dan büyük olmalı.",
                        },
                        status=400,
                    )
                order_qty, stock_qty = _split_siparis_stok_uretim_miktari(gerekli, produce_qty)
                if order_qty > 0:
                    order_uretim_map[product_id] = order_qty
                    ozet["siparis_uret"] += 1
                if stock_qty > 0:
                    stock_uretim_map[product_id] = stock_qty
                    ozet["stok_uret"] += 1

        emirler = []
        if order_uretim_map:
            try:
                result = _siparis_uretim_emri_olustur_core(
                    siparis,
                    miktar_override_by_item=order_uretim_map,
                    auto_start_username=request.user.username,
                )
            except SiparisUretimBaslatHatasi as e:
                return JsonResponse({"success": False, "error": e.message}, status=400)
            if not result.get("ok"):
                return JsonResponse(
                    {"success": False, "error": result.get("error") or "Üretim emri oluşturulamadı."},
                    status=400,
                )
            if not result.get("olusturulan_emirler"):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Sipariş üretim emri oluşturulamadı. Ürün reçetelerini kontrol edin.",
                    },
                    status=400,
                )
            emirler.extend(result.get("olusturulan_emirler") or [])

        if stock_uretim_map:
            try:
                stock_result = _stok_uretim_emirleri_olustur(
                    siparis,
                    stock_uretim_map,
                    auto_start_username=request.user.username,
                )
            except SiparisUretimBaslatHatasi as e:
                return JsonResponse({"success": False, "error": e.message}, status=400)
            if not stock_result.get("ok"):
                return JsonResponse(
                    {"success": False, "error": stock_result.get("error") or "Stok üretim emri oluşturulamadı."},
                    status=400,
                )
            emirler.extend(stock_result.get("olusturulan_emirler") or [])

        # Sipariş durumu
        if order_uretim_map or stock_uretim_map or wait_production_ids:
            siparis.uretim_durumu = "DEVAM_EDIYOR"
            siparis.teslimat_durumu = "HAZIRLANIYOR"
            update_fields = ["uretim_durumu", "teslimat_durumu"]
            if stock_fulfill_ids and (order_uretim_map or stock_uretim_map):
                siparis.stok_durumu = "KISMI_STOK"
                update_fields.append("stok_durumu")
            siparis.save(update_fields=update_fields)
        else:
            siparis.uretim_durumu = "STOKTAN_SEVK"
            siparis.teslimat_durumu = "HAZIRLANIYOR"
            siparis.save(update_fields=["uretim_durumu", "teslimat_durumu"])

    parts = []
    if ozet["stoktan"]:
        parts.append(f"{ozet['stoktan']} kalem stoktan")
    if ozet["uretimden"]:
        parts.append(f"{ozet['uretimden']} kalem üretimden beklemeye")
    if ozet["siparis_uret"]:
        parts.append(f"{ozet['siparis_uret']} kalem sipariş üretimi")
    if ozet["stok_uret"]:
        parts.append(f"{ozet['stok_uret']} kalem stok üretimi")
    message = "Kararlar uygulandı: " + (", ".join(parts) if parts else "işlem yok") + "."
    if emirler:
        message += f" Emirler: {', '.join(emirler)}"

    return JsonResponse({
        "success": True,
        "message": message,
        "ozet": ozet,
        "emirler": emirler,
    })


@login_required
def fulfill_from_stock(request, pk):
    """Stoktan direkt satış: üretim emri oluşturma, teslim için hazırla"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    kalemler = list(SiparisKalemi.objects.filter(siparis=siparis).select_related("stok_item"))
    if not kalemler:
        return JsonResponse({"success": False, "error": "Siparişte ürün bulunmuyor."}, status=400)

    with transaction.atomic():
        for kalem in kalemler:
            stok_item = StokItem.objects.select_for_update().get(pk=kalem.stok_item_id)
            miktar = Decimal(str(kalem.miktar))
            if stok_item.mevcut_miktar < miktar:
                return JsonResponse({
                    "success": False,
                    "error": f"{stok_item.stok_kodu} için stok yetersiz. Mevcut: {stok_item.mevcut_miktar}, Gerekli: {miktar}",
                }, status=400)
            StokHareketi.objects.create(
                stok_item=stok_item,
                hareket_tipi="SATIS_STOK",
                miktar=miktar,
                birim=stok_item.birim,
                referans_no=siparis.siparis_numarasi,
                aciklama=f"Sipariş {siparis.siparis_numarasi} stoktan direkt satış",
                user=request.user.username,
            )

        siparis.uretim_durumu = "STOKTAN_SEVK"
        siparis.teslimat_durumu = "HAZIRLANIYOR"
        siparis.save(update_fields=["uretim_durumu", "teslimat_durumu"])

    return JsonResponse({"success": True, "message": "Sipariş stoktan sevk için hazırlandı."})


@login_required
def fulfill_from_inproduction(request, pk):
    """Yeni emir açmadan, halihazırda üretimde olan miktarı beklemeye al."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    kalan_map = _siparis_kalan_teslim_miktari_map(siparis)
    if not kalan_map:
        siparis.uretim_durumu = "TAMAMLANDI"
        siparis.save(update_fields=["uretim_durumu"])
        return JsonResponse({"success": True, "message": "Sipariş zaten teslime hazır."})

    stok_map = {
        row["id"]: Decimal(str(row["mevcut_miktar"] or 0))
        for row in StokItem.objects.filter(id__in=list(kalan_map.keys())).values("id", "mevcut_miktar")
    }
    basladi_map = _basladi_uretim_miktar_map(list(kalan_map.keys()))

    for stok_item_id, gerekli in kalan_map.items():
        mevcut = stok_map.get(stok_item_id, Decimal("0"))
        uretimde = basladi_map.get(stok_item_id, Decimal("0"))
        if (mevcut + uretimde) < gerekli:
            item = StokItem.objects.filter(pk=stok_item_id).first()
            kod = item.stok_kodu if item else str(stok_item_id)
            return JsonResponse(
                {
                    "success": False,
                    "error": f"{kod} için stok+üretimde toplamı yetersiz. Mevcut: {mevcut}, Üretimde: {uretimde}, Gerekli: {gerekli}",
                },
                status=400,
            )

    siparis.uretim_durumu = "DEVAM_EDIYOR"
    siparis.teslimat_durumu = "HAZIRLANIYOR"
    siparis.save(update_fields=["uretim_durumu", "teslimat_durumu"])
    return JsonResponse(
        {
            "success": True,
            "message": "Sipariş, mevcut üretimdeki miktardan karşılanmak üzere beklemeye alındı.",
        }
    )


@login_required
def produce_remaining(request, pk):
    """Stoktan karşılanabilen kadar düş, eksik miktar için üretim emri oluştur"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    kalemler = list(SiparisKalemi.objects.filter(siparis=siparis).select_related("stok_item"))
    if not kalemler:
        return JsonResponse({"success": False, "error": "Siparişte ürün bulunmuyor."}, status=400)

    # Aynı ürün birden fazla satırda olabilir; ürün bazında birleştir
    item_map = {}
    for kalem in kalemler:
        key = kalem.stok_item_id
        if key not in item_map:
            item_map[key] = {
                "stok_item": kalem.stok_item,
                "siparis_miktari": Decimal("0"),
            }
        item_map[key]["siparis_miktari"] += Decimal(str(kalem.miktar))

    uretim_map = {}
    stoktan_tam_karsilanan = 0
    with transaction.atomic():
        for data in item_map.values():
            stok_item = StokItem.objects.select_for_update().get(pk=data["stok_item"].pk)
            siparis_miktari = data["siparis_miktari"]
            stok_miktari = Decimal(str(stok_item.mevcut_miktar or 0))
            stoktan_karsilanan = min(stok_miktari, siparis_miktari)
            eksik = siparis_miktari - stoktan_karsilanan

            if stoktan_karsilanan > 0:
                StokHareketi.objects.create(
                    stok_item=stok_item,
                    hareket_tipi="SATIS_STOK",
                    miktar=stoktan_karsilanan,
                    birim=stok_item.birim,
                    referans_no=siparis.siparis_numarasi,
                    aciklama=f"Sipariş {siparis.siparis_numarasi} stoktan kısmi karşılama",
                    user=request.user.username,
                )
            if eksik > 0:
                uretim_map[stok_item.id] = eksik
            elif siparis_miktari > 0:
                stoktan_tam_karsilanan += 1

        if not uretim_map:
            siparis.uretim_durumu = "STOKTAN_SEVK"
            siparis.teslimat_durumu = "HAZIRLANIYOR"
            siparis.save(update_fields=["uretim_durumu", "teslimat_durumu"])
            return JsonResponse({"success": True, "message": "Sipariş tamamen stoktan karşılandı."})

        try:
            result = _siparis_uretim_emri_olustur_core(
                siparis, miktar_override_by_item=uretim_map, auto_start_username=request.user.username
            )
        except SiparisUretimBaslatHatasi as e:
            return JsonResponse({"success": False, "error": e.message}, status=400)
        if not result.get("ok"):
            return JsonResponse({"success": False, "error": result.get("error") or "Kalan üretim oluşturulamadı."}, status=400)
        if not result.get("olusturulan_emirler"):
            return JsonResponse({
                "success": False,
                "error": "Kalan miktar için üretim emri oluşturulamadı. Reçete kontrolü yapın.",
            }, status=400)
        siparis.uretim_durumu = "DEVAM_EDIYOR"
        if stoktan_tam_karsilanan > 0:
            siparis.stok_durumu = "KISMI_STOK"
        siparis.save(update_fields=["uretim_durumu", "stok_durumu"])

    return JsonResponse({
        "success": True,
        "message": "Kalan miktar için üretim emri oluşturuldu ve başlatıldı.",
        "emirler": result.get("olusturulan_emirler", []),
    })


@login_required
def produce_full(request, pk):
    """Siparişin tamamını üret"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek"}, status=405)
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != "ONAYLANDI":
        return JsonResponse({"success": False, "error": "Sadece onaylı siparişlerde işlem yapılabilir."}, status=400)

    try:
        result = _siparis_uretim_emri_olustur_core(siparis, auto_start_username=request.user.username)
    except SiparisUretimBaslatHatasi as e:
        return JsonResponse({"success": False, "error": e.message}, status=400)
    if not result.get("ok"):
        return JsonResponse({"success": False, "error": result.get("error") or "Üretim emri oluşturulamadı."}, status=400)
    if not result.get("olusturulan_emirler"):
        return JsonResponse({
            "success": False,
            "error": "Üretim emri oluşturulamadı. Ürün reçetelerini kontrol edin.",
        }, status=400)
    return JsonResponse({
        "success": True,
        "message": "Siparişin tamamı için üretim emri oluşturuldu ve başlatıldı.",
        "emirler": result.get("olusturulan_emirler", []),
    })


@login_required
def siparis_onayla(request, pk):
    """Onay bekleyen sipariş için müşteri mail alıcı seçim akışına yönlendir."""
    siparis = get_object_or_404(Siparis, pk=pk)
    if siparis.siparis_durumu != 'ONAY_BEKLIYOR':
        messages.warning(request, 'Sadece onay bekleyen siparişler için bu işlem yapılabilir.')
        return redirect('stokapp:siparis_listesi')
    return redirect('stokapp:siparis_onay_mail_alici_sec', pk=pk)


def _siparis_onay_mail_finalize_status(siparis):
    siparis.siparis_durumu = 'ONAYLANDI'
    siparis.red_nedeni = ''
    siparis.red_tarihi = None
    siparis.save(update_fields=['siparis_durumu', 'red_nedeni', 'red_tarihi'])


@login_required
def siparis_onay_mail_alici_sec(request, pk):
    """Sipariş onayı — müşteri yetkililerinden mail alıcı seçimi."""
    siparis = get_object_or_404(
        Siparis.objects.select_related('musteri').prefetch_related('musteri__ilgili_kisiler'),
        pk=pk,
    )
    if siparis.siparis_durumu != 'ONAY_BEKLIYOR':
        messages.warning(request, 'Sadece onay bekleyen siparişler için bu işlem yapılabilir.')
        return redirect('stokapp:siparis_listesi')

    from .satinalma_mail_send import (
        musteri_mail_recipient_choices,
        satinalma_mail_emails_from_keys,
        satinalma_mail_labels_from_keys,
    )

    choices = musteri_mail_recipient_choices(siparis.musteri)

    if request.method == 'POST':
        if request.POST.get('skip_email') == '1':
            request.session.pop(SIPARIS_ONAY_MAIL_SESSION_KEY, None)
            _siparis_onay_mail_finalize_status(siparis)
            messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" onaylandı (e-posta gönderilmedi).')
            return redirect('stokapp:siparis_listesi')

        selected = request.POST.getlist('recipient_key')
        emails = satinalma_mail_emails_from_keys(choices, selected)
        if not emails:
            messages.error(request, 'En az bir alıcı seçin veya «Göndermeden onayla» kullanın.')
            return render(
                request,
                'stokapp/siparis_onay_mail_alici_sec.html',
                {
                    'siparis': siparis,
                    'choices': choices,
                    'preview_ctx': _siparis_onay_mail_template_vars(request, siparis),
                    'no_musteri': siparis.musteri is None,
                },
            )

        labels = satinalma_mail_labels_from_keys(choices, selected)
        request.session[SIPARIS_ONAY_MAIL_SESSION_KEY] = {
            'siparis_pk': siparis.pk,
            'emails': emails,
            'labels': labels,
            'uid': request.user.pk,
        }
        return redirect('stokapp:siparis_onay_mail_onay', pk=pk)

    return render(
        request,
        'stokapp/siparis_onay_mail_alici_sec.html',
        {
            'siparis': siparis,
            'choices': choices,
            'preview_ctx': _siparis_onay_mail_template_vars(request, siparis),
            'no_musteri': siparis.musteri is None,
        },
    )


@login_required
def siparis_onay_mail_onay(request, pk):
    """Sipariş onayı — mail özeti ve gönderim."""
    siparis = get_object_or_404(
        Siparis.objects.select_related('musteri').prefetch_related('musteri__ilgili_kisiler'),
        pk=pk,
    )
    if siparis.siparis_durumu != 'ONAY_BEKLIYOR':
        messages.warning(request, 'Sadece onay bekleyen siparişler için bu işlem yapılabilir.')
        return redirect('stokapp:siparis_listesi')

    data = request.session.get(SIPARIS_ONAY_MAIL_SESSION_KEY)
    if not data or data.get('uid') != request.user.pk or data.get('siparis_pk') != siparis.pk:
        messages.error(request, 'Oturum süresi doldu. Alıcı seçimini yeniden yapın.')
        return redirect('stokapp:siparis_onay_mail_alici_sec', pk=pk)

    from .satinalma_mail_send import musteri_mail_recipient_choices, satinalma_mail_normalize_to_allowed

    choices = musteri_mail_recipient_choices(siparis.musteri)
    emails = list(data['emails'])
    labels = list(data['labels'])
    allowed = satinalma_mail_normalize_to_allowed(emails, choices)

    preview_ctx = _siparis_onay_mail_template_vars(request, siparis)
    ctx = {
        'siparis': siparis,
        'labels': labels,
        'emails_invalid': not allowed,
        'preview_ctx': preview_ctx,
        'geri_url': reverse('stokapp:siparis_onay_mail_alici_sec', kwargs={'pk': pk}),
    }

    if request.method == 'POST':
        if not allowed:
            del request.session[SIPARIS_ONAY_MAIL_SESSION_KEY]
            messages.error(request, 'Seçilen adresler güncel müşteri listesiyle eşleşmiyor. Yeniden seçin.')
            return redirect('stokapp:siparis_onay_mail_alici_sec', pk=pk)

        try:
            _siparis_onay_mail_send(request, siparis, allowed)
        except Exception as exc:
            messages.error(request, str(exc))
            return render(request, 'stokapp/siparis_onay_mail_onay.html', ctx)

        del request.session[SIPARIS_ONAY_MAIL_SESSION_KEY]
        _siparis_onay_mail_finalize_status(siparis)
        messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" onaylandı ve e-posta gönderildi.')
        return redirect('stokapp:siparis_listesi')

    return render(request, 'stokapp/siparis_onay_mail_onay.html', ctx)


@login_required
def siparis_reddet(request, pk):
    """Siparişi red durumuna al"""
    siparis = get_object_or_404(Siparis, pk=pk)
    if request.method == 'POST':
        red_nedeni = (request.POST.get('red_nedeni') or '').strip()
        if not red_nedeni:
            messages.error(request, 'Red nedeni girilmelidir.')
            return redirect('stokapp:siparis_listesi')
        siparis.siparis_durumu = 'RED'
        siparis.red_nedeni = red_nedeni
        siparis.red_tarihi = timezone.now()
        siparis.save(update_fields=['siparis_durumu', 'red_nedeni', 'red_tarihi'])
        messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" reddedildi.')
    return redirect('stokapp:siparis_listesi')


@login_required
def siparis_teslim_et(request, pk):
    """Üretimi tamamlanan siparişi teslim edildiye taşı"""
    siparis = get_object_or_404(Siparis, pk=pk)
    if request.method == 'POST':
        if siparis.siparis_durumu == 'TESLIM_EDILDI':
            messages.warning(request, 'Sipariş zaten teslim edilmiş.')
            return redirect('stokapp:siparis_listesi')

        if siparis.uretim_durumu not in ['TAMAMLANDI', 'STOKTAN_SEVK']:
            messages.error(request, 'Sadece üretimi tamamlanan veya stoktan sevke alınan siparişler teslim edilebilir.')
            return redirect('stokapp:siparis_listesi')

        kalemler = SiparisKalemi.objects.filter(siparis=siparis).select_related('stok_item')
        if not kalemler.exists():
            messages.error(request, 'Siparişte ürün bulunamadı.')
            return redirect('stokapp:siparis_listesi')

        # Aynı ürün tekrar ediyorsa toplam teslim miktarını birleştir
        siparis_toplam_map = _siparis_kalem_toplam_map(siparis)
        stoktan_dusulen_map = _siparis_stoktan_dusulen_map(siparis)
        teslim_map = {}
        for stok_item_id, siparis_miktari in siparis_toplam_map.items():
            daha_once_stoktan = stoktan_dusulen_map.get(stok_item_id, Decimal("0"))
            kalan_teslim = siparis_miktari - daha_once_stoktan
            if kalan_teslim > 0:
                teslim_map[stok_item_id] = kalan_teslim

        # Stok yeterlilik kontrolü (daha önce stoktan düşülen kısım hariç)
        for stok_item_id, teslim_miktari in teslim_map.items():
            item = StokItem.objects.get(pk=stok_item_id)
            if item.mevcut_miktar < teslim_miktari:
                messages.error(
                    request,
                    f'{item.stok_kodu} için stok yetersiz. Mevcut: {item.mevcut_miktar}, Teslim edilecek: {teslim_miktari}'
                )
                return redirect('stokapp:siparis_listesi')

        with transaction.atomic():
            # Teslim edilen miktarı stoktan düş
            for stok_item_id, teslim_miktari in teslim_map.items():
                item = StokItem.objects.get(pk=stok_item_id)
                StokHareketi.objects.create(
                    stok_item=item,
                    hareket_tipi='CIKIS',
                    miktar=teslim_miktari,
                    birim=item.birim,
                    referans_no=siparis.siparis_numarasi,
                    aciklama=f'Sipariş {siparis.siparis_numarasi} teslimatı',
                    user=request.user.username
                )

            siparis.teslimat_durumu = 'TESLIM_EDILDI'
            siparis.siparis_durumu = 'TESLIM_EDILDI'
            siparis.save(update_fields=['teslimat_durumu', 'siparis_durumu'])

        messages.success(request, f'Sipariş "{siparis.siparis_numarasi}" teslim edildi olarak işaretlendi.')
    return_tab = (request.POST.get('return_tab') or '').strip()
    if return_tab:
        return redirect(f"{reverse('stokapp:siparis_listesi')}?tab={return_tab}")
    return redirect('stokapp:siparis_listesi')


@login_required
def siparis_maliyetleri(request, pk):
    """Sipariş maliyetleri listesi"""
    siparis = get_object_or_404(Siparis, pk=pk)
    maliyetler = SiparisMaliyeti.objects.filter(siparis=siparis).order_by('maliyet_tipi', 'kayit_tarihi', 'id')
    
    # Toplamlar
    malzeme_toplam = maliyetler.filter(maliyet_tipi='MALZEME').aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
    operasyon_toplam = maliyetler.filter(maliyet_tipi='OPERASYON').aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
    genel_toplam = malzeme_toplam + operasyon_toplam
    
    context = {
        'siparis': siparis,
        'maliyetler': maliyetler,
        'malzeme_toplam': malzeme_toplam,
        'operasyon_toplam': operasyon_toplam,
        'genel_toplam': genel_toplam,
    }
    return render(request, 'stokapp/siparis_maliyetleri.html', context)


@login_required
@never_cache
def siparis_maliyetleri_export_pdf(request, pk):
    siparis = get_object_or_404(Siparis, pk=pk)
    maliyetler = SiparisMaliyeti.objects.filter(siparis=siparis).order_by('maliyet_tipi', 'kayit_tarihi', 'id')
    malzeme_toplam = maliyetler.filter(maliyet_tipi='MALZEME').aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
    operasyon_toplam = maliyetler.filter(maliyet_tipi='OPERASYON').aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
    genel_toplam = malzeme_toplam + operasyon_toplam

    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:siparis_maliyetleri', pk=pk)

    from django.template.loader import get_template
    olusturma_tarihi = timezone.localtime(timezone.now())
    template = get_template('stokapp/siparis_maliyetleri_pdf.html')
    html = template.render({
        'siparis': siparis,
        'maliyetler': maliyetler,
        'malzeme_toplam': malzeme_toplam,
        'operasyon_toplam': operasyon_toplam,
        'genel_toplam': genel_toplam,
        'olusturma_tarihi': olusturma_tarihi,
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
        .totals { margin-top: 8px; font-size: 9pt; }
        .empty { text-align: center; color: #6b7280; padding: 24px; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:siparis_maliyetleri', pk=pk)

    filename = f'siparis_maliyetleri_{siparis.siparis_numarasi}_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@never_cache
def teslimat_bekleyen_kalemleri_export_pdf(request):
    """Teslimat bekleyen ürün kalemleri listesini PDF olarak indirir."""
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect(f"{reverse('stokapp:siparis_listesi')}?tab=teslimat_bekleyen_kalemleri")

    from django.template.loader import get_template

    rows = _build_teslimat_bekleyen_kalem_rows()
    olusturma_tarihi = timezone.localtime(timezone.now())
    ayarlar = GenelAyarlar.get_ayarlar()

    template = get_template('stokapp/teslimat_bekleyen_kalemleri_pdf.html')
    html = template.render({
        'rows': rows,
        'kayit_sayisi': len(rows),
        'olusturma_tarihi': olusturma_tarihi,
        'firma_ismi': ayarlar.firma_ismi or '',
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
        .highlight { font-weight: 600; color: #0369a1; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(stylesheets=[css])
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect(f"{reverse('stokapp:siparis_listesi')}?tab=teslimat_bekleyen_kalemleri")

    filename = f'teslimat_bekleyen_urunler_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def siparis_maliyeti_duzenle(request, pk, maliyet_id):
    """Sipariş maliyeti düzenle"""
    siparis = get_object_or_404(Siparis, pk=pk)
    maliyet = get_object_or_404(SiparisMaliyeti, pk=maliyet_id, siparis=siparis)
    
    if request.method == 'POST':
        form = SiparisMaliyetiForm(request.POST, instance=maliyet)
        if form.is_valid():
            maliyet = form.save()
            messages.success(request, f'Maliyet başarıyla güncellendi.')
            return redirect('stokapp:siparis_maliyetleri', pk=siparis.pk)
    else:
        form = SiparisMaliyetiForm(instance=maliyet)
    
    context = {
        'siparis': siparis,
        'maliyet': maliyet,
        'form': form,
    }
    return render(request, 'stokapp/siparis_maliyeti_duzenle.html', context)


@login_required
def siparis_maliyeti_sil(request, pk, maliyet_id):
    """Sipariş maliyeti sil"""
    siparis = get_object_or_404(Siparis, pk=pk)
    maliyet = get_object_or_404(SiparisMaliyeti, pk=maliyet_id, siparis=siparis)
    
    if request.method == 'POST':
        maliyet.delete()
        messages.success(request, 'Maliyet başarıyla silindi.')
        return redirect('stokapp:siparis_maliyetleri', pk=siparis.pk)
    
    context = {
        'siparis': siparis,
        'maliyet': maliyet,
    }
    return render(request, 'stokapp/siparis_maliyeti_sil.html', context)


@login_required
def siparis_maliyetleri_listesi(request):
    """Tamamlanan siparişlerin maliyet listesi"""
    # Sadece tamamlanan siparişleri getir
    siparisler = Siparis.objects.filter(siparis_durumu='TESLIM_EDILDI').order_by('-olusturulma_tarihi')
    
    # Arama filtresi
    arama = request.GET.get('arama', '')
    if arama:
        siparisler = siparisler.filter(
            Q(siparis_numarasi__icontains=arama) |
            Q(musteri_adi__icontains=arama) |
            Q(musteri__ad__icontains=arama)
        )
    
    # Sayfalama
    paginator = Paginator(siparisler, 20)
    page = request.GET.get('page', 1)
    siparisler_page = paginator.get_page(page)
    
    # Her sipariş için toplam maliyet hesapla
    siparisler_with_costs = []
    for siparis in siparisler_page:
        maliyetler = SiparisMaliyeti.objects.filter(siparis=siparis)
        toplam_maliyet = maliyetler.aggregate(Sum('toplam'))['toplam__sum'] or Decimal('0')
        maliyet_sayisi = maliyetler.count()
        
        siparisler_with_costs.append({
            'siparis': siparis,
            'toplam_maliyet': toplam_maliyet,
            'maliyet_sayisi': maliyet_sayisi,
        })
    
    context = {
        'siparisler_with_costs': siparisler_with_costs,
        'siparisler': siparisler_page,
        'arama': arama,
    }
    return render(request, 'stokapp/siparis_maliyetleri_listesi.html', context)
