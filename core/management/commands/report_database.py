"""Report active database engine and migration status (no secrets)."""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Report database engine and applied migration counts (safe for logs)."

    def handle(self, *args, **options):
        engine = connection.settings_dict.get("ENGINE", "")
        vendor = connection.vendor
        name = connection.settings_dict.get("NAME", "")
        # Avoid printing full paths that might include credentials; NAME for SQLite is a path.
        if vendor == "postgresql":
            display_name = str(name)
        else:
            display_name = str(name).rsplit("/", 1)[-1] if name else ""

        self.stdout.write(f"vendor={vendor}")
        self.stdout.write(f"engine={engine}")
        self.stdout.write(f"name={display_name}")

        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write("connection=ok")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"connection=error ({type(exc).__name__})"))
            return

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        applied = len(executor.loader.applied_migrations)
        self.stdout.write(f"migrations_applied={applied}")
        self.stdout.write(f"migrations_pending={len(plan)}")
        if plan:
            self.stdout.write(self.style.WARNING("pending migrations exist"))
        else:
            self.stdout.write(self.style.SUCCESS("migrations_up_to_date=yes"))
