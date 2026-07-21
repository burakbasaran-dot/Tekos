from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import Depo, Kategori, StokHareketi, StokItem, StokSayimi, StokSayimiKalemi
from .templatetags.currency_filters import format_adet


def _fmt_miktar(value) -> str:
    """Tam sayıysa ondalıksız; kesirliyse Türkçe format (format_adet)."""
    if value is None:
        return "—"
    return format_adet(value)


def _tamamla_sayim_if_bitti(sayim: StokSayimi) -> bool:
    """Bekleyen kalem kalmadıysa oturumu Tamamlandı yap."""
    if sayim.durum != "DEVAM":
        return False
    if sayim.kalemler.filter(durum="BEKLIYOR").exists():
        return False
    sayim.durum = "TAMAMLANDI"
    sayim.tamamlanma_zamani = timezone.now()
    sayim.save(update_fields=["durum", "tamamlanma_zamani"])
    return True


@login_required
def stok_sayim_listesi(request):
    sayimlar = (
        StokSayimi.objects.annotate(
            kalem_sayisi=Count("kalemler"),
            bekliyor_sayisi=Count("kalemler", filter=Q(durum="BEKLIYOR")),
            sayildi_sayisi=Count("kalemler", filter=Q(durum="SAYILDI")),
            atlandi_sayisi=Count("kalemler", filter=Q(durum="ATLANDI")),
        )
        .order_by("-created_at")[:300]
    )
    return render(request, "stokapp/stok_sayim_listesi.html", {"sayimlar": sayimlar})


@login_required
def stok_sayim_baslat(request):
    depolar = Depo.objects.all().order_by("ad")
    kategoriler = Kategori.objects.all().order_by("ad")

    if request.method != "POST":
        return render(
            request,
            "stokapp/stok_sayim_baslat.html",
            {"depolar": depolar, "kategoriler": kategoriler},
        )

    baslik = (request.POST.get("baslik") or "").strip()
    sadece_stok_takip = request.POST.get("sadece_stok_takip") == "1"
    depo_id = request.POST.get("depo") or ""
    kategori_id = request.POST.get("kategori") or ""

    qs = StokItem.objects.filter(arsivli=False).select_related("kategori", "depo")
    if sadece_stok_takip:
        qs = qs.filter(stok_takip=True)
    if depo_id.isdigit():
        qs = qs.filter(depo_id=int(depo_id))
    if kategori_id.isdigit():
        qs = qs.filter(kategori_id=int(kategori_id))
    qs = qs.order_by("stok_kodu")

    stoklar = list(qs)
    if not stoklar:
        messages.error(request, "Seçilen filtrelere uyan stok bulunamadı.")
        return render(
            request,
            "stokapp/stok_sayim_baslat.html",
            {"depolar": depolar, "kategoriler": kategoriler},
        )

    with transaction.atomic():
        sayim = StokSayimi.objects.create(
            baslik=baslik or f"Sayım {timezone.now().strftime('%d.%m.%Y %H:%M')}",
            durum="HAZIR",
            olusturan=request.user if request.user.is_authenticated else None,
            depo_id=int(depo_id) if depo_id.isdigit() else None,
            sadece_stok_takip=sadece_stok_takip,
        )
        kalemler = [
            StokSayimiKalemi(
                sayim=sayim,
                stok_item=s,
                sira=idx,
                sistem_miktar_snapshot=s.mevcut_miktar,
                durum="BEKLIYOR",
            )
            for idx, s in enumerate(stoklar)
        ]
        StokSayimiKalemi.objects.bulk_create(kalemler)

    messages.success(
        request,
        f"Sayım oluşturuldu (#{sayim.pk}, {len(stoklar)} kalem). "
        f"Rapor/PDF ile listeyi yazdırıp sayımı kağıda işleyebilir; ardından listeden Başlat diyebilirsiniz.",
    )
    return redirect("stokapp:stok_sayim_listesi")


