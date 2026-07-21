"""TEKORA proaktif uyarı motorunu çalıştırır ve özet yazar."""

from django.core.management.base import BaseCommand

from stokapp.tekora_alert_engine import run_proactive_tekora_analysis


class Command(BaseCommand):
    help = "TEKORA ERP proaktif analiz ve uyarı üretimi (tekora_alert_engine)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[TEKORA ANALYZE]"))
        self.stdout.write("Çalışıyor...")
        try:
            stats = run_proactive_tekora_analysis()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"[TEKORA ANALYZE] Kritik hata: {exc}"))
            raise
        self.stdout.write(f"[DEBUG] Critical items found: {stats.get('critical_items_found', 0)}")
        self.stdout.write(f"[DEBUG] Critical stock alerts created: {stats.get('critical_stock_alerts', 0)}")
        self.stdout.write(f"[DEBUG] Critical stock alerts skipped existing: {stats.get('critical_stock_skipped', 0)}")
        self.stdout.write(f"[DEBUG] Critical stock alert errors: {stats.get('critical_stock_errors', 0)}")
        self.stdout.write(f"Critical stock alerts: {stats['critical_stock_alerts']}")
        self.stdout.write(f"Pending approval alerts: {stats['pending_approval_alerts']}")
        self.stdout.write(f"Production alerts: {stats['production_alerts']}")
        self.stdout.write(f"Critical severity alerts: {stats['critical_severity_alerts']}")
        self.stdout.write(self.style.SUCCESS(f"Total new alerts created: {stats['total_created']}"))
