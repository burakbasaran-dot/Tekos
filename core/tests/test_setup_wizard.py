from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import Company, CompanyMembership, CompanySetupDraft, Department
from core.views_setup import complete_setup


User = get_user_model()


class SetupWizardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("wizuser", password="Pass12345!")
        self.company = Company.objects.create(
            name="Incomplete Co", slug="incomplete-co", setup_completed=False
        )
        CompanyMembership.objects.create(
            user=self.user,
            company=self.company,
            role="owner",
            is_default=True,
            is_active=True,
        )

    def test_incomplete_redirects_to_wizard(self):
        client = Client()
        client.login(username="wizuser", password="Pass12345!")
        session = client.session
        session["active_company_id"] = self.company.pk
        session.save()
        response = client.get("/stok/dashboard/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/platform/setup/", response["Location"])

    def test_completed_company_skips_wizard(self):
        self.company.setup_completed = True
        self.company.save()
        client = Client()
        client.login(username="wizuser", password="Pass12345!")
        session = client.session
        session["active_company_id"] = self.company.pk
        session.save()
        response = client.get("/platform/setup/1/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/stok/dashboard/", response["Location"])

    def test_draft_persists_between_steps(self):
        client = Client()
        client.login(username="wizuser", password="Pass12345!")
        session = client.session
        session["active_company_id"] = self.company.pk
        session.save()
        response = client.post(
            "/platform/setup/1/",
            {
                "name": "Acme Sanayi",
                "tax_number": "123",
                "action": "next",
            },
        )
        self.assertEqual(response.status_code, 302)
        draft = CompanySetupDraft.objects.get(company=self.company)
        self.assertEqual(draft.data.get("name"), "Acme Sanayi")
        self.assertEqual(draft.current_step, 2)

    def test_complete_sets_flag_and_seeds(self):
        draft = CompanySetupDraft.objects.create(
            company=self.company,
            current_step=7,
            data={
                "name": "Acme Final",
                "departments": ["Yönetim", "Üretim"],
                "warehouses": ["Ana Depo"],
                "currency": "TRY",
            },
        )
        complete_setup(self.company, draft, self.user)
        self.company.refresh_from_db()
        self.assertTrue(self.company.setup_completed)
        self.assertEqual(self.company.name, "Acme Final")
        self.assertTrue(
            Department.objects.filter(company=self.company, name="Yönetim").exists()
        )
        self.assertFalse(CompanySetupDraft.objects.filter(company=self.company).exists())

    def test_name_required_on_step_1(self):
        client = Client()
        client.login(username="wizuser", password="Pass12345!")
        session = client.session
        session["active_company_id"] = self.company.pk
        session.save()
        response = client.post(
            "/platform/setup/1/",
            {"name": "", "action": "next"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["errors"])