@login_required
def stok_sayim_basla(request, pk):
    """Oluşturulmuş sayımı fiilen başlatır (giriş ekranına geçer)."""
    sayim = get_object_or_404(StokSayimi, pk=pk)

    if sayim.durum == "DEVAM":
        return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)
    if sayim.durum != "HAZIR":
        messages.warning(request, "Bu sayım başlatılamaz (durum uygun değil).")
        return redirect("stokapp:stok_sayim_listesi")

    sayim.durum = "DEVAM"
    sayim.save(update_fields=["durum"])
    messages.success(request, f"Sayım #{sayim.pk} başlatıldı. Kalemleri sırayla girebilirsiniz.")
    return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)


@login_required
def stok_sayim_calis(request, pk):
    sayim = get_object_or_404(StokSayimi.objects.prefetch_related("kalemler"), pk=pk)

    if sayim.durum == "IPTAL":
        messages.warning(request, "Bu sayım iptal edilmiş.")
        return redirect("stokapp:stok_sayim_listesi")

    if sayim.durum == "HAZIR":
        messages.info(
            request,
            "Bu sayım henüz başlatılmadı. Önce rapor alıp yazdırabilir; listeden Başlat ile girişi açabilirsiniz.",
        )
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

    if sayim.durum == "TAMAMLANDI":
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

    kalem = (
        sayim.kalemler.filter(durum="BEKLIYOR")
        .select_related("stok_item", "stok_item__kategori")
        .order_by("sira")
        .first()
    )

    if request.method == "POST":
        if not kalem:
            _tamamla_sayim_if_bitti(sayim)
            return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

        action = request.POST.get("action") or ""
        kalem_pk = request.POST.get("kalem_pk")

        if str(kalem.pk) != str(kalem_pk):
            messages.error(request, "Geçersiz sayım satırı.")
            return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

        if action == "gec":
            with transaction.atomic():
                locked = StokSayimiKalemi.objects.select_for_update().get(pk=kalem.pk, sayim=sayim)
                if locked.durum != "BEKLIYOR":
                    messages.warning(request, "Bu satır zaten işlenmiş.")
                    return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)
                locked.durum = "ATLANDI"
                locked.notlar = "Geçildi"
                locked.save(update_fields=["durum", "notlar"])

            messages.info(request, f"{locked.stok_item.stok_kodu} atlandı.")
            _tamamla_sayim_if_bitti(sayim)
            if sayim.durum == "TAMAMLANDI":
                messages.success(request, "Tüm satırlar işlendi. Sayım raporu hazır.")
                return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)
            return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

        if action == "kaydet":
            raw = (request.POST.get("sayilan_miktar") or "").strip().replace(",", ".")
            try:
                sayilan = Decimal(raw)
            except InvalidOperation:
                messages.error(request, "Geçerli bir sayı girin.")
                return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

            with transaction.atomic():
                locked_k = (
                    StokSayimiKalemi.objects.select_for_update().select_related("sayim").get(pk=kalem.pk)
                )
                if locked_k.sayim_id != sayim.pk or locked_k.durum != "BEKLIYOR":
                    messages.warning(request, "Bu satır güncellenemez.")
                    return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

                stok = StokItem.objects.select_for_update().get(pk=locked_k.stok_item_id)
                mevcut = stok.mevcut_miktar
                delta = sayilan - mevcut

                locked_k.sayilan_miktar = sayilan
                locked_k.durum = "SAYILDI"
                locked_k.fark_miktar = delta

                if delta != 0:
                    h = StokHareketi(
                        stok_item=stok,
                        hareket_tipi="SAYIM",
                        miktar=delta,
                        birim=stok.birim or "Adet",
                        referans_no=f"SAYIM-{sayim.pk}",
                        depo=stok.depo,
                        raf=stok.raf,
                        aciklama=(
                            f"Stok sayım #{sayim.pk}"
                            + (f" — {sayim.baslik}" if sayim.baslik else "")
                        ).strip(),
                        user=request.user.get_username() if request.user.is_authenticated else "Sistem",
                    )
                    h.save()
                    locked_k.hareket = h
                else:
                    locked_k.fark_miktar = Decimal("0")

                locked_k.save()

            if delta != 0:
                messages.success(
                    request,
                    f"{stok.stok_kodu}: fark {delta:+} uygulandı (mevcut → {sayilan}).",
                )
            else:
                messages.success(request, f"{stok.stok_kodu}: fark yok, stok aynı kaldı.")

            sayim.refresh_from_db()
            _tamamla_sayim_if_bitti(sayim)
            if sayim.durum == "TAMAMLANDI":
                messages.success(request, "Son satır tamamlandı. Raporu inceleyebilirsiniz.")
                return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)
            return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

        messages.error(request, "Geçersiz işlem.")
        return redirect("stokapp:stok_sayim_calis", pk=sayim.pk)

    # GET
    if not kalem:
        _tamamla_sayim_if_bitti(sayim)
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

    toplam = sayim.kalemler.count()
    yapilan = sayim.kalemler.exclude(durum="BEKLIYOR").count()
    stok = kalem.stok_item
    stok.refresh_from_db()

    return render(
        request,
        "stokapp/stok_sayim_calis.html",
        {
            "sayim": sayim,
            "kalem": kalem,
            "stok": stok,
            "toplam": toplam,
            "yapilan": yapilan,
            "ilerleme_pct": int(yapilan * 100 / toplam) if toplam else 100,
        },
    )


