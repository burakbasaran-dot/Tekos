"""Satınalma RFQ (Teklif Talebi) görünümleri.

Bu modül "Yeni Teklif Talebi → Tedarikçilere Gönder (BCC) → Teklif Girişi →
Karşılaştırma → Siparişe Dönüştür" akışının view katmanını içerir.

Not: Bu dosya kasıtlı olarak `views_satinalma.py`'dan ayrı tutulmuştur,
çünkü mevcut dosya 2000+ satır ve karıştırmak istemedik.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from collections import defaultdict, OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Kategori,
    ParaBirimi,
    Satinalma,
    SatinalmaKalemi,
    Siparis,
    StokItem,
    Tedarikci,
    TeklifTalebi,
    TeklifTalebiKalemi,
    TeklifTalebiTedarikci,
    TedarikciTeklifKalemi,
)


SATINALMA_RFQ_MAIL_WIZARD_KEY = "satinalma_rfq_mail_wizard"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _decimal_or_none(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_miktar_display(value) -> str:
    """Tam sayıda .000 gizler; ondalıklıda trailing zero temizler."""
    num = value if isinstance(value, Decimal) else _decimal_or_none(value)
    if num is None:
        return ""
    if num == num.to_integral_value():
        return str(int(num))
    return f"{num:.10f}".rstrip("0").rstrip(".")


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value, default=None):
    if not value:
        return default
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _kategori_ids_from_kalemler(rfq):
    ids = set()
    for kalem in rfq.kalemler.all():
        if kalem.stok_item and kalem.stok_item.kategori_id:
            ids.add(kalem.stok_item.kategori_id)
    return ids


def _onerilen_tedarikciler(rfq):
    kat_ids = _kategori_ids_from_kalemler(rfq)
    if not kat_ids:
        return Tedarikci.objects.none()
    return (
        Tedarikci.objects.filter(aktif=True, kategoriler__in=kat_ids)
        .distinct()
        .prefetch_related("kategoriler", "ilgili_kisiler")
        .order_by("ad")
    )


def _rfq_durum_yenile(rfq):
    """Tüm bağlı tedarikçilerden teklif girişi yapıldıysa DEGERLENDIRMEDE'ye geçir."""
    bag_qs = rfq.tedarikci_baglantilari.exclude(durum="IPTAL")
    if not bag_qs.exists():
        return
    if all(b.durum == "TEKLIF_GIRDI" for b in bag_qs) and rfq.durum == "TEKLIF_BEKLENIYOR":
        rfq.durum = "DEGERLENDIRMEDE"
        rfq.save(update_fields=["durum", "updated_at"])


def _kazanan_secimi_temizle(rfq):
    TedarikciTeklifKalemi.objects.filter(
        rfq_tedarikci__rfq=rfq, secildi=True
    ).update(secildi=False)


# Basit kur dönüşümü; gelişmiş tarihli kur entegrasyonu sonraya bırakıldı.
DEFAULT_KUR_TABLOSU = {
    "TRY": Decimal("1"),
    "TL": Decimal("1"),
    "USD": Decimal("34"),
    "EUR": Decimal("37"),
    "GBP": Decimal("43"),
}


def _aktif_kur_tablosu():
    """ParaBirimi tablosundan aktif kurları al; yoksa varsayılan tabloya düş.

    ParaBirimi modelinde 'kur' alanı yoksa varsayılan tabloya düşeriz; bu
    proje genelinde gerçek kur entegrasyonu (TCMB) ileride eklenebilir.
    """
    out = dict(DEFAULT_KUR_TABLOSU)
    try:
        for pb in ParaBirimi.objects.filter(aktif=True):
            try:
                kur_raw = getattr(pb, "kur", None)
                if kur_raw is None:
                    continue
                kur = Decimal(str(kur_raw))
                kod = (pb.kod or "").strip().upper()
                if kod and kur > 0:
                    out[kod] = kur
            except Exception:
                continue
    except Exception:
        pass
    if "TRY" not in out:
        out["TRY"] = Decimal("1")
    if "TL" not in out:
        out["TL"] = out["TRY"]
    return out


def _try_karsiligi(birim_fiyat, para_birimi, kur_tablosu):
    if birim_fiyat is None:
        return None
    pb = (para_birimi or "TRY").upper()
    if pb in ("TRY", "TL"):
        return Decimal(str(birim_fiyat))
    kur = kur_tablosu.get(pb)
    if not kur:
        return Decimal(str(birim_fiyat))
    return Decimal(str(birim_fiyat)) * Decimal(str(kur))


# ---------------------------------------------------------------------------
# RFQ CRUD
# ---------------------------------------------------------------------------


