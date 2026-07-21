from django.core.management.base import BaseCommand

from stokapp.services.tekora_approval_refresh import refresh_all_pending_email_orders


class Command(BaseCommand):
    help = "Onay bekleyen ve hatalı TEKORA e-posta onay kayıtlarında ürün/stok analizini güncel kurallarla yeniden hesaplar (hatalılar tekrar bekliyor olur)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="En fazla kaç kayıt işlensin (1–1000, varsayılan 500).",
        )

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 1000))
        stats = refresh_all_pending_email_orders(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Güncellenen: {stats['updated']}"))
        self.stdout.write(f"Hatalı → bekliyor: {stats.get('failed_reset_to_pending', 0)}")
        self.stdout.write(f"Atlanan: {stats['skipped']}")
        if stats["errors"]:
            self.stdout.write(self.style.WARNING(f"Hata sayısı: {len(stats['errors'])}"))
            for e in stats["errors"][:20]:
                self.stdout.write(f"  - {e.get('id')}: {e.get('error')}")
