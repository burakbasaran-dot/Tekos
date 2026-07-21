"""Satın alma talep yönetimi (ihtiyaç talepleri)."""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    TalepForm,
    TalepKalemiFormSet,
    TalepSatinalmaBilgisiForm,
    TalepKapatForm,
    TalepDosyaForm,
    TalepNotEkleForm,
)
from .models import Talep, TalepKalemi, TalepDosya, TalepGecmisi, TalepSatinalmaBilgisi, Satinalma, SatinalmaKalemi, Tedarikci, ParaBirimi


def _get_satinalma_bilgi(talep):
    try:
        return talep.satinalma_bilgi
    except TalepSatinalmaBilgisi.DoesNotExist:
        return None


def _yonetici_mi(user):
    return user.is_authenticated and user.is_staff


def _talep_log(talep, user, olay, mesaj="", eski="", yeni=""):
    TalepGecmisi.objects.create(
        talep=talep,
        kullanici=user if user.is_authenticated else None,
        olay=olay,
        eski_durum=eski,
        yeni_durum=yeni,
        mesaj=mesaj,
    )


def _satinalma_toplam_guncelle(sat: Satinalma) -> None:
    toplam = Decimal("0")
    for k in SatinalmaKalemi.objects.filter(satinalma=sat):
        toplam += Decimal(str(k.toplam_fiyat or 0))
    sat.toplam = toplam
    sat.save(update_fields=["toplam"])


def _yeni_satinalma_numarasi():
    from datetime import date

    today = date.today()
    tarih_format = f"{today.day:02d}{today.month:02d}{str(today.year)[-2:]}"
    n = Satinalma.objects.filter(satinalma_numarasi__startswith=f"TSAT_{tarih_format}_").count()
    return f"TSAT_{tarih_format}_{n + 1:02d}"


def _varsayilan_para_kodu():
    pb = ParaBirimi.objects.filter(aktif=True).first()
    return pb.kod if pb else "TRY"


def _talep_kalemler_satinalma_notu(talep: Talep) -> str:
    lines = [f"Talep: {talep.talep_no} — {talep.baslik}", ""]
    lines.append("Talep kalemleri özeti:")
    for k in talep.kalemler.all().order_by("id"):
        birim_ad = k.birim.ad if k.birim else "—"
        acik = (k.aciklama or "").strip()
        lines.append(f"• {k.kalem_adi}: {k.miktar} {birim_ad}")
        if acik:
            lines.append(f"  Açıklama: {acik}")
    return "\n".join(lines)


def _duzenleme_kisitli(talep: Talep) -> bool:
    """Tamamlanmış / arşiv talepte ana form kapalı (yönetici detay formları ayrı)."""
    if talep.arsivlendi:
        return True
    if talep.durum in ("TAMAMLANDI", "REDDEDILDI", "IPTAL"):
        return True
    return False


def _talep_duzenleyebilir(talep: Talep, user) -> bool:
    if not user.is_authenticated:
        return False
    if _yonetici_mi(user):
        return not talep.arsivlendi
    return talep.talep_eden_id == user.id and not _duzenleme_kisitli(talep)


def _satinalma_durum_yazisi(talep: Talep) -> str:
    b = _get_satinalma_bilgi(talep)
    if b is None:
        if talep.satinalma_id:
            return "Satın alma kaydı var"
        return "—"
    parts = []
    if b.teklif_alindi:
        parts.append("Teklif alındı")
    if b.siparis_verildi:
        parts.append("Sipariş verildi")
    if b.alim_yontemi:
        parts.append(b.get_alim_yontemi_display())
    if talep.satinalma_id:
        parts.append(talep.satinalma.satinalma_numarasi)
    return ", ".join(parts) if parts else "Bekliyor"


def _siparis_bekliyor_etiket(talep: Talep) -> bool:
    if talep.durum != "SATINALMAYA_AKTARILDI":
        return False
    b = _get_satinalma_bilgi(talep)
    if b and b.siparis_verildi:
        return False
    return True


