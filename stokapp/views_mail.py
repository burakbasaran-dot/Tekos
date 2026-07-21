import re
import quopri
import html
import hashlib
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from email.utils import parseaddr

from bs4 import BeautifulSoup
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from stokapp.constants import SYSTEM_AI_NAME
from stokapp.models import ApprovalRequest, StokItem, GenelAyarlar
from stokapp.services.imap_mail_reader import fetch_all_mailboxes


ORDER_KEYWORDS = ["sipariş", "siparis", "order", "teklif kabul", "purchase"]
QUOTATION_KEYWORDS = ["teklif", "fiyat", "quote"]
PRODUCT_CODE_PATTERN = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
# Baykon vb. siparişlerde sık görülen TF ile başlayan sipariş referansı
TF_ORDER_PATTERN = re.compile(r"\b(TF[A-Z0-9][A-Z0-9\-]{2,39})\b", re.IGNORECASE)


def _repair_mojibake(text):
    # Sık görülen UTF-8/latin-1 bozulmalarını toparlamayı dener.
    if not text:
        return text
    markers = ["Ã", "Â", "Ä", "Å", "�"]
    if any(m in text for m in markers):
        try:
            return text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            return text
    return text


def _decode_mail_body_fragment(raw):
    """QP decode + entity repair (tablo parse ve temizlik için ortak)."""
    raw = str(raw or "")
    try:
        raw = quopri.decodestring(raw.encode("utf-8", errors="replace")).decode("utf-8", errors="replace")
    except Exception:
        pass
    return _repair_mojibake(html.unescape(raw))


