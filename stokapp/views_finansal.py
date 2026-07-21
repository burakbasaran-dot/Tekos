import uuid
from collections import defaultdict
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from .models import BankaHesabi, KrediKarti, AylikOdeme
from .forms import BankaHesabiForm, KrediKartiForm, AylikOdemeForm


def _aylik_odeme_yapildi_tarih_guncelle(o: AylikOdeme) -> None:
    if o.odeme_durumu == "ODENDI" and not o.odeme_yapildi_tarih:
        o.odeme_yapildi_tarih = date.today()
        o.save(update_fields=["odeme_yapildi_tarih"])
    elif o.odeme_durumu != "ODENDI":
        o.odeme_yapildi_tarih = None
        o.save(update_fields=["odeme_yapildi_tarih"])


def _aylik_plan_tekrar_eden_duzenle(plan_uid) -> None:
    if not plan_uid:
        return
    satirlar = sorted(
        AylikOdeme.objects.filter(plan_uid=plan_uid),
        key=lambda r: (r.odeme_tarihi, r.pk),
    )
    for i, r in enumerate(satirlar):
        olmali = i == 0
        if r.tekrar_eden != olmali:
            r.tekrar_eden = olmali
            r.save(update_fields=["tekrar_eden"])


def _aylik_son_taksit_pks_for_queryset(qs):
    """
    plan_uid ile gruplanmış çok taksitli planlarda, son vadeli kaydın pk'lerini döner.
    Tek taksitli veya plansız kayıtlar dahil edilmez.
    """
    plan_uids = list(
        qs.exclude(plan_uid__isnull=True).values_list("plan_uid", flat=True).distinct()
    )
    if not plan_uids:
        return frozenset()
    rows = AylikOdeme.objects.filter(plan_uid__in=plan_uids).only(
        "pk", "plan_uid", "odeme_tarihi"
    )
    by_plan = defaultdict(list)
    for r in rows:
        by_plan[r.plan_uid].append(r)
    out = set()
    for _uid, lst in by_plan.items():
        if len(lst) < 2:
            continue
        last = max(lst, key=lambda x: (x.odeme_tarihi, x.pk))
        out.add(last.pk)
    return frozenset(out)
# ============== BANKA HESAPLARI ==============

@login_required
def banka_hesaplari_listesi(request):
    """Banka hesapları listesi"""
    hesaplar = BankaHesabi.objects.all().order_by('-created_at')
    return render(request, 'stokapp/banka_hesaplari_listesi.html', {
        'hesaplar': hesaplar,
        'title': 'Banka Hesapları'
    })


@login_required
def banka_hesabi_ekle(request):
    """Yeni banka hesabı ekle"""
    if request.method == 'POST':
        form = BankaHesabiForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Banka hesabı başarıyla eklendi.')
            return redirect('stokapp:banka_hesaplari_listesi')
    else:
        form = BankaHesabiForm()
    return render(request, 'stokapp/banka_hesabi_form.html', {
        'form': form,
        'title': 'Yeni Banka Hesabı Ekle',
        'is_edit': False
    })


@login_required
def banka_hesabi_duzenle(request, pk):
    """Banka hesabı düzenle"""
    hesap = get_object_or_404(BankaHesabi, pk=pk)
    if request.method == 'POST':
        form = BankaHesabiForm(request.POST, request.FILES, instance=hesap)
        if form.is_valid():
            form.save()
            messages.success(request, 'Banka hesabı başarıyla güncellendi.')
            return redirect('stokapp:banka_hesaplari_listesi')
    else:
        form = BankaHesabiForm(instance=hesap)
    return render(request, 'stokapp/banka_hesabi_form.html', {
        'form': form,
        'hesap': hesap,
        'title': 'Banka Hesabı Düzenle',
        'is_edit': True
    })


@login_required
def banka_hesabi_sil(request, pk):
    """Banka hesabı sil"""
    hesap = get_object_or_404(BankaHesabi, pk=pk)
    if request.method == 'POST':
        hesap.delete()
        messages.success(request, 'Banka hesabı başarıyla silindi.')
        return redirect('stokapp:banka_hesaplari_listesi')
    return render(request, 'stokapp/banka_hesabi_sil.html', {
        'hesap': hesap,
        'title': 'Banka Hesabı Sil'
    })


