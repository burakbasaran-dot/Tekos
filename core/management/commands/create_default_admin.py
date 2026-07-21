from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create default Admin superuser if it does not exist.'

    def handle(self, *args, **options):
        User = get_user_model()
        username = "Admin"

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists. Skipping.'))
            return

        User.objects.create_superuser(
            username=username,
            email="burakbasaran@hotmail.com.tr",
            password="Tekos2026!",
        )
        self.stdout.write(self.style.SUCCESS(f'User "{username}" created successfully.'))