@login_required
def stok_sayim_rapor(request, pk):
    sayim = get_object_or_404(StokSayimi.objects, pk=pk)
    kalemler = (
        sayim.kalemler.select_related("stok_item__kategori", "hareket")
        .order_by("sira")
        .all()
    )

    ozet = sayim.kalemler.aggregate(
        bek=Count("id", filter=Q(durum="BEKLIYOR")),
        sy=Count("id", filter=Q(durum="SAYILDI")),
        atl=Count("id", filter=Q(durum="ATLANDI")),
    )

    hareket_sayisi = sayim.kalemler.filter(hareket__isnull=False).count()
    toplam_fark_artis = Decimal("0")
    toplam_fark_azalis = Decimal("0")
    for k in kalemler:
        if k.fark_miktar is None:
            continue
        if k.fark_miktar > 0:
            toplam_fark_artis += k.fark_miktar
        elif k.fark_miktar < 0:
            toplam_fark_azalis += abs(k.fark_miktar)

    return render(
        request,
        "stokapp/stok_sayim_rapor.html",
        {
            "sayim": sayim,
            "kalemler": kalemler,
            "ozet": ozet,
            "hareket_sayisi": hareket_sayisi,
            "toplam_fark_artis": toplam_fark_artis,
            "toplam_fark_azalis": toplam_fark_azalis,
        },
    )


@login_required
@never_cache
def stok_sayim_rapor_excel(request, pk):
    sayim = get_object_or_404(StokSayimi.objects, pk=pk)
    kalemler = (
        sayim.kalemler.select_related("stok_item__kategori", "hareket")
        .order_by("sira")
        .all()
    )
    try:
        import pandas as pd
        satirlar = [{
            "Sıra": k.sira,
            "Stok Kodu": k.stok_item.stok_kodu if k.stok_item else "",
            "Ürün": k.stok_item.ad if k.stok_item else "",
            "Sistem Miktarı": _fmt_miktar(k.sistem_miktar_snapshot),
            "Sayılan Miktar": _fmt_miktar(k.sayilan_miktar) if k.sayilan_miktar is not None else "",
            "Fark": _fmt_miktar(k.fark_miktar) if k.fark_miktar is not None else "",
            "Durum": k.get_durum_display(),
            "Notlar": k.notlar or "",
        } for k in kalemler]
        df = pd.DataFrame(satirlar)
        if df.empty:
            df = pd.DataFrame(columns=["Sıra", "Stok Kodu", "Ürün", "Sistem Miktarı", "Sayılan Miktar", "Fark", "Durum", "Notlar"])
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="stok_sayim_rapor_{sayim.pk}_{ts}.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sayim Raporu', index=False)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)