# ============== KREDİ KARTLARI ==============

@login_required
def kredi_kartlari_listesi(request):
    """Kredi kartları listesi"""
    kartlar = KrediKarti.objects.all().order_by('-created_at')
    return render(request, 'stokapp/kredi_kartlari_listesi.html', {
        'kartlar': kartlar,
        'title': 'Kredi Kartları'
    })


@login_required
def kredi_karti_ekle(request):
    """Yeni kredi kartı ekle"""
    if request.method == 'POST':
        form = KrediKartiForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kredi kartı başarıyla eklendi.')
            return redirect('stokapp:kredi_kartlari_listesi')
    else:
        form = KrediKartiForm()
    return render(request, 'stokapp/kredi_karti_form.html', {
        'form': form,
        'title': 'Yeni Kredi Kartı Ekle',
        'is_edit': False
    })


@login_required
def kredi_karti_duzenle(request, pk):
    """Kredi kartı düzenle"""
    kart = get_object_or_404(KrediKarti, pk=pk)
    if request.method == 'POST':
        form = KrediKartiForm(request.POST, request.FILES, instance=kart)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kredi kartı başarıyla güncellendi.')
            return redirect('stokapp:kredi_kartlari_listesi')
    else:
        form = KrediKartiForm(instance=kart)
        # CVV'yi göster (düzenleme için)
        if form.instance.cvv:
            form.fields['cvv'].widget.attrs['type'] = 'text'
    return render(request, 'stokapp/kredi_karti_form.html', {
        'form': form,
        'kart': kart,
        'title': 'Kredi Kartı Düzenle',
        'is_edit': True
    })


@login_required
def kredi_karti_sil(request, pk):
    """Kredi kartı sil"""
    kart = get_object_or_404(KrediKarti, pk=pk)
    if request.method == 'POST':
        kart.delete()
        messages.success(request, 'Kredi kartı başarıyla silindi.')
        return redirect('stokapp:kredi_kartlari_listesi')
    return render(request, 'stokapp/kredi_karti_sil.html', {
        'kart': kart,
        'title': 'Kredi Kartı Sil'
    })


# ============== AYLIK ÖDEMELER ==============

AYLIK_ODEME_SIRALAMA_ALANLARI = {
    "aciklama": "odeme_aciklamasi",
    "odeme_sekli": "odeme_sekli",
    "kayit_tarihi": "kayit_tarihi",
    "odeme_tarihi": "odeme_tarihi",
    "tutar": "tutar",
    "durum": "odeme_durumu",
}


