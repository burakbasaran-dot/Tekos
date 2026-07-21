"""
Teklif şartları: hazır şablonlar, parametre doğrulama, metin üretimi ve istemci meta verisi.

İleride müşteri bazlı varsayılan set vb. için SABLONLAR veya varsayılan satır üretimi genişletilebilir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from dateutil.relativedelta import relativedelta
from django.db import transaction

from .models import Teklif, TeklifSarti


def _int_safe(v: Any, default: int = 0) -> int:
    try:
        return int(float(str(v).strip().replace(',', '.')))
    except (ValueError, TypeError, AttributeError):
        return default


def _strip(v: Any) -> str:
    return (str(v) if v is not None else '').strip()


def sure_metni_tr(miktar: int, birim: str) -> str:
    """Sayı + birim için doğal Türkçe ifade."""
    m = max(1, int(miktar))
    b = _strip(birim).lower()
    if b == 'hafta':
        return f'{m} hafta'
    if b == 'ay':
        return f'{m} ay'
    if b in ('yil', 'yıl'):
        return f'{m} yıl'
    return f'{m} gün'


def _sure_from_vals(vals: dict[str, Any], default_miktar: int, default_birim: str = 'gun') -> tuple[int, str]:
    """miktar+birim veya eski tekil gun alanından süre üretir."""
    vals = dict(vals or {})
    birim = _strip(vals.get('birim')).lower() or default_birim
    if birim == 'yıl':
        birim = 'yil'
    miktar = _int_safe(vals.get('miktar'), 0)
    if miktar <= 0 and vals.get('gun') is not None:
        miktar = max(1, _int_safe(vals.get('gun'), default_miktar))
        birim = 'gun'
    elif miktar <= 0:
        miktar = max(1, default_miktar)
    return miktar, birim


def gecerlilik_bitis_tarihi(duzenleme: date, raw_rows: list[dict[str, Any]]) -> date | None:
    """İstemci/POST şart satırlarından aktif GECERLILIK_GUN için bitiş tarihi."""
    if not duzenleme or not isinstance(raw_rows, list):
        return None
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        tip = _strip(row.get('tip')).upper()
        if tip != TeklifSarti.TIP_HAZIR:
            continue
        if _strip(row.get('sablon_kodu')) != 'GECERLILIK_GUN':
            continue
        if not row.get('aktif'):
            continue
        dv = dict(row.get('degerler') or {})
        coerce_legacy_degerler('GECERLILIK_GUN', dv)
        m, b = _sure_from_vals(dv, 10, 'gun')
        if b == 'gun':
            return duzenleme + timedelta(days=m)
        if b == 'hafta':
            return duzenleme + timedelta(days=7 * m)
        if b == 'ay':
            return duzenleme + relativedelta(months=m)
        if b in ('yil', 'yıl'):
            return duzenleme + relativedelta(years=m)
        return duzenleme + timedelta(days=m)
    return None


def coerce_legacy_degerler(kod: str, dv: dict[str, Any]) -> None:
    """DB / eski istemci anahtarlarını yeni şemaya uyarlar."""
    if kod == 'GECERLILIK_GUN':
        if dv.get('miktar') in (None, '', 0) and dv.get('gun') is not None:
            dv['miktar'] = _int_safe(dv.get('gun'), 10)
        if not _strip(dv.get('birim')):
            dv['birim'] = 'gun'
    elif kod == 'TESLIM_GUN':
        if dv.get('miktar') in (None, '', 0) and dv.get('gun') is not None:
            dv['miktar'] = _int_safe(dv.get('gun'), 7)
        if not _strip(dv.get('birim')):
            dv['birim'] = 'gun'
    elif kod == 'ODEME_ORAN':
        if not _strip(dv.get('odeme_modu')):
            dv['odeme_modu'] = 'oran'
        if dv.get('vade_miktar') in (None, '', 0):
            dv['vade_miktar'] = 30
        if not _strip(dv.get('vade_birim')):
            dv['vade_birim'] = 'gun'


SURE_BIRIM_SECENEKLERI = [
    {'v': 'gun', 'l': 'Gün'},
    {'v': 'hafta', 'l': 'Hafta'},
    {'v': 'ay', 'l': 'Ay'},
    {'v': 'yil', 'l': 'Yıl'},
]


@dataclass
class Alan:
    ad: str
    tur: str  # sayi | secim
    etiket: str = ''
    varsayilan: Any = None
    secenekler: list[dict[str, str]] = field(default_factory=list)  # [{"v":"x","l":"Y"}]
    odeme_alt_grup: str | None = None  # 'oran' | 'vadeli' — istemci koşullu gösterim


@dataclass
class Sablon:
    kod: str
    baslik: str
    yardim: str
    alanlar: list[Alan] = field(default_factory=list)
    sadece_onay: bool = False  # checkbox ile aktif/pasif
    varsayilan_aktif: bool = False

    def varsayilan_degerler(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for a in self.alanlar:
            d[a.ad] = a.varsayilan
        return d


def _render_gecerlilik(vals: dict[str, Any]) -> str:
    m, b = _sure_from_vals(vals, 10, 'gun')
    s = sure_metni_tr(m, b)
    return f'Bu teklif, teklif tarihinden itibaren {s} süreyle geçerlidir.'


def _render_kdv(vals: dict[str, Any]) -> str:
    s = _strip(vals.get('secim')).lower() or 'haric'
    if s == 'dahil':
        return 'Fiyatlara KDV dahildir.'
    return 'Fiyatlara KDV dahil değildir.'


def _render_teslim(vals: dict[str, Any]) -> str:
    m, b = _sure_from_vals(vals, 7, 'gun')
    s = sure_metni_tr(m, b)
    return f'Teslim süresi, sipariş onayı sonrası {s}dır.'


def _render_odeme(vals: dict[str, Any]) -> str:
    mod = _strip(vals.get('odeme_modu')).lower() or 'oran'
    if mod == 'vadeli':
        vm, vb = _sure_from_vals(
            {
                'miktar': vals.get('vade_miktar'),
                'birim': vals.get('vade_birim'),
                'gun': vals.get('vade_gun'),
            },
            30,
            'gun',
        )
        s = sure_metni_tr(vm, vb)
        return f'Ödeme, fatura tarihinden itibaren {s} vadelidir.'
    ilk = max(0, min(100, _int_safe(vals.get('ilk'), 50)))
    kalan = max(0, min(100, _int_safe(vals.get('kalan'), 50)))
    return f'Ödeme şekli: %{ilk} sipariş onayında, %{kalan} teslim öncesi.'


def _render_nakliye(vals: dict[str, Any]) -> str:
    s = _strip(vals.get('secim')).lower() or 'haric'
    if s == 'dahil':
        return 'Nakliye fiyata dahildir.'
    return 'Nakliye fiyata dahil değildir.'


TEKNIK_ONAY_METNI = (
    'Üretim, müşteri tarafından onaylanan teknik resim veya şartnameye göre yapılır.'
)
REVIZYON_METNI = 'Teklif kapsamı dışında istenen revizyonlar ayrıca fiyatlandırılır.'
TERMIN_METNI = 'Malzeme temini ve dış prosesler teslim süresini etkileyebilir.'
IPTAL_METNI = 'Sipariş onayından sonra iptal durumunda oluşan maliyetler yansıtılır.'
GARANTI_METNI = 'Hatalı kullanım ve montaj garanti kapsamı dışındadır.'


SABLONLAR: list[Sablon] = [
    Sablon(
        'GECERLILIK_GUN',
        'Teklif Geçerlilik Süresi',
        'Geçerlilik süresi ve birimi (gün / hafta / ay / yıl).',
        [
            Alan('miktar', 'sayi', 'Süre', 10),
            Alan('birim', 'secim', 'Birim', 'gun', SURE_BIRIM_SECENEKLERI),
        ],
    ),
    Sablon(
        'KDV_DURUM',
        'KDV Durumu',
        'Fiyatlarda KDV’nin durumu.',
        [
            Alan(
                'secim',
                'secim',
                '',
                'haric',
                [{'v': 'dahil', 'l': 'Dahil'}, {'v': 'haric', 'l': 'Hariç'}],
            )
        ],
        varsayilan_aktif=True,
    ),
    Sablon(
        'TESLIM_GUN',
        'Teslim Süresi',
        'Sipariş onayı sonrası teslim süresi ve birimi.',
        [
            Alan('miktar', 'sayi', 'Süre', 7),
            Alan('birim', 'secim', 'Birim', 'gun', SURE_BIRIM_SECENEKLERI),
        ],
    ),
    Sablon(
        'ODEME_ORAN',
        'Ödeme Şekli',
        'Oranlı ödeme veya fatura tarihi + vadeli ödeme.',
        [
            Alan(
                'odeme_modu',
                'secim',
                'Ödeme tipi',
                'oran',
                [
                    {'v': 'oran', 'l': 'Oranlı (sipariş / teslim)'},
                    {'v': 'vadeli', 'l': 'Fatura + vade'},
                ],
            ),
            Alan('ilk', 'sayi', 'İlk % (sipariş onayı)', 50, odeme_alt_grup='oran'),
            Alan('kalan', 'sayi', 'Kalan % (teslim öncesi)', 50, odeme_alt_grup='oran'),
            Alan('vade_miktar', 'sayi', 'Vade süresi', 30, odeme_alt_grup='vadeli'),
            Alan(
                'vade_birim',
                'secim',
                'Vade birimi',
                'gun',
                SURE_BIRIM_SECENEKLERI,
                odeme_alt_grup='vadeli',
            ),
        ],
    ),
    Sablon(
        'NAKLIYE_DURUM',
        'Nakliye',
        'Nakliyenin fiyata dahil olup olmaması.',
        [
            Alan(
                'secim',
                'secim',
                '',
                'haric',
                [{'v': 'dahil', 'l': 'Dahil'}, {'v': 'haric', 'l': 'Hariç'}],
            )
        ],
    ),
    Sablon(
        'TEKNIK_ONAY',
        'Teknik Onay',
        'Teknik resim / şartnameye uygun üretim.',
        sadece_onay=True,
    ),
    Sablon(
        'REVIZYON',
        'Revizyon',
        'Kapsam dışı revizyon fiyatlandırması.',
        sadece_onay=True,
    ),
    Sablon(
        'TERMIN_DEGISIKLIGI',
        'Termin Değişikliği',
        'Malzeme ve dış proseslerin teslim süresine etkisi.',
        sadece_onay=True,
    ),
    Sablon(
        'IPTAL_SARTI',
        'İptal Şartı',
        'Onay sonrası iptal maliyetleri.',
        sadece_onay=True,
    ),
    Sablon(
        'GARANTI_SORUMLULUK',
        'Garanti / Sorumluluk',
        'Kullanım ve montaj istisnası.',
        sadece_onay=True,
    ),
]

SABLON_MAP: dict[str, Sablon] = {s.kod: s for s in SABLONLAR}

_RENDERER: dict[str, Callable[[dict[str, Any]], str]] = {
    'GECERLILIK_GUN': _render_gecerlilik,
    'KDV_DURUM': _render_kdv,
    'TESLIM_GUN': _render_teslim,
    'ODEME_ORAN': _render_odeme,
    'NAKLIYE_DURUM': _render_nakliye,
}

_OZEL_METIN_SABILITLER = {
    'TEKNIK_ONAY': TEKNIK_ONAY_METNI,
    'REVIZYON': REVIZYON_METNI,
    'TERMIN_DEGISIKLIGI': TERMIN_METNI,
    'IPTAL_SARTI': IPTAL_METNI,
    'GARANTI_SORUMLULUK': GARANTI_METNI,
}


def tek_satir_metni(kod: str, degerler: dict[str, Any]) -> tuple[str, str | None]:
    """Şablona göre tek satır metni döner (numara yok). İkinci değer hata mesajı veya None."""
    sab = SABLON_MAP.get(kod)
    if not sab:
        return '', 'Bilinmeyen şablon'

    if sab.sadece_onay:
        m = _OZEL_METIN_SABILITLER.get(kod, '')
        if not m:
            return '', 'İçerik tanımsız'
        return m, None

    fn = _RENDERER.get(kod)
    if not fn:
        return '', 'Renderer yok'
    try:
        t = fn(dict(degerler or {}))
    except Exception as e:
        return '', str(e)
    if not (t or '').strip():
        return '', 'Boş metin'
    return t, None


def render_ozel_metin(degerler: dict[str, Any]) -> str:
    baslik = _strip(degerler.get('baslik'))
    aciklama = _strip(degerler.get('aciklama'))
    if baslik and aciklama:
        return f'{baslik}. {aciklama}'
    return baslik or aciklama


def normalize_client_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    tip = _strip(raw.get('tip')).upper() or 'HAZIR'
    if tip in ('OZEL', 'ÖZEL'):
        degerler = dict(raw.get('degerler') or {})
        return {
            'tip': TeklifSarti.TIP_OZEL,
            'sablon_kodu': '',
            'aktif': bool(raw.get('aktif', True)),
            'degerler': degerler,
        }
    kod = _strip(raw.get('sablon_kodu'))
    if kod not in SABLON_MAP:
        return None
    sab = SABLON_MAP[kod]
    dv = dict(sab.varsayilan_degerler())
    if isinstance(raw.get('degerler'), dict):
        dv.update(raw['degerler'])
    coerce_legacy_degerler(kod, dv)
    return {
        'tip': TeklifSarti.TIP_HAZIR,
        'sablon_kodu': kod,
        'aktif': bool(raw.get('aktif', False)),
        'degerler': dv,
    }


def build_numbered_text(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """İstemciden gelen ham satırları sıralayıp numaralı metin üretir."""
    hatalar: list[str] = []
    parcalar: list[str] = []
    normalized: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        n = normalize_client_row(r)
        if n:
            n['sira'] = _int_safe(r.get('sira'), i)
            normalized.append(n)

    normalized.sort(key=lambda x: x['sira'])

    nokta = 1
    for entry in normalized:
        if not entry.get('aktif'):
            continue
        if entry['tip'] == TeklifSarti.TIP_OZEL:
            m = render_ozel_metni(entry['degerler'])
            if not m:
                hatalar.append('Özel şartta metin boş')
                continue
            parcalar.append(f'{nokta}. {m}')
            nokta += 1
            continue
        kod = entry['sablon_kodu']
        metin, err = tek_satir_metni(kod, entry['degerler'])
        if err:
            hatalar.append(f'{kod}: {err}')
            continue
        if metin:
            parcalar.append(f'{nokta}. {metin}')
            nokta += 1

    return '\n'.join(parcalar), hatalar


def default_client_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, sab in enumerate(SABLONLAR):
        out.append(
            {
                'tip': TeklifSarti.TIP_HAZIR,
                'sablon_kodu': sab.kod,
                'aktif': sab.varsayilan_aktif,
                'degerler': sab.varsayilan_degerler(),
                'sira': i,
            }
        )
    return out


def rows_from_teklif(teklif: Teklif) -> list[dict[str, Any]]:
    """DB kayıtları + eksik şablonları varsayılanla tamamlar."""
    saved = list(teklif.sart_kayitlari.all().order_by('sira'))
    by_kod: dict[str, TeklifSarti] = {
        r.sablon_kodu: r
        for r in saved
        if r.tip == TeklifSarti.TIP_HAZIR and r.sablon_kodu
    }
    ozel_rows = [r for r in saved if r.tip == TeklifSarti.TIP_OZEL]

    out: list[dict[str, Any]] = []
    si = 0
    for sab in SABLONLAR:
        db_row = by_kod.get(sab.kod)
        if db_row:
            dv = dict(sab.varsayilan_degerler())
            if isinstance(db_row.degerler_json, dict):
                dv.update(db_row.degerler_json)
            coerce_legacy_degerler(sab.kod, dv)
            out.append(
                {
                    'tip': TeklifSarti.TIP_HAZIR,
                    'sablon_kodu': sab.kod,
                    'aktif': db_row.aktif,
                    'degerler': dv,
                    'sira': si,
                }
            )
        else:
            out.append(
                {
                    'tip': TeklifSarti.TIP_HAZIR,
                    'sablon_kodu': sab.kod,
                    'aktif': sab.varsayilan_aktif,
                    'degerler': sab.varsayilan_degerler(),
                    'sira': si,
                }
            )
        si += 1

    for db_row in sorted(ozel_rows, key=lambda x: x.sira):
        dv = dict(db_row.degerler_json or {})
        if db_row.baslik and 'baslik' not in dv:
            dv['baslik'] = db_row.baslik
        if db_row.metin and 'aciklama' not in dv:
            dv.setdefault('aciklama', db_row.metin)
        out.append(
            {
                'tip': TeklifSarti.TIP_OZEL,
                'sablon_kodu': '',
                'aktif': db_row.aktif,
                'degerler': dv,
                'sira': si,
            }
        )
        si += 1

    return out


def client_meta_for_js() -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = []
    for sab in SABLONLAR:
        item: dict[str, Any] = {
            'kod': sab.kod,
            'baslik': sab.baslik,
            'yardim': sab.yardim,
            'sadece_onay': sab.sadece_onay,
            'varsayilan_aktif': sab.varsayilan_aktif,
            'alanlar': [],
        }
        for a in sab.alanlar:
            adict: dict[str, Any] = {
                'ad': a.ad,
                'tur': a.tur,
                'etiket': a.etiket,
                'varsayilan': a.varsayilan,
            }
            if a.secenekler:
                adict['secenekler'] = a.secenekler
            if a.odeme_alt_grup:
                adict['odeme_alt_grup'] = a.odeme_alt_grup
            item['alanlar'].append(adict)
        meta.append(item)
    return meta


@transaction.atomic
def persist_teklif_sartlari(teklif: Teklif, json_raw: str) -> None:
    TeklifSarti.objects.filter(teklif=teklif).delete()
    try:
        raw_rows = json.loads(json_raw or '[]')
    except json.JSONDecodeError:
        raw_rows = []

    if not isinstance(raw_rows, list):
        return

    normalized: list[dict[str, Any]] = []
    for i, r in enumerate(raw_rows):
        n = normalize_client_row(r)
        if n:
            n['sira'] = _int_safe(r.get('sira'), i)
            normalized.append(n)

    normalized.sort(key=lambda x: x['sira'])

    seq = 0
    for entry in normalized:
        if not entry.get('aktif'):
            continue
        if entry['tip'] == TeklifSarti.TIP_OZEL:
            dv = entry['degerler']
            metin = render_ozel_metni(dv)
            if not metin:
                continue
            TeklifSarti.objects.create(
                teklif=teklif,
                tip=TeklifSarti.TIP_OZEL,
                sablon_kodu='',
                baslik=_strip(dv.get('baslik'))[:300] or 'Özel şart',
                degerler_json=dv,
                metin=metin,
                sira=seq,
                aktif=True,
            )
            seq += 1
            continue

        kod = entry['sablon_kodu']
        metin, err = tek_satir_metni(kod, entry['degerler'])
        if err or not metin:
            continue
        sab = SABLON_MAP[kod]
        TeklifSarti.objects.create(
            teklif=teklif,
            tip=TeklifSarti.TIP_HAZIR,
            sablon_kodu=kod,
            baslik=sab.baslik[:300],
            degerler_json=entry['degerler'],
            metin=metin,
            sira=seq,
            aktif=True,
        )
        seq += 1


def sartlar_metni_for_pdf(teklif: Teklif) -> str:
    """Önce kaydedilmiş metin alanı (manuel düzenleme); boşsa şart kayıtlarından derlenir."""
    manual = (teklif.sartlar_metni or '').strip()
    if manual:
        return manual
    rows_db = list(teklif.sart_kayitlari.filter(aktif=True).order_by('sira'))
    parcalar: list[str] = []
    for i, r in enumerate(rows_db, start=1):
        m = (r.metin or '').strip()
        if m:
            parcalar.append(f'{i}. {m}')
    return '\n'.join(parcalar)