@login_required
def talep_listesi(request):
    arsiv = request.GET.get("arsiv") == "1"
    qs = Talep.objects.select_related("talep_eden", "satinalma", "kapanis_tedarikci").prefetch_related(
        "satinalma_bilgi"
    ).filter(arsivlendi=arsiv)
    durum = request.GET.get("durum")
    if durum:
        qs = qs.filter(durum=durum)
    oncelik = request.GET.get("oncelik")
    if oncelik:
        qs = qs.filter(oncelik=oncelik)
    kategori = request.GET.get("kategori")
    if kategori:
        qs = qs.filter(kategori=kategori)
    talep_eden = request.GET.get("talep_eden")
    if talep_eden:
        qs = qs.filter(talep_eden_id=talep_eden)
    departman = request.GET.get("departman", "").strip()
    if departman:
        qs = qs.filter(departman__icontains=departman)
    sorumlu = request.GET.get("sorumlu")
    if sorumlu:
        qs = qs.filter(satinalma_bilgi__satinalma_sorumlusu_id=sorumlu)

    if request.GET.get("geciken") == "1":
        from datetime import date

        bugun = date.today()
        qs = qs.exclude(durum__in=("TAMAMLANDI", "REDDEDILDI", "IPTAL")).filter(istenen_termin__lt=bugun)
    if request.GET.get("acik") == "1":
        qs = qs.exclude(durum__in=("TAMAMLANDI", "REDDEDILDI", "IPTAL"))
    if request.GET.get("tamamlanan") == "1":
        qs = qs.filter(durum="TAMAMLANDI")

    d1 = request.GET.get("tarih_bas")
    d2 = request.GET.get("tarih_bit")
    if d1:
        qs = qs.filter(talep_tarihi__gte=d1)
    if d2:
        qs = qs.filter(talep_tarihi__lte=d2)

    qs = qs.order_by("-talep_tarihi", "-pk")

    talepler = list(qs[:500])
    for t in talepler:
        t.row_satinalma_ozet = _satinalma_durum_yazisi(t)
        t.row_gecikti = t.gecikti_mi()
        t.row_siparis_bekliyor = _siparis_bekliyor_etiket(t)

    kullanicilar = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")

    return render(
        request,
        "stokapp/talep_listesi.html",
        {
            "title": "Talep Yönetimi",
            "talepler": talepler,
            "kullanicilar": kullanicilar,
            "filtre": request.GET,
            "yonetici": _yonetici_mi(request.user),
        },
    )


@login_required
def talep_ekle(request):
    if request.method == "POST":
        form = TalepForm(request.POST)
        fs = TalepKalemiFormSet(request.POST)
        if form.is_valid() and fs.is_valid():
            valid_rows = [
                f
                for f in fs
                if f.cleaned_data
                and not f.cleaned_data.get("DELETE", False)
                and (f.cleaned_data.get("kalem_adi") or "").strip()
            ]
            if not valid_rows:
                messages.error(request, "En az bir talep kalemi ekleyin.")
            else:
                with transaction.atomic():
                    talep: Talep = form.save(commit=False)
                    talep.talep_eden = request.user
                    talep.durum = "YENI"
                    talep.save()
                    fs.instance = talep
                    fs.save()
                    _talep_log(talep, request.user, "OLUSTURULDU", f"Talep oluşturuldu.", "", talep.durum)
                messages.success(request, "Talep kaydedildi.")
                return redirect("stokapp:talep_detay", pk=talep.pk)
        else:
            messages.error(request, "Formu kontrol edin.")
    else:
        form = TalepForm()
        fs = TalepKalemiFormSet()
    return render(
        request,
        "stokapp/talep_form.html",
        {"title": "Yeni Talep", "form": form, "formset": fs, "duzenle": False},
    )


