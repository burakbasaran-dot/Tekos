from django.core.management.base import BaseCommand

from stokapp.models import GenelAyarlar
from stokapp.views_mail import process_imap_mail_flow


class Command(BaseCommand):
    help = "TEKORA için IMAP mailbox kontrolü yapar ve siparişleri onay kuyruğuna alır."

    def handle(self, *args, **options):
        ayarlar = GenelAyarlar.get_ayarlar()
        if not ayarlar.tekora_aktif:
            self.stdout.write(self.style.WARNING("TEKORA pasif: IMAP mail takibi çalıştırılmadı."))
            return

        result = process_imap_mail_flow()

        total_read = result.get("count", 0)
        approvals_created = result.get("approvals_created_count", 0)
        skipped_duplicate_count = result.get("skipped_duplicate_count", 0)
        error_count = result.get("error_count", 0)
        processing_errors = result.get("processing_errors", [])
        mailbox_errors = result.get("mailbox_errors", [])
        sanitized_existing = result.get("sanitized_existing_count", 0)

        self.stdout.write(self.style.SUCCESS("TEKORA mail kontrolü tamamlandı."))
        self.stdout.write(f"Okunan mail sayısı: {total_read}")
        self.stdout.write(f"Oluşturulan onay kaydı: {approvals_created}")
        self.stdout.write(f"Atlanan tekrar mail sayısı: {skipped_duplicate_count}")
        self.stdout.write(f"Hatalı mail sayısı: {error_count}")
        self.stdout.write(f"Temizlenen eski kayıt: {sanitized_existing}")

        if mailbox_errors:
            self.stdout.write(self.style.WARNING("Mailbox hataları:"))
            for err in mailbox_errors:
                self.stdout.write(f"- {err.get('email')}: {err.get('error')}")

        if processing_errors:
            self.stdout.write(self.style.WARNING("Mail işleme hataları:"))
            for err in processing_errors:
                self.stdout.write(
                    f"- sender={err.get('sender')} subject={err.get('subject')} error={err.get('error')}"
                )