@login_required
def rfq_olustur(request):
    """Yeni RFQ oluştur (Talep'ten de gelinebilir)."""
    return _rfq_form(request, rfq=None)


@login_required
def rfq_duzenle(request, pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    if rfq.durum not in ("TASLAK", "TEKLIF_BEKLENIYOR"):
        messages.warning(
            request,
            "Bu RFQ artık düzenlenemez (sipariş aşamasına geçmiş).",
        )
        return redirect("stokapp:rfq_detay", pk=rfq.pk)
    return _rfq_form(request, rfq=rfq)


def _rfq_form(request, rfq):
    is_new = rfq is None
    source_siparis_id = request.POST.get("source_siparis") or request.GET.get("source_siparis")
    kaynak_siparis = None
    if source_siparis_id:
        try:
            kaynak_siparis = Siparis.objects.filter(pk=int(source_siparis_id)).first()
        except (TypeError, ValueError):
            kaynak_siparis = None

    if request.method == "POST":
        baslik = (request.POST.get("baslik") or "").strip()
        olusturma_tarihi = _parse_date(
            request.POST.get("olusturma_tarihi"), timezone.now().date()
        )
        son_teklif_tarihi = _parse_date(request.POST.get("son_teklif_tarihi"))
        oncelik = (request.POST.get("oncelik") or "FIYAT").upper()
        if oncelik not in ("FIYAT", "TERMIN"):
            oncelik = "FIYAT"
        para_birimi = (request.POST.get("para_birimi") or "TRY").upper()
        notlar = (request.POST.get("notlar") or "").strip()

        try:
            kalemler_data = json.loads(request.POST.get("kalemler", "[]"))
        except json.JSONDecodeError:
            kalemler_data = []
        if not isinstance(kalemler_data, list):
            kalemler_data = []

        if not baslik:
            messages.error(request, "Başlık zorunlu.")
        elif not kalemler_data:
            messages.error(request, "En az bir kalem eklemelisiniz.")
        else:
            try:
                with transaction.atomic():
                    if rfq is None:
                        rfq = TeklifTalebi(olusturma_tarihi=olusturma_tarihi)
                    if is_new:
                        rfq.kaynak_siparis = kaynak_siparis
                    rfq.baslik = baslik
                    rfq.olusturma_tarihi = olusturma_tarihi
                    rfq.son_teklif_tarihi = son_teklif_tarihi
                    rfq.oncelik = oncelik
                    rfq.para_birimi = para_birimi
                    rfq.notlar = notlar
                    if is_new and request.user.is_authenticated:
                        rfq.olusturan = request.user
                    if is_new and rfq.durum == "TASLAK":
                        # taslakta başlat; gönderilince TEKLIF_BEKLENIYOR'a geçer
                        pass
                    rfq.save()

                    # Kalemleri yeniden yaz (basit ve güvenli)
                    rfq.kalemler.all().delete()
                    sira = 0
                    for k in kalemler_data:
                        if not isinstance(k, dict):
                            continue
                        ad = (k.get("kalem_adi") or "").strip()
                        if not ad:
                            continue
                        stok_pk = k.get("stok_item") or None
                        stok = None
                        if stok_pk:
                            try:
                                stok = StokItem.objects.get(pk=stok_pk)
                            except StokItem.DoesNotExist:
                                stok = None
                        miktar = _decimal_or_none(k.get("miktar")) or Decimal("1")
                        TeklifTalebiKalemi.objects.create(
                            rfq=rfq,
                            stok_item=stok,
                            kalem_adi=ad[:300],
                            miktar=miktar,
                            birim=(k.get("birim") or (stok.birim if stok else "Adet"))[:20],
                            teknik_notlar=(k.get("teknik_notlar") or "")[:5000],
                            istenen_termin=_parse_date(k.get("istenen_termin")),
                            sira=sira,
                        )
                        sira += 1

                messages.success(request, f'Teklif Talebi "{rfq.rfq_no}" kaydedildi.')
                if request.POST.get("save_and_send"):
                    return redirect("stokapp:rfq_mail_alici_sec", pk=rfq.pk)
                return redirect("stokapp:rfq_detay", pk=rfq.pk)
            except Exception as exc:  # pragma: no cover - kullanıcıya gösterim
                messages.error(request, f"Hata: {exc}")

    # GET
    stok_items = StokItem.objects.filter(arsivli=False).order_by("ad")[:5000]
    if rfq:
        kalemler_initial = [
            {
                "kalem_adi": k.kalem_adi,
                "stok_item": k.stok_item_id,
                "miktar": _format_miktar_display(k.miktar),
                "birim": k.birim,
                "teknik_notlar": k.teknik_notlar,
                "istenen_termin": k.istenen_termin.isoformat() if k.istenen_termin else "",
            }
            for k in rfq.kalemler.all()
        ]
    else:
        kalemler_initial = []
        # Üretim malzemesi planlama ekranından prefill desteği
        if request.GET.get("planlama") == "1":
            idx = 0
            while request.GET.get(f"malzeme_{idx}") is not None:
                stok_item_id = request.GET.get(f"malzeme_{idx}")
                miktar = request.GET.get(f"miktar_{idx}", "1")
                try:
                    stok = StokItem.objects.get(pk=stok_item_id)
                    kalemler_initial.append(
                        {
                            "kalem_adi": stok.ad,
                            "stok_item": stok.pk,
                            "miktar": _format_miktar_display(_decimal_or_none(miktar) or Decimal("1")),
                            "birim": stok.birim or "Adet",
                            "teknik_notlar": "",
                            "istenen_termin": "",
                        }
                    )
                except (StokItem.DoesNotExist, TypeError, ValueError):
                    pass
                idx += 1

    olusturma_ref = rfq.olusturma_tarihi if rfq else timezone.now().date()
    if rfq and rfq.son_teklif_tarihi:
        default_son_teklif_tarihi = rfq.son_teklif_tarihi.isoformat()
    else:
        default_son_teklif_tarihi = (olusturma_ref + timedelta(days=1)).isoformat()

    context = {
        "rfq": rfq,
        "is_new": is_new,
        "stok_items": stok_items,
        "kalemler_initial_json": json.dumps(kalemler_initial, ensure_ascii=False),
        "default_olusturma_tarihi": (
            rfq.olusturma_tarihi.isoformat() if rfq else timezone.now().date().isoformat()
        ),
        "default_son_teklif_tarihi": default_son_teklif_tarihi,
        "default_baslik": (
            rfq.baslik
            if rfq
            else (
                f"Üretim Malzemesi Teklif Talebi - {timezone.now().date().strftime('%d.%m.%Y')}"
                if request.GET.get("planlama") == "1"
                else ""
            )
        ),
        "source_siparis_id": kaynak_siparis.pk if (is_new and kaynak_siparis) else "",
    }
    return render(request, "stokapp/rfq_form.html", context)


@login_required
def rfq_detay(request, pk):
    rfq = get_object_or_404(
        TeklifTalebi.objects.prefetch_related(
            "kalemler",
            Prefetch(
                "tedarikci_baglantilari",
                queryset=TeklifTalebiTedarikci.objects.select_related("tedarikci"),
            ),
        ),
        pk=pk,
    )
    onerilen = _onerilen_tedarikciler(rfq)
    secilmis_tedarikci_ids = set(
        rfq.tedarikci_baglantilari.exclude(tedarikci__isnull=True).values_list(
            "tedarikci_id", flat=True
        )
    )
    onerilen_listesi = [
        {
            "tedarikci": t,
            "secili": t.pk in secilmis_tedarikci_ids,
        }
        for t in onerilen
    ]
    context = {
        "rfq": rfq,
        "onerilen_listesi": onerilen_listesi,
        "kalem_count": rfq.kalemler.count(),
        "tedarikci_count": rfq.tedarikci_baglantilari.exclude(durum="IPTAL").count(),
    }
    return render(request, "stokapp/rfq_detay.html", context)


@login_required
@require_POST
def rfq_sil(request, pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    if rfq.durum == "SIPARISE_DONUSTURULDU":
        messages.error(request, "Siparişe dönüştürülmüş bir RFQ silinemez.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)
    no = rfq.rfq_no
    rfq.delete()
    messages.success(request, f"{no} silindi.")
    return redirect("stokapp:satinalma_listesi")


# ---------------------------------------------------------------------------
# Tedarikçi öneri AJAX
# ---------------------------------------------------------------------------


@login_required
def rfq_oneri_tedarikciler_api(request):
    """Verilen StokItem ID'lerine göre kategori eşleşen tedarikçileri döner."""
    raw_ids = request.GET.get("stok_ids", "")
    ids = [s for s in (x.strip() for x in raw_ids.split(",")) if s.isdigit()]
    if not ids:
        return JsonResponse({"tedarikciler": []})
    kat_ids = set(
        StokItem.objects.filter(pk__in=ids).values_list("kategori_id", flat=True)
    )
    kat_ids = {k for k in kat_ids if k}
    if not kat_ids:
        return JsonResponse({"tedarikciler": []})
    qs = (
        Tedarikci.objects.filter(aktif=True, kategoriler__in=kat_ids)
        .distinct()
        .prefetch_related("kategoriler")
        .order_by("ad")
    )
    out = [
        {
            "id": t.pk,
            "ad": t.ad,
            "email": t.email or "",
            "kategoriler": [k.ad for k in t.kategoriler.all()],
        }
        for t in qs
    ]
    return JsonResponse({"tedarikciler": out})


# ---------------------------------------------------------------------------
# RFQ Mail Wizard (BCC)
# ---------------------------------------------------------------------------


@login_required
def rfq_mail_alici_sec(request, pk):
    """Tedarikçi seçimi + harici mail eklemenin yapıldığı ekran."""
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    if rfq.kalemler.count() == 0:
        messages.error(request, "Önce en az bir kalem ekleyin.")
        return redirect("stokapp:rfq_duzenle", pk=rfq.pk)
    onerilen = _onerilen_tedarikciler(rfq)
    diger = (
        Tedarikci.objects.filter(aktif=True)
        .exclude(pk__in=[t.pk for t in onerilen])
        .order_by("ad")
    )
    secilmis_tedarikci_ids = set(
        rfq.tedarikci_baglantilari.exclude(tedarikci__isnull=True).values_list(
            "tedarikci_id", flat=True
        )
    )
    secilmis_ilgili_keys = set()
    onerilen_listesi = []
    for t in list(onerilen) + list(diger):
        kisiler = []
        for k in t.ilgili_kisiler.all():
            em = (k.email or "").strip()
            if not em:
                continue
            kisiler.append({
                "key": f"ilgili-{k.pk}",
                "ad": k.ad_soyad,
                "gorev": k.gorev,
                "email": em,
            })
        onerilen_listesi.append({
            "tedarikci": t,
            "kategoriler": list(t.kategoriler.all()),
            "secili": t.pk in secilmis_tedarikci_ids,
            "kisiler": kisiler,
            "onerilen": t in onerilen,
        })

    # Mevcut harici mailler
    harici_mevcut = list(
        rfq.tedarikci_baglantilari.filter(tedarikci__isnull=True)
        .exclude(durum="IPTAL")
        .values("harici_ad", "harici_email")
    )

    context = {
        "rfq": rfq,
        "tedarikci_listesi": onerilen_listesi,
        "harici_mevcut_json": json.dumps(harici_mevcut, ensure_ascii=False),
    }
    return render(request, "stokapp/rfq_mail_alici_sec.html", context)


@login_required
@require_POST
def rfq_mail_gonder(request, pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    if rfq.kalemler.count() == 0:
        messages.error(request, "Önce en az bir kalem ekleyin.")
        return redirect("stokapp:rfq_duzenle", pk=rfq.pk)

    secili_tedarikci_ids = request.POST.getlist("tedarikci_ids")
    secili_tedarikci_ids = [int(x) for x in secili_tedarikci_ids if x.isdigit()]
    try:
        harici_listesi = json.loads(request.POST.get("harici_mailler", "[]"))
    except json.JSONDecodeError:
        harici_listesi = []
    if not isinstance(harici_listesi, list):
        harici_listesi = []

    # Toplam alıcılar
    secili_tedarikciler = list(
        Tedarikci.objects.filter(pk__in=secili_tedarikci_ids).prefetch_related(
            "ilgili_kisiler"
        )
    )

    # Hangi maillere gönderilecek?
    bcc_emails = []
    seen = set()

    def _ekle(em):
        em = (em or "").strip()
        if not em:
            return
        low = em.lower()
        if low in seen:
            return
        seen.add(low)
        bcc_emails.append(em)

    for t in secili_tedarikciler:
        if t.email:
            _ekle(t.email)
        # Bu tedarikçi için seçilen ilgili kişi mailleri
        secili_ilgili_keys = set(
            request.POST.getlist(f"tedarikci_{t.pk}_ilgili")
        )
        for kisi in t.ilgili_kisiler.all():
            key = f"ilgili-{kisi.pk}"
            if key in secili_ilgili_keys and kisi.email:
                _ekle(kisi.email)

    harici_kaydedilecek = []
    for h in harici_listesi:
        if not isinstance(h, dict):
            continue
        em = (h.get("email") or "").strip()
        if not em:
            continue
        ad = (h.get("ad") or "").strip()
        _ekle(em)
        harici_kaydedilecek.append({"ad": ad, "email": em})

    if not bcc_emails:
        messages.error(request, "En az bir alıcı seçmelisiniz (firma, ilgili kişi veya harici mail).")
        return redirect("stokapp:rfq_mail_alici_sec", pk=rfq.pk)

    try:
        with transaction.atomic():
            # 1) Tedarikçi bağlantılarını oluştur (henüz yoksa)
            for t in secili_tedarikciler:
                bag, _ = TeklifTalebiTedarikci.objects.get_or_create(
                    rfq=rfq,
                    tedarikci=t,
                    defaults={"durum": "BEKLIYOR", "mail_gonderildi": True},
                )
                bag.mail_gonderildi = True
                bag.gonderim_tarihi = timezone.now()
                if bag.durum == "IPTAL":
                    bag.durum = "BEKLIYOR"
                bag.save()
                _ensure_bos_teklif_kalemleri(bag, rfq)

            # 2) Harici mailler için ayrı bağlantı
            for h in harici_kaydedilecek:
                bag, _ = TeklifTalebiTedarikci.objects.get_or_create(
                    rfq=rfq,
                    tedarikci=None,
                    harici_email=h["email"][:254],
                    defaults={
                        "harici_ad": h["ad"][:200],
                        "durum": "BEKLIYOR",
                        "mail_gonderildi": True,
                    },
                )
                if h["ad"]:
                    bag.harici_ad = h["ad"][:200]
                bag.mail_gonderildi = True
                bag.gonderim_tarihi = timezone.now()
                if bag.durum == "IPTAL":
                    bag.durum = "BEKLIYOR"
                bag.save()
                _ensure_bos_teklif_kalemleri(bag, rfq)

            # 3) RFQ durumunu yenile
            if rfq.durum in ("TASLAK", "TEKLIF_BEKLENIYOR"):
                rfq.durum = "TEKLIF_BEKLENIYOR"
                rfq.save(update_fields=["durum", "updated_at"])

        # 4) Mail gönder (transaction dışında — mail başarısız olsa bile DB tutarlı kalır)
        from .satinalma_mail_send import send_rfq_mail
        send_rfq_mail(request, rfq, bcc_emails)
        messages.success(
            request,
            f"{rfq.rfq_no} için {len(bcc_emails)} alıcıya BCC ile teklif talebi gönderildi.",
        )
    except Exception as exc:
        messages.error(request, f"Mail gönderilirken hata: {exc}")
        return redirect("stokapp:rfq_mail_alici_sec", pk=rfq.pk)

    return redirect("stokapp:rfq_detay", pk=rfq.pk)


def _ensure_bos_teklif_kalemleri(rfq_tedarikci, rfq):
    """RFQ kalemleri için boş TedarikciTeklifKalemi kayıtlarını hazırla."""
    mevcut_ids = set(
        TedarikciTeklifKalemi.objects.filter(rfq_tedarikci=rfq_tedarikci).values_list(
            "rfq_kalemi_id", flat=True
        )
    )
    for k in rfq.kalemler.all():
        if k.pk in mevcut_ids:
            continue
        TedarikciTeklifKalemi.objects.create(
            rfq_tedarikci=rfq_tedarikci,
            rfq_kalemi=k,
            birim_fiyat=None,
            para_birimi=rfq.para_birimi or "TRY",
            teslim_suresi_gun=None,
        )


# ---------------------------------------------------------------------------
# Teklif Girişi
# ---------------------------------------------------------------------------


@login_required
def rfq_teklif_girisi(request, pk, rfq_tedarikci_pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    bag = get_object_or_404(
        TeklifTalebiTedarikci, pk=rfq_tedarikci_pk, rfq=rfq
    )
    _ensure_bos_teklif_kalemleri(bag, rfq)
    teklif_kalemleri = (
        TedarikciTeklifKalemi.objects.filter(rfq_tedarikci=bag)
        .select_related("rfq_kalemi", "rfq_kalemi__stok_item")
        .order_by("rfq_kalemi__sira", "rfq_kalemi_id")
    )

    if request.method == "POST":
        try:
            rows = json.loads(request.POST.get("kalemler", "[]"))
        except json.JSONDecodeError:
            rows = []
        if not isinstance(rows, list):
            rows = []
        try:
            with transaction.atomic():
                herhangi_giris = False
                kalem_map = {tk.pk: tk for tk in teklif_kalemleri}
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    pk_id = row.get("id")
                    tk = kalem_map.get(pk_id)
                    if not tk:
                        continue
                    fiyat = _decimal_or_none(row.get("birim_fiyat"))
                    pb = (row.get("para_birimi") or rfq.para_birimi or "TRY").upper()
                    if pb not in dict(TedarikciTeklifKalemi.PARA_BIRIMLERI):
                        pb = "TRY"
                    sure = _int_or_none(row.get("teslim_suresi_gun"))
                    teslim_t = _parse_date(row.get("teslim_tarihi"))
                    notu = (row.get("notlar") or "")[:5000]

                    tk.birim_fiyat = fiyat
                    tk.para_birimi = pb
                    tk.teslim_suresi_gun = sure
                    tk.teslim_tarihi = teslim_t
                    tk.notlar = notu
                    tk.girildi_mi = bool(fiyat is not None or sure is not None)
                    if tk.girildi_mi:
                        herhangi_giris = True
                    tk.save()

                if herhangi_giris:
                    bag.durum = "TEKLIF_GIRDI"
                    bag.notlar = (request.POST.get("genel_not") or "").strip()
                    bag.save(update_fields=["durum", "notlar"])
                _rfq_durum_yenile(rfq)
            messages.success(request, "Teklif girişi kaydedildi.")
            return redirect("stokapp:rfq_detay", pk=rfq.pk)
        except Exception as exc:
            messages.error(request, f"Hata: {exc}")

    para_birimleri = list(TedarikciTeklifKalemi.PARA_BIRIMLERI)
    initial = [
        {
            "id": tk.pk,
            "kalem_adi": tk.rfq_kalemi.kalem_adi,
            "miktar": _format_miktar_display(tk.rfq_kalemi.miktar),
            "birim": tk.rfq_kalemi.birim,
            "stok_kodu": tk.rfq_kalemi.stok_item.stok_kodu if tk.rfq_kalemi.stok_item else "",
            "teknik_notlar": tk.rfq_kalemi.teknik_notlar,
            "istenen_termin": tk.rfq_kalemi.istenen_termin.isoformat()
            if tk.rfq_kalemi.istenen_termin
            else "",
            "birim_fiyat": str(tk.birim_fiyat) if tk.birim_fiyat is not None else "",
            "para_birimi": tk.para_birimi,
            "teslim_suresi_gun": tk.teslim_suresi_gun if tk.teslim_suresi_gun is not None else "",
            "teslim_tarihi": tk.teslim_tarihi.isoformat() if tk.teslim_tarihi else "",
            "notlar": tk.notlar or "",
        }
        for tk in teklif_kalemleri
    ]
    context = {
        "rfq": rfq,
        "bag": bag,
        "para_birimleri": para_birimleri,
        "kalemler_initial_json": json.dumps(initial, ensure_ascii=False),
        "genel_not": bag.notlar or "",
    }
    return render(request, "stokapp/rfq_teklif_girisi.html", context)


# ---------------------------------------------------------------------------
# Karşılaştırma
# ---------------------------------------------------------------------------


@login_required
def rfq_karsilastirma(request, pk):
    rfq = get_object_or_404(
        TeklifTalebi.objects.prefetch_related(
            "kalemler",
            Prefetch(
                "tedarikci_baglantilari",
                queryset=TeklifTalebiTedarikci.objects.exclude(durum="IPTAL").select_related(
                    "tedarikci"
                ),
            ),
        ),
        pk=pk,
    )
    if rfq.durum in ("TASLAK",):
        messages.warning(request, "Karşılaştırma için en az bir teklif girmiş olmanız gerekir.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)

    kalemler = list(rfq.kalemler.all())
    bags = list(rfq.tedarikci_baglantilari.all())
    teklifler = (
        TedarikciTeklifKalemi.objects.filter(rfq_tedarikci__in=bags)
        .select_related("rfq_tedarikci", "rfq_kalemi")
    )
    teklif_map = {(t.rfq_tedarikci_id, t.rfq_kalemi_id): t for t in teklifler}

    kur = _aktif_kur_tablosu()

    # Her kalem için min fiyat ve min termin tedarikçi bul
    matrix = []
    for k in kalemler:
        row = {
            "kalem": k,
            "hucreler": [],
            "min_fiyat_try": None,
            "min_termin": None,
            "min_fiyat_bag_id": None,
            "min_termin_bag_id": None,
        }
        for bag in bags:
            tk = teklif_map.get((bag.pk, k.pk))
            try_karsilik = None
            if tk and tk.birim_fiyat is not None:
                try_karsilik = _try_karsiligi(tk.birim_fiyat, tk.para_birimi, kur)
            row["hucreler"].append({
                "bag": bag,
                "tk": tk,
                "try_karsilik": try_karsilik,
            })
            if try_karsilik is not None:
                if (row["min_fiyat_try"] is None) or (try_karsilik < row["min_fiyat_try"]):
                    row["min_fiyat_try"] = try_karsilik
                    row["min_fiyat_bag_id"] = bag.pk
            if tk and tk.teslim_suresi_gun is not None:
                if (row["min_termin"] is None) or (tk.teslim_suresi_gun < row["min_termin"]):
                    row["min_termin"] = tk.teslim_suresi_gun
                    row["min_termin_bag_id"] = bag.pk
        matrix.append(row)

    # Şu anki kazananları map'le
    secili_map = {
        (tk.rfq_kalemi_id): tk.pk
        for tk in TedarikciTeklifKalemi.objects.filter(
            rfq_tedarikci__rfq=rfq, secildi=True
        )
    }

    context = {
        "rfq": rfq,
        "bags": bags,
        "matrix": matrix,
        "secili_map_json": json.dumps(secili_map, ensure_ascii=False),
        "kur_tablosu": kur,
    }
    return render(request, "stokapp/rfq_karsilastirma.html", context)


@login_required
@require_POST
def rfq_kazananlari_kaydet(request, pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    try:
        secimler = json.loads(request.POST.get("secimler", "{}"))
    except json.JSONDecodeError:
        secimler = {}
    if not isinstance(secimler, dict):
        secimler = {}

    try:
        with transaction.atomic():
            _kazanan_secimi_temizle(rfq)
            for kalem_id_s, tk_id in secimler.items():
                try:
                    kalem_id = int(kalem_id_s)
                    tk_id_i = int(tk_id) if tk_id else None
                except (TypeError, ValueError):
                    continue
                if not tk_id_i:
                    continue
                # tutarlılık: bu tk gerçekten o kalemin teklifi mi?
                TedarikciTeklifKalemi.objects.filter(
                    pk=tk_id_i, rfq_kalemi_id=kalem_id, rfq_tedarikci__rfq=rfq
                ).update(secildi=True)
        return JsonResponse({"success": True})
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)


# ---------------------------------------------------------------------------
# Siparişe Dönüştürme
# ---------------------------------------------------------------------------


@login_required
@require_POST
def rfq_siparise_donustur(request, pk):
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    if rfq.durum == "SIPARISE_DONUSTURULDU":
        messages.warning(request, "Bu RFQ zaten siparişe dönüştürüldü.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)

    secili_teklifler = (
        TedarikciTeklifKalemi.objects.filter(
            rfq_tedarikci__rfq=rfq, secildi=True
        )
        .select_related("rfq_tedarikci", "rfq_tedarikci__tedarikci", "rfq_kalemi", "rfq_kalemi__stok_item")
    )
    if not secili_teklifler.exists():
        messages.error(request, "Önce karşılaştırma sayfasından kazananları seçin.")
        return redirect("stokapp:rfq_karsilastirma", pk=rfq.pk)

    # Tedarikçi bazlı grupla — yalnızca KAYITLI tedarikçi olanları siparişe çevirebiliriz
    grup_map = defaultdict(list)
    es_disi_var = False
    for tk in secili_teklifler:
        bag = tk.rfq_tedarikci
        if not bag.tedarikci_id:
            es_disi_var = True
            continue
        grup_map[bag.tedarikci_id].append(tk)

    if es_disi_var:
        messages.warning(
            request,
            "Bazı kazanan teklifler harici tedarikçilere ait. Bunlar siparişe çevrilmeden atlandı; lütfen önce ilgili tedarikçiyi sisteme tanımlayın.",
        )

    if not grup_map:
        messages.error(request, "Siparişe dönüştürülecek tedarikçi tabanlı kazanan bulunamadı.")
        return redirect("stokapp:rfq_karsilastirma", pk=rfq.pk)

    olusturulan_satinalmalar = []
    try:
        with transaction.atomic():
            for tedarikci_id, tk_list in grup_map.items():
                tedarikci = Tedarikci.objects.get(pk=tedarikci_id)
                # Yeni Satinalma numarası: TSAT_GGAAYY_NN
                today = date.today()
                tarih_format = f"{today.day:02d}{today.month:02d}{str(today.year)[-2:]}"
                bugun_baslayan_count = Satinalma.objects.filter(
                    satinalma_numarasi__startswith=f"TSAT_{tarih_format}_"
                ).count()
                sira_no = bugun_baslayan_count + 1
                satinalma = Satinalma.objects.create(
                    satinalma_numarasi=f"TSAT_{tarih_format}_{sira_no:02d}",
                    tedarikci=tedarikci,
                    tedarikci_adi=tedarikci.ad,
                    etiketler=f"RFQ:{rfq.rfq_no}",
                    olusturulma_tarihi=today,
                    teslim_durumu="BEKLIYOR",
                    para_birimi=tk_list[0].para_birimi or rfq.para_birimi or "TRY",
                    notlar=f"{rfq.rfq_no} kapsamında oluşturulmuştur.",
                )
                toplam = Decimal("0")
                for tk in tk_list:
                    rfq_kalemi = tk.rfq_kalemi
                    stok = rfq_kalemi.stok_item
                    if stok is None:
                        # Ad bazlı kalemi stoktan ara - olmazsa atla
                        continue
                    miktar = Decimal(str(rfq_kalemi.miktar))
                    fiyat = Decimal(str(tk.birim_fiyat or 0))
                    vergi_y = Decimal("20")
                    ara = miktar * fiyat
                    toplam_fiyat = ara + (ara * vergi_y / Decimal("100"))
                    SatinalmaKalemi.objects.create(
                        satinalma=satinalma,
                        stok_item=stok,
                        miktar=miktar,
                        birim_fiyat=fiyat,
                        vergi_yuzdesi=vergi_y,
                        toplam_fiyat=toplam_fiyat,
                        tedarikci_fiyat=fiyat,
                        teslim_suresi=tk.teslim_suresi_gun,
                        kaynak_rfq_kalemi=rfq_kalemi,
                        kaynak_teklif_kalemi=tk,
                        notlar=tk.notlar or "",
                    )
                    toplam += toplam_fiyat
                satinalma.toplam = toplam
                satinalma.save(update_fields=["toplam"])
                olusturulan_satinalmalar.append(satinalma.pk)

            rfq.durum = "SIPARISE_DONUSTURULDU"
            rfq.save(update_fields=["durum", "updated_at"])
    except Exception as exc:
        messages.error(request, f"Siparişe dönüşüm hatası: {exc}")
        return redirect("stokapp:rfq_karsilastirma", pk=rfq.pk)

    messages.success(
        request,
        f"{len(olusturulan_satinalmalar)} sipariş oluşturuldu. "
        "Siparişleri tedarikçilere mail olarak göndermek ister misiniz?",
    )

    # Çoklu sipariş mail wizard zinciri başlat
    request.session[SATINALMA_RFQ_MAIL_WIZARD_KEY] = {
        "rfq_id": rfq.pk,
        "satinalma_ids": olusturulan_satinalmalar,
        "kalan_ids": list(olusturulan_satinalmalar),
    }
    request.session.modified = True

    # Onay sayfasına yönlendir
    return redirect("stokapp:rfq_siparis_mail_secimi", pk=rfq.pk)


# ---------------------------------------------------------------------------
# Sipariş mail wizard zinciri
# ---------------------------------------------------------------------------


@login_required
def rfq_siparis_mail_secimi(request, pk):
    """RFQ sonrası oluşan siparişlerin mail gönderim seçim ekranı (overview)."""
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    state = request.session.get(SATINALMA_RFQ_MAIL_WIZARD_KEY) or {}
    if state.get("rfq_id") != rfq.pk:
        messages.warning(request, "Mail gönderim oturumu bulunamadı.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)
    satinalma_ids = state.get("satinalma_ids", [])
    satinalmalar = Satinalma.objects.filter(pk__in=satinalma_ids).select_related("tedarikci")
    kalan_ids = state.get("kalan_ids", [])
    context = {
        "rfq": rfq,
        "satinalmalar": satinalmalar,
        "kalan_ids": kalan_ids,
    }
    return render(request, "stokapp/rfq_siparis_mail_secimi.html", context)


@login_required
def rfq_siparis_mail_baslat(request, pk, satinalma_pk):
    """Mevcut satinalma_mail_alici_sec view'ına yönlendiren köprü.

    Wizard sonrası `kalan_ids` listesinden ilgili siparişi düşürür.
    """
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    state = request.session.get(SATINALMA_RFQ_MAIL_WIZARD_KEY) or {}
    if state.get("rfq_id") != rfq.pk:
        messages.warning(request, "Mail oturumu bulunamadı.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)
    if satinalma_pk not in state.get("satinalma_ids", []):
        messages.error(request, "Bu sipariş bu RFQ oturumuna ait değil.")
        return redirect("stokapp:rfq_siparis_mail_secimi", pk=rfq.pk)

    # Mevcut satınalma mail wizard akışını kullan
    url = (
        reverse("stokapp:satinalma_mail_alici_sec")
        + f"?kind=siparis&ids={satinalma_pk}&rfq={rfq.pk}"
    )
    return redirect(url)


@login_required
@require_POST
def rfq_siparis_mail_atla(request, pk, satinalma_pk):
    """Bu siparişi mail göndermeden atla (kalan listesi güncellensin)."""
    rfq = get_object_or_404(TeklifTalebi, pk=pk)
    state = request.session.get(SATINALMA_RFQ_MAIL_WIZARD_KEY) or {}
    if state.get("rfq_id") != rfq.pk:
        messages.warning(request, "Mail oturumu bulunamadı.")
        return redirect("stokapp:rfq_detay", pk=rfq.pk)
    kalan = [x for x in state.get("kalan_ids", []) if x != satinalma_pk]
    state["kalan_ids"] = kalan
    request.session[SATINALMA_RFQ_MAIL_WIZARD_KEY] = state
    request.session.modified = True
    if not kalan:
        # Wizard tamamlandı
        request.session.pop(SATINALMA_RFQ_MAIL_WIZARD_KEY, None)
        messages.info(request, "Tüm siparişlerin mail aşaması atlandı.")
        return redirect("stokapp:satinalma_listesi")
    return redirect("stokapp:rfq_siparis_mail_secimi", pk=rfq.pk)
