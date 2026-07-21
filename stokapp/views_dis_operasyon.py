"""
Dış Operasyonlar modülü — liste, oluşturma, dönüş, kalite, arşiv, stok hareketleri.
"""

from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Depo,
    DisOperasyon,
    DisOperasyonDosya,
    DisOperasyonDonus,
    DisOperasyonKaliteKontrol,
    DisOperasyonLog,
    DisOperasyonTipi,
    StokHareketi,
    StokItem,
    Tedarikci,
    UretimEmri,
)


def _log(dis_op: DisOperasyon, user, islem: str, eski: str = '', yeni: str = '', aciklama: str = ''):
    DisOperasyonLog.objects.create(
        dis_operasyon=dis_op,
        islem=islem,
        eski_durum=eski,
        yeni_durum=yeni,
        kullanici=getattr(user, 'username', '') or '',
        aciklama=aciklama,
    )


def _temp_operasyon_no() -> str:
    return 'TMP-' + secrets.token_hex(8)


def _finalize_operasyon_no(dis_op: DisOperasyon):
    y = timezone.now().year
    dis_op.operasyon_no = f'DISOP-{y}-{dis_op.pk:06d}'
    dis_op.save(update_fields=['operasyon_no'])


def _sync_durum(dis_op: DisOperasyon):
    """Emir durumunu kalan / kalite bekleyen / dönüş durumuna göre günceller."""
    if dis_op.arsivli or dis_op.durum in ('IPTAL', 'ARSIV'):
        return
    kb = dis_op.miktar_kalite_bekliyor or Decimal('0')
    kalan = dis_op.miktar_tedarikcide_kalan or Decimal('0')
    toplam_hesap = (
        (dis_op.toplam_donen_miktar or Decimal('0'))
        + (dis_op.toplam_fire_miktar or Decimal('0'))
        + (dis_op.toplam_eksik_miktar or Decimal('0'))
    )
    if kb > 0:
        dis_op.durum = 'KALITE_BEKLIYOR'
    elif kalan <= 0:
        dis_op.durum = 'TAMAMLANDI'
    elif kalan > 0 and toplam_hesap > 0:
        dis_op.durum = 'KISMI_DONUS'
    elif dis_op.durum == 'TASLAK':
        pass
    elif dis_op.durum in ('GONDERILDI', 'TEDARIKCIDE') and toplam_hesap == 0:
        dis_op.durum = 'TEDARIKCIDE'


def _etiketler(dis_op: DisOperasyon):
    et = []
    if dis_op.beklenen_donus_tarihi and dis_op.beklenen_donus_tarihi < date.today():
        if dis_op.durum not in ('TAMAMLANDI', 'IPTAL', 'ARSIV', 'TASLAK'):
            et.append('gecikti')
    acc = (dis_op.toplam_donen_miktar or Decimal('0')) + (dis_op.toplam_fire_miktar or Decimal('0')) + (
        dis_op.toplam_eksik_miktar or Decimal('0')
    )
    g = dis_op.gonderilen_miktar or Decimal('0')
    if g > 0 and acc < g - Decimal('0.0005') and dis_op.durum == 'TAMAMLANDI':
        et.append('eksik_donus')
    return et