@login_required
def talep_duzenle(request, pk):
    talep = get_object_or_404(Talep, pk=pk)
    if not _talep_duzenleyebilir(talep, request.user):
        return HttpResponseForbidden("Bu talebi düzenleme yetkiniz yok.")
    if _duzenleme_kisitli(talep) and not _yonetici_mi(request.user):
        return HttpResponseForbidden("Talep kapalı; düzenlenemez.")

    if request.method == "POST":
        form = TalepForm(request.POST, instance=talep)
        fs = TalepKalemiFormSet(request.POST, instance=talep)
        if form.is_valid() and fs.is_valid():
            valid_rows = [
                f
                for f in fs
                if f.cleaned_data
                and not f.cleaned_data.get("DELETE", False)
                and (f.cleaned_data.get("kalem_adi") or "").strip()
            ]
            if not valid_rows:
                messages.error(request, "En az bir talep kalemi olmalı.")
            else:
                eski = talep.durum
                with transaction.atomic():
                    form.save()
                    fs.save()
                talep.refresh_from_db()
                if talep.durum != eski:
                    _talep_log(talep, request.user, "GUNCELLEME", "Talep veya kalemler güncellendi.", eski, talep.durum)
                else:
                    _talep_log(talep, request.user, "GUNCELLEME", "Talep güncellendi.")
                messages.success(request, "Kaydedildi.")
                return redirect("stokapp:talep_detay", pk=talep.pk)
        messages.error(request, "Formu kontrol edin.")
    else:
        form = TalepForm(instance=talep)
        fs = TalepKalemiFormSet(instance=talep)
    return render(
        request,
        "stokapp/talep_form.html",
        {"title": f"Talep Düzenle — {talep.talep_no}", "form": form, "formset": fs, "duzenle": True, "talep": talep},
    )


@login_required
def talep_detay(request, pk):
    talep = get_object_or_404(
        Talep.objects.select_related("talep_eden", "satinalma", "kapanis_tedarikci").prefetch_related(
            "kalemler__birim", "dosyalar", "gecmis__kullanici"
        ),
        pk=pk,
    )
    sb = _get_satinalma_bilgi(talep)
    sat_form = TalepSatinalmaBilgisiForm(instance=sb) if sb else TalepSatinalmaBilgisiForm()

    kapat_form = TalepKapatForm(
        initial={
            "kapanis_tipi": talep.kapanis_tipi or "TAMAMLANDI",
            "gerceklesen_toplam_tutar": talep.gerceklesen_toplam_tutar,
            "kapanis_tedarikci": talep.kapanis_tedarikci_id,
            "fatura_no": talep.fatura_no,
            "irsaliye_no": talep.irsaliye_no,
            "alim_tarihi": talep.alim_tarihi,
            "teslim_alan_kisi": talep.teslim_alan_kisi,
            "kapanis_notu": talep.kapanis_notu,
        }
    )
    dosya_form = TalepDosyaForm()
    not_form = TalepNotEkleForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "satinalma_bilgi" and _yonetici_mi(request.user):
            sb = _get_satinalma_bilgi(talep)
            if sb:
                sform = TalepSatinalmaBilgisiForm(request.POST, instance=sb)
            else:
                sform = TalepSatinalmaBilgisiForm(request.POST)
            if sform.is_valid():
                obj = sform.save(commit=False)
                obj.talep = talep
                obj.save()
                yeni_durum = talep.durum
                if obj.siparis_verildi and talep.durum == "SATINALMAYA_AKTARILDI":
                    yeni_durum = "SIPARIS_VERILDI"
                eski = talep.durum
                if yeni_durum != eski:
                    talep.durum = yeni_durum
                    talep.save(update_fields=["durum", "updated_at"])
                    _talep_log(talep, request.user, "DURUM", "Satınalma bilgisi güncellendi.", eski, yeni_durum)
                else:
                    _talep_log(talep, request.user, "SATINALMA_BILGI", "Satınalma bilgileri kaydedildi.")
                messages.success(request, "Satınalma bilgileri kaydedildi.")
                return redirect("stokapp:talep_detay", pk=pk)
            messages.error(request, "Satınalma formunda hata var.")
        elif action == "dosya_ekle":
            dform = TalepDosyaForm(request.POST, request.FILES)
            if dform.is_valid():
                d = dform.save(commit=False)
                d.talep = talep
                d.yukleyen = request.user
                d.save()
                _talep_log(talep, request.user, "DOSYA", d.aciklama or d.dosya.name)
                messages.success(request, "Dosya yüklendi.")
                return redirect("stokapp:talep_detay", pk=pk)
        elif action == "not_ekle":
            nform = TalepNotEkleForm(request.POST)
            if nform.is_valid():
                _talep_log(talep, request.user, "NOT", nform.cleaned_data["mesaj"])
                messages.success(request, "Not eklendi.")
                return redirect("stokapp:talep_detay", pk=pk)

    tab = request.GET.get("tab", "ozet")

    return render(
        request,
        "stokapp/talep_detay.html",
        {
            "title": f"Talep {talep.talep_no}",
            "talep": talep,
            "sat_form": sat_form,
            "kapat_form": kapat_form,
            "dosya_form": dosya_form,
            "not_form": not_form,
            "tab": tab,
            "yonetici": _yonetici_mi(request.user),
            "satinalma_yazi": _satinalma_durum_yazisi(talep),
            "gecikti": talep.gecikti_mi(),
            "siparis_bekliyor": _siparis_bekliyor_etiket(talep),
            "tedarikciler": Tedarikci.objects.all().order_by("ad"),
            "sorumlu_adaylari": User.objects.filter(is_active=True).order_by("first_name", "last_name", "username"),
        },
    )


