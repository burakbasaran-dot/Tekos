"""Satınalma teklif/sipariş formu e-postaları — alıcı listesi çağırandan gelir."""

import os
from decimal import Decimal
from datetime import datetime
from io import BytesIO

from django.conf import settings
from django.template.loader import get_template
from django.core.mail import EmailMultiAlternatives

from .models import Satinalma, SatinalmaKalemi, Tedarikci, GenelAyarlar, YazdirmaSablonu

AUTO_MAIL_NOTE_HTML = (
    "Bu e-posta, TEKOS / TEKORA tarafından otomatik olarak oluşturulmuştur.<br>"
    "Süreçlerimizin kesintisiz ve hatasız ilerlemesi için dijital sistemimiz tarafından iletilmiştir.<br>"
    "© 2025 TEKOS / TEKORA. Tekmar Endüstriyel Makina Otomasyon San. ve Tic. Ltd. Şti.'nin "
    "tescilli dijital yönetim platformlarıdır."
)

AUTO_MAIL_NOTE_TEXT = (
    "Bu e-posta, TEKOS / TEKORA tarafından otomatik olarak oluşturulmuştur.\n"
    "Süreçlerimizin kesintisiz ve hatasız ilerlemesi için dijital sistemimiz tarafından iletilmiştir.\n"
    "© 2025 TEKOS / TEKORA. Tekmar Endüstriyel Makina Otomasyon San. ve Tic. Ltd. Şti.'nin "
    "tescilli dijital yönetim platformlarıdır."
)


def _build_cc_list(auto_cc_email: str, *recipient_lists) -> list[str]:
    cc = (auto_cc_email or "").strip()
    if not cc:
        return []
    recipient_set = set()
    for recipients in recipient_lists:
        for email in recipients or []:
            if email:
                recipient_set.add(str(email).strip().lower())
    if cc.lower() in recipient_set:
        return []
    return [cc]


def _resolve_brand_logo_paths():
    """TEKOS / TEKORA küçük logo path'lerini (varsa) döndür."""
    tekos_logo_path = None
    tekora_logo_path = None
    static_dirs = getattr(settings, "STATICFILES_DIRS", None) or []
    candidates = [
        ("tekos", ["tekos-logo.png", "tekos_logo.png", "tekos-logo.jpg", "tekos_logo.jpg"]),
        ("tekora", ["tekora-logo.png", "tekora_logo.png", "tekora-logo.jpg", "tekora_logo.jpg"]),
    ]
    for static_dir in static_dirs:
        image_dir = os.path.join(static_dir, "stokapp", "images")
        if not os.path.isdir(image_dir):
            continue
        for brand, files in candidates:
            for fname in files:
                fpath = os.path.join(image_dir, fname)
                if os.path.exists(fpath):
                    if brand == "tekos" and tekos_logo_path is None:
                        tekos_logo_path = fpath
                    if brand == "tekora" and tekora_logo_path is None:
                        tekora_logo_path = fpath
    return tekos_logo_path, tekora_logo_path


def _resolve_company_logo_abs_path(ayarlar=None, sablon=None):
    """
    Mail PDF eklerinde kullanılacak şirket logosunu bulur.
    Öncelik: Genel Ayarlar firma logosu > Yazdırma şablonu logosu > assets/TEKMAR_9001_LOGO*
    """
    candidates = []

    if ayarlar and getattr(ayarlar, "firma_logo", None):
        logo_field = ayarlar.firma_logo
        try:
            if hasattr(logo_field, "path") and logo_field.path:
                candidates.append(logo_field.path)
        except Exception:
            pass
        if getattr(logo_field, "name", None):
            candidates.append(os.path.join(settings.MEDIA_ROOT, logo_field.name))

    if sablon and getattr(sablon, "logo_goster", False) and getattr(sablon, "logo_yolu", None):
        logo_field = sablon.logo_yolu
        try:
            if hasattr(logo_field, "path") and logo_field.path:
                candidates.append(logo_field.path)
        except Exception:
            pass
        if getattr(logo_field, "name", None):
            candidates.append(os.path.join(settings.MEDIA_ROOT, logo_field.name))

    assets_dir = os.path.join(settings.BASE_DIR, "assets")
    if os.path.isdir(assets_dir):
        try:
            asset_names = sorted(
                os.listdir(assets_dir),
                key=lambda name: os.path.getmtime(os.path.join(assets_dir, name)),
                reverse=True,
            )
            for fname in asset_names:
                low = fname.lower()
                if not low.startswith("tekmar_9001_logo"):
                    continue
                if not low.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                candidates.append(os.path.join(assets_dir, fname))
        except Exception:
            pass

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def satinalma_mail_recipient_choices(satinalmalar_qs):
    """Seçilen satınalmalardaki tedarikçilerin firma + ilgili kişi e-postaları."""
    choices = []
    t_ids = {s.tedarikci_id for s in satinalmalar_qs if s.tedarikci_id}
    if not t_ids:
        return choices
    for t in Tedarikci.objects.filter(pk__in=t_ids).prefetch_related('ilgili_kisiler').order_by('ad'):
        em = (t.email or '').strip()
        if em:
            choices.append({
                'key': f'firma-{t.pk}',
                'email': em,
                'label': f'Firma genel — {t.ad} ({em})',
            })
        for ilg in t.ilgili_kisiler.all():
            em2 = (ilg.email or '').strip()
            if not em2:
                continue
            lbl = ilg.ad_soyad
            if ilg.gorev:
                lbl += f' ({ilg.gorev})'
            lbl += f' — {em2}'
            choices.append({'key': f'ilgili-{ilg.pk}', 'email': em2, 'label': lbl})
    return choices


