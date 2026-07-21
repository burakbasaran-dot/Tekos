from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import UretimDegisiklikKaydiForm
from .models import UretimDegisiklikKaydi


@login_required
def uretim_degisim_listesi(request):
    q = (request.GET.get("q") or "").strip()
    durum = (request.GET.get("durum") or "acik").strip()

    kayitlar = UretimDegisiklikKaydi.objects.select_related("urun", "olusturan", "kapatan")
    if q:
        kayitlar = kayitlar.filter(
            Q(baslik__icontains=q)
            | Q(aciklama__icontains=q)
            | Q(degisiklik_tipi__icontains=q)
            | Q(urun__stok_kodu__icontains=q)
            | Q(urun__ad__icontains=q)
        )

    if durum == "kapali":
        kayitlar = kayitlar.filter(durum="TAMAMLANDI")
    elif durum == "devam":
        kayitlar = kayitlar.filter(durum="DEVAM")
    elif durum != "tum":
        kayitlar = kayitlar.exclude(durum="TAMAMLANDI")

    paginator = Paginator(kayitlar, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    tum = UretimDegisiklikKaydi.objects.all()
    context = {
        "kayitlar": page_obj,
        "q": q,
        "durum_filtre": durum,
        "sayilar": {
            "acik": tum.exclude(durum="TAMAMLANDI").count(),
            "devam": tum.filter(durum="DEVAM").count(),
            "kapali": tum.filter(durum="TAMAMLANDI").count(),
            "tum": tum.count(),
        },
    }
    return render(request, "stokapp/uretim/degisim_listesi.html", context)


@login_required
def uretim_degisim_ekle(request):
    if request.method == "POST":
        form = UretimDegisiklikKaydiForm(request.POST)
        if form.is_valid():
            kayit = form.save(commit=False)
            kayit.olusturan = request.user
            if kayit.durum == "TAMAMLANDI":
                kayit.kapatilan_tarih = timezone.now()
                kayit.kapatan = request.user
            kayit.save()
            messages.success(request, "Üretim değişiklik kaydı eklendi.")
            return redirect("stokapp:uretim_degisim_listesi")
    else:
        form = UretimDegisiklikKaydiForm()
    return render(request, "stokapp/uretim/degisim_form.html", {"form": form, "is_edit": False, "kayit": None})


@login_required
def uretim_degisim_duzenle(request, pk):
    kayit = get_object_or_404(UretimDegisiklikKaydi, pk=pk)
    if request.method == "POST":
        form = UretimDegisiklikKaydiForm(request.POST, instance=kayit)
        if form.is_valid():
            kayit = form.save(commit=False)
            if kayit.durum == "TAMAMLANDI" and kayit.kapatilan_tarih is None:
                kayit.kapatilan_tarih = timezone.now()
                kayit.kapatan = request.user
            elif kayit.durum != "TAMAMLANDI":
                kayit.kapatilan_tarih = None
                kayit.kapatan = None
            kayit.save()
            messages.success(request, "Kayıt güncellendi.")
            return redirect("stokapp:uretim_degisim_listesi")
    else:
        form = UretimDegisiklikKaydiForm(instance=kayit)
    return render(request, "stokapp/uretim/degisim_form.html", {"form": form, "is_edit": True, "kayit": kayit})


@login_required
def uretim_degisim_goruntule(request, pk):
    kayit = get_object_or_404(
        UretimDegisiklikKaydi.objects.select_related("urun", "olusturan", "kapatan"),
        pk=pk,
    )
    return render(request, "stokapp/uretim/degisim_detay.html", {"kayit": kayit})


@login_required
def uretim_degisim_kapat(request, pk):
    kayit = get_object_or_404(UretimDegisiklikKaydi, pk=pk)
    if request.method == "POST":
        kayit.kapatma_notu = (request.POST.get("kapatma_notu") or "").strip()
        kayit.durum = "TAMAMLANDI"
        kayit.kapatilan_tarih = timezone.now()
        kayit.kapatan = request.user
        kayit.save(update_fields=["kapatma_notu", "durum", "kapatilan_tarih", "kapatan", "updated_at"])
        messages.success(request, "İş başarıyla kapatıldı.")
    return redirect("stokapp:uretim_degisim_listesi")
