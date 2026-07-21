from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

import pandas as pd

from .stok_tamamlanma import (
    STOK_TAMAMLANMA_ALANLARI,
    STOK_TIPLERI,
    get_stok_tamamlanma_kurallari,
    kaydet_stok_tamamlanma_kurallari,
    stok_tamamlanma_rapor_verisi,
)
from .nav_visibility import (
    NAV_KEY_STOK_TAMAMLANMA_KURALLARI,
    NAV_KEY_STOK_TAMAMLANMA_RAPORU,
    hidden_nav_access_required,
)

_tamamlanma_rapor_guard = hidden_nav_access_required(NAV_KEY_STOK_TAMAMLANMA_RAPORU)
_tamamlanma_kural_guard = hidden_nav_access_required(NAV_KEY_STOK_TAMAMLANMA_KURALLARI)


@login_required
@_tamamlanma_kural_guard
def stok_tamamlanma_ayarlari(request):
    """Stok tipine göre tamamlanma kuralları."""
    kurallar = get_stok_tamamlanma_kurallari()

    if request.method == 'POST':
        kaydet_stok_tamamlanma_kurallari(request.POST)
        messages.success(request, 'Stok tamamlanma kuralları kaydedildi.')
        return redirect('stokapp:stok_tamamlanma_ayarlari')

    tip_etiket = {
        'HAM_MADDE': 'Ham Madde',
        'YARI_MAMUL': 'Yarı Mamül',
        'URUN': 'Ürün',
    }
    stok_tipleri = [(t, tip_etiket[t]) for t in STOK_TIPLERI]
    kural_matris = []
    for alan in STOK_TAMAMLANMA_ALANLARI:
        hucreler = []
        for tip_kod, tip_ad in stok_tipleri:
            hucreler.append({
                'tip_kod': tip_kod,
                'field_name': f'kural_{tip_kod}_{alan["key"]}',
                'checked': bool(kurallar.get(tip_kod, {}).get(alan['key'], False)),
            })
        kural_matris.append({'alan': alan, 'hucreler': hucreler})
    return render(request, 'stokapp/stok_tamamlanma_ayarlari.html', {
        'kural_matris': kural_matris,
        'stok_tipleri': stok_tipleri,
    })


@login_required
@_tamamlanma_rapor_guard
def stok_tamamlanma_raporu(request):
    veri = stok_tamamlanma_rapor_verisi(request)
    return render(request, 'stokapp/stok_tamamlanma_raporu.html', veri)


def _rapor_export_satirlari(request):
    veri = stok_tamamlanma_rapor_verisi(request)
    satirlar = []
    for row in veri['satirlar']:
        stok = row['stok']
        durum = row['durum']
        satir = {
            'Stok Kodu': stok.stok_kodu,
            'Ürün Adı': stok.ad,
            'Stok Tipi': durum['stok_tipi'],
            'Kategori': stok.kategori.ad if stok.kategori else '',
            'Tamamlanma %': durum['yuzde'],
            'Durum': 'Tamam' if durum['tamam'] else 'Eksik',
        }
        for alan in veri['gosterilecek_alanlar']:
            key = alan['key']
            info = durum['alanlar'].get(key, {})
            if info.get('gerekli'):
                satir[alan['label']] = 'Var' if info.get('dolu') else 'Eksik'
            else:
                satir[alan['label']] = 'O'
        satirlar.append(satir)
    return veri, satirlar


@login_required
@_tamamlanma_rapor_guard
@never_cache
def stok_tamamlanma_raporu_export_excel(request):
    try:
        veri, satirlar = _rapor_export_satirlari(request)
        df = pd.DataFrame(satirlar)
        if df.empty:
            cols = ['Stok Kodu', 'Ürün Adı', 'Stok Tipi', 'Kategori', 'Tamamlanma %', 'Durum']
            for alan in veri['gosterilecek_alanlar']:
                cols.append(alan['label'])
            df = pd.DataFrame(columns=cols)

        from django.utils import timezone
        ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="stok_tamamlanma_{ts}.xlsx"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            ozet_df = pd.DataFrame([{
                'Toplam Stok': veri['ozet']['toplam'],
                'Tam Tamamlanmış': veri['ozet']['tam'],
                'Eksik': veri['ozet']['eksik'],
                'Tamamlanma Oranı %': veri['ozet']['tam_yuzde'],
            }])
            ozet_df.to_excel(writer, sheet_name='Özet', index=False)
            df.to_excel(writer, sheet_name='Detay', index=False)
            for sheet_name in ('Özet', 'Detay'):
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except Exception:
                            pass
                    worksheet.column_dimensions[column_letter].width = min(max_length + 2, 40)
        return response
    except Exception as exc:
        messages.error(request, f'Excel oluşturulamadı: {exc}')
        return redirect('stokapp:stok_tamamlanma_raporu')