@login_required
def aylik_odemeler_listesi(request):
    """Aylık ödemeler listesi — Ödenecekler / Ödenenler sekmeleri."""
    temel = AylikOdeme.objects.select_related(
        "para_birimi", "banka_hesabi", "kredi_karti"
    ).all()

    durum_filtresi = request.GET.get("durum", "")
    if durum_filtresi:
        temel = temel.filter(odeme_durumu=durum_filtresi)

    arama = request.GET.get("arama", "")
    if arama:
        temel = temel.filter(
            Q(odeme_aciklamasi__icontains=arama) | Q(aciklama__icontains=arama)
        )

    sekme = request.GET.get("sekme", "odenecek")
    if sekme not in ("odenecek", "odenen"):
        sekme = "odenecek"

    if sekme == "odenen":
        odemeler = temel.filter(odeme_durumu="ODENDI")
    else:
        odemeler = temel.exclude(odeme_durumu="ODENDI")

    odenecek_sayisi = temel.exclude(odeme_durumu="ODENDI").count()
    odenen_sayisi = temel.filter(odeme_durumu="ODENDI").count()

    sirala = request.GET.get("sirala", "")
    yon = request.GET.get("yon", "desc")
    if yon not in ("asc", "desc"):
        yon = "desc"

    if sirala in AYLIK_ODEME_SIRALAMA_ALANLARI:
        alan = AYLIK_ODEME_SIRALAMA_ALANLARI[sirala]
        onek = "" if yon == "asc" else "-"
        odemeler = odemeler.order_by(f"{onek}{alan}", "pk")
    else:
        sirala = ""
        yon = "desc"
        if sekme == "odenen":
            odemeler = odemeler.order_by("-odeme_yapildi_tarih", "-odeme_tarihi", "pk")
        else:
            # Ödenecekler: vadesi en yakın kayıtlar üstte (ödeme tarihi artan)
            odemeler = odemeler.order_by("odeme_tarihi", "kayit_tarihi", "pk")

    base_q = {"sekme": sekme}
    if arama:
        base_q["arama"] = arama
    if durum_filtresi:
        base_q["durum"] = durum_filtresi

    sirala_urls = {}
    desc_onceki = ("kayit_tarihi", "odeme_tarihi", "tutar")
    for anahtar in AYLIK_ODEME_SIRALAMA_ALANLARI:
        if sirala == anahtar:
            sonraki_yon = "desc" if yon == "asc" else "asc"
        else:
            sonraki_yon = "desc" if anahtar in desc_onceki else "asc"
        q = {**base_q, "sirala": anahtar, "yon": sonraki_yon}
        sirala_urls[anahtar] = "?" + urlencode(q)

    odenmeyen = temel.exclude(odeme_durumu="ODENDI")
    bugun = date.today()
    yaklasan_adaylar = odenmeyen.filter(
        odeme_durumu="BEKLEMEDE",
        odeme_tarihi__gte=bugun,
    )
    yaklasan_odemeler = [o for o in yaklasan_adaylar if o.hatirlatma_gecerli_mi()]

    gecikmis_odemeler = odenmeyen.filter(
        odeme_durumu="BEKLEMEDE",
        odeme_tarihi__lt=bugun,
    )

    son_taksit_pks = _aylik_son_taksit_pks_for_queryset(odemeler)

    return render(
        request,
        "stokapp/aylik_odemeler_listesi.html",
        {
            "odemeler": odemeler,
            "yaklasan_odemeler": yaklasan_odemeler,
            "gecikmis_odemeler": gecikmis_odemeler,
            "durum_filtresi": durum_filtresi,
            "arama": arama,
            "sirala": sirala,
            "yon": yon,
            "sirala_urls": sirala_urls,
            "sekme": sekme,
            "odenecek_sayisi": odenecek_sayisi,
            "odenen_sayisi": odenen_sayisi,
            "sekme_odenecek_url": "?" + urlencode({k: v for k, v in {**base_q, "sekme": "odenecek"}.items()}),
            "sekme_odenen_url": "?" + urlencode({k: v for k, v in {**base_q, "sekme": "odenen"}.items()}),
            "title": "Aylık Ödemeler Takibi",
            "son_taksit_pks": son_taksit_pks,
        },
    )


@login_required
def aylik_odeme_ekle(request):
    """Yeni aylık ödeme ekle"""
    if request.method == 'POST':
        form = AylikOdemeForm(request.POST)
        if form.is_valid():
            tekrar_eden = form.cleaned_data.get('tekrar_eden', False)
            tekrar_sayisi = form.cleaned_data.get('tekrar_sayisi')
            
            # İlk ödemeyi kaydet (tekrarlı planda tüm taksitler aynı plan_uid ile gruplanır)
            odeme = form.save(commit=False)
            if tekrar_eden:
                odeme.plan_uid = uuid.uuid4()
            odeme.save()
            
            # Eğer ödeme durumu ODEendi ise, tarihi kaydet
            if odeme.odeme_durumu == 'ODENDI' and not odeme.odeme_yapildi_tarih:
                odeme.odeme_yapildi_tarih = date.today()
                odeme.save()
            
            # Tekrar eden ödeme seçilmişse ve tekrar sayısı varsa, ek kayıtlar oluştur
            if tekrar_eden and tekrar_sayisi and tekrar_sayisi > 1:
                ilk_odeme_tarihi = odeme.odeme_tarihi
                olusturulan_sayisi = 1  # İlk kayıt zaten oluşturuldu
                
                for i in range(1, tekrar_sayisi):
                    # Her ay için yeni bir ödeme kaydı oluştur
                    yeni_odeme_tarihi = ilk_odeme_tarihi + relativedelta(months=i)
                    
                    # Yeni ödeme kaydı oluştur
                    yeni_odeme = AylikOdeme(
                        odeme_aciklamasi=odeme.odeme_aciklamasi,
                        odeme_sekli=odeme.odeme_sekli,
                        banka_hesabi=odeme.banka_hesabi,
                        kredi_karti=odeme.kredi_karti,
                        kayit_tarihi=odeme.kayit_tarihi,
                        odeme_tarihi=yeni_odeme_tarihi,
                        tutar=odeme.tutar,
                        para_birimi=odeme.para_birimi,
                        tekrar_eden=False,  # Tekrar eden sadece ilk kayıtta True
                        aktif=odeme.aktif,
                        odeme_durumu='BEKLEMEDE',  # Yeni kayıtlar beklemede
                        odeme_yapildi_tarih=None,
                        aciklama=odeme.aciklama,
                        plan_uid=odeme.plan_uid,
                        hatirlatma_gun_once=odeme.hatirlatma_gun_once,
                    )
                    yeni_odeme.save()
                    olusturulan_sayisi += 1
                
                messages.success(request, f'{olusturulan_sayisi} adet aylık ödeme planı başarıyla oluşturuldu.')
            else:
                messages.success(request, 'Aylık ödeme başarıyla eklendi.')
            
            return redirect('stokapp:aylik_odemeler_listesi')
    else:
        form = AylikOdemeForm()
        form.fields['kayit_tarihi'].initial = date.today()
        form.fields['odeme_tarihi'].initial = date.today()
    return render(request, 'stokapp/aylik_odeme_form.html', {
        'form': form,
        'title': 'Yeni Aylık Ödeme Ekle',
        'is_edit': False
    })