@login_required
def talep_durum_aksiyon(request, pk):
    if not _yonetici_mi(request.user):
        return HttpResponseForbidden()
    talep = get_object_or_404(Talep, pk=pk)
    if request.method != "POST":
        return redirect("stokapp:talep_detay", pk=pk)
    aksiyon = request.POST.get("aksiyon")
    eski = talep.durum
    if aksiyon == "inceleme" and eski == "YENI":
        talep.durum = "INCELEMEDE"
        talep.save(update_fields=["durum", "updated_at"])
        _talep_log(talep, request.user, "INCELEME", "Talep incelemeye alındı.", eski, talep.durum)
    elif aksiyon == "onay" and eski in ("YENI", "INCELEMEDE"):
        talep.durum = "ONAYLANDI"
        talep.save(update_fields=["durum", "updated_at"])
        _talep_log(talep, request.user, "ONAY", "Talep onaylandı.", eski, talep.durum)
    elif aksiyon == "red" and eski in ("YENI", "INCELEMEDE", "ONAYLANDI"):
        talep.durum = "REDDEDILDI"
        talep.save(update_fields=["durum", "updated_at"])
        _talep_log(talep, request.user, "RED", request.POST.get("red_notu", "Reddedildi"), eski, talep.durum)
    elif aksiyon == "iptal" and eski not in ("TAMAMLANDI",):
        talep.durum = "IPTAL"
        talep.save(update_fields=["durum", "updated_at"])
        _talep_log(talep, request.user, "IPTAL", request.POST.get("iptal_notu", "İptal"), eski, talep.durum)
    messages.success(request, "İşlem kaydedildi.")
    return redirect("stokapp:talep_detay", pk=pk)


