"""Müşteri satış teklifi PDF (WeasyPrint) ve e-posta yardımcıları."""

from __future__ import annotations

import os
from typing import Any
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import get_template

from collections import defaultdict

from .models import BankaHesabi, GenelAyarlar, Teklif
from .satinalma_mail_send import AUTO_MAIL_NOTE_HTML, AUTO_MAIL_NOTE_TEXT
from .teklif_sartlari_registry import sartlar_metni_for_pdf

_PDF_VALID_PB = frozenset({'TL', 'USD', 'EUR', 'GBP'})

TEKLIF_BANKA_LEGAL_HEADER = (
    'Banka Hesap Adı : Tekmar Endüstriyel Makina Otomasyon Sanayi ve Ticaret Ltd Şti'
)

TEKLIF_PDF_FIRMA_ADRES_SATIRLARI = [
    'Tekmar Endüstriyel Makina Otomasyon Sanayi ve Ticaret Ltd. Şti.',
    'Karadenizliler Mahallesi, Horon Sokak, No:7',
    'Kocaeli / Başiskele',
    '05324883809',
    'VD: Tepecik',
    '8360669996',
]


def _pdf_norm_pb(pb) -> str:
    if pb is None or pb == '':
        return 'TL'
    x = str(pb).strip().upper()
    if x == 'TRY':
        return 'TL'
    return x[:3]


_PB_SYMBOL = {'TL': '₺', 'USD': '$', 'EUR': '€', 'GBP': '£'}


def _iban_with_spaces(iban: str) -> str:
    s = ''.join((iban or '').split()).upper()
    if not s:
        return ''
    if len(s) <= 4:
        return s
    parts = [s[:4]]
    rest = s[4:]
    for i in range(0, len(rest), 4):
        parts.append(rest[i : i + 4])
    return ' '.join(parts)


def _pb_symbol(pb: str) -> str:
    return _PB_SYMBOL.get(_pdf_norm_pb(pb), _pdf_norm_pb(pb))


def _teklif_pdf_banka_detay(teklif: Teklif) -> list[dict[str, Any]]:
    raw_ids = getattr(teklif, 'teklif_banka_hesap_ids', None) or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return []
    order: dict[int, int] = {}
    for i, x in enumerate(raw_ids):
        try:
            order[int(x)] = i
        except (TypeError, ValueError):
            continue
    if not order:
        return []
    hesaplar = list(BankaHesabi.objects.filter(pk__in=list(order.keys()), aktif=True))
    hesaplar.sort(key=lambda h: order.get(h.pk, 9999))
    out: list[dict[str, Any]] = []
    for h in hesaplar:
        pb_sym = _pb_symbol(h.para_birimi)
        iban_disp = _iban_with_spaces(h.iban)
        out.append(
            {
                'banka_adi': h.banka_adi,
                'hesap_adi': h.hesap_adi,
                'iban': h.iban,
                'iban_display': iban_disp,
                'pb_simge': pb_sym,
                'para_birimi': h.para_birimi,
                'sube_kodu': h.sube_kodu or '',
                'hesap_no': h.hesap_no or '',
            }
        )
    return out


def _teklif_pdf_ozet_paralar(kalemler: list) -> list[dict[str, Any]]:
    """Satırları para birimine göre gruplayarak PDF özet satırları üretir."""
    net_map: dict[str, Decimal] = defaultdict(Decimal)
    brut_map: dict[str, Decimal] = defaultdict(Decimal)
    for k in kalemler:
        pb = _pdf_norm_pb(getattr(k, 'para_birimi', None))
        if pb not in _PDF_VALID_PB:
            pb = 'TL'
        net_map[pb] += k.miktar * k.birim_fiyat
        brut_map[pb] += k.satir_toplam
    q = Decimal('0.01')
    out: list[dict[str, Any]] = []
    for pb in sorted(brut_map.keys()):
        g_net = net_map[pb]
        g_brut = brut_map[pb]
        kdv = g_brut - g_net
        out.append(
            {
                'para': pb,
                'pdf_tutar_kdv_haric': g_net.quantize(q),
                'pdf_kdv_tutari': kdv.quantize(q),
                'pdf_genel_toplam': g_brut.quantize(q),
            }
        )
    return out


def teklif_logo_absolute_path() -> str | None:
    rel = "stokapp/images/tekmar_endustriyel_logo.png"
    found = finders.find(rel)
    if found and os.path.isfile(found):
        return os.path.abspath(found)
    fallback = os.path.join(settings.BASE_DIR, "stokapp", "static", rel)
    if os.path.isfile(fallback):
        return os.path.abspath(fallback)
    return None


def build_teklif_pdf_context(teklif: Teklif) -> dict:
    ayarlar = GenelAyarlar.get_ayarlar()
    kalemler = list(
        teklif.kalemler.all().select_related("stok_item").order_by("sira", "id")
    )
    logo_path = teklif_logo_absolute_path()
    musteri_unvan = (
        teklif.musteri.ad if teklif.musteri_id else (teklif.musteri_adi or "—")
    )
    ozet_paralar = _teklif_pdf_ozet_paralar(kalemler)
    ctx: dict[str, Any] = {
        "teklif": teklif,
        "ayarlar": ayarlar,
        "kalemler": kalemler,
        "logo_path": logo_path,
        "musteri_unvan": musteri_unvan,
        "for_pdf": True,
        "sartlar_pdf_metni": sartlar_metni_for_pdf(teklif),
        "pdf_ozet_paralar": ozet_paralar,
        "teklif_pdf_firma_adres_satirlari": TEKLIF_PDF_FIRMA_ADRES_SATIRLARI,
        "teklif_banka_legal_header": TEKLIF_BANKA_LEGAL_HEADER,
        "teklif_banka_pdf_detay": _teklif_pdf_banka_detay(teklif),
    }
    if len(ozet_paralar) == 1:
        ctx.update(
            {
                "pdf_tutar_kdv_haric": ozet_paralar[0]["pdf_tutar_kdv_haric"],
                "pdf_kdv_tutari": ozet_paralar[0]["pdf_kdv_tutari"],
                "pdf_genel_toplam": ozet_paralar[0]["pdf_genel_toplam"],
            }
        )
    else:
        z = Decimal("0").quantize(Decimal("0.01"))
        ctx.update(
            {
                "pdf_tutar_kdv_haric": z,
                "pdf_kdv_tutari": z,
                "pdf_genel_toplam": z,
            }
        )
    return ctx