@login_required
def aylik_odeme_duzenle(request, pk):
    """Aylık ödeme düzenle — tekrarlı planlarda taksit sayısı kaydedildiğinde tüm plan senkronize edilir."""
    odeme = get_object_or_404(AylikOdeme, pk=pk)

    ilgili_odemeler = odeme.plan_odemeleri()
    tekrar_sayisi_hesap = ilgili_odemeler.count()

    if request.method == 'POST':
        form = AylikOdemeForm(
            request.POST,
            instance=odeme,
            plan_taksit_sayisi=tekrar_sayisi_hesap,
        )
        if form.is_valid():
            cd = form.cleaned_data
            tekrar_eden = cd.get('tekrar_eden', False)
            ts = cd.get('tekrar_sayisi')

            if tekrar_eden and ts and 1 <= int(ts) <= 12:
                n = int(ts)
                plan_satirlari = sorted(
                    list(odeme.plan_odemeleri()),
                    key=lambda r: (r.odeme_tarihi, r.pk),
                )
                if not plan_satirlari:
                    plan_satirlari = [odeme]

                mevcut_n = len(plan_satirlari)
                uid = plan_satirlari[0].plan_uid or odeme.plan_uid
                if not uid:
                    uid = uuid.uuid4()
                    for r in plan_satirlari:
                        r.plan_uid = uid
                        r.save(update_fields=["plan_uid"])
                    odeme.refresh_from_db(fields=["plan_uid"])
                else:
                    uid = plan_satirlari[0].plan_uid

                if n == mevcut_n:
                    odeme = form.save()
                    _aylik_odeme_yapildi_tarih_guncelle(odeme)
                    messages.success(request, "Aylık ödeme güncellendi.")
                elif n > mevcut_n:
                    odeme = form.save()
                    _aylik_odeme_yapildi_tarih_guncelle(odeme)
                    guncel = sorted(
                        AylikOdeme.objects.filter(plan_uid=uid),
                        key=lambda r: (r.odeme_tarihi, r.pk),
                    )
                    son = guncel[-1]
                    imlec = son.odeme_tarihi
                    for _ in range(mevcut_n, n):
                        imlec = imlec + relativedelta(months=1)
                        AylikOdeme.objects.create(
                            odeme_aciklamasi=son.odeme_aciklamasi,
                            odeme_sekli=son.odeme_sekli,
                            banka_hesabi=son.banka_hesabi,
                            kredi_karti=son.kredi_karti,
                            kayit_tarihi=son.kayit_tarihi,
                            odeme_tarihi=imlec,
                            tutar=son.tutar,
                            para_birimi=son.para_birimi,
                            tekrar_eden=False,
                            aktif=son.aktif,
                            odeme_durumu="BEKLEMEDE",
                            odeme_yapildi_tarih=None,
                            aciklama=son.aciklama,
                            plan_uid=uid,
                            hatirlatma_gun_once=son.hatirlatma_gun_once,
                        )
                    _aylik_plan_tekrar_eden_duzenle(uid)
                    messages.success(
                        request, f"Plana {n - mevcut_n} taksit eklendi."
                    )
                else:
                    odeme = form.save()
                    _aylik_odeme_yapildi_tarih_guncelle(odeme)
                    guncel = sorted(
                        AylikOdeme.objects.filter(plan_uid=uid),
                        key=lambda r: (r.odeme_tarihi, r.pk),
                    )
                    silinecek_adet = mevcut_n - n
                    silinen = 0
                    for satir in reversed(guncel):
                        if silinecek_adet <= 0:
                            break
                        if satir.odeme_durumu == "BEKLEMEDE":
                            satir.delete()
                            silinecek_adet -= 1
                            silinen += 1
                    if silinecek_adet > 0:
                        messages.warning(
                            request,
                            f"{silinecek_adet} taksit ödenmiş veya işaretlenmiş olduğu için silinemedi.",
                        )
                    _aylik_plan_tekrar_eden_duzenle(uid)
                    messages.success(request, "Ödeme planı güncellendi.")
            else:
                odeme = form.save()
                _aylik_odeme_yapildi_tarih_guncelle(odeme)
                messages.success(request, 'Aylık ödeme başarıyla güncellendi.')
            return redirect('stokapp:aylik_odemeler_listesi')
    else:
        form = AylikOdemeForm(
            instance=odeme,
            plan_taksit_sayisi=tekrar_sayisi_hesap,
        )
        if tekrar_sayisi_hesap > 0:
            form.fields['tekrar_sayisi'].initial = tekrar_sayisi_hesap
        if odeme.tekrar_eden or tekrar_sayisi_hesap > 1:
            form.fields['tekrar_sayisi'].widget.attrs['style'] = 'display: block;'

    return render(request, 'stokapp/aylik_odeme_form.html', {
        'form': form,
        'odeme': odeme,
        'ilgili_odemeler': ilgili_odemeler,
        'tekrar_sayisi': tekrar_sayisi_hesap,
        'title': 'Aylık Ödeme Düzenle',
        'is_edit': True
    })