@login_required
def talep_satinalmaya_aktar(request, pk):
    if not _yonetici_mi(request.user):
        return HttpResponseForbidden()
    talep = get_object_or_404(Talep, pk=pk)
    if request.method != "POST":
        return redirect("stokapp:talep_detay", pk=pk)
    if talep.durum != "ONAYLANDI":
        messages.error(request, "Satınalmaya aktarmak için talep onaylı olmalı.")
        return redirect("stokapp:talep_detay", pk=pk)
    if talep.satinalma_id:
        messages.warning(request, "Bu talep zaten bir satın alma kaydına bağlı.")
        return redirect("stokapp:talep_detay", pk=pk)

    tedarikci_id = request.POST.get("tedarikci")
    tedarikci = Tedarikci.objects.filter(pk=tedarikci_id).first() if tedarikci_id else None
    sorumlu_id = request.POST.get("satinalma_sorumlusu")
    sorumlu = User.objects.filter(pk=sorumlu_id).first() if sorumlu_id else None

    if not talep.kalemler.exists():
        messages.error(request, "Satınalmaya aktarmak için en az bir talep kalemi olmalı.")
        return redirect("stokapp:talep_detay", pk=pk)

    eski = talep.durum
    not_ozet = _talep_kalemler_satinalma_notu(talep)
    with transaction.atomic():
        sat = Satinalma.objects.create(
            satinalma_numarasi=_yeni_satinalma_numarasi(),
            tedarikci=tedarikci,
            tedarikci_adi=tedarikci.ad if tedarikci else "",
            olusturulma_tarihi=timezone.now().date(),
            para_birimi=_varsayilan_para_kodu(),
            teslim_durumu="BEKLIYOR",
            notlar=not_ozet,
        )
        _satinalma_toplam_guncelle(sat)
        bilgi, _ = TalepSatinalmaBilgisi.objects.get_or_create(talep=talep)
        bilgi.tedarikci = tedarikci or bilgi.tedarikci
        bilgi.satinalma_sorumlusu = sorumlu or bilgi.satinalma_sorumlusu
        bilgi.aktarilma_zamani = timezone.now()
        bilgi.save()

        talep.satinalma = sat
        talep.durum = "SATINALMAYA_AKTARILDI"
        talep.save(update_fields=["satinalma", "durum", "updated_at"])
        _talep_log(
            talep,
            request.user,
            "SATINALMAYA_AKTAR",
            f"Satın alma oluşturuldu: {sat.satinalma_numarasi}",
            eski,
            talep.durum,
        )
    messages.success(
        request,
        f"Satın alma kaydı oluşturuldu: {sat.satinalma_numarasi}. "
        "Kalemler satın alma notlarına işlendi; satır kalemlerini satın alma ekranından elle ekleyebilirsiniz.",
    )
    return redirect("stokapp:talep_detay", pk=pk)


@login_required
def talep_kapat(request, pk):
    if not _yonetici_mi(request.user):
        return HttpResponseForbidden()
    talep = get_object_or_404(Talep, pk=pk)
    if request.method != "POST":
        return redirect("stokapp:talep_detay", pk=pk)
    form = TalepKapatForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Kapanış formunu kontrol edin.")
        return redirect("stokapp:talep_detay", pk=pk)

    cd = form.cleaned_data
    eski = talep.durum
    durum_map = {
        "TAMAMLANDI": "TAMAMLANDI",
        "KISMEN": "KISMEN_KARSILANDI",
        "RED": "REDDEDILDI",
        "IPTAL": "IPTAL",
    }
    yeni = durum_map.get(cd["kapanis_tipi"], "TAMAMLANDI")

    with transaction.atomic():
        talep.kapanis_tipi = cd["kapanis_tipi"]
        talep.gerceklesen_toplam_tutar = cd.get("gerceklesen_toplam_tutar")
        talep.kapanis_tedarikci = cd.get("kapanis_tedarikci")
        talep.fatura_no = cd.get("fatura_no") or ""
        talep.irsaliye_no = cd.get("irsaliye_no") or ""
        talep.alim_tarihi = cd.get("alim_tarihi")
        talep.teslim_alan_kisi = cd.get("teslim_alan_kisi") or ""
        talep.kapanis_notu = cd.get("kapanis_notu") or ""
        talep.kapanis_tarihi = timezone.now()
        talep.durum = yeni
        talep.save()
        _talep_log(talep, request.user, "KAPATIS", talep.kapanis_notu or "Talep kapatıldı.", eski, yeni)

    messages.success(request, "Talep kapatıldı.")
    return redirect("stokapp:talep_detay", pk=pk)


@login_required
def talep_arsivle(request, pk):
    if not _yonetici_mi(request.user):
        return HttpResponseForbidden()
    talep = get_object_or_404(Talep, pk=pk)
    if request.method == "POST":
        talep.arsivlendi = True
        talep.save(update_fields=["arsivlendi", "updated_at"])
        _talep_log(talep, request.user, "ARSIV", "Talep arşivlendi.")
        messages.success(request, "Arşivlendi.")
    return redirect("stokapp:talep_listesi")