def build_teklif_pdf_bytes(teklif: Teklif, base_url: str | None = None) -> bytes:
    ctx = build_teklif_pdf_context(teklif)
    template = get_template("stokapp/teklif_musteri_pdf.html")
    html = template.render(ctx)

    logo_path = ctx.get("logo_path")
    if logo_path:
        base_url = Path(logo_path).parent.as_uri() + "/"
    elif base_url is None:
        base_url = getattr(settings, "STATIC_URL", "/") or "/"

    from weasyprint import HTML, CSS

    html_obj = HTML(string=html, base_url=base_url)
    css = CSS(
        string="""
        @page { size: A4; margin: 12mm; }
        body { font-family: Georgia, "Times New Roman", serif; font-size: 10.5pt; color: #111; }
        .sans { font-family: Arial, Helvetica, sans-serif; font-size: 9.5pt; }
        table.meta { width: 100%; border-collapse: collapse; margin-bottom: 8mm; }
        table.meta td { padding: 3px 6px; vertical-align: top; }
        table.grid { width: 100%; border-collapse: collapse; margin-top: 4mm; }
        table.grid th, table.grid td { border: 1px solid #1e3a5f; padding: 6px; }
        table.grid th { background: #1e3a5f; color: #fff; font-weight: bold; }
        .firm-title { font-size: 13pt; font-weight: bold; color: #1e3a5f; letter-spacing: 0.03em; }
        .doc-title { text-align: center; font-size: 16pt; font-weight: bold; color: #1e3a5f; margin: 6mm 0; }
        .rule { border: none; border-top: 2px solid #1e3a5f; margin: 4mm 0; }
        .totals { margin-top: 4mm; width: 55%; margin-left: auto; }
        .totals td { border: 1px solid #ccc; padding: 5px 8px; }
        .totals-grand td { background: #f4f6f9; border-color: #1e3a5f; }
        .muted { color: #444; font-size: 9pt; }
        img.logo { max-height: 22mm; max-width: 85mm; }
    """
    )
    pdf_bytes = html_obj.write_pdf(stylesheets=[css])
    if not pdf_bytes:
        raise RuntimeError("PDF oluşturulamadı.")
    return pdf_bytes


def default_teklif_mail_subject(teklif: Teklif) -> str:
    unvan = teklif.musteri.ad if teklif.musteri_id else (teklif.musteri_adi or "Müşteri")
    return f"Tekmar Teklif - {teklif.teklif_no} - {unvan}"


def teklif_mail_footer_html() -> str:
    return (
        '<div style="margin-top:24px; padding-top:16px; border-top:1px solid #e5e7eb; '
        'font-size:12px; line-height:1.6; color:#6b7280;">'
        '<div style="font-weight:700; font-size:13px; color:#374151; margin-bottom:8px;">'
        'TEKOS<span style="font-weight:500; color:#9ca3af; margin:0 4px;">/</span>TEKORA'
        '</div>'
        f'{AUTO_MAIL_NOTE_HTML}'
        '</div>'
    )


def teklif_mail_footer_text() -> str:
    return (
        'TEKOS/TEKORA\n'
        f'{AUTO_MAIL_NOTE_TEXT}'
    )


def ensure_teklif_mail_footer(html: str) -> str:
    """TEKOS/TEKORA dipnotu yoksa mesajın sonuna ekler."""
    marker = 'tescilli dijital yönetim platformlarıdır'
    if marker in (html or ''):
        return html
    body = (html or '').rstrip()
    return f'{body}{teklif_mail_footer_html()}'


def default_teklif_mail_html(teklif: Teklif) -> str:
    unvan = teklif.musteri.ad if teklif.musteri_id else (teklif.musteri_adi or "")
    body = (
        f"<p>Sayın Yetkili,</p>"
        f"<p><strong>{unvan}</strong> firmasına hazırladığımız "
        f"<strong>{teklif.teklif_no}</strong> numaralı teklif ektedir.</p>"
        f"<p>Geçerlilik ve ödeme koşulları teklif şartları metninde yer almaktadır.</p>"
        f"<p>Saygılarımızla,<br/>Tekmar Endüstriyel</p>"
    )
    return ensure_teklif_mail_footer(body)


def parse_extra_emails(raw: str) -> list[str]:
    """CC/BCC için virgül, noktalı virgül veya satır sonundan ayrıştırılmış adresler."""
    if not (raw or "").strip():
        return []
    parts = re.split(r"[\s,;]+", raw.strip())
    out = []
    for p in parts:
        e = p.strip()
        if not e:
            continue
        try:
            validate_email(e)
            out.append(e)
        except ValidationError:
            continue
    return out

