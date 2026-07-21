from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import Company, CompanyMembership, PlatformAuditLog
from core.services.audit import log_action, redact_dict


User = get_user_model()


class AuditTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Audit Co", slug="audit-co", setup_completed=True
        )
        self.other = Company.objects.create(
            name="Other Co", slug="other-co", setup_completed=True
        )
        self.user = User.objects.create_user("auditor", password="Pass12345!")
        CompanyMembership.objects.create(
            user=self.user, company=self.company, role="owner", is_default=True
        )

    def test_create_logged_via_signal(self):
        before = PlatformAuditLog.objects.count()
        Company.objects.create(name="New Co", slug="new-co-x", setup_completed=True)
        self.assertGreater(PlatformAuditLog.objects.count(), before)

    def test_update_keeps_old_and_new(self):
        self.company.name = "Audit Co Renamed"
        self.company.save()
        log = (
            PlatformAuditLog.objects.filter(
                model_name__endswith="Company", object_id=str(self.company.pk)
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(log)
        self.assertIn("name", log.old_values)
        self.assertEqual(log.new_values.get("name"), "Audit Co Renamed")

    def test_delete_membership_logged(self):
        m = CompanyMembership.objects.get(user=self.user, company=self.company)
        pk = m.pk
        m.delete()
        self.assertTrue(
            PlatformAuditLog.objects.filter(
                action=PlatformAuditLog.ACTION_DELETE, object_id=str(pk)
            ).exists()
        )

    def test_password_redacted(self):
        redacted = redact_dict({"username": "a", "password": "secret", "token": "xyz"})
        self.assertEqual(redacted["password"], "***REDACTED***")
        self.assertEqual(redacted["token"], "***REDACTED***")
        self.assertEqual(redacted["username"], "a")

    def test_login_creates_audit(self):
        client = Client()
        client.login(username="auditor", password="Pass12345!")
        self.assertTrue(
            PlatformAuditLog.objects.filter(
                action=PlatformAuditLog.ACTION_LOGIN, user=self.user
            ).exists()
        )

    def test_company_isolation_query(self):
        log_action(
            action=PlatformAuditLog.ACTION_VIEW,
            company=self.company,
            user=self.user,
            model_name="demo",
        )
        log_action(
            action=PlatformAuditLog.ACTION_VIEW,
            company=self.other,
            user=self.user,
            model_name="demo",
        )
        self.assertEqual(
            PlatformAuditLog.objects.filter(company=self.company, model_name="demo").count(),
            1,
        )

    def test_normal_user_cannot_delete_audit_in_admin_logic(self):
        from django.contrib.admin.sites import AdminSite

        from core.admin import PlatformAuditLogAdmin

        admin_inst = PlatformAuditLogAdmin(PlatformAuditLog, AdminSite())
        request = type("R", (), {"user": self.user})()
        self.assertFalse(admin_inst.has_delete_permission(request))
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(admin_inst.has_delete_permission(request))