@login_required
def dis_operasyon_listesi(request):
    qs = DisOperasyon.objects.select_related(
        'stok_item', 'operasyon_tipi', 'tedarikci', 'uretim_emri'
    )
    if request.GET.get('f_arsiv') == '1':
        qs = qs.filter(arsivli=True)
    else:
        qs = qs.filter(arsivli=False)

    tip_id = request.GET.get('operasyon_tipi')
    if tip_id:
        qs = qs.filter(operasyon_tipi_id=tip_id)
    ted_id = request.GET.get('tedarikci')
    if ted_id:
        qs = qs.filter(tedarikci_id=ted_id)
    durum = request.GET.get('durum')
    if durum:
        qs = qs.filter(durum=durum)
    kd = request.GET.get('kalite_durumu')
    if kd:
        qs = qs.filter(kalite_durumu=kd)
    d0 = request.GET.get('tarih_bas')
    d1 = request.GET.get('tarih_bit')
    if d0:
        qs = qs.filter(gonderim_tarihi__gte=d0)
    if d1:
        qs = qs.filter(gonderim_tarihi__lte=d1)

    if request.GET.get('geciken') == '1':
        qs = qs.filter(beklenen_donus_tarihi__lt=date.today()).exclude(
            durum__in=('TAMAMLANDI', 'IPTAL', 'ARSIV', 'TASLAK')
        )
    if request.GET.get('acik') == '1':
        qs = qs.exclude(durum__in=('TAMAMLANDI', 'IPTAL', 'ARSIV', 'TASLAK'))
    if request.GET.get('kalite_bekleyen') == '1':
        qs = qs.filter(durum='KALITE_BEKLIYOR')

    arama = (request.GET.get('q') or '').strip()
    if arama:
        qs = qs.filter(
            Q(operasyon_no__icontains=arama)
            | Q(stok_item__stok_kodu__icontains=arama)
            | Q(stok_item__ad__icontains=arama)
        )

    qs = qs.order_by('-created_at')[:500]

    rows = []
    for op in qs:
        mal = op.toplam_gerceklesen_maliyet or Decimal('0')
        rows.append(
            {
                'op': op,
                'etiketler': _etiketler(op),
                'toplam_maliyet': mal,
            }
        )

    try:
        selected_tip_id = int(request.GET.get('operasyon_tipi') or 0) or None
    except (TypeError, ValueError):
        selected_tip_id = None
    try:
        selected_ted_id = int(request.GET.get('tedarikci') or 0) or None
    except (TypeError, ValueError):
        selected_ted_id = None

    context = {
        'rows': rows,
        'tipler': DisOperasyonTipi.objects.filter(aktif=True).order_by('ad'),
        'tedarikciler': Tedarikci.objects.filter(aktif=True).order_by('ad')[:300],
        'durum_secenekleri': DisOperasyon.DURUMLAR,
        'kalite_secenekleri': DisOperasyon.KALITE_DURUMLARI,
        'filtre': request.GET,
        'selected_tip_id': selected_tip_id,
        'selected_ted_id': selected_ted_id,
    }
    return render(request, 'stokapp/dis_operasyon_listesi.html', context)


