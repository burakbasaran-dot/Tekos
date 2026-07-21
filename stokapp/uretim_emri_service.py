"""Üretim emri oluşturma yardımcıları."""
from decimal import Decimal
from typing import Optional

from django.db.models import Count

from .models import Recete, StokItem, UretimEmri, UretimAsamasi


def get_aktif_recete_for_urun(urun) -> Optional[Recete]:
    """Ürün için en güncel aktif reçeteyi döndürür.

    Önce operasyonlu reçeteyi tercih eder; yoksa bileşenli (yalnızca BOM)
    aktif reçete de kabul edilir — üretim emri ve alt emir planlaması için yeterlidir.
    """
    urun_id = urun.pk if isinstance(urun, StokItem) else urun
    qs = (
        Recete.objects.filter(urun_id=urun_id, aktif=True)
        .annotate(op_count=Count("operasyonlar"))
        .order_by("-op_count", "-versiyon")
    )
    return qs.first()



def yeni_uretim_emir_no() -> str:
    son_emir = UretimEmri.objects.order_by("-id").first()
    if son_emir:
        try:
            num = int(son_emir.emir_no.replace("UE-", "")) + 1
        except Exception:
            num = 1
    else:
        num = 1
    emir_no = f"UE-{num}"
    while UretimEmri.objects.filter(emir_no=emir_no).exists():
        num += 1
        emir_no = f"UE-{num}"
    return emir_no


def create_uretim_emri_with_stages(
    *,
    recete: Recete,
    miktar: Decimal,
    planlanan_baslama,
    planlanan_bitis,
    aciklama: str = "",
    production_type: str = "STOCK",
    ust_uretim_emri=None,
    alt_emir_otomatik: bool = False,
) -> UretimEmri:
    uretim_emri = UretimEmri.objects.create(
        emir_no=yeni_uretim_emir_no(),
        recete=recete,
        miktar=miktar,
        production_type=production_type,
        durum="PLANLANDI",
        planlanan_baslama=planlanan_baslama,
        planlanan_bitis=planlanan_bitis,
        aciklama=aciklama or "",
        ust_uretim_emri=ust_uretim_emri,
        alt_emir_otomatik=alt_emir_otomatik,
    )
    operasyonlar = recete.operasyonlar.select_related("operasyon", "recete_detay").order_by(
        "recete_detay__sira", "recete_detay_id", "sira", "id"
    )
    global_sira = 1
    for operasyon in operasyonlar:
        UretimAsamasi.objects.create(
            uretim_emri=uretim_emri,
            recete_detay=operasyon.recete_detay,
            recete_operasyon=operasyon,
            ad=operasyon.operasyon.ad,
            sira=global_sira,
            planlanan_sure=operasyon.sure_dakika,
            durum="BEKLIYOR",
        )
        global_sira += 1
    return uretim_emri