def satinalma_mail_emails_from_keys(choices, selected_keys):
    cmap = {c['key']: c['email'] for c in choices}
    out = []
    seen = set()
    for k in selected_keys:
        em = cmap.get(k)
        if not em:
            continue
        low = em.strip().lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(em.strip())
    return out


def satinalma_mail_labels_from_keys(choices, selected_keys):
    cmap = {c['key']: c['label'] for c in choices}
    return [cmap[k] for k in selected_keys if k in cmap]


def send_teklif_talep_formu_mail(request, satinalmalar, to_emails):
    """Teklif talep formu PDF ve e-posta. to_emails: doğrulanmış adres listesi."""
    if not to_emails:
        raise ValueError('En az bir alıcı e-postası gerekli.')
    tedarikci_emails = list(to_emails)
    satinalma_ids = list(satinalmalar.values_list('pk', flat=True))
    # Tedarikçi bilgisi (PDF şablonu için)
    ilk_satinalma = satinalmalar.first()
    tedarikci = None
    tedarikci_ad = None

    if ilk_satinalma.tedarikci:
        tedarikci = ilk_satinalma.tedarikci
        # Tedarikci modelinde 'ad' field'ı var
        tedarikci_ad = tedarikci.ad if hasattr(tedarikci, 'ad') and tedarikci.ad else (tedarikci.unvan if hasattr(tedarikci, 'unvan') and tedarikci.unvan else str(tedarikci))
    elif ilk_satinalma.tedarikci_adi:
        tedarikci_ad = ilk_satinalma.tedarikci_adi

    # PDF'i oluştur - teklif_talep_formu_pdf ile AYNI mantık (WeasyPrint kullanarak)
    # Teklif numarası oluştur - Satın alma numarasındaki TSAT'i TTTF ile değiştir
    ilk_satinalma_for_numara = satinalmalar.first()
    if ilk_satinalma_for_numara and ilk_satinalma_for_numara.satinalma_numarasi:
        # TSAT_GGAAYY_NN formatındaki TSAT'i TTTF ile değiştir
        teklif_no = ilk_satinalma_for_numara.satinalma_numarasi.replace('TSAT_', 'TTTF_', 1)
    else:
        # Fallback: Eski format kullanılıyorsa
        teklif_no = f"TTTF-{satinalma_ids[0]}"

    from .models import GenelAyarlar, YazdirmaSablonu
    ayarlar = GenelAyarlar.get_ayarlar()
    sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()

    tum_kalemler = []
    toplam_birim = Decimal('0')
    toplam_ara_toplam = Decimal('0')

    for satinalma in satinalmalar:
        kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
        for kalem in kalemler:
            tum_kalemler.append({
                'satinalma': satinalma,
                'kalem': kalem,
                'urun_adi': kalem.stok_item.ad,
                'aciklama': kalem.stok_item.aciklama or '',
                'adet': kalem.miktar,
                'birim_fiyat': kalem.birim_fiyat,
                'ara_toplam': kalem.miktar * kalem.birim_fiyat,
            })
            toplam_birim += kalem.miktar
            toplam_ara_toplam += kalem.miktar * kalem.birim_fiyat

    vergi = toplam_ara_toplam * Decimal('0.20')
    toplam = toplam_ara_toplam + vergi

    termin_tarihi = None
    for satinalma in satinalmalar:
        if satinalma.tamamlanma_tarihi:
            if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                termin_tarihi = satinalma.tamamlanma_tarihi

    context = {
        'teklif_no': teklif_no,
        'satinalmalar': satinalmalar,
        'tedarikci': tedarikci or {'ad': tedarikci_ad},
        'termin_tarihi': termin_tarihi or datetime.now().date(),
        'kalemler': tum_kalemler,
        'toplam_birim': toplam_birim,
        'toplam_ara_toplam': toplam_ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
        'ayarlar': ayarlar,
        'sablon': sablon,
        'for_pdf': True,
    }
    tekos_logo_path, tekora_logo_path = _resolve_brand_logo_paths()
    context['tekos_logo_path'] = tekos_logo_path
    context['tekora_logo_path'] = tekora_logo_path

    template = get_template('stokapp/teklif_talep_formu_pdf.html')

    # Logo için absolute path oluştur (WeasyPrint için)
    if sablon and sablon.logo_goster and sablon.logo_yolu:
        from django.conf import settings
        import os
        logo_abs_path = os.path.join(settings.MEDIA_ROOT, sablon.logo_yolu.name)
        if os.path.exists(logo_abs_path):
            # WeasyPrint için absolute path kullan
            context['logo_path'] = logo_abs_path
        else:
            context['logo_path'] = None
    else:
        context['logo_path'] = None

    html = template.render(context)

    # PDF oluştur - WeasyPrint kullanarak (PDF indirme ile AYNI)
    try:
        # WeasyPrint'i lazy import et
        from weasyprint import HTML, CSS
    
        # WeasyPrint ile PDF oluştur
        # HTML objesi oluştur - base_url logo ve diğer asset'ler için gerekli
        base_url = request.build_absolute_uri('/')
        html_obj = HTML(string=html, base_url=base_url)
    
        # CSS stilleri (PDF indirme ile AYNI)
        css = CSS(string="""
            @page {
                size: A4;
                margin: 10mm;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 12px;
                color: #000;
                margin: 0;
                padding: 15px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            th, td {
                border: 1px solid #000;
                padding: 10px;
            }
            img {
                max-width: 250px;
                max-height: 120px;
            }
        """)
    
        # PDF oluştur
        pdf_bytes = html_obj.write_pdf(stylesheets=[css])
    
        if not pdf_bytes:
            raise RuntimeError('PDF oluşturuldu ancak içerik boş.')
    
        pdf_data = pdf_bytes
    
    except Exception as pdf_error:
        import traceback
        print(f"PDF Error: {traceback.format_exc()}")
        raise RuntimeError(f'PDF oluşturma hatası: {str(pdf_error)}')

    # E-posta gönder
    try:
        # E-posta konusu - Foto 1 formatına göre
        tarih_str = datetime.now().date().strftime('%d.%m.%Y')
        email_subject = f'Teklif Talep Formu – {teklif_no} / {tarih_str}'
    
        # Firma bilgilerini al (sablon veya ayarlardan)
        firma_adi = ''
        firma_adres = ''
        firma_telefon = ''
        firma_email_address = ''
    
        if sablon:
            firma_adi = sablon.firma_adi or ''
            firma_adres = sablon.firma_adres or ''
            firma_telefon = sablon.firma_telefon or ''
            firma_email_address = sablon.firma_email or ''
    
        if ayarlar:
            if not firma_adi and ayarlar.firma_ismi:
                firma_adi = ayarlar.firma_ismi
            if not firma_telefon and ayarlar.telefon:
                firma_telefon = ayarlar.telefon
            if not firma_email_address and ayarlar.email:
                firma_email_address = ayarlar.email
    
        # Logo path'i al (e-posta için inline attachment olarak ekle)
        logo_cid = None
        logo_abs_path = None
        if sablon and sablon.logo_goster and sablon.logo_yolu:
            # Önce sablon.logo_yolu.path kullan (Django ImageField'ın path özelliği)
            if hasattr(sablon.logo_yolu, 'path') and os.path.exists(sablon.logo_yolu.path):
                logo_abs_path = sablon.logo_yolu.path
                logo_cid = 'logo_signature'  # Content-ID
                print(f"Logo bulundu (path): {logo_abs_path}")
            else:
                # Fallback: MEDIA_ROOT ile birleştir
                logo_abs_path = os.path.join(settings.MEDIA_ROOT, sablon.logo_yolu.name)
                if os.path.exists(logo_abs_path):
                    logo_cid = 'logo_signature'
                    print(f"Logo bulundu (MEDIA_ROOT): {logo_abs_path}")
                else:
                    print(f"Logo dosyası bulunamadı: {logo_abs_path}")
                print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
                print(f"logo_yolu.name: {sablon.logo_yolu.name}")
    
        # TEKOS logosunu kontrol et (footer için)
        tekos_logo_path = None
        tekos_logo_cid = None
        # STATICFILES_DIRS'den TEKOS logosunu bul
        if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
            for static_dir in settings.STATICFILES_DIRS:
                tekos_logo_candidate = os.path.join(static_dir, 'stokapp', 'images', 'tekos-logo.png')
                if os.path.exists(tekos_logo_candidate):
                    tekos_logo_path = tekos_logo_candidate
                    tekos_logo_cid = 'tekos_logo'
                    break
    
        # E-posta içeriği - HTML formatında (Foto 1 ve Foto 2'ye göre)
        termin_tarihi_str = (termin_tarihi or datetime.now().date()).strftime('%d.%m.%Y')
    
        email_body_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
    body {{
        font-family: Arial, sans-serif;
        font-size: 14px;
        color: #000000;
        line-height: 1.6;
        margin: 0;
        padding: 20px;
    }}
    .email-content {{
        max-width: 600px;
        margin: 0 auto;
    }}
    .subject {{
        font-weight: bold;
        margin-bottom: 20px;
    }}
    .greeting {{
        margin-bottom: 15px;
    }}
    .body-text {{
        margin-bottom: 15px;
    }}
    .signature {{
        margin-top: 40px;
        border-top: 2px solid #1e40af;
        padding-top: 20px;
    }}
    .signature-header {{
        display: flex;
        align-items: flex-start;
        margin-bottom: 15px;
    }}
    .signature-logo {{
        margin-right: 15px;
        flex-shrink: 0;
    }}
    .signature-logo img {{
        max-width: 240px;
        max-height: 160px;
    }}
    .signature-name-section {{
        flex: 1;
    }}
    .signature-name {{
        font-weight: bold;
        font-size: 16px;
        color: #1e40af;
        margin-bottom: 5px;
    }}
    .signature-title {{
        font-size: 14px;
        color: #1e40af;
        margin-bottom: 10px;
    }}
    .signature-company {{
        font-weight: bold;
        font-size: 12px;
        color: #1e40af;
        margin-bottom: 15px;
    }}
    .signature-info {{
        font-size: 11px;
        color: #1e40af;
        line-height: 1.8;
    }}
    .signature-info a {{
        color: #1e40af;
        text-decoration: underline;
    }}
    .email-footer {{
        margin-top: 40px;
        border-top: 2px solid #1e40af;
        padding-top: 20px;
    }}
    .email-footer-content {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    .email-footer-logo {{
        flex-shrink: 0;
    }}
    .email-footer-logo img {{
        max-width: 120px;
        max-height: 80px;
    }}
    .email-footer-text {{
        flex: 1;
        text-align: center;
        font-weight: 600;
        font-size: 11px;
        color: #1e40af;
        line-height: 1.8;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }}
    .auto-mail-note {{
        margin-top: 16px;
        background: linear-gradient(135deg, #eff6ff 0%, #eef2ff 100%);
        border: 1px solid #c7d2fe;
        border-radius: 10px;
        padding: 12px 14px;
        font-size: 11px;
        color: #1e3a8a;
        text-align: center;
        line-height: 1.75;
        box-shadow: 0 6px 16px rgba(30, 64, 175, 0.08);
    }}
        </style>
    </head>
    <body>
        <div class="email-content">
    <div class="subject">Konu: Teklif Talep Formu – {teklif_no} / {tarih_str}</div>

    <div class="greeting">Sayın Yetkili,</div>

    <div class="body-text">
        Şirketimiz tarafından temin edilmesi planlanan ürün/hizmetlere ilişkin Teklif Talep Formu ekte bilgilerinize sunulmuştur.
    </div>

    <div class="body-text">
        Belirtilen kalemler için fiyat, termin süresi ve diğer teknik/lojistik koşulları içeren teklifinizi iletmenizi rica ederiz.
    </div>

    <div class="body-text">
        Herhangi bir ek bilgiye ihtiyaç duymanız durumunda tarafımızla iletişime geçebilirsiniz.
    </div>

    <div class="body-text">
        İşbirliğiniz için teşekkür eder, çalışmalarınızda başarılar dileriz.
    </div>

    <div class="body-text" style="margin-top: 20px;">Saygılarımızla,</div>

    <div class="signature">
        <div class="signature-header">
            {f'<div class="signature-logo"><img src="cid:{logo_cid}" alt="Logo"></div>' if logo_cid else ''}
            <div class="signature-name-section">
                <div class="signature-name">Burak BAŞARAN</div>
                <div class="signature-title">Teknik Müdür</div>
            </div>
        </div>
        <div class="signature-company">{firma_adi or 'Tekmar Endüstriyel Sanayi ve Ticaret Limited Şirketi'}</div>
        <div class="signature-info">
            {f'Cep Tel : {firma_telefon}' if firma_telefon else ''}<br>
            {f'E-Posta : <a href="mailto:{firma_email_address}">{firma_email_address}</a>' if firma_email_address else ''}<br>
            {f'Adres : {firma_adres}' if firma_adres else 'Adres : Karadenizliler Mah. Horon Sok. No:7 Başiskele / KOCAELİ'}
        </div>
    </div>

    <div class="email-footer">
        <div class="email-footer-content">
            <div class="email-footer-logo">
                {'<img src="cid:tekos_logo" alt="TEKOS Logo">' if tekos_logo_cid else ''}
            </div>
        </div>
        <div class="auto-mail-note">
            {AUTO_MAIL_NOTE_HTML}
        </div>
    </div>
        </div>
    </body>
    </html>
    '''
    
        # Plain text versiyonu (fallback)
        email_body_text = f'''Konu: Teklif Talep Formu – {teklif_no} / {tarih_str}

    Sayın Yetkili,

    Şirketimiz tarafından temin edilmesi planlanan ürün/hizmetlere ilişkin Teklif Talep Formu ekte bilgilerinize sunulmuştur.

    Belirtilen kalemler için fiyat, termin süresi ve diğer teknik/lojistik koşulları içeren teklifinizi iletmenizi rica ederiz.

    Herhangi bir ek bilgiye ihtiyaç duymanız durumunda tarafımızla iletişime geçebilirsiniz.

    İşbirliğiniz için teşekkür eder, çalışmalarınızda başarılar dileriz.

    Saygılarımızla,

    Burak BAŞARAN
    Teknik Müdür
    {firma_adi or 'Tekmar Endüstriyel Sanayi ve Ticaret Limited Şirketi'}
    {f'Cep Tel : {firma_telefon}' if firma_telefon else ''}
    {f'E-Posta : {firma_email_address}' if firma_email_address else ''}
    {f'Adres : {firma_adres}' if firma_adres else 'Adres : Karadenizliler Mah. Horon Sok. No:7 Başiskele / KOCAELİ'}

    {AUTO_MAIL_NOTE_TEXT}
    '''
    
        # E-posta mesajı oluştur - EmailMultiAlternatives kullan (HTML + inline attachments için)
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
        # CC: Satınalma merkezi takip adresi
        cc_email = GenelAyarlar.get_satinalma_mail_cc_adresi()
        cc_list = _build_cc_list(cc_email, tedarikci_emails)
        email = EmailMultiAlternatives(
            subject=email_subject,
            body=email_body_text,
            from_email=from_email,
            to=tedarikci_emails,
            cc=cc_list,
        )
        # HTML içeriği ekle
        email.attach_alternative(email_body_html, "text/html")
    
        # Logo'yu inline attachment olarak ekle (e-posta içinde görünmesi için)
        if logo_cid and logo_abs_path and os.path.exists(logo_abs_path):
            try:
                with open(logo_abs_path, 'rb') as logo_file:
                    logo_data = logo_file.read()
                    logo_ext = os.path.splitext(logo_abs_path)[1].lower()
                    if logo_ext == '.png':
                        logo_mime = 'image/png'
                    elif logo_ext in ['.jpg', '.jpeg']:
                        logo_mime = 'image/jpeg'
                    else:
                        logo_mime = 'image/png'
                
                    # Inline attachment için MIMEImage kullan
                    from email.mime.image import MIMEImage
                    logo_img = MIMEImage(logo_data)
                    logo_img.add_header('Content-ID', f'<{logo_cid}>')
                    logo_img.add_header('Content-Disposition', 'inline', filename=os.path.basename(logo_abs_path))
                
                    # EmailMultiAlternatives'ın attachments listesine ekle
                    email.attachments.append(logo_img)
            except Exception as e:
                print(f"Logo inline attachment ekleme hatası: {str(e)}")
                import traceback
                traceback.print_exc()
    
        # TEKOS logosunu inline attachment olarak ekle (footer için)
        if tekos_logo_path and tekos_logo_cid and os.path.exists(tekos_logo_path):
            try:
                with open(tekos_logo_path, 'rb') as tekos_logo_file:
                    tekos_logo_data = tekos_logo_file.read()
                
                    # Inline attachment için MIMEImage kullan
                    from email.mime.image import MIMEImage
                    tekos_logo_img = MIMEImage(tekos_logo_data)
                    tekos_logo_img.add_header('Content-ID', f'<{tekos_logo_cid}>')
                    tekos_logo_img.add_header('Content-Disposition', 'inline', filename='tekos-logo.png')
                
                    # EmailMultiAlternatives'ın attachments listesine ekle
                    email.attachments.append(tekos_logo_img)
                    print(f"TEKOS logo eklendi: {tekos_logo_path}")
            except Exception as e:
                print(f"TEKOS logo inline attachment ekleme hatası: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print(f"TEKOS logo bulunamadı. STATICFILES_DIRS: {getattr(settings, 'STATICFILES_DIRS', None)}")
    
        # PDF'i attachment olarak ekle
        email.attach(
            filename=f'teklif_talep_formu_{teklif_no}.pdf',
            content=pdf_data,
            mimetype='application/pdf'
        )
    
        # Güncellenmiş teknik resimleri mail'e ekle
        guncellenmis_teknik_resimler = []
        for satinalma in satinalmalar:
            kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
            for kalem in kalemler:
                # Önce güncellenmiş teknik resim var mı kontrol et
                if kalem.teknik_resim_guncellenmis:
                    teknik_resim_dosyasi = kalem.teknik_resim_guncellenmis
                    try:
                        # Dosya yolunu al
                        if hasattr(teknik_resim_dosyasi, 'path') and os.path.exists(teknik_resim_dosyasi.path):
                            teknik_resim_yolu = teknik_resim_dosyasi.path
                        else:
                            teknik_resim_yolu = os.path.join(settings.MEDIA_ROOT, teknik_resim_dosyasi.name)
                            if not os.path.exists(teknik_resim_yolu):
                                continue
                    
                        # Dosya uzantısını kontrol et
                        dosya_adi = os.path.basename(teknik_resim_yolu)
                        dosya_uzantisi = os.path.splitext(dosya_adi)[1].lower()
                    
                        # Mail'e attachment olarak ekle
                        with open(teknik_resim_yolu, 'rb') as f:
                            email.attach(
                                filename=dosya_adi,
                                content=f.read(),
                                mimetype='application/dxf' if dosya_uzantisi == '.dxf' else 'application/acad'
                            )
                    
                        guncellenmis_teknik_resimler.append(dosya_adi)
                    except Exception as e:
                        print(f"Güncellenmiş teknik resim eklenemedi ({kalem.stok_item.ad}): {str(e)}")
                # Eğer güncellenmiş yoksa, orijinal teknik resmi ekle (isteğe bağlı)
                elif kalem.stok_item.teknik_resim:
                    teknik_resim_dosyasi = kalem.stok_item.teknik_resim
                    try:
                        if hasattr(teknik_resim_dosyasi, 'path') and os.path.exists(teknik_resim_dosyasi.path):
                            teknik_resim_yolu = teknik_resim_dosyasi.path
                        else:
                            teknik_resim_yolu = os.path.join(settings.MEDIA_ROOT, teknik_resim_dosyasi.name)
                            if not os.path.exists(teknik_resim_yolu):
                                continue
                    
                        dosya_adi = os.path.basename(teknik_resim_yolu)
                        dosya_uzantisi = os.path.splitext(dosya_adi)[1].lower()
                    
                        with open(teknik_resim_yolu, 'rb') as f:
                            email.attach(
                                filename=dosya_adi,
                                content=f.read(),
                                mimetype='application/dxf' if dosya_uzantisi == '.dxf' else 'application/acad'
                            )
                    except Exception as e:
                        print(f"Orijinal teknik resim eklenemedi ({kalem.stok_item.ad}): {str(e)}")
    
        # E-postayı gönder
        email.send()

    except Exception as email_error:
        import traceback

        print(f"Email Error: {traceback.format_exc()}")
        raise RuntimeError(f'E-posta gönderilirken hata: {email_error}') from email_error


def send_siparis_formu_mail(request, satinalmalar, to_emails):
    """Sipariş formu PDF ve e-posta."""
    if not to_emails:
        raise ValueError('En az bir alıcı e-postası gerekli.')
    tedarikci_emails = list(to_emails)
    satinalma_ids = list(satinalmalar.values_list('pk', flat=True))
    ilk_satinalma = satinalmalar.first()
    tedarikci = None
    tedarikci_ad = None

    if ilk_satinalma.tedarikci:
        tedarikci = ilk_satinalma.tedarikci
        tedarikci_ad = tedarikci.ad if hasattr(tedarikci, 'ad') and tedarikci.ad else (tedarikci.unvan if hasattr(tedarikci, 'unvan') and tedarikci.unvan else str(tedarikci))
    elif ilk_satinalma.tedarikci_adi:
        tedarikci_ad = ilk_satinalma.tedarikci_adi

    # PDF'i oluştur - siparis_formu_pdf ile AYNI mantık
    siparis_no = ilk_satinalma.satinalma_numarasi if ilk_satinalma else f"SIP-{satinalma_ids[0]}"

    from .models import GenelAyarlar, YazdirmaSablonu
    ayarlar = GenelAyarlar.get_ayarlar()
    sablon = YazdirmaSablonu.objects.filter(tip='SIPARIS', aktif=True).first()
    # Eğer SIPARIS tipinde sablon yoksa, TEKLIF_TALEBI tipindeki sablonu kullan (görsel olarak aynı)
    if not sablon:
        sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()

    tum_kalemler = []
    toplam_birim = Decimal('0')
    toplam_ara_toplam = Decimal('0')

    for satinalma in satinalmalar:
        kalemler = SatinalmaKalemi.objects.filter(satinalma=satinalma).order_by('id')
        for kalem in kalemler:
            fiyat = kalem.tedarikci_fiyat if kalem.tedarikci_fiyat else kalem.birim_fiyat
            tum_kalemler.append({
                'satinalma': satinalma,
                'kalem': kalem,
                'urun_adi': kalem.stok_item.ad,
                'aciklama': kalem.stok_item.aciklama or '',
                'adet': kalem.miktar,
                'birim_fiyat': fiyat,
                'ara_toplam': kalem.miktar * fiyat,
            })
            toplam_birim += kalem.miktar
            toplam_ara_toplam += kalem.miktar * fiyat

    vergi = toplam_ara_toplam * Decimal('0.20')
    toplam = toplam_ara_toplam + vergi

    termin_tarihi = None
    for satinalma in satinalmalar:
        if satinalma.tamamlanma_tarihi:
            if termin_tarihi is None or satinalma.tamamlanma_tarihi > termin_tarihi:
                termin_tarihi = satinalma.tamamlanma_tarihi

    context = {
        'siparis_no': siparis_no,
        'satinalmalar': satinalmalar,
        'tedarikci': tedarikci or {'ad': tedarikci_ad} if tedarikci_ad else None,
        'tedarikci_adi': tedarikci_ad,
        'termin_tarihi': termin_tarihi or datetime.now().date(),
        'kalemler': tum_kalemler,
        'toplam_birim': toplam_birim,
        'toplam_ara_toplam': toplam_ara_toplam,
        'vergi': vergi,
        'toplam': toplam,
        'para_birimi': ilk_satinalma.para_birimi if ilk_satinalma else 'TRY',
        'ayarlar': ayarlar,
        'sablon': sablon,
        'for_pdf': True,
    }

    template = get_template('stokapp/siparis_formu_pdf.html')

    context['logo_path'] = _resolve_company_logo_abs_path(ayarlar=ayarlar, sablon=sablon)

    html_content = template.render(context)

    # WeasyPrint ile PDF oluştur
    try:
        from weasyprint import HTML
        pdf_file = BytesIO()
        HTML(string=html_content, base_url=request.build_absolute_uri('/')).write_pdf(pdf_file)
        pdf_file.seek(0)
    except ImportError as e:
        raise RuntimeError('WeasyPrint kütüphanesi bulunamadı.') from e
    except Exception as e:
        raise RuntimeError(f'PDF oluşturma hatası: {e}') from e

    # E-posta gönder
    from django.utils import timezone

    tarih_str = timezone.now().strftime('%d.%m.%Y')
    subject = f'Sipariş Formu – {siparis_no} / {tarih_str}'

    # E-posta içeriği
    email_body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333;">
        <p>Sayın Yetkili,</p>
    
        <p>Ek'te {siparis_no} numaralı sipariş formumuzu bulabilirsiniz.</p>
    
        <p>Lütfen sipariş formumuzu inceleyiniz.</p>
    
        <p style="margin-top: 40px;">
            Saygılarımızla,<br><br>
            <strong style="font-size: 16px;">Burak BAŞARAN</strong><br>
            <span style="font-size: 14px;">Teknik Müdür</span>
        </p>
        <div style="margin-top:24px; background:linear-gradient(135deg,#eff6ff 0%,#eef2ff 100%); border:1px solid #c7d2fe; border-radius:10px; padding:12px 14px; text-align:center; font-size:11px; line-height:1.75; color:#1e3a8a; box-shadow:0 6px 16px rgba(30,64,175,0.08);">
            {AUTO_MAIL_NOTE_HTML}
        </div>
    </body>
    </html>
    """

    cc_email = GenelAyarlar.get_satinalma_mail_cc_adresi()
    cc_list = _build_cc_list(cc_email, tedarikci_emails)
    email = EmailMultiAlternatives(
        subject=subject,
        body=email_body_html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=tedarikci_emails,
        cc=cc_list,
    )
    email.attach_alternative(email_body_html, "text/html")
    email.attach(f'siparis_formu_{siparis_no}.pdf', pdf_file.read(), 'application/pdf')
    email.send()

def send_rfq_mail(request, rfq, bcc_emails):
    """RFQ (TeklifTalebi) PDF'i ile çoklu tedarikçiye **BCC** olarak teklif talebi gönderir.

    Tedarikçiler birbirlerinin e-posta adresini görmemelidir; bu yüzden tüm alıcılar
    BCC alanına eklenir, TO alanı şirket from_email'ı, CC alanı satınalma takip kutusu olur.
    """
    if not bcc_emails:
        raise ValueError('En az bir BCC alıcısı gerekli.')

    bcc_clean = []
    seen = set()
    for em in bcc_emails:
        em = (em or '').strip()
        if not em:
            continue
        low = em.lower()
        if low in seen:
            continue
        seen.add(low)
        bcc_clean.append(em)

    ayarlar = GenelAyarlar.get_ayarlar() if hasattr(GenelAyarlar, 'get_ayarlar') else None
    sablon = YazdirmaSablonu.objects.filter(tip='TEKLIF_TALEBI', aktif=True).first()

    kalemler = list(rfq.kalemler.all().select_related('stok_item'))

    # PDF context
    context = {
        'rfq': rfq,
        'kalemler': kalemler,
        'ayarlar': ayarlar,
        'sablon': sablon,
        'logo_path': None,
    }
    tekos_logo_path, tekora_logo_path = _resolve_brand_logo_paths()
    context['tekos_logo_path'] = tekos_logo_path
    context['tekora_logo_path'] = tekora_logo_path

    if sablon and sablon.logo_goster and sablon.logo_yolu:
        try:
            logo_abs_path = os.path.join(settings.MEDIA_ROOT, sablon.logo_yolu.name)
            if os.path.exists(logo_abs_path):
                context['logo_path'] = logo_abs_path
        except Exception:
            pass

    template = get_template('stokapp/rfq_pdf.html')
    html = template.render(context)

    try:
        from weasyprint import HTML, CSS
        base_url = request.build_absolute_uri('/') if request else None
        html_obj = HTML(string=html, base_url=base_url)
        css = CSS(string="""
            @page { size: A4; margin: 10mm; }
            body { font-family: Arial, sans-serif; font-size: 12px; color: #000; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #000; padding: 8px; }
        """)
        pdf_bytes = html_obj.write_pdf(stylesheets=[css])
        if not pdf_bytes:
            raise RuntimeError('PDF üretildi ama içerik boş.')
    except Exception as e:
        raise RuntimeError(f'RFQ PDF oluşturma hatası: {e}') from e

    # E-posta gövdesi (BCC olduğu için ortak gövde)
    tarih_str = datetime.now().strftime('%d.%m.%Y')
    subject = f'Teklif Talebi – {rfq.rfq_no} / {tarih_str}'

    # Logo inline attachments
    logo_cid = None
    logo_abs_path = None
    if sablon and sablon.logo_goster and sablon.logo_yolu:
        try:
            if hasattr(sablon.logo_yolu, 'path') and os.path.exists(sablon.logo_yolu.path):
                logo_abs_path = sablon.logo_yolu.path
            else:
                logo_abs_path = os.path.join(settings.MEDIA_ROOT, sablon.logo_yolu.name)
            if logo_abs_path and os.path.exists(logo_abs_path):
                logo_cid = 'logo_signature'
        except Exception:
            logo_abs_path = None

    tekos_logo_path = None
    tekos_logo_cid = None
    if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
        for static_dir in settings.STATICFILES_DIRS:
            tekos_candidate = os.path.join(static_dir, 'stokapp', 'images', 'tekos-logo.png')
            if os.path.exists(tekos_candidate):
                tekos_logo_path = tekos_candidate
                tekos_logo_cid = 'tekos_logo'
                break

    firma_adi = ''
    firma_telefon = ''
    firma_email_address = ''
    firma_adres = ''
    if sablon:
        firma_adi = sablon.firma_adi or ''
        firma_telefon = sablon.firma_telefon or ''
        firma_email_address = sablon.firma_email or ''
        firma_adres = sablon.firma_adres or ''
    if ayarlar:
        firma_adi = firma_adi or getattr(ayarlar, 'firma_ismi', '') or ''
        firma_telefon = firma_telefon or getattr(ayarlar, 'telefon', '') or ''
        firma_email_address = firma_email_address or getattr(ayarlar, 'email', '') or ''

    son_teklif_str = rfq.son_teklif_tarihi.strftime('%d.%m.%Y') if rfq.son_teklif_tarihi else '-'

    body_html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body {{ font-family: Arial, sans-serif; font-size: 14px; color: #000; line-height: 1.6; padding: 20px; }}
.signature {{ margin-top: 30px; border-top: 2px solid #1e40af; padding-top: 16px; }}
.signature-name {{ font-weight: bold; font-size: 16px; color: #1e40af; }}
.signature-title {{ color: #1e40af; }}
.signature-info {{ color: #1e40af; font-size: 12px; line-height: 1.7; }}
.email-footer {{ margin-top: 30px; border-top: 2px solid #1e40af; padding-top: 14px; }}
.email-footer-text {{ font-size: 11px; color: #1e40af; line-height: 1.7; text-align: center; }}
.auto-mail-note {{ margin-top: 14px; background: linear-gradient(135deg,#eff6ff 0%,#eef2ff 100%); border: 1px solid #c7d2fe; border-radius: 10px; padding: 10px 12px; font-size: 11px; color: #1e3a8a; line-height: 1.75; text-align: center; }}
</style></head><body>
<p><strong>Konu: Teklif Talebi – {rfq.rfq_no} / {tarih_str}</strong></p>
<p>Sayın Yetkili,</p>
<p>Şirketimiz tarafından temin edilmesi planlanan ürün/hizmetlere ilişkin <strong>Teklif Talep Formu</strong> ekte bilgilerinize sunulmuştur.</p>
<p>Belirtilen kalemler için fiyat, termin süresi ve diğer teknik/lojistik koşulları içeren teklifinizi {son_teklif_str} tarihine kadar iletmenizi rica ederiz.</p>
<p>Herhangi bir ek bilgiye ihtiyaç duymanız durumunda tarafımızla iletişime geçebilirsiniz.</p>
<p>İşbirliğiniz için teşekkür eder, çalışmalarınızda başarılar dileriz.</p>
<p style="margin-top:20px;">Saygılarımızla,</p>
<div class="signature">
    {f'<div style="margin-bottom:10px;"><img src="cid:{logo_cid}" style="max-width:240px; max-height:120px;" alt="Logo"></div>' if logo_cid else ''}
    <div class="signature-name">Burak BAŞARAN</div>
    <div class="signature-title">Teknik Müdür</div>
    <div class="signature-info" style="margin-top:8px;">
        <strong>{firma_adi or 'Tekmar Endüstriyel Sanayi ve Ticaret Limited Şirketi'}</strong><br>
        {f'Cep Tel : {firma_telefon}<br>' if firma_telefon else ''}
        {f'E-Posta : <a href="mailto:{firma_email_address}" style="color:#1e40af;">{firma_email_address}</a><br>' if firma_email_address else ''}
        {f'Adres : {firma_adres}' if firma_adres else 'Adres : Karadenizliler Mah. Horon Sok. No:7 Başiskele / KOCAELİ'}
    </div>
</div>
<div class="email-footer">
    {f'<div style="text-align:center; margin-bottom:8px;"><img src="cid:{tekos_logo_cid}" style="max-width:120px;" alt="TEKOS"></div>' if tekos_logo_cid else ''}
    <div class="auto-mail-note">
        {AUTO_MAIL_NOTE_HTML}
    </div>
</div>
</body></html>'''

    body_text = (
        f'Konu: Teklif Talebi – {rfq.rfq_no} / {tarih_str}\n\n'
        'Sayın Yetkili,\n\n'
        'Şirketimiz tarafından temin edilmesi planlanan ürün/hizmetlere ilişkin Teklif Talep Formu '
        'ekte bilgilerinize sunulmuştur.\n\n'
        f'Lütfen teklifinizi {son_teklif_str} tarihine kadar iletiniz.\n\n'
        'Saygılarımızla,\nBurak BAŞARAN\nTeknik Müdür\n\n'
        f'{AUTO_MAIL_NOTE_TEXT}\n'
    )

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
    cc_email = GenelAyarlar.get_satinalma_mail_cc_adresi()
    cc_list = _build_cc_list(cc_email, [from_email], bcc_clean)

    email = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=from_email,
        to=[from_email],   # TO: kendimiz; tedarikçiler birbirini görmesin
        cc=cc_list,
        bcc=bcc_clean,
    )
    email.attach_alternative(body_html, 'text/html')

    if logo_cid and logo_abs_path and os.path.exists(logo_abs_path):
        try:
            with open(logo_abs_path, 'rb') as f:
                from email.mime.image import MIMEImage
                img = MIMEImage(f.read())
                img.add_header('Content-ID', f'<{logo_cid}>')
                img.add_header('Content-Disposition', 'inline', filename=os.path.basename(logo_abs_path))
                email.attachments.append(img)
        except Exception:
            pass
    if tekos_logo_path and tekos_logo_cid and os.path.exists(tekos_logo_path):
        try:
            with open(tekos_logo_path, 'rb') as f:
                from email.mime.image import MIMEImage
                img = MIMEImage(f.read())
                img.add_header('Content-ID', f'<{tekos_logo_cid}>')
                img.add_header('Content-Disposition', 'inline', filename='tekos-logo.png')
                email.attachments.append(img)
        except Exception:
            pass

    email.attach(
        filename=f'teklif_talebi_{rfq.rfq_no}.pdf',
        content=pdf_bytes,
        mimetype='application/pdf',
    )

    # İlgili stok kartlarındaki teknik resimleri de ekle (varsa)
    eklenen_resimler = set()
    for k in kalemler:
        if k.stok_item and k.stok_item.teknik_resim:
            try:
                resim = k.stok_item.teknik_resim
                resim_path = resim.path if hasattr(resim, 'path') else os.path.join(settings.MEDIA_ROOT, resim.name)
                if not os.path.exists(resim_path):
                    continue
                base = os.path.basename(resim_path)
                if base in eklenen_resimler:
                    continue
                eklenen_resimler.add(base)
                with open(resim_path, 'rb') as fh:
                    ext = os.path.splitext(base)[1].lower()
                    mime = 'application/dxf' if ext == '.dxf' else 'application/acad'
                    email.attach(filename=base, content=fh.read(), mimetype=mime)
            except Exception:
                continue

    email.send()


def satinalma_mail_normalize_to_allowed(raw_emails, choices):
    """choices içinde tanımlı adreslere göre sırayı koruyarak tekilleştirir."""
    allowed_lower = {c['email'].strip().lower(): c['email'].strip() for c in choices}
    out = []
    seen = set()
    for e in raw_emails:
        em = allowed_lower.get(str(e).strip().lower())
        if em and em.lower() not in seen:
            seen.add(em.lower())
            out.append(em)
    return out


def musteri_mail_recipient_choices(musteri):
    """Kayıtlı müşteri kartı: firma e-postası + ilgili kişiler (e-postası olanlar)."""
    if musteri is None:
        return []
    choices = []
    em = (musteri.email or '').strip()
    if em:
        choices.append(
            {
                'key': f'm-firma-{musteri.pk}',
                'email': em,
                'label': f'Firma genel — {musteri.ad} ({em})',
            }
        )
    for ilg in musteri.ilgili_kisiler.all().order_by('sira', 'id'):
        em2 = (ilg.email or '').strip()
        if not em2:
            continue
        lbl = ilg.ad_soyad
        if ilg.gorev:
            lbl += f' ({ilg.gorev})'
        lbl += f' — {em2}'
        choices.append({'key': f'm-ilgili-{ilg.pk}', 'email': em2, 'label': lbl})
    return choices

