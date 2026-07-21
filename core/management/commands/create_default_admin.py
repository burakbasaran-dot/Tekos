from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
import os


class Command(BaseCommand):
    help = (
        "Create a default superuser from DJANGO_SUPERUSER_* env vars "
        "if the user does not already exist."
    )

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "").strip()

        if not username or not email or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME / EMAIL / PASSWORD not fully set; "
                "skipping admin creation."
            )
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'User "{username}" already exists.')
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'User "{username}" created successfully.'))
