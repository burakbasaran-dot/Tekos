from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create default Admin superuser if it does not exist."

    def handle(self, *args, **options):
        User = get_user_model()
        username = "Admin"

        if User.objects.filter(username=username).exists():
            self.stdout.write("Admin already exists.")
            return

        user = User.objects.create_user(
            username=username,
            email="burakbasaran@hotmail.com.tr",
            password="Tekos2026!",
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save(update_fields=["is_staff", "is_superuser", "is_active"])
        self.stdout.write(self.style.SUCCESS(f'User "{username}" created successfully.'))
