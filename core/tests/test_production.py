import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase

from stok_sistemi.env_utils import env_flag, parse_csv_env


class EnvUtilsTests(SimpleTestCase):
    def test_env_flag_true_variants(self):
        with mock.patch.dict(os.environ, {"DEBUG": "True"}):
            self.assertTrue(env_flag("DEBUG", "False"))
        with mock.patch.dict(os.environ, {"DEBUG": "true"}):
            self.assertTrue(env_flag("DEBUG", "False"))
        with mock.patch.dict(os.environ, {"DEBUG": "FALSE"}):
            self.assertFalse(env_flag("DEBUG", "True"))

    def test_parse_csv_env_strips_and_skips_empty(self):
        with mock.patch.dict(
            os.environ,
            {"ALLOWED_HOSTS": " localhost, ,127.0.0.1, tekos.example.com "},
        ):
            self.assertEqual(
                parse_csv_env("ALLOWED_HOSTS", ""),
                ["localhost", "127.0.0.1", "tekos.example.com"],
            )

    def test_parse_csrf_trusted_origins(self):
        with mock.patch.dict(
            os.environ,
            {
                "CSRF_TRUSTED_ORIGINS": (
                    "https://tekos-9155.onrender.com, https://app.example.com"
                )
            },
        ):
            self.assertEqual(
                parse_csv_env("CSRF_TRUSTED_ORIGINS", ""),
                [
                    "https://tekos-9155.onrender.com",
                    "https://app.example.com",
                ],
            )


class HealthEndpointTests(TestCase):
    def test_health_returns_ok(self):
        client = Client()
        response = client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, {"status": "ok"})

    def test_health_does_not_leak_sensitive_info(self):
        client = Client()
        response = client.get("/api/health/")
        body = response.content.decode()
        for needle in (
            "SECRET_KEY",
            "DATABASE_URL",
            "password",
            "DEBUG",
            "sqlite",
            "postgres",
        ):
            self.assertNotIn(needle.lower(), body.lower())


class CreateDefaultAdminCommandTests(TestCase):
    def test_skips_when_env_incomplete(self):
        User = get_user_model()
        out = StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                "DJANGO_SUPERUSER_USERNAME",
                "DJANGO_SUPERUSER_EMAIL",
                "DJANGO_SUPERUSER_PASSWORD",
            ):
                os.environ.pop(key, None)
            call_command("create_default_admin", stdout=out)
        self.assertEqual(User.objects.count(), 0)
        self.assertIn("skipping", out.getvalue().lower())

    def test_creates_user_when_missing(self):
        User = get_user_model()
        out = StringIO()
        env = {
            "DJANGO_SUPERUSER_USERNAME": "ci_admin",
            "DJANGO_SUPERUSER_EMAIL": "ci_admin@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "CiAdminPass123!",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("create_default_admin", stdout=out)
        user = User.objects.get(username="ci_admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertIn("created", out.getvalue().lower())

    def test_does_not_recreate_or_change_password(self):
        User = get_user_model()
        user = User.objects.create_superuser(
            username="ci_admin",
            email="ci_admin@example.com",
            password="OriginalPass123!",
        )
        env = {
            "DJANGO_SUPERUSER_USERNAME": "ci_admin",
            "DJANGO_SUPERUSER_EMAIL": "other@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "ChangedPass123!",
        }
        out = StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("create_default_admin", stdout=out)
        user.refresh_from_db()
        self.assertEqual(User.objects.filter(username="ci_admin").count(), 1)
        self.assertTrue(user.check_password("OriginalPass123!"))
        self.assertFalse(user.check_password("ChangedPass123!"))
        self.assertIn("already exists", out.getvalue().lower())