@login_required
def aylik_odeme_sil(request, pk):
    """Aylık ödeme sil"""
    odeme = get_object_or_404(AylikOdeme, pk=pk)
    if request.method == 'POST':
        odeme.delete()
        messages.success(request, 'Aylık ödeme başarıyla silindi.')
        return redirect('stokapp:aylik_odemeler_listesi')
    return render(request, 'stokapp/aylik_odeme_sil.html', {
        'odeme': odeme,
        'title': 'Aylık Ödeme Sil'
    })


@login_required
def aylik_odeme_odendi_isaretle(request, pk):
    """Ödeme yapıldı olarak işaretle (AJAX)"""
    odeme = get_object_or_404(AylikOdeme, pk=pk)
    if request.method == 'POST':
        odeme.odeme_durumu = 'ODENDI'
        odeme.odeme_yapildi_tarih = date.today()
        odeme.save()
        return JsonResponse({'success': True, 'message': 'Ödeme yapıldı olarak işaretlendi.'})
    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})


@login_required
def get_odeme_sekli_options(request):
    """Ödeme şekline göre banka hesabı veya kredi kartı seçeneklerini getir (AJAX)"""
    odeme_sekli = request.GET.get('odeme_sekli', '')
    
    if odeme_sekli in ['BANKA_HESABI', 'HAVALE_EFT']:
        hesaplar = BankaHesabi.objects.filter(aktif=True).values('id', 'hesap_adi', 'banka_adi')
        return JsonResponse({
            'type': 'banka_hesabi',
            'options': list(hesaplar)
        })
    elif odeme_sekli == 'KREDI_KARTI':
        kartlar = KrediKarti.objects.filter(aktif=True).values('id', 'kart_adi', 'kart_numarasi')
        # Kart numarasının son 4 hanesini göster
        for kart in kartlar:
            if kart['kart_numarasi'] and len(kart['kart_numarasi']) >= 4:
                kart['kart_numarasi'] = f"****{kart['kart_numarasi'][-4:]}"
        return JsonResponse({
            'type': 'kredi_karti',
            'options': list(kartlar)
        })
    
    return JsonResponse({'type': 'none', 'options': []})

