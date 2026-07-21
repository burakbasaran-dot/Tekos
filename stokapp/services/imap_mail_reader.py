import email
import imaplib
import json
import os
from email.header import decode_header

from stokapp.mail_config import get_imap_config


def _decode_header(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _extract_body(message_obj):
    """
    Gövdeyi çıkarır: HTML tablolu sipariş mailleri için text/html tercih edilir,
    aksi halde text/plain. Uzunluk IMAP_BODY_MAX_CHARS ile sınırlanır (varsayılan 512KiB).
    """
    max_chars = int(os.getenv("IMAP_BODY_MAX_CHARS", "524288"))
    plain = ""
    html_body = ""

    def part_text(part):
        disposition = str(part.get("Content-Disposition") or "").lower()
        if "attachment" in disposition:
            return None
        payload = part.get_payload(decode=True)
        if not payload:
            return None
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    if message_obj.is_multipart():
        for part in message_obj.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                t = part_text(part)
                if t:
                    plain = t
            elif content_type == "text/html":
                t = part_text(part)
                if t:
                    html_body = t
    else:
        content_type = message_obj.get_content_type()
        payload = message_obj.get_payload(decode=True)
        charset = message_obj.get_content_charset() or "utf-8"
        if payload:
            text = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                html_body = text
            else:
                plain = text

    if html_body and "<table" in html_body.lower():
        body = html_body
    elif plain:
        body = plain
    else:
        body = html_body

    if len(body) > max_chars:
        body = body[:max_chars]
    return body


def _imap_connect(imap_server, port, use_ssl=True):
    if use_ssl:
        return imaplib.IMAP4_SSL(imap_server, port)
    return imaplib.IMAP4(imap_server, port)


def fetch_emails_from_imap(email_address=None, password=None, imap_server=None, port=None, limit=10, mailbox=None, use_ssl=None):
    config = get_imap_config()
    email_address = email_address or os.getenv("IMAP_EMAIL")
    password = password or os.getenv("IMAP_PASSWORD")
    imap_server = imap_server or config["server"] or os.getenv("IMAP_SERVER")
    port = int(port or config["port"] or os.getenv("IMAP_PORT", "993"))
    mailbox = (mailbox or config["mailbox"] or "INBOX").strip() or "INBOX"
    if use_ssl is None:
        use_ssl = config.get("use_ssl", True)

    if not email_address or not password or not imap_server:
        raise ValueError("IMAP e-posta, şifre ve sunucu ayarları zorunludur.")

    with _imap_connect(imap_server, port, use_ssl=use_ssl) as mail:
        mail.login(email_address, password)
        mail.select(mailbox)

        status, data = mail.search(None, "ALL")
        if status != "OK":
            return []

        message_ids = data[0].split()
        latest_ids = message_ids[-limit:]

        emails = []
        for msg_id in reversed(latest_ids):
            fetch_status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if fetch_status != "OK" or not msg_data or msg_data[0] is None:
                continue

            raw_email = msg_data[0][1]
            message_obj = email.message_from_bytes(raw_email)

            subject = _decode_header(message_obj.get("Subject", ""))
            sender = _decode_header(message_obj.get("From", ""))
            received_at = message_obj.get("Date", "")
            message_id = _decode_header(message_obj.get("Message-ID", ""))
            body = _extract_body(message_obj)

            emails.append(
                {
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_at": received_at,
                    "message_id": message_id,
                }
            )

        return emails


def fetch_all_mailboxes():
    config = get_imap_config()
    imap_server = config["server"]
    port = config["port"]
    accounts = config["accounts"]
    use_ssl = config.get("use_ssl", True)
    mailbox = config.get("mailbox") or "INBOX"

    if not imap_server:
        raise ValueError("IMAP sunucu ayarı zorunludur.")

    if not isinstance(accounts, list) or not accounts:
        raise ValueError("En az bir IMAP hesabı tanımlanmalıdır.")

    all_emails = []
    mailbox_errors = []

    for account in accounts:
        email_address = (account or {}).get("email")
        password = (account or {}).get("password")
        if not email_address or not password:
            mailbox_errors.append({"email": email_address or "unknown", "error": "email/password eksik"})
            continue

        try:
            emails = fetch_emails_from_imap(
                email_address=email_address,
                password=password,
                imap_server=imap_server,
                port=port,
                limit=5,
                mailbox=mailbox,
                use_ssl=use_ssl,
            )
            for item in emails:
                item["mailbox"] = email_address
            all_emails.extend(emails)
        except Exception as exc:
            mailbox_errors.append({"email": email_address, "error": str(exc)})

    return {"emails": all_emails, "mailbox_errors": mailbox_errors}


def test_imap_connection():
    config = get_imap_config()
    imap_server = config["server"]
    port = config["port"]
    accounts = config["accounts"]
    use_ssl = config.get("use_ssl", True)
    mailbox = config.get("mailbox") or "INBOX"

    if not imap_server:
        raise ValueError("IMAP sunucu ayarı zorunludur.")
    if not accounts:
        raise ValueError("En az bir IMAP hesabı tanımlanmalıdır.")

    tested = []
    errors = []
    for account in accounts:
        email_address = (account or {}).get("email")
        password = (account or {}).get("password")
        if not email_address or not password:
            errors.append({"email": email_address or "unknown", "error": "email/password eksik"})
            continue
        try:
            with _imap_connect(imap_server, port, use_ssl=use_ssl) as mail:
                mail.login(email_address, password)
                status, _ = mail.select(mailbox)
                if status != "OK":
                    raise ValueError(f"{mailbox} klasörü açılamadı.")
            tested.append(email_address)
        except Exception as exc:
            errors.append({"email": email_address, "error": str(exc)})

    if not tested:
        raise ValueError(errors[0]["error"] if errors else "IMAP bağlantısı kurulamadı.")

    msg = f"{len(tested)} hesap için IMAP bağlantısı başarılı."
    if errors:
        msg += f" {len(errors)} hesapta hata."
    return {"message": msg, "tested": tested, "errors": errors}
