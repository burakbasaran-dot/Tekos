from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import Company, CompanyMembership, PlatformAuditLog


User = get_user_model()

PAGES = [
    "/platform/companies/",
    "/platform/demo-companies/",
    "/platform/system-health/",
    "/platform/audit-logs/",
]


class PlatformAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "root", "root@example.com", "Pass12345!"
        )
        self.owner = User.objects.create_user("owner1", password="Pass12345!")
        self.member = User.objects.create_user("member1", password="Pass12345!")
        self.co_a = Company.objects.create(
            name="Alpha", slug="alpha", setup_completed=True, is_demo=True
        )
        self.co_b = Company.objects.create(
            name="Beta", slug="beta", setup_completed=True
        )
        CompanyMembership.objects.create(
            user=self.owner,
            company=self.co_a,
            role=CompanyMembership.ROLE_OWNER,
            is_default=True,
            is_active=True,
        )
        CompanyMembership.objects.create(
            user=self.member,
            company=self.co_a,
            role=CompanyMembership.ROLE_MEMBER,
            is_default=True,
            is_active=True,
        )
        PlatformAuditLog.objects.create(
            company=self.co_a,
            user=self.owner,
            action=PlatformAuditLog.ACTION_VIEW,
            object_repr="alpha-log",
        )
        PlatformAuditLog.objects.create(
            company=self.co_b,
            user=self.superuser,
            action=PlatformAuditLog.ACTION_VIEW,
            object_repr="beta-secret-log",
        )

    def test_superuser_gets_200_on_all_pages(self):
        client = Client()
        self.assertTrue(client.login(username="root", password="Pass12345!"))
        for url in PAGES:
            response = client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_owner_gets_200(self):
        client = Client()
        self.assertTrue(client.login(username="owner1", password="Pass12345!"))
        session = client.session
        session["active_company_id"] = self.co_a.pk
        session.save()
        for url in PAGES:
            response = client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_plain_member_gets_403(self):
        client = Client()
        self.assertTrue(client.login(username="member1", password="Pass12345!"))
        session = client.session
        session["active_company_id"] = self.co_a.pk
        session.save()
        for url in PAGES:
            response = client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_audit_tenant_isolation(self):
        client = Client()
        self.assertTrue(client.login(username="owner1", password="Pass12345!"))
        session = client.session
        session["active_company_id"] = self.co_a.pk
        session.save()
        response = client.get("/platform/audit-logs/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("alpha-log", body)
        self.assertNotIn("beta-secret-log", body)

    def test_health_html_has_no_secrets(self):
        client = Client()
        self.assertTrue(client.login(username="root", password="Pass12345!"))
        response = client.get("/platform/system-health/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        body_lower = body.lower()
        for needle in (
            "SECRET_KEY",
            "DATABASE_URL",
            "django-insecure",
            "postgres://",
            "postgresql://",
        ):
            self.assertNotIn(needle.lower(), body_lower)
        from django.conf import settings

        db_password = (settings.DATABASES.get("default") or {}).get("PASSWORD") or ""
        if db_password:
            self.assertNotIn(db_password, body)

    def test_audit_post_not_allowed(self):
        client = Client()
        self.assertTrue(client.login(username="root", password="Pass12345!"))
        before = PlatformAuditLog.objects.count()
        response = client.post("/platform/audit-logs/", {"action": "delete"})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(PlatformAuditLog.objects.count(), before)