@login_required
@never_cache
def stok_sayim_rapor_pdf(request, pk):
    sayim = get_object_or_404(StokSayimi.objects, pk=pk)
    kalemler = (
        sayim.kalemler.select_related("stok_item__kategori", "hareket")
        .order_by("sira")
        .all()
    )
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

    olusturma_tarihi = timezone.localtime(timezone.now())
    html_rows = []
    for k in kalemler[:1500]:
        html_rows.append(
            f"""
            <tr>
                <td>{k.sira}</td>
                <td>{k.stok_item.stok_kodu if k.stok_item else '-'}</td>
                <td>{k.stok_item.ad if k.stok_item else '-'}</td>
                <td class="num">{_fmt_miktar(k.sistem_miktar_snapshot)}</td>
                <td class="num">{_fmt_miktar(k.sayilan_miktar) if k.sayilan_miktar is not None else '—'}</td>
                <td class="num">{_fmt_miktar(k.fark_miktar) if k.fark_miktar is not None else '—'}</td>
                <td>{k.get_durum_display()}</td>
            </tr>
            """
        )
    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Stok Sayım Raporu #{sayim.pk}</h1>
      <div class="meta">Başlık: {sayim.baslik or '-'} · Oluşturma: {olusturma_tarihi.strftime("%d.%m.%Y %H:%M")} · Kayıt: {len(kalemler)}</div>
      <table>
        <thead><tr><th>Sıra</th><th>Stok Kodu</th><th>Ürün</th><th>Sistem</th><th>Sayılan</th><th>Fark</th><th>Durum</th></tr></thead>
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
        return redirect("stokapp:stok_sayim_rapor", pk=sayim.pk)

    filename = f'stok_sayim_rapor_{sayim.pk}_{olusturma_tarihi.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def stok_sayim_sil(request, pk):
    """Yalnızca başlatılmamış (HAZIR) sayımı ve kalemlerini siler."""
    sayim = get_object_or_404(StokSayimi, pk=pk)
    if sayim.durum != "HAZIR":
        messages.warning(request, "Yalnızca başlatılmamış sayımlar silinebilir.")
        return redirect("stokapp:stok_sayim_listesi")

    if request.method == "POST":
        sayim_no = sayim.pk
        sayim.delete()
        messages.success(request, f"Sayım #{sayim_no} silindi.")
        return redirect("stokapp:stok_sayim_listesi")

    return render(request, "stokapp/stok_sayim_sil_confirm.html", {"sayim": sayim})


@login_required
def stok_sayim_iptal(request, pk):
    sayim = get_object_or_404(StokSayimi, pk=pk)
    if sayim.durum != "DEVAM":
        messages.warning(request, "Yalnızca devam eden sayımlar iptal edilebilir. Başlatılmamış sayımı Sil ile kaldırabilirsiniz.")
        return redirect("stokapp:stok_sayim_listesi")

    if request.method == "POST":
        with transaction.atomic():
            sayim.kalemler.filter(durum="BEKLIYOR").update(durum="ATLANDI", notlar="Sayım iptal")
            sayim.durum = "IPTAL"
            sayim.tamamlanma_zamani = timezone.now()
            sayim.save(update_fields=["durum", "tamamlanma_zamani"])
        messages.info(request, "Sayım iptal edildi (stok hareketi oluşturulmadı).")
        return redirect("stokapp:stok_sayim_listesi")

    return render(request, "stokapp/stok_sayim_iptal_confirm.html", {"sayim": sayim})
