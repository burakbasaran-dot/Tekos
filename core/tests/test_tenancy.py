from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import Company, CompanyMembership
from core.services.tenancy import (
    get_user_companies,
    set_active_company,
    user_can_access_company,
)


User = get_user_model()


class TenancyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member1", password="Pass12345!")
        self.other = User.objects.create_user("member2", password="Pass12345!")
        self.superuser = User.objects.create_superuser(
            "root", "root@example.com", "Pass12345!"
        )
        self.co_a = Company.objects.create(name="Alpha", slug="alpha", setup_completed=True)
        self.co_b = Company.objects.create(name="Beta", slug="beta", setup_completed=True)
        self.co_inactive = Company.objects.create(
            name="Inactive Co", slug="inactive", is_active=False, setup_completed=True
        )
        CompanyMembership.objects.create(
            user=self.user, company=self.co_a, role="owner", is_default=True, is_active=True
        )
        CompanyMembership.objects.create(
            user=self.user, company=self.co_b, role="member", is_active=True
        )
        CompanyMembership.objects.create(
            user=self.other, company=self.co_b, role="owner", is_default=True
        )

    def test_user_sees_only_membership_companies(self):
        companies = list(get_user_companies(self.user))
        self.assertEqual({c.slug for c in companies}, {"alpha", "beta"})
        self.assertFalse(user_can_access_company(self.user, self.co_inactive))

    def test_user_cannot_access_other_company(self):
        self.assertFalse(user_can_access_company(self.other, self.co_a))

    def test_inactive_company_blocked(self):
        CompanyMembership.objects.create(
            user=self.user, company=self.co_inactive, role="member", is_active=True
        )
        self.assertFalse(user_can_access_company(self.user, self.co_inactive))

    def test_default_company_selection(self):
        memberships = CompanyMembership.objects.filter(user=self.user, is_default=True)
        self.assertEqual(memberships.count(), 1)
        self.assertEqual(memberships.get().company, self.co_a)

    def test_request_company_via_middleware(self):
        client = Client()
        client.login(username="member1", password="Pass12345!")
        session = client.session
        session["active_company_id"] = self.co_b.pk
        session.save()
        response = client.get("/platform/company/select/")
        self.assertEqual(response.status_code, 200)
        # Middleware sets request.company; check via select page context
        self.assertEqual(response.context["active_company"], self.co_b)

    def test_superuser_sees_all_active(self):
        companies = list(get_user_companies(self.superuser))
        slugs = {c.slug for c in companies}
        self.assertIn("alpha", slugs)
        self.assertIn("beta", slugs)
        self.assertNotIn("inactive", slugs)

    def test_set_active_company_rejects_unauthorized(self):
        client = Client()
        client.login(username="member2", password="Pass12345!")
        request = client.get("/platform/company/select/").wsgi_request
        request.user = self.other
        self.assertFalse(set_active_company(request, self.co_a))
