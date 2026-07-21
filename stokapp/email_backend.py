"""
Özel SMTP Email Backend - SSL sertifika doğrulama sorunlarını çözmek için
"""
import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.utils.functional import cached_property


class CustomSMTPEmailBackend(SMTPBackend):
    """
    SSL sertifika doğrulaması sorunlarını çözen özel SMTP backend
    """
    
    @cached_property
    def ssl_context(self):
        """
        SSL bağlamı oluştur - sertifika doğrulamasını geçici olarak devre dışı bırak
        Self-signed sertifikalar için güvenlik uyarısı: Production ortamında dikkatli kullanın
        """
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