@login_required
def dis_operasyon_ekle(request):
    tipler = DisOperasyonTipi.objects.filter(aktif=True, ic_dis_tipi='DIS').order_by('ad')
    stoklar = StokItem.objects.filter(arsivli=False, stok_takip=True).order_by('stok_kodu')[:500]
    depolar = Depo.objects.all().order_by('ad')
    tedarikciler = Tedarikci.objects.filter(aktif=True).order_by('ad')
    uretimler = UretimEmri.objects.select_related('recete__urun').order_by('-created_at')[:200]

    if request.method == 'POST':
        taslak = request.POST.get('taslak') == '1'
        try:
            stok_id = int(request.POST.get('stok_item') or 0)
            tip_id = int(request.POST.get('operasyon_tipi') or 0)
            ted_id = int(request.POST.get('tedarikci') or 0)
            g_mik = Decimal(request.POST.get('gonderilen_miktar') or '0')
        except Exception:
            messages.error(request, 'Geçersiz form verisi.')
            return redirect('stokapp:dis_operasyon_ekle')

        if g_mik <= 0:
            messages.error(request, 'Gönderilen miktar 0’dan büyük olmalıdır.')
            return redirect('stokapp:dis_operasyon_ekle')

        op_tipi = get_object_or_404(DisOperasyonTipi, pk=tip_id)
        stok = get_object_or_404(StokItem, pk=stok_id)
        ted = get_object_or_404(Tedarikci, pk=ted_id)

        depo_id = request.POST.get('gonderim_deposu') or ''
        depo = None
        if depo_id:
            depo = get_object_or_404(Depo, pk=int(depo_id))

        ue_id = request.POST.get('uretim_emri') or ''
        ue = None
        if ue_id:
            ue = get_object_or_404(UretimEmri, pk=int(ue_id))

        birim = (request.POST.get('birim') or stok.birim or 'Adet').strip()[:20]
        try:
            bf = Decimal(request.POST.get('birim_fiyat') or '0')
        except Exception:
            bf = Decimal('0')
        try:
            tahmini = Decimal(request.POST.get('tahmini_toplam_maliyet') or '0')
        except Exception:
            tahmini = Decimal('0')

        pb = (request.POST.get('para_birimi') or 'TL').strip()[:3]

        gonderim_t = request.POST.get('gonderim_tarihi') or str(date.today())
        bek_t = request.POST.get('beklenen_donus_tarihi') or ''

        with transaction.atomic():
            dis_op = DisOperasyon(
                operasyon_no=_temp_operasyon_no(),
                stok_item=stok,
                uretim_emri=ue,
                parti_no=(request.POST.get('parti_no') or '').strip()[:120],
                operasyon_tipi=op_tipi,
                tedarikci=ted,
                gonderim_deposu=depo,
                dis_operasyon_lokasyonu=(request.POST.get('dis_operasyon_lokasyonu') or '').strip()[:255],
                gonderilen_miktar=g_mik,
                birim=birim,
                gonderim_tarihi=gonderim_t,
                beklenen_donus_tarihi=bek_t or None,
                birim_fiyat=bf,
                para_birimi=pb,
                tahmini_toplam_maliyet=tahmini,
                durum='TASLAK' if taslak else 'TEDARIKCIDE',
                aciklama=request.POST.get('aciklama') or '',
                sevk_evrak_no=(request.POST.get('sevk_evrak_no') or '').strip()[:120],
                miktar_tedarikcide_kalan=Decimal('0') if taslak else g_mik,
            )
            dis_op.save()
            _finalize_operasyon_no(dis_op)

            if not taslak:
                sitem = (
                    StokItem.objects.select_for_update()
                    .filter(pk=stok.pk)
                    .first()
                )
                if sitem.mevcut_miktar < g_mik:
                    raise ValueError('Depoda yeterli miktar yok.')
                StokHareketi.objects.create(
                    stok_item=sitem,
                    hareket_tipi='DISOP_GONDERIM',
                    miktar=g_mik,
                    birim=birim,
                    referans_no=dis_op.operasyon_no,
                    depo=depo,
                    aciklama=f'Dış operasyon gönderim — {dis_op.operasyon_no}',
                    user=request.user.username,
                    dis_operasyon=dis_op,
                )
                _log(
                    dis_op,
                    request.user,
                    'Gönderim',
                    '',
                    dis_op.durum,
                    f'{g_mik} {birim} tedarikçiye sevk',
                )
            else:
                _log(dis_op, request.user, 'Taslak oluşturuldu', '', 'TASLAK', '')

        messages.success(request, f'Dış operasyon kaydedildi: {dis_op.operasyon_no}')
        return redirect('stokapp:dis_operasyon_detay', pk=dis_op.pk)

    return render(
        request,
        'stokapp/dis_operasyon_form.html',
        {
            'mode': 'ekle',
            'tipler': tipler,
            'stoklar': stoklar,
            'depolar': depolar,
            'tedarikciler': tedarikciler,
            'uretimler': uretimler,
            'bugun': timezone.now().date(),
        },
    )