def clean_email_body(body, max_chars=800):
    """Mail gövdesini düz metne çevirir. Tablo ayıklaması için max_chars yükseltilebilir."""
    if not body:
        return ""
    raw = _decode_mail_body_fragment(body)

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "head", "meta"]):
        tag.decompose()
    text = soup.get_text(" ")

    patterns = [
        r"<[^>]*>",
        r"<\s*style\b[^>]*>",
        r"<\s*style\b",
        r"style\s*=\s*['\"][^'\"]*['\"]",
        r"font-family\s*:[^;]+;?",
        r"font-size\s*:[^;]+;?",
        r"line-height\s*:[^;]+;?",
        r"charset\s*=\s*[^ ]+",
        r"DOCTYPE|html|head|body|meta",
        r"Arial|sans-serif|serif",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = _repair_mojibake(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars is not None:
        text = text[:max_chars]
    return text


def _prepare_mail_soup(body):
    """HTML tablolarını ayıklamak için BeautifulSoup (kesme yok)."""
    soup = BeautifulSoup(_decode_mail_body_fragment(body), "html.parser")
    for tag in soup(["script", "style", "head", "meta"]):
        tag.decompose()
    return soup


def _normalize_cell_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def _normalize_header_key(value):
    t = _normalize_cell_text(value).lower()
    for a, b in (
        ("ı", "i"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ş", "s"),
        ("ö", "o"),
        ("ç", "c"),
        ("â", "a"),
        ("î", "i"),
        ("û", "u"),
    ):
        t = t.replace(a, b)
    return t


def _header_compact(norm_cell):
    return _normalize_header_key(norm_cell).replace(" ", "").replace(".", "")


def _classify_table_header_cell(raw_cell_text):
    """
    Kurumsal sipariş / satın alma tabloları için kolon sınıfı.
    Dönüş: 'product_code' | 'product_name' | 'quantity' | 'currency' | 'unit_price' | None
    """
    nk = _normalize_header_key(raw_cell_text)
    nc = nk.replace(" ", "").replace(".", "")

    if not nc:
        return None

    # Kod kolonları: Mal Kodu, Stok Kodu, Ürün Kodu (normalize sonrası kompakt)
    if nc in ("malkodu", "stokkodu", "urunkodu"):
        return "product_code"
    if nc.endswith("kodu"):
        if nc.startswith("mal") or nc.startswith("stok") or nc.startswith("urun"):
            return "product_code"

    # Ürün / mal adı
    if nc in ("maladi", "maladii", "urunadi"):
        return "product_name"
    if ("mal" in nk or "urun" in nk) and ("ad" in nk or "adi" in nk) and "kod" not in nk:
        return "product_name"

    # Miktar / Adet / Qty / Quantity
    if nc in ("miktar", "adet", "qty", "quantity"):
        return "quantity"
    if "miktar" in nc:
        return "quantity"

    # Opsiyonel fiyatlandırma (Baykon vb.)
    if nc.endswith("doviz") or nc == "pb" or nc.startswith("para"):
        return "currency"
    if nc == "fiyat" or nc.endswith("fiyat") or nc.startswith("birimfiyat"):
        return "unit_price"

    return None


def _parse_product_table_header_row(cell_texts):
    """
    Header satırından kolon indekslerini çıkarır.
    Ürün kodu için öncelik: mal kodu > stok kodu > ürün kodu (soldan sağa ilk eşleşme yerine öncelik sırası).
    """
    kinds = [_classify_table_header_cell(t) for t in cell_texts]

    col_qty = col_curr = col_price = col_name = None
    code_candidates = []

    for i, kind in enumerate(kinds):
        if kind == "quantity" and col_qty is None:
            col_qty = i
        elif kind == "currency" and col_curr is None:
            col_curr = i
        elif kind == "unit_price" and col_price is None:
            col_price = i
        elif kind == "product_name" and col_name is None:
            col_name = i
        elif kind == "product_code":
            raw = cell_texts[i] if i < len(cell_texts) else ""
            pri = 0
            nc = _header_compact(raw)
            if nc.startswith("mal"):
                pri = 1
            elif nc.startswith("stok"):
                pri = 2
            elif nc.startswith("urun"):
                pri = 3
            code_candidates.append((pri, i))

    col_code = None
    if code_candidates:
        code_candidates.sort(key=lambda x: (x[0], x[1]))
        col_code = code_candidates[0][1]

    return col_code, col_name, col_qty, col_curr, col_price


def _parse_decimal_cell(val):
    if val is None:
        return None
    s = _normalize_cell_text(val).replace(" ", "")
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


_QTY_TRAILING_UNIT = re.compile(
    r"\s+(?:adet|pcs|piece|pieces|pk\.?|qty|quantity)\s*$",
    re.IGNORECASE,
)


def _parse_quantity_cell_value(val):
    """Miktar hücresi: 50 | 50,00 | 50.0 | 50 adet → sayı."""
    if val is None:
        return None
    s = _normalize_cell_text(str(val))
    if not s:
        return None
    for _ in range(4):
        s_new = _QTY_TRAILING_UNIT.sub("", s).strip()
        if s_new == s:
            break
        s = s_new
    s_compact = s.replace(" ", "")
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", s_compact)
    if not m:
        return None
    num = m.group(0).replace(",", ".")
    try:
        d = Decimal(num)
    except Exception:
        return None
    if d <= 0:
        return None
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def _normalize_mail_currency_for_order(raw):
    """Siparis.para_birimi / ParaBirimi.kod ile uyumlu kısa kod."""
    if not raw:
        return None
    c = _normalize_cell_text(raw).upper()
    if c in ("TRL", "TRY", "TL", "₺"):
        return "TL"
    if c in ("USD", "US$", "$"):
        return "USD"
    if c in ("EUR", "€"):
        return "EUR"
    if c in ("GBP", "£"):
        return "GBP"
    return c[:10] if c else None


def parse_html_tables(raw_html):
    """
    Ham HTML üzerinden tablo parse (clean_email_body çalıştırılmadan önce çağrılmalı).
    İlk uygun satır (>=2 hücre, th/td fark etmez) başlık kabul edilir.
    """
    if not raw_html:
        return []
    soup = _prepare_mail_soup(raw_html)
    items = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_idx = None
        col_code = col_name = col_qty = col_curr = col_price = None

        for ri, tr in enumerate(rows):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            texts = [_normalize_cell_text(c.get_text(" ", strip=True)) for c in cells]
            cc, cn, cq, ccur, cp = _parse_product_table_header_row(texts)
            header_idx = ri
            col_code, col_name, col_qty, col_curr, col_price = cc, cn, cq, ccur, cp
            break

        if header_idx is None or col_qty is None:
            continue

        idx_list = [i for i in (col_code, col_name, col_qty, col_curr, col_price) if i is not None]
        max_idx = max(idx_list)

        for tr in rows[header_idx + 1 :]:
            cells = tr.find_all(["th", "td"])
            texts = [_normalize_cell_text(c.get_text(" ", strip=True)) for c in cells]
            if len(texts) <= max_idx:
                continue
            code = texts[col_code].strip() if col_code is not None and col_code < len(texts) else ""
            name = texts[col_name].strip() if col_name is not None and col_name < len(texts) else ""
            qty_raw = texts[col_qty] if col_qty < len(texts) else ""
            qty = _parse_quantity_cell_value(qty_raw)
            if qty is None:
                continue

            curr_raw = texts[col_curr].strip() if col_curr is not None and col_curr < len(texts) else ""
            price = (
                _parse_decimal_cell(texts[col_price])
                if col_price is not None and col_price < len(texts)
                else None
            )

            if not code and not name:
                continue

            row = {
                "product_code": code,
                "product_name": name,
                "quantity": qty,
                "unit": "adet",
                "source": "html_table",
            }
            if col_curr is not None and curr_raw:
                row["currency"] = _normalize_mail_currency_for_order(curr_raw)
            if price is not None:
                row["unit_price"] = float(price)
            items.append(row)

    return items


def _extract_detected_items_from_html_tables(body):
    """Geriye dönük isim; ham gövde ile parse_html_tables kullanır."""
    return parse_html_tables(body)


_FLAT_ORDER_ROW_RE = re.compile(
    r"(\S+)\s+(.+)\s+(\d+)\s+(TRL|USD|EUR|TRY|TL|GBP)\s+(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _extract_detected_items_flat_text(text):
    """Düz metinde Mal Kodu … Fiyat başlığı sonrası satırlar (tek veya çok satır)."""
    if not text:
        return []
    compact = _normalize_header_key(text).replace(" ", "")
    if not all(k in compact for k in ("malkodu", "maladi", "miktar", "doviz", "fiyat")):
        return []

    hdr = re.search(
        r"mal\s+kodu.*?mal\s+ad[iı].*?miktar.*?d[oö]viz.*?fiyat",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not hdr:
        return []
    rest = text[hdr.end() :].strip()
    items = []
    for line in re.split(r"[\n\r]+", rest):
        line = line.strip()
        if not line:
            continue
        m = _FLAT_ORDER_ROW_RE.search(line)
        if not m:
            continue
        code, name, qty_s, curr_raw, price_s = m.groups()
        qty = _parse_decimal_cell(qty_s)
        price = _parse_decimal_cell(price_s)
        if not code or qty is None:
            continue
        items.append(
            {
                "product_code": code.strip(),
                "product_name": name.strip(),
                "quantity": qty,
                "unit_price": float(price) if price is not None else None,
                "currency": _normalize_mail_currency_for_order(curr_raw),
                "unit": "adet",
                "source": "flat_text",
            }
        )
    return items


def _resolve_stok_for_detected_item(item):
    """
    Önce Mal Kodu (stok_kodu / tedarikci_kodu); bulunamazsa Mal Adı ile tam eşleşme.
    """
    code = (item.get("product_code") or "").strip()
    name = (item.get("product_name") or "").strip()
    stok = _find_product_for_mail_code(code)
    if stok:
        return stok
    if name:
        return StokItem.objects.filter(ad__iexact=name).first()
    return None


def _extract_customer_name(mail, cleaned_body):
    sender_name, sender_email = parseaddr(mail.get("sender") or "")
    if sender_name and len(sender_name.strip()) >= 2:
        return sender_name.strip()

    patterns = [
        r"say[ıi]n\s+([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9\s\.\-]{2,60})",
        r"m[üu]şteri\s*[:\-]\s*([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9\s\.\-]{2,60})",
        r"firma\s*[:\-]\s*([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9\s\.\-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned_body, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    domain = (sender_email.split("@")[1] if "@" in sender_email else "unknown").split(".")[0]
    return (domain or "unknown").replace("-", " ").replace("_", " ").title()


def _extract_quantity(content):
    quantity_patterns = [
        r"(\d+)\s*adet",
        r"adet\s*(\d+)",
        r"(\d+)\s*pcs",
        r"qty\s*(\d+)",
        r"miktar\s*(\d+)",
    ]
    for pattern in quantity_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _build_detected_items(product_codes, quantity):
    unique_codes = []
    for code in product_codes:
        if code not in unique_codes:
            unique_codes.append(code)
    if not unique_codes:
        return []
    return [
        {
            "product_code": code,
            "quantity": quantity,
            "unit": "adet",
        }
        for code in unique_codes
    ]


def _extract_tf_order_number(subject_raw, cleaned_body):
    """Konuda ve gövdede TF ile başlayan sipariş numarasını bulur (Baykon vb.)."""
    text_priority = [
        (subject_raw or "").strip(),
        (cleaned_body or "").strip(),
    ]
    for chunk in text_priority:
        if not chunk:
            continue
        m = TF_ORDER_PATTERN.search(chunk)
        if m:
            return m.group(1).upper()
    return None


def _email_fingerprint(mail):
    sender = (mail.get("sender") or "").strip().lower()
    subject = (mail.get("subject") or "").strip().lower()
    received_at = (mail.get("received_at") or "").strip().lower()
    message_id = (mail.get("message_id") or "").strip().lower()
    base = message_id or f"{sender}|{subject}|{received_at}"
    return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()


def _to_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_product_code(value):
    return re.sub(r"[^A-Za-z0-9]", "", (value or "")).upper()


def _find_product_for_mail_code(product_code):
    """
    Baykon mail kodları için önce stok_kodu, sonra tedarikci_kodu ile arar.
    Gerekirse ayraçlardan bağımsız normalize edilmiş karşılaştırma yapar.
    """
    code = (product_code or "").strip()
    if not code:
        return None

    direct_match = StokItem.objects.filter(
        Q(stok_kodu__iexact=code) | Q(tedarikci_kodu__iexact=code)
    ).first()
    if direct_match:
        return direct_match

    normalized = _normalize_product_code(code)
    if not normalized:
        return None

    for candidate in StokItem.objects.only("id", "stok_kodu", "tedarikci_kodu"):
        if (
            _normalize_product_code(candidate.stok_kodu) == normalized
            or _normalize_product_code(candidate.tedarikci_kodu) == normalized
        ):
            return candidate
    return None


def make_json_serializable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: make_json_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [make_json_serializable(v) for v in value]
    return value


def _run_stock_check(detected_items):
    stock_checks = []
    has_insufficient = False

    for item in detected_items:
        product_code = (item.get("product_code") or "").strip()
        requested_qty = _to_decimal(item.get("quantity"))
        unit = item.get("unit") or "adet"

        product = _resolve_stok_for_detected_item(item)
        if not product:
            stock_checks.append(
                {
                    "product_code": product_code,
                    "requested_quantity": requested_qty,
                    "available_stock": None,
                    "missing_quantity": None,
                    "status": "product_not_found",
                    "unit": unit,
                }
            )
            continue

        available = _to_decimal(product.mevcut_miktar) or Decimal("0")
        missing = None
        status = "sufficient"

        if requested_qty is not None and requested_qty > available:
            status = "insufficient"
            has_insufficient = True
            missing = requested_qty - available

        stock_checks.append(
            {
                "product_code": product.stok_kodu,
                "requested_quantity": requested_qty,
                "available_stock": available,
                "missing_quantity": missing,
                "status": status,
                "unit": unit,
            }
        )

    return stock_checks, has_insufficient


def _is_duplicate_order(mail):
    fingerprint = _email_fingerprint(mail)
    return ApprovalRequest.objects.filter(
        action_type__in=[
            ApprovalRequest.ACTION_CREATE_SALES_ORDER,
            ApprovalRequest.ACTION_CREATE_PURCHASE_REQUEST,
        ],
        source=ApprovalRequest.SOURCE_EMAIL,
        payload__ingestion_fingerprint=fingerprint,
    ).exists()


def analyze_email(mail):
    subject_raw = mail.get("subject") or ""
    subject = subject_raw.lower()
    raw_body = mail.get("body") or ""

    parsed_table_items = parse_html_tables(raw_body)
    cleaned_body = clean_email_body(raw_body, max_chars=16000)

    table_items = list(parsed_table_items)
    if not table_items:
        table_items = _extract_detected_items_flat_text(cleaned_body)

    body = cleaned_body.lower()
    content = f"{subject} {body}"

    mail_type = "other"
    if any(keyword in content for keyword in ORDER_KEYWORDS):
        mail_type = "order"
    elif any(keyword in content for keyword in QUOTATION_KEYWORDS):
        mail_type = "quotation"

    if table_items:
        detected_items = make_json_serializable(table_items)
        q0 = table_items[0].get("quantity")
        quantity = q0
        if q0 is not None:
            try:
                quantity = int(Decimal(str(q0)))
            except Exception:
                pass
    else:
        product_codes = PRODUCT_CODE_PATTERN.findall((subject_raw + " " + cleaned_body).upper())
        product_codes = [code for code in product_codes if code.startswith("TMW") or "-" in code]
        quantity = _extract_quantity(content)
        detected_items = _build_detected_items(product_codes, quantity)
    customer_name = _extract_customer_name(mail, cleaned_body)
    sender = (mail.get("sender") or "").strip()
    subject_clean = clean_email_body(subject_raw)

    summary = cleaned_body.strip().replace("\n", " ")
    summary = re.sub(r"\s+", " ", summary)[:180]
    if not summary:
        summary = "Mail içeriği kısa veya boş."

    parsed_table_items_serial = make_json_serializable(parsed_table_items)

    return {
        "type": mail_type,
        "quantity": quantity,
        "detected_items": detected_items,
        "parsed_table_items": parsed_table_items_serial,
        "summary": summary,
        "cleaned_body": cleaned_body,
        "extracted_data": {
            "customer_name": customer_name,
            "items": detected_items if detected_items else [{"product_code": "", "quantity": None, "unit": "adet"}],
            "sender": sender,
            "subject": subject_clean,
        },
    }


def _create_order_approval_from_email(email, analysis):
    body = clean_email_body(analysis.get("cleaned_body") or email.get("body", ""), max_chars=8000)
    subject = (email.get("subject") or "").strip()
    sender = (email.get("sender") or "").strip()
    summary_text = analysis.get("summary") or "Mail içeriği kısa veya boş."
    cleaned_summary = clean_email_body(summary_text)
    cleaned_description = clean_email_body(f"Mail içeriği sipariş olarak yorumlandı: {summary_text}")
    stock_checks, _ = _run_stock_check(analysis.get("detected_items", []))
    preferred_no = _extract_tf_order_number(subject, body)

    first_insufficient = next((x for x in stock_checks if x.get("status") == "insufficient"), None)
    html_snap = email.get("body") or ""
    if len(html_snap) > 120000:
        html_snap = html_snap[:120000]

    payload = {
        "sender": sender,
        "subject": subject,
        "raw_body": body,
        "html_body_snapshot": html_snap,
        "customer_name": analysis["extracted_data"]["customer_name"],
        "detected_items": analysis.get("detected_items", []),
        "parsed_table_items": analysis.get("parsed_table_items") or [],
        "stock_checks": stock_checks,
        "stock_check": stock_checks[0] if stock_checks else None,
        "ingestion_fingerprint": _email_fingerprint(email),
        "preferred_siparis_numarasi": preferred_no,
    }
    if first_insufficient:
        payload["purchase_recommendation"] = {
            "product_code": first_insufficient.get("product_code"),
            "required_quantity": first_insufficient.get("missing_quantity"),
            "unit": first_insufficient.get("unit") or "adet",
            "reason": "Stok yetersiz; sipariş kalemleri oluşturulur, satın alma ihtiyacı sipariş notlarında görülebilir.",
        }
    payload = make_json_serializable(payload)

    return ApprovalRequest.objects.create(
        action_type=ApprovalRequest.ACTION_CREATE_SALES_ORDER,
        title=f"{SYSTEM_AI_NAME} mailden sipariş algıladı",
        description=cleaned_description,
        ai_summary=clean_email_body(f"{SYSTEM_AI_NAME} özeti: {cleaned_summary}"),
        payload=payload,
        status=ApprovalRequest.STATUS_PENDING,
        risk_level=ApprovalRequest.RISK_MEDIUM,
        source=ApprovalRequest.SOURCE_EMAIL,
    )


def _sanitize_existing_approval_records():
    # Daha önce HTML/encoding ile kaydedilmiş kayıtları geriye dönük temizle.
    qs = ApprovalRequest.objects.filter(
        action_type=ApprovalRequest.ACTION_CREATE_SALES_ORDER,
        source=ApprovalRequest.SOURCE_EMAIL,
    ).order_by("-created_at")[:300]

    cleaned = 0
    for record in qs:
        old_description = record.description or ""
        old_summary = record.ai_summary or ""
        payload = record.payload or {}
        old_raw_body = payload.get("raw_body", "")

        new_description = clean_email_body(old_description)
        new_summary = clean_email_body(old_summary)
        new_raw_body = clean_email_body(old_raw_body)

        changed = False
        if new_description and new_description != old_description:
            record.description = new_description
            changed = True
        if new_summary and new_summary != old_summary:
            record.ai_summary = new_summary
            changed = True
        if new_raw_body != old_raw_body:
            payload["raw_body"] = new_raw_body
            record.payload = payload
            changed = True

        if changed:
            record.save(update_fields=["description", "ai_summary", "payload", "updated_at"])
            cleaned += 1

    return cleaned


@login_required
@require_GET
def test_read_mails_imap_api(request):
    try:
        result = process_imap_mail_flow()
        return JsonResponse(result)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


def process_imap_mail_flow():
    ayarlar = GenelAyarlar.get_ayarlar()
    if not ayarlar.tekora_aktif:
        return {
            "count": 0,
            "emails": [],
            "analyzed": [],
            "mailbox_errors": [],
            "approvals_created_count": 0,
            "approval_request_ids": [],
            "sanitized_existing_count": 0,
            "skipped_duplicate_count": 0,
            "error_count": 0,
            "processing_errors": [],
            "tekora_inactive": True,
            "message": "TEKORA pasif. Mail takibi durduruldu.",
        }

    mail_result = fetch_all_mailboxes()
    emails = mail_result["emails"]
    mailbox_errors = mail_result["mailbox_errors"]
    created_approvals = []
    analyzed = []
    skipped_duplicates = 0
    processing_errors = []

    for email in emails:
        try:
            analysis = analyze_email(email)
            analyzed.append(
                {
                    "mailbox": email.get("mailbox"),
                    "subject": email.get("subject"),
                    "type": analysis["type"],
                    "quantity": analysis["quantity"],
                    "extracted_data": analysis["extracted_data"],
                    "parsed_table_items": analysis.get("parsed_table_items") or [],
                }
            )
            if analysis["type"] == "order":
                if _is_duplicate_order(email):
                    skipped_duplicates += 1
                    continue
                approval = _create_order_approval_from_email(email, analysis)
                created_approvals.append(str(approval.id))
        except Exception as exc:
            processing_errors.append(
                {
                    "sender": email.get("sender"),
                    "subject": email.get("subject"),
                    "error": str(exc),
                }
            )
            continue

    sanitized_count = _sanitize_existing_approval_records()
    return {
        "count": len(emails),
        "emails": emails,
        "analyzed": analyzed,
        "mailbox_errors": mailbox_errors,
        "approvals_created_count": len(created_approvals),
        "approval_request_ids": created_approvals,
        "sanitized_existing_count": sanitized_count,
        "skipped_duplicate_count": skipped_duplicates,
        "error_count": len(processing_errors),
        "processing_errors": processing_errors,
    }
