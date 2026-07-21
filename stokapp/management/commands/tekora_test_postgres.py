"""Varsayılan PostgreSQL bağlantısını (DATABASES['default']) test eder."""

from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "DATABASES['default'] (PostgreSQL) bağlantı testi (SELECT 1)."

    def handle(self, *args, **options):
        self.stdout.write("[TEKORA POSTGRES]")
        conn = connections["default"]
        try:
            conn.ensure_connection()
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"Connection failed: {exc}\n"
                    "Kontrol: psycopg kurulu mu, PostgreSQL çalışıyor mu, "
                    ".env içinde TEKOS_POSTGRES_* değerleri doğru mu?"
                )
            )
            raise SystemExit(1) from exc

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            one = cursor.fetchone()
        if one is None or one[0] != 1:
            self.stderr.write(self.style.ERROR("SELECT 1 beklenmeyen sonuç döndü."))
            raise SystemExit(1)

        self.stdout.write("Connection successful.")