@login_required
def dis_operasyon_duzenle(request, pk):
    dis_op = get_object_or_404(DisOperasyon, pk=pk)
    if dis_op.arsivli:
        messages.error(request, 'Arşivlenmiş kayıt düzenlenemez.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    if dis_op.durum not in ('TASLAK', 'GONDERILDI', 'TEDARIKCIDE'):
        messages.error(request, 'Bu aşamada kayıt sadece sınırlı alanlarda düzenlenebilir.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)

    tipler = DisOperasyonTipi.objects.filter(aktif=True).order_by('ad')
    depolar = Depo.objects.all().order_by('ad')
    tedarikciler = Tedarikci.objects.filter(aktif=True).order_by('ad')
    uretimler = UretimEmri.objects.select_related('recete__urun').order_by('-created_at')[:200]

    if request.method == 'POST':
        dis_op.parti_no = (request.POST.get('parti_no') or '').strip()[:120]
        dis_op.dis_operasyon_lokasyonu = (request.POST.get('dis_operasyon_lokasyonu') or '').strip()[:255]
        dis_op.aciklama = request.POST.get('aciklama') or ''
        dis_op.sevk_evrak_no = (request.POST.get('sevk_evrak_no') or '').strip()[:120]
        dis_op.beklenen_donus_tarihi = request.POST.get('beklenen_donus_tarihi') or None
        depo_id = request.POST.get('gonderim_deposu') or ''
        dis_op.gonderim_deposu = get_object_or_404(Depo, pk=int(depo_id)) if depo_id else None
        ue_id = request.POST.get('uretim_emri') or ''
        dis_op.uretim_emri = get_object_or_404(UretimEmri, pk=int(ue_id)) if ue_id else None

        if dis_op.durum == 'TASLAK':
            try:
                dis_op.operasyon_tipi = get_object_or_404(
                    DisOperasyonTipi, pk=int(request.POST.get('operasyon_tipi') or 0)
                )
                dis_op.tedarikci = get_object_or_404(Tedarikci, pk=int(request.POST.get('tedarikci') or 0))
                dis_op.gonderim_tarihi = request.POST.get('gonderim_tarihi') or dis_op.gonderim_tarihi
                dis_op.birim_fiyat = Decimal(request.POST.get('birim_fiyat') or '0')
                dis_op.para_birimi = (request.POST.get('para_birimi') or 'TL').strip()[:3]
                dis_op.tahmini_toplam_maliyet = Decimal(request.POST.get('tahmini_toplam_maliyet') or '0')
            except Exception:
                messages.error(request, 'Form alanları geçersiz.')
                return redirect('stokapp:dis_operasyon_duzenle', pk=pk)

        dis_op.save()
        _log(dis_op, request.user, 'Düzenleme', '', dis_op.durum, '')
        messages.success(request, 'Kayıt güncellendi.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)

    return render(
        request,
        'stokapp/dis_operasyon_form.html',
        {
            'mode': 'duzenle',
            'op': dis_op,
            'tipler': tipler,
            'stoklar': StokItem.objects.filter(pk=dis_op.stok_item_id),
            'depolar': depolar,
            'tedarikciler': tedarikciler,
            'uretimler': uretimler,
        },
    )


@login_required
def dis_operasyon_detay(request, pk):
    dis_op = get_object_or_404(
        DisOperasyon.objects.select_related('stok_item', 'operasyon_tipi', 'tedarikci', 'gonderim_deposu', 'uretim_emri'),
        pk=pk,
    )
    tab = request.GET.get('tab') or 'genel'
    donuslar = dis_op.donuslar.all().prefetch_related('kalite_kayitlari')
    kaliteler = dis_op.kalite_kayitlari.select_related('donus').order_by('-created_at')
    dosyalar = dis_op.dosyalar.all()
    loglar = dis_op.loglar.all()[:200]

    toplam_donus_mik = sum((d.donen_miktar or Decimal('0')) for d in donuslar)
    toplam_maliyet = dis_op.toplam_gerceklesen_maliyet or Decimal('0')
    birim_ek = Decimal('0')
    if dis_op.gonderilen_miktar and dis_op.gonderilen_miktar > 0:
        birim_ek = (toplam_maliyet / dis_op.gonderilen_miktar).quantize(Decimal('0.0001'))

    context = {
        'op': dis_op,
        'tab': tab,
        'donuslar': donuslar,
        'kaliteler': kaliteler,
        'dosyalar': dosyalar,
        'loglar': loglar,
        'etiketler': _etiketler(dis_op),
        'toplam_donus_mik': toplam_donus_mik,
        'toplam_maliyet': toplam_maliyet,
        'birim_ek_maliyet': birim_ek,
    }
    return render(request, 'stokapp/dis_operasyon_detay.html', context)


@login_required
def dis_operasyon_gonder(request, pk):
    """Taslaktan stoğu düşürerek gönderime çevirir."""
    if request.method != 'POST':
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    dis_op = get_object_or_404(DisOperasyon, pk=pk)
    if dis_op.durum != 'TASLAK':
        messages.error(request, 'Yalnızca taslak kayıtlar gönderilebilir.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    try:
        with transaction.atomic():
            sitem = StokItem.objects.select_for_update().get(pk=dis_op.stok_item_id)
            g = dis_op.gonderilen_miktar
            if sitem.mevcut_miktar < g:
                raise ValueError('Depoda yeterli stok yok.')
            StokHareketi.objects.create(
                stok_item=sitem,
                hareket_tipi='DISOP_GONDERIM',
                miktar=g,
                birim=dis_op.birim,
                referans_no=dis_op.operasyon_no,
                depo=dis_op.gonderim_deposu,
                aciklama=f'Dış operasyon gönderim — {dis_op.operasyon_no}',
                user=request.user.username,
                dis_operasyon=dis_op,
            )
            eski = dis_op.durum
            dis_op.miktar_tedarikcide_kalan = g
            dis_op.durum = 'TEDARIKCIDE'
            dis_op.save(update_fields=['miktar_tedarikcide_kalan', 'durum', 'updated_at'])
            _log(dis_op, request.user, 'Taslaktan gönderim', eski, dis_op.durum, str(g))
        messages.success(request, 'Stok düşüldü, kayıt tedarikçide olarak işaretlendi.')
    except Exception as e:
        messages.error(request, str(e))
    return redirect('stokapp:dis_operasyon_detay', pk=pk)


@login_required
def dis_operasyon_donus_al(request, pk):
    dis_op = get_object_or_404(DisOperasyon, pk=pk)
    if dis_op.arsivli or dis_op.durum in ('IPTAL', 'ARSIV', 'TASLAK'):
        messages.error(request, 'Bu kayıt için dönüş alınamaz.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)

    onceki_toplam = dis_op.donuslar.aggregate(
        sm=Sum('donen_miktar'),
        sf=Sum('fire_miktari'),
        se=Sum('eksik_miktari'),
    )
    prev_d = onceki_toplam['sm'] or Decimal('0')
    prev_f = onceki_toplam['sf'] or Decimal('0')
    prev_e = onceki_toplam['se'] or Decimal('0')

    if request.method == 'POST':
        try:
            donen = Decimal(request.POST.get('donen_miktar') or '0')
            fire = Decimal(request.POST.get('fire_miktari') or '0')
            eksik = Decimal(request.POST.get('eksik_miktari') or '0')
        except Exception:
            messages.error(request, 'Miktar alanları geçersiz.')
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

        qc = request.POST.get('kalite_kontrol_gerekli') == '1'
        donus_tarihi = request.POST.get('donus_tarihi') or str(date.today())

        paket = donen + fire + eksik
        if paket <= 0:
            messages.error(request, 'Dönen + fire + eksik toplamı 0’dan büyük olmalıdır.')
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

        kalan_emir = dis_op.miktar_tedarikcide_kalan or Decimal('0')
        if paket > kalan_emir + Decimal('0.0001'):
            messages.error(request, 'Bu dönüş, tedarikçide kalan miktardan fazla olamaz.')
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

        g = dis_op.gonderilen_miktar or Decimal('0')
        if prev_d + prev_f + prev_e + paket > g + Decimal('0.0001'):
            messages.error(request, 'Dönen + fire + eksik toplamı gönderilen miktarı aşamaz.')
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

        try:
            nak = Decimal(request.POST.get('nakliye_maliyeti') or '0')
            ek = Decimal(request.POST.get('ek_maliyet') or '0')
            top = Decimal(request.POST.get('toplam_maliyet') or '0')
            gbf = request.POST.get('gerceklesen_birim_fiyat') or ''
            gbf_dec = Decimal(gbf) if gbf.strip() else None
        except Exception:
            messages.error(request, 'Maliyet alanları geçersiz.')
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

        try:
            with transaction.atomic():
                sitem = StokItem.objects.select_for_update().get(pk=dis_op.stok_item_id)
                if sitem.dis_operasyonda_miktar < paket - Decimal('0.0001'):
                    raise ValueError('Dış operasyonda takip edilen miktar yetersiz (stok tutarsızlığı).')

                if fire > 0:
                    StokHareketi.objects.create(
                        stok_item=sitem,
                        hareket_tipi='DISOP_FIRE',
                        miktar=fire,
                        birim=dis_op.birim,
                        referans_no=dis_op.operasyon_no,
                        aciklama=f'Dış operasyon fire — {dis_op.operasyon_no}',
                        user=request.user.username,
                        dis_operasyon=dis_op,
                    )
                if eksik > 0:
                    StokHareketi.objects.create(
                        stok_item=sitem,
                        hareket_tipi='DISOP_EKSIK',
                        miktar=eksik,
                        birim=dis_op.birim,
                        referans_no=dis_op.operasyon_no,
                        aciklama=f'Dış operasyon eksik — {dis_op.operasyon_no}',
                        user=request.user.username,
                        dis_operasyon=dis_op,
                    )

                if qc and donen > 0:
                    StokHareketi.objects.create(
                        stok_item=sitem,
                        hareket_tipi='DISOP_TESLIM_KALITE',
                        miktar=donen,
                        birim=dis_op.birim,
                        referans_no=dis_op.operasyon_no,
                        aciklama=f'Dış operasyon teslim (kalite bekliyor) — {dis_op.operasyon_no}',
                        user=request.user.username,
                        dis_operasyon=dis_op,
                    )
                elif donen > 0:
                    StokHareketi.objects.create(
                        stok_item=sitem,
                        hareket_tipi='DISOP_DONUS',
                        miktar=donen,
                        birim=dis_op.birim,
                        referans_no=dis_op.operasyon_no,
                        aciklama=f'Dış operasyon dönüş — {dis_op.operasyon_no}',
                        user=request.user.username,
                        dis_operasyon=dis_op,
                    )

                donus = DisOperasyonDonus.objects.create(
                    dis_operasyon=dis_op,
                    donus_tarihi=donus_tarihi,
                    donen_miktar=donen,
                    fire_miktari=fire,
                    eksik_miktari=eksik,
                    gerceklesen_birim_fiyat=gbf_dec,
                    nakliye_maliyeti=nak,
                    ek_maliyet=ek,
                    toplam_maliyet=top,
                    kalite_kontrol_gerekli=qc,
                    kalite_islenildi=not qc,
                    aciklama=request.POST.get('aciklama') or '',
                )

                dis_op.miktar_tedarikcide_kalan = kalan_emir - paket
                dis_op.toplam_donen_miktar = (dis_op.toplam_donen_miktar or Decimal('0')) + donen
                dis_op.toplam_fire_miktar = (dis_op.toplam_fire_miktar or Decimal('0')) + fire
                dis_op.toplam_eksik_miktar = (dis_op.toplam_eksik_miktar or Decimal('0')) + eksik
                dis_op.toplam_gerceklesen_maliyet = (dis_op.toplam_gerceklesen_maliyet or Decimal('0')) + top
                if qc and donen > 0:
                    dis_op.miktar_kalite_bekliyor = (dis_op.miktar_kalite_bekliyor or Decimal('0')) + donen
                if qc:
                    dis_op.kalite_durumu = 'BEKLIYOR'
                _sync_durum(dis_op)
                dis_op.save()
                _log(dis_op, request.user, 'Dönüş alındı', '', dis_op.durum, f'Dönüş #{donus.pk}')

            messages.success(request, 'Dönüş kaydedildi.')
            return redirect('stokapp:dis_operasyon_detay', pk=pk)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('stokapp:dis_operasyon_donus_al', pk=pk)

    return render(
        request,
        'stokapp/dis_operasyon_donus.html',
        {
            'op': dis_op,
            'prev_donen': prev_d,
            'prev_fire': prev_f,
            'prev_eksik': prev_e,
        },
    )


@login_required
def dis_operasyon_kalite(request, donus_pk):
    donus = get_object_or_404(DisOperasyonDonus.objects.select_related('dis_operasyon'), pk=donus_pk)
    dis_op = donus.dis_operasyon
    if not donus.kalite_kontrol_gerekli or donus.kalite_islenildi:
        messages.error(request, 'Bu dönüş için kalite girişi gerekli değil veya tamamlanmış.')
        return redirect('stokapp:dis_operasyon_detay', pk=dis_op.pk)

    if request.method == 'POST':
        sonuc = request.POST.get('sonuc') or 'KABUL'
        if sonuc not in ('KABUL', 'SARTLI_KABUL', 'RED'):
            sonuc = 'KABUL'
        try:
            kabul = Decimal(request.POST.get('kabul_miktari') or '0')
            red = Decimal(request.POST.get('red_miktari') or '0')
        except Exception:
            messages.error(request, 'Miktar geçersiz.')
            return redirect('stokapp:dis_operasyon_kalite', donus_pk=donus_pk)

        if kabul + red > donus.donen_miktar + Decimal('0.0001'):
            messages.error(request, 'Kabul + red, dönen miktardan fazla olamaz.')
            return redirect('stokapp:dis_operasyon_kalite', donus_pk=donus_pk)

        try:
            with transaction.atomic():
                sitem = StokItem.objects.select_for_update().get(pk=dis_op.stok_item_id)
                kb = dis_op.miktar_kalite_bekliyor or Decimal('0')
                if kb < donus.donen_miktar - Decimal('0.0001'):
                    raise ValueError('Kalite bekleyen miktar tutarsız.')

                if kabul > 0:
                    StokHareketi.objects.create(
                        stok_item=sitem,
                        hareket_tipi='DISOP_QC_KABUL',
                        miktar=kabul,
                        birim=dis_op.birim,
                        referans_no=dis_op.operasyon_no,
                        aciklama=f'Dış operasyon kalite kabul — {dis_op.operasyon_no}',
                        user=request.user.username,
                        dis_operasyon=dis_op,
                    )

                DisOperasyonKaliteKontrol.objects.create(
                    dis_operasyon=dis_op,
                    donus=donus,
                    kontrol_tarihi=request.POST.get('kontrol_tarihi') or str(date.today()),
                    kontrol_eden=(request.POST.get('kontrol_eden') or request.user.username)[:200],
                    sonuc=sonuc,
                    kabul_miktari=kabul,
                    red_miktari=red,
                    sartli_kabul_notu=request.POST.get('sartli_kabul_notu') or '',
                    red_nedeni=request.POST.get('red_nedeni') or '',
                    aciklama=request.POST.get('aciklama') or '',
                )

                dis_op.miktar_kalite_bekliyor = kb - donus.donen_miktar
                if dis_op.miktar_kalite_bekliyor < 0:
                    dis_op.miktar_kalite_bekliyor = Decimal('0')
                donus.kalite_islenildi = True
                donus.save(update_fields=['kalite_islenildi'])

                if sonuc == 'RED':
                    dis_op.kalite_durumu = 'RED'
                elif sonuc == 'SARTLI_KABUL':
                    dis_op.kalite_durumu = 'SARTLI_KABUL'
                else:
                    dis_op.kalite_durumu = 'KABUL'

                _sync_durum(dis_op)
                dis_op.save()
                _log(dis_op, request.user, 'Kalite kontrol', '', dis_op.durum, f'Dönüş #{donus.pk}')

            messages.success(request, 'Kalite kaydı oluşturuldu.')
            return redirect('stokapp:dis_operasyon_detay', pk=dis_op.pk)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('stokapp:dis_operasyon_kalite', donus_pk=donus_pk)

    return render(request, 'stokapp/dis_operasyon_kalite.html', {'op': dis_op, 'donus': donus})


@login_required
def dis_operasyon_arsivle(request, pk):
    if request.method != 'POST':
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    dis_op = get_object_or_404(DisOperasyon, pk=pk)
    if dis_op.miktar_kalite_bekliyor and dis_op.miktar_kalite_bekliyor > 0:
        messages.error(request, 'Kalite bekleyen miktar varken arşivlenemez.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    eski = dis_op.durum
    dis_op.arsivli = True
    dis_op.durum = 'ARSIV'
    dis_op.save(update_fields=['arsivli', 'durum', 'updated_at'])
    _log(dis_op, request.user, 'Arşivlendi', eski, 'ARSIV', '')
    messages.success(request, 'Kayıt arşivlendi.')
    return redirect('stokapp:dis_operasyon_listesi')


@login_required
def dis_operasyon_dosya_ekle(request, pk):
    if request.method != 'POST':
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    dis_op = get_object_or_404(DisOperasyon, pk=pk)
    f = request.FILES.get('dosya')
    if not f:
        messages.error(request, 'Dosya seçilmedi.')
        return redirect('stokapp:dis_operasyon_detay', pk=pk)
    DisOperasyonDosya.objects.create(
        dis_operasyon=dis_op,
        dosya=f,
        dosya_tipi=request.POST.get('dosya_tipi') or 'GENEL',
        aciklama=(request.POST.get('aciklama') or '')[:255],
    )
    _log(dis_op, request.user, 'Dosya eklendi', dis_op.durum, dis_op.durum, f.name)
    messages.success(request, 'Dosya yüklendi.')
    return redirect('stokapp:dis_operasyon_detay', pk=pk)