@login_required
@_tamamlanma_rapor_guard
@never_cache
def stok_tamamlanma_raporu_export_pdf(request):
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        messages.error(request, 'PDF oluşturma için WeasyPrint kütüphanesi gerekli.')
        return redirect('stokapp:stok_tamamlanma_raporu')

    from django.utils import timezone

    veri, _ = _rapor_export_satirlari(request)
    olusturma = timezone.localtime(timezone.now())
    f = veri['filtreler']

    alan_basliklar = ''.join(
        f'<th>{a["label"]}</th>' for a in veri['gosterilecek_alanlar']
    )
    html_rows = []
    for row in veri['satirlar'][:1500]:
        stok = row['stok']
        durum = row['durum']
        hucreler = ''
        for alan in veri['gosterilecek_alanlar']:
            info = durum['alanlar'].get(alan['key'], {})
            if info.get('gerekli'):
                hucreler += (
                    f'<td class="center ok">✓</td>'
                    if info.get('dolu')
                    else '<td class="center no">✗</td>'
                )
            else:
                hucreler += '<td class="center op">O</td>'
        durum_cls = 'ok' if durum['tamam'] else 'no'
        html_rows.append(
            f'<tr>'
            f'<td>{stok.stok_kodu}</td>'
            f'<td>{stok.ad}</td>'
            f'<td>{durum["stok_tipi"]}</td>'
            f'<td class="num {durum_cls}">{durum["yuzde"]}%</td>'
            f'{hucreler}'
            f'</tr>'
        )

    ozet_satirlar = ''
    for alan in veri['gosterilecek_alanlar']:
        say = veri['alan_eksik_ozet'].get(alan['key'], 0)
        if say:
            ozet_satirlar += f'<li>{alan["label"]}: <strong>{say}</strong> stokta eksik</li>'

    filtre_metin = []
    if f['tip'] != 'TUMU':
        filtre_metin.append(f'Stok tipi: {f["tip"]}')
    if f['sadece_eksik']:
        filtre_metin.append('Yalnızca eksikler')
    if f['eksik_alan']:
        etiket = next(
            (a['label'] for a in STOK_TAMAMLANMA_ALANLARI if a['key'] == f['eksik_alan']),
            f['eksik_alan'],
        )
        filtre_metin.append(f'Eksik alan: {etiket}')
    if f['q']:
        filtre_metin.append(f'Arama: {f["q"]}')

    html = f"""
    <html><head><meta charset="utf-8"></head><body>
      <h1>Stok Tamamlanma Raporu</h1>
      <div class="meta">
        Oluşturma: {olusturma.strftime('%d.%m.%Y %H:%M')}
        · Kayıt: {veri['ozet']['toplam']}
        · Tam: {veri['ozet']['tam']} ({veri['ozet']['tam_yuzde']}%)
        · Eksik: {veri['ozet']['eksik']}
        {' · Filtre: ' + ', '.join(filtre_metin) if filtre_metin else ''}
      </div>
      <div class="ozet-box">
        <strong>Alan bazında eksik özet</strong>
        <ul>{ozet_satirlar or '<li>Eksik kayıt yok</li>'}</ul>
      </div>
      <table>
        <thead>
          <tr>
            <th>Stok Kodu</th><th>Ürün</th><th>Tip</th><th>%</th>{alan_basliklar}
          </tr>
        </thead>
        <tbody>
          {''.join(html_rows) if html_rows else '<tr><td colspan="20" class="empty">Kayıt bulunamadı.</td></tr>'}
        </tbody>
      </table>
    </body></html>
    """
    css = CSS(string="""
        @page { size: A4 landscape; margin: 8mm; }
        body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 7.5pt; color: #111827; }
        h1 { font-size: 13pt; margin: 0 0 4px 0; }
        .meta { color: #6b7280; font-size: 7.5pt; margin-bottom: 8px; }
        .ozet-box { background: #f9fafb; border: 1px solid #e5e7eb; padding: 6px 8px;
                    margin-bottom: 10px; border-radius: 4px; font-size: 7.5pt; }
        .ozet-box ul { margin: 4px 0 0 16px; padding: 0; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f3f4f6; border: 1px solid #d1d5db; padding: 4px 3px; text-align: left; }
        td { border: 1px solid #e5e7eb; padding: 3px; vertical-align: middle; }
        .num { text-align: right; font-weight: 600; }
        .center { text-align: center; }
        .ok { color: #065f46; }
        .no { color: #991b1b; }
        .op { color: #2563eb; font-weight: 700; }
        .empty { text-align: center; color: #6b7280; padding: 20px; }
    """)
    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(
            stylesheets=[css]
        )
    except Exception as exc:
        messages.error(request, f'PDF oluşturulamadı: {exc}')
        return redirect('stokapp:stok_tamamlanma_raporu')

    filename = f'stok_tamamlanma_{olusturma.strftime("%Y%m%d_%H%M")}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
