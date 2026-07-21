"""
Üretim aşaması (işi başlat / bitir) ile reçetedeki dış operasyon şablonunu eşleştirir.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta
from decimal import Decimal

from types import SimpleNamespace

from django.db.models import Sum
from django.utils import timezone

from .models import DisOperasyon, DisOperasyonDonus, ReceteOperasyon, StokHareketi, StokItem
from .views_dis_operasyon import _finalize_operasyon_no, _log, _sync_durum


def _temp_no() -> str:
    return 'TMP-' + secrets.token_hex(8)


def _username(user) -> str:
    if user is None:
        return 'Sistem'
    if isinstance(user, str):
        return user
    return getattr(user, 'username', '') or 'Sistem'


def _recete_operasyon_for_asama(asama) -> ReceteOperasyon | None:
    emir = asama.uretim_emri
    lst = list(
        ReceteOperasyon.objects.filter(recete_id=emir.recete_id)
        .select_related('operasyon', 'dis_operasyon_tipi', 'dis_tedarikci', 'dis_gonderim_deposu')
        .order_by('sira', 'id')
    )
    by_sira = {op.sira: op for op in lst}
    ro = by_sira.get(asama.sira)
    if ro:
        return ro
    aad = (asama.ad or '').strip().lower()
    for op in lst:
        if op.operasyon and op.operasyon.ad.strip().lower() == aad:
            return op
    return None


def _open_dis_for_ro(emir_id: int, ro: ReceteOperasyon):
    return (
        DisOperasyon.objects.filter(uretim_emri_id=emir_id, recete_operasyon=ro)
        .exclude(durum__in=('IPTAL', 'ARSIV', 'TAMAMLANDI'))
        .order_by('-id')
        .first()
    )


def sync_dis_on_devam(asama, user=None) -> None:
    """İşi başlat (DEVAM): reçete dış şablonu varsa dış operasyon kaydı oluşturur."""
    ro = _recete_operasyon_for_asama(asama)
    if not ro or not ro.operasyon or not ro.operasyon.akis_dis_operasyon:
        return
    if not ro.dis_tedarikci_id or not ro.dis_operasyon_tipi_id:
        return

    emir = asama.uretim_emri
    if _open_dis_for_ro(emir.id, ro):
        return

    stok = emir.recete.urun
    g = emir.miktar
    birim = (stok.birim or 'Adet').strip()[:20]
    gonderim = timezone.now().date()
    gun = int(ro.dis_beklenen_donus_gun or 0)
    bek = gonderim + timedelta(days=gun) if gun > 0 else None

    bf = Decimal(str(ro.dis_birim_fiyat or 0))
    tahmini = (Decimal(str(g)) * bf).quantize(Decimal('0.01')) if bf else Decimal('0')

    sitem = StokItem.objects.select_for_update().filter(pk=stok.pk).first()
    if not sitem:
        return
    if sitem.mevcut_miktar < g:
        raise ValueError(
            'Dış operasyon gönderimi için depoda yeterli ürün yok '
            f'({sitem.stok_kodu}: gerekli {g}, mevcut {sitem.mevcut_miktar}).'
        )

    dis_op = DisOperasyon(
        operasyon_no=_temp_no(),
        stok_item=stok,
        uretim_emri=emir,
        recete_operasyon=ro,
        parti_no='',
        operasyon_tipi_id=ro.dis_operasyon_tipi_id,
        tedarikci_id=ro.dis_tedarikci_id,
        gonderim_deposu_id=ro.dis_gonderim_deposu_id,
        dis_operasyon_lokasyonu='',
        gonderilen_miktar=g,
        birim=birim,
        gonderim_tarihi=gonderim,
        beklenen_donus_tarihi=bek,
        birim_fiyat=bf,
        para_birimi=(ro.dis_para_birimi or 'TL')[:3],
        tahmini_toplam_maliyet=tahmini,
        durum='TEDARIKCIDE',
        sevk_evrak_no=(ro.dis_sevk_evrak_no or '')[:120],
        miktar_tedarikcide_kalan=g,
    )
    dis_op.save()
    _finalize_operasyon_no(dis_op)

    StokHareketi.objects.create(
        stok_item=sitem,
        hareket_tipi='DISOP_GONDERIM',
        miktar=g,
        birim=birim,
        referans_no=dis_op.operasyon_no,
        depo_id=ro.dis_gonderim_deposu_id,
        uretim_emri=emir,
        aciklama=f'Dış operasyon gönderim (reçete adımı) — {dis_op.operasyon_no}',
        user=_username(user),
        dis_operasyon=dis_op,
    )
    _log(dis_op, SimpleNamespace(username=_username(user)), 'Gönderim (reçete)', '', dis_op.durum, f'{g} {birim} tedarikçiye sevk')


def sync_dis_on_tamamlandi(asama, user=None) -> None:
    """İşi bitir: bu adıma bağlı açık dış operasyonu tam dönüşle kapatır."""
    ro = _recete_operasyon_for_asama(asama)
    if not ro:
        return
    emir = asama.uretim_emri
    dis_op = _open_dis_for_ro(emir.id, ro)
    if not dis_op:
        return

    kalan = dis_op.miktar_tedarikcide_kalan or Decimal('0')
    if kalan <= 0:
        return

    onceki = dis_op.donuslar.aggregate(
        sm=Sum('donen_miktar'),
        sf=Sum('fire_miktari'),
        se=Sum('eksik_miktari'),
    )
    prev_d = onceki['sm'] or Decimal('0')
    prev_f = onceki['sf'] or Decimal('0')
    prev_e = onceki['se'] or Decimal('0')
    g = dis_op.gonderilen_miktar or Decimal('0')
    if prev_d + prev_f + prev_e + kalan > g + Decimal('0.0001'):
        kalan = max(Decimal('0'), g - prev_d - prev_f - prev_e)

    donen = kalan
    if donen <= 0:
        return

    sitem = StokItem.objects.select_for_update().get(pk=dis_op.stok_item_id)
    if (sitem.dis_operasyonda_miktar or Decimal('0')) < donen - Decimal('0.0001'):
        raise ValueError('Dış operasyonda takip edilen miktar yetersiz (stok tutarsızlığı).')

    bf = dis_op.birim_fiyat or Decimal('0')
    top_m = (donen * bf).quantize(Decimal('0.01')) if bf else Decimal('0')

    StokHareketi.objects.create(
        stok_item=sitem,
        hareket_tipi='DISOP_DONUS',
        miktar=donen,
        birim=dis_op.birim,
        referans_no=dis_op.operasyon_no,
        aciklama=f'Dış operasyon dönüş (iş emri adımı tamamlandı) — {dis_op.operasyon_no}',
        user=_username(user),
        dis_operasyon=dis_op,
    )

    donus = DisOperasyonDonus.objects.create(
        dis_operasyon=dis_op,
        donus_tarihi=timezone.now().date(),
        donen_miktar=donen,
        fire_miktari=Decimal('0'),
        eksik_miktari=Decimal('0'),
        gerceklesen_birim_fiyat=bf if bf else None,
        nakliye_maliyeti=Decimal('0'),
        ek_maliyet=Decimal('0'),
        toplam_maliyet=top_m,
        kalite_kontrol_gerekli=False,
        kalite_islenildi=True,
        aciklama='Üretim aşaması tamamlandı — otomatik dönüş',
    )

    dis_op.miktar_tedarikcide_kalan = (dis_op.miktar_tedarikcide_kalan or Decimal('0')) - donen
    dis_op.toplam_donen_miktar = (dis_op.toplam_donen_miktar or Decimal('0')) + donen
    dis_op.toplam_gerceklesen_maliyet = (dis_op.toplam_gerceklesen_maliyet or Decimal('0')) + top_m
    _sync_durum(dis_op)
    dis_op.save()
    _log(dis_op, SimpleNamespace(username=_username(user)), 'Dönüş (reçete)', '', dis_op.durum, f'Otomatik dönüş #{donus.pk}')
