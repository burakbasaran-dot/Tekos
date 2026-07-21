"""Gayrimenkul yönetimi — TEKOS Varlık Yönetimi."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import GayrimenkulDosyaForm, GayrimenkulForm, GayrimenkulIslemiForm
from .models import Gayrimenkul, GayrimenkulDosya, GayrimenkulIslemi

UYARI_GUN = 30


def _islem_acik(islem: GayrimenkulIslemi) -> bool:
    return islem.durum not in (GayrimenkulIslemi.DURUM_SECENEKLERI[1][0], GayrimenkulIslemi.DURUM_SECENEKLERI[3][0])


def _islem_efektif_gecikti(islem: GayrimenkulIslemi, bugun: date) -> bool:
    if not _islem_acik(islem):
        return False
    if islem.durum == "GECIKTI":
        return True
    return islem.vade_tarihi < bugun


def _islem_yaklasiyor(islem: GayrimenkulIslemi, bugun: date) -> bool:
    if not _islem_acik(islem):
        return False
    if islem.vade_tarihi < bugun:
        return False
    return islem.vade_tarihi <= bugun + timedelta(days=UYARI_GUN)


def _gayrimenkul_ozet(gm: Gayrimenkul, islemler: list[GayrimenkulIslemi], bugun: date) -> dict:
    geciken = 0
    yakin = 0
    sonraki: date | None = None
    yaklasan_yukumluluk = False

    for islem in islemler:
        if _islem_efektif_gecikti(islem, bugun):
            geciken += 1
        if _islem_yaklasiyor(islem, bugun):
            yakin += 1
            yaklasan_yukumluluk = True
        if _islem_acik(islem):
            if sonraki is None or islem.vade_tarihi < sonraki:
                sonraki = islem.vade_tarihi

    sigorta_yakin = False
    sigorta_gecikti = False
    if gm.sigorta_bitis_tarihi:
        if gm.sigorta_bitis_tarihi < bugun:
            sigorta_gecikti = True
        elif gm.sigorta_bitis_tarihi <= bugun + timedelta(days=UYARI_GUN):
            sigorta_yakin = True
            yaklasan_yukumluluk = True

    etiket = "NORMAL"
    if geciken > 0 or sigorta_gecikti:
        etiket = "GECIKTI"
    elif yakin > 0 or sigorta_yakin:
        etiket = "YAKLASIYOR"

    yil_bas = date(bugun.year, 1, 1)
    yil_top = Decimal("0")
    for islem in islemler:
        if islem.durum != "ODENDI":
            continue
        if islem.odeme_tarihi and islem.odeme_tarihi >= yil_bas:
            if islem.tutar:
                yil_top += islem.tutar

    return {
        "etiket": etiket,
        "sonraki_odeme": sonraki,
        "yaklasan_yukumluluk": yaklasan_yukumluluk,
        "geciken_sayisi": geciken + (1 if sigorta_gecikti else 0),
        "yakin_sayisi": yakin + (1 if sigorta_yakin else 0),
        "yillik_odeme_toplam": yil_top,
        "sigorta_bitis": gm.sigorta_bitis_tarihi,
    }


def _liste_satirlari(queryset, bugun: date, filtre_yakin: bool, filtre_geciken: bool, filtre_sigorta_yakin: bool):
    gm_ids = list(queryset.values_list("pk", flat=True))
    if not gm_ids:
        return []

    islemler_qs = GayrimenkulIslemi.objects.filter(gayrimenkul_id__in=gm_ids)
    by_gm: dict[int, list[GayrimenkulIslemi]] = {i: [] for i in gm_ids}
    for islem in islemler_qs:
        by_gm.setdefault(islem.gayrimenkul_id, []).append(islem)

    rows = []
    for gm in queryset:
        ozet = _gayrimenkul_ozet(gm, by_gm.get(gm.pk, []), bugun)
        if filtre_yakin and ozet["yakin_sayisi"] == 0:
            continue
        if filtre_geciken and ozet["geciken_sayisi"] == 0:
            continue
        if filtre_sigorta_yakin:
            sb = gm.sigorta_bitis_tarihi
            if not sb or sb < bugun or sb > bugun + timedelta(days=UYARI_GUN):
                continue
        rows.append({"gm": gm, **ozet})
    return rows


@login_required
def gayrimenkul_listesi(request):
    bugun = date.today()
    arsiv = request.GET.get("arsiv", "0")
    search = request.GET.get("search", "").strip()

    qs = Gayrimenkul.objects.all()
    if arsiv == "1":
        qs = qs.filter(arsivlendi=True)
    else:
        qs = qs.filter(arsivlendi=False)

    if search:
        qs = qs.filter(
            Q(ad__icontains=search)
            | Q(il__icontains=search)
            | Q(ilce__icontains=search)
            | Q(adres__icontains=search)
            | Q(tapu_no__icontains=search)
            | Q(sorumlu_kisi__icontains=search)
        )

    tip = request.GET.get("tip", "")
    if tip:
        qs = qs.filter(tip=tip)
    st = request.GET.get("sahiplik", "")
    if st:
        qs = qs.filter(sahiplik_tipi=st)
    il = request.GET.get("il", "").strip()
    if il:
        qs = qs.filter(il__icontains=il)
    ilce = request.GET.get("ilce", "").strip()
    if ilce:
        qs = qs.filter(ilce__icontains=ilce)
    kd = request.GET.get("kullanim", "")
    if kd:
        qs = qs.filter(kullanim_durumu=kd)

    filtre_yakin = request.GET.get("yakin_odeme") == "1"
    filtre_geciken = request.GET.get("geciken") == "1"
    filtre_sigorta_yakin = request.GET.get("sigorta_yakin") == "1"

    qs = qs.order_by("il", "ilce", "ad")
    tablo_satirlari = _liste_satirlari(qs, bugun, filtre_yakin, filtre_geciken, filtre_sigorta_yakin)

    paginator = Paginator(tablo_satirlari, 15)
    page = request.GET.get("page", 1)
    sayfa = paginator.get_page(page)

    context = {
        "satirlar": sayfa,
        "arsiv": arsiv,
        "search": search,
        "filtre_tip": tip,
        "filtre_sahiplik": st,
        "filtre_il": il,
        "filtre_ilce": ilce,
        "filtre_kullanim": kd,
        "filtre_yakin_odeme": filtre_yakin,
        "filtre_geciken": filtre_geciken,
        "filtre_sigorta_yakin": filtre_sigorta_yakin,
        "gm_tipleri": Gayrimenkul.GM_TIPLERI,
        "sahiplik_tipleri": Gayrimenkul.SAHIPLIK_TIPLERI,
        "kullanim_secenekleri": Gayrimenkul.KULLANIM_DURUMU,
        "bugun": bugun,
        "uyari_gun": UYARI_GUN,
    }
    return render(request, "stokapp/gayrimenkul_listesi.html", context)


@login_required
def gayrimenkul_ekle(request):
    if request.method == "POST":
        form = GayrimenkulForm(request.POST)
        if form.is_valid():
            gm = form.save()
            messages.success(request, f'"{gm.ad}" kaydedildi.')
            return redirect("stokapp:gayrimenkul_detay", pk=gm.pk)
    else:
        form = GayrimenkulForm()
        form.fields["para_birimi"].initial = "TRY"
    return render(request, "stokapp/gayrimenkul_form.html", {"form": form, "is_edit": False})


@login_required
def gayrimenkul_duzenle(request, pk):
    gm = get_object_or_404(Gayrimenkul, pk=pk)
    if request.method == "POST":
        form = GayrimenkulForm(request.POST, instance=gm)
        if form.is_valid():
            form.save()
            messages.success(request, "Güncellendi.")
            return redirect("stokapp:gayrimenkul_detay", pk=gm.pk)
    else:
        form = GayrimenkulForm(instance=gm)
    return render(
        request,
        "stokapp/gayrimenkul_form.html",
        {"form": form, "gm": gm, "is_edit": True},
    )


@login_required
def gayrimenkul_detay(request, pk):
    gm = get_object_or_404(Gayrimenkul, pk=pk)
    bugun = date.today()
    islemler = list(gm.islemler.all().order_by("vade_tarihi", "id"))
    ozet = _gayrimenkul_ozet(gm, islemler, bugun)

    tab = request.GET.get("tab", "genel")
    if tab not in ("genel", "takip", "dosyalar", "notlar", "gecmis"):
        tab = "genel"

    takip_islemler = [i for i in islemler if i.durum in ("BEKLIYOR", "GECIKTI")]
    gecmis_islemler = [i for i in islemler if i.durum in ("ODENDI", "IPTAL")]

    dosyalar = gm.dosyalar.all()

    sigorta_uyari = ""
    if gm.sigorta_bitis_tarihi:
        if gm.sigorta_bitis_tarihi < bugun:
            sigorta_uyari = "gecikti"
        elif gm.sigorta_bitis_tarihi <= bugun + timedelta(days=UYARI_GUN):
            sigorta_uyari = "yakin"

    uyari_bitis_tarihi = bugun + timedelta(days=UYARI_GUN)

    context = {
        "gm": gm,
        "islemler": islemler,
        "takip_islemler": takip_islemler,
        "gecmis_islemler": sorted(gecmis_islemler, key=lambda x: (x.odeme_tarihi or x.vade_tarihi), reverse=True),
        "dosyalar": dosyalar,
        "ozet": ozet,
        "tab": tab,
        "bugun": bugun,
        "uyari_gun": UYARI_GUN,
        "uyari_bitis_tarihi": uyari_bitis_tarihi,
        "sigorta_uyari": sigorta_uyari,
    }
    return render(request, "stokapp/gayrimenkul_detay.html", context)


@login_required
def gayrimenkul_arsivle(request, pk):
    gm = get_object_or_404(Gayrimenkul, pk=pk)
    if request.method == "POST":
        gm.arsivlendi = True
        gm.save(update_fields=["arsivlendi", "updated_at"])
        messages.success(request, f'"{gm.ad}" arşivlendi.')
        return redirect("stokapp:gayrimenkul_listesi")
    return render(request, "stokapp/gayrimenkul_arsivle.html", {"gm": gm})


@login_required
def gayrimenkul_islem_ekle(request, gm_pk):
    from django import forms as django_forms

    gm = get_object_or_404(Gayrimenkul, pk=gm_pk)
    if request.method == "POST":
        data = request.POST.copy()
        data["gayrimenkul"] = str(gm.pk)
        form = GayrimenkulIslemiForm(data, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Yükümlülük kaydı eklendi.")
            return HttpResponseRedirect(
                reverse("stokapp:gayrimenkul_detay", kwargs={"pk": gm.pk}) + "?tab=takip"
            )
    else:
        form = GayrimenkulIslemiForm(initial={"para_birimi": gm.para_birimi or "TRY"})
    form.fields["gayrimenkul"].widget = django_forms.HiddenInput()
    form.fields["gayrimenkul"].initial = gm.pk

    return render(
        request,
        "stokapp/gayrimenkul_islem_form.html",
        {"form": form, "gm": gm, "is_edit": False},
    )


@login_required
def gayrimenkul_islem_duzenle(request, pk):
    islem = get_object_or_404(GayrimenkulIslemi, pk=pk)
    gm = islem.gayrimenkul
    if request.method == "POST":
        form = GayrimenkulIslemiForm(request.POST, request.FILES, instance=islem)
        if form.is_valid():
            form.save()
            messages.success(request, "Kayıt güncellendi.")
            return HttpResponseRedirect(
                reverse("stokapp:gayrimenkul_detay", kwargs={"pk": gm.pk}) + "?tab=takip"
            )
    else:
        form = GayrimenkulIslemiForm(instance=islem)
    from django import forms as django_forms

    form.fields["gayrimenkul"].widget = django_forms.HiddenInput()
    return render(
        request,
        "stokapp/gayrimenkul_islem_form.html",
        {"form": form, "gm": gm, "islem": islem, "is_edit": True},
    )


@login_required
def gayrimenkul_dosya_ekle(request, gm_pk):
    from django import forms as django_forms

    gm = get_object_or_404(Gayrimenkul, pk=gm_pk)
    if request.method == "POST":
        data = request.POST.copy()
        data["gayrimenkul"] = str(gm.pk)
        form = GayrimenkulDosyaForm(data, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Dosya eklendi.")
            return HttpResponseRedirect(
                reverse("stokapp:gayrimenkul_detay", kwargs={"pk": gm.pk}) + "?tab=dosyalar"
            )
    else:
        form = GayrimenkulDosyaForm()
    form.fields["gayrimenkul"].widget = django_forms.HiddenInput()
    form.fields["gayrimenkul"].initial = gm.pk

    return render(
        request,
        "stokapp/gayrimenkul_dosya_form.html",
        {"form": form, "gm": gm},
    )
