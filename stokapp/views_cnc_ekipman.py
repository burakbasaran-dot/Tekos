"""CNC ekipman / aparat kataloğu (torna, freze, ortak)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CncEkipmanForm
from .models import CncEkipman


def _filter_qs_for_tab(tab: str):
    """tab: tumu | torna | freze | ortak"""
    base = CncEkipman.objects.all().order_by("machine_scope", "sira", "id")
    if tab == "torna":
        return base.filter(Q(machine_scope="cnc_lathe") | Q(machine_scope="cnc_common"))
    if tab == "freze":
        return base.filter(Q(machine_scope="cnc_mill") | Q(machine_scope="cnc_common"))
    if tab == "ortak":
        return base.filter(machine_scope="cnc_common")
    return base


@login_required
def cnc_ekipman_listesi(request):
    tab = (request.GET.get("tab") or "tumu").strip().lower()
    if tab not in ("tumu", "torna", "freze", "ortak"):
        tab = "tumu"

    hepsini = request.GET.get("hepsini_goster", "false") == "true"
    qs = _filter_qs_for_tab(tab)
    if not hepsini:
        qs = qs.filter(aktif=True)

    ekipmanlar = list(qs)

    counts = {
        "tumu": CncEkipman.objects.filter(aktif=True).count() if not hepsini else CncEkipman.objects.count(),
        "torna": _filter_qs_for_tab("torna").filter(aktif=True).count()
        if not hepsini
        else _filter_qs_for_tab("torna").count(),
        "freze": _filter_qs_for_tab("freze").filter(aktif=True).count()
        if not hepsini
        else _filter_qs_for_tab("freze").count(),
        "ortak": _filter_qs_for_tab("ortak").filter(aktif=True).count()
        if not hepsini
        else _filter_qs_for_tab("ortak").count(),
    }

    return render(
        request,
        "stokapp/cnc_ekipman_listesi.html",
        {
            "ekipmanlar": ekipmanlar,
            "tab": tab,
            "hepsini_goster": hepsini,
            "counts": counts,
        },
    )


@login_required
def cnc_ekipman_ekle(request):
    if request.method == "POST":
        form = CncEkipmanForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            if request.user.is_authenticated:
                obj.created_by = request.user
            if "aktif" not in request.POST:
                obj.aktif = True
            obj.save()
            messages.success(request, f"«{obj.ad}» kaydedildi.")
            return redirect("stokapp:cnc_ekipman_listesi")
    else:
        form = CncEkipmanForm()
        form.fields["aktif"].initial = True
    return render(request, "stokapp/cnc_ekipman_form.html", {"form": form, "baslik": "Yeni CNC ekipmanı"})


@login_required
def cnc_ekipman_duzenle(request, pk):
    obj = get_object_or_404(CncEkipman, pk=pk)
    if request.method == "POST":
        form = CncEkipmanForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"«{obj.ad}» güncellendi.")
            return redirect("stokapp:cnc_ekipman_listesi")
    else:
        form = CncEkipmanForm(instance=obj)
    return render(
        request,
        "stokapp/cnc_ekipman_form.html",
        {"form": form, "baslik": "CNC ekipmanını düzenle", "ekipman": obj},
    )


@login_required
def cnc_ekipman_sil(request, pk):
    obj = get_object_or_404(CncEkipman, pk=pk)
    if request.method == "POST":
        ad = obj.ad
        obj.delete()
        messages.success(request, f"«{ad}» silindi.")
        return redirect("stokapp:cnc_ekipman_listesi")
    return render(request, "stokapp/cnc_ekipman_sil.html", {"ekipman": obj})
