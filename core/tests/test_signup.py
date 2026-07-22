"""Tests for public signup flows."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings

from core.models import LegalDocument, SignupApplication
from core.services.email_verification import create_verification_token

User = get_user_model()


class LoginSignupButtonTests(TestCase):
    def test_login_page_shows_signup_buttons(self):
        response = Client().get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Ücretsiz Deneme", body)
        self.assertIn("/accounts/trial/register/", body)
        self.assertIn("Geliştirici Olmak İstiyorum", body)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TRIAL_DAYS=30,
)
class TrialSignupFlowTests(TestCase):
    def setUp(self):
        LegalDocument.objects.get_or_create(
            doc_type=LegalDocument.DOC_KVKK,
            version="1.0",
            defaults={"title": "KVKK", "content": "Test", "is_active": True},
        )
        LegalDocument.objects.get_or_create(
            doc_type=LegalDocument.DOC_TERMS,
            version="1.0",
            defaults={"title": "Terms", "content": "Test", "is_active": True},
        )

    def _trial_post_data(self, email="trial-new@example.com"):
        return {
            "first_name": "Deneme",
            "last_name": "Kullanıcı",
            "email": email,
            "phone": "05321234567",
            "company_name": "Deneme A.Ş.",
            "industry": "metal",
            "city": "İstanbul",
            "company_size": "1-5",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
            "kvkk_accepted": "on",
            "terms_accepted": "on",
            "source": "test",
            "website_url": "",
        }

    def test_trial_form_requires_kvkk(self):
        data = self._trial_post_data()
        data.pop("kvkk_accepted")
        response = Client().post("/accounts/trial/register/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SignupApplication.objects.count(), 0)

    def test_trial_form_submission_sends_email(self):
        client = Client()
        response = client.post("/accounts/trial/register/", self._trial_post_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SignupApplication.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_verification_and_provisioning(self):
        from core.models import Plan

        Plan.objects.get_or_create(
            code="free_trial",
            defaults={"name": "Free Trial", "trial_days": 30, "is_active": True},
        )
        client = Client()
        email = "provision-test@example.com"
        client.post("/accounts/trial/register/", self._trial_post_data(email))
        app = SignupApplication.objects.get(email=email)
        token = create_verification_token(app)
        response = client.get(f"/accounts/verify-email/{token}/")
        self.assertEqual(response.status_code, 302)
        app.refresh_from_db()
        self.assertTrue(app.email_verified)
        self.assertEqual(app.status, SignupApplication.STATUS_ACTIVE)
        self.assertIsNotNone(app.created_company)
        self.assertIsNotNone(app.created_user)
        self.assertTrue(app.created_company.is_demo)


class DeveloperSignupTests(TestCase):
    def setUp(self):
        LegalDocument.objects.get_or_create(
            doc_type=LegalDocument.DOC_KVKK,
            version="1.0",
            defaults={"title": "KVKK", "content": "Test", "is_active": True},
        )
        LegalDocument.objects.get_or_create(
            doc_type=LegalDocument.DOC_TERMS,
            version="1.0",
            defaults={"title": "Terms", "content": "Test", "is_active": True},
        )

    def test_developer_submission_goes_review_pending_after_verify(self):
        client = Client()
        data = {
            "first_name": "Dev",
            "last_name": "User",
            "email": "dev@example.com",
            "phone": "05329998877",
            "city": "Ankara",
            "country": "Türkiye",
            "company_name": "Dev Co",
            "job_title": "Backend",
            "experience_level": "senior",
            "work_style": "freelance",
            "kvkk_accepted": "on",
            "terms_accepted": "on",
            "website_url": "",
        }
        client.post("/accounts/developer/register/", data)
        app = SignupApplication.objects.get(email="dev@example.com")
        token = create_verification_token(app)
        client.get(f"/accounts/verify-email/{token}/")
        app.refresh_from_db()
        self.assertEqual(app.status, SignupApplication.STATUS_REVIEW_PENDING)
        self.assertIsNone(app.created_company)


class ApplicationAdminAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="Pass12345!")
        from core.models import Company, CompanyMembership

        self.company = Company.objects.create(name="Admin Co", slug="admin-co", setup_completed=True)
        CompanyMembership.objects.create(
            user=self.owner,
            company=self.company,
            role=CompanyMembership.ROLE_OWNER,
            is_active=True,
            is_default=True,
        )
        self.member = User.objects.create_user("member", password="Pass12345!")
        CompanyMembership.objects.create(
            user=self.member,
            company=self.company,
            role=CompanyMembership.ROLE_MEMBER,
            is_active=True,
        )

    def test_member_cannot_access_applications(self):
        client = Client()
        client.login(username="member", password="Pass12345!")
        response = client.get("/platform/applications/")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_access_applications(self):
        client = Client()
        client.login(username="owner", password="Pass12345!")
        response = client.get("/platform/applications/")
        self.assertEqual(response.status_code, 200)
