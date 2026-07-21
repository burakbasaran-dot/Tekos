from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyMembership, Plan, PlanModuleEntitlement, Subscription
from core.services.licensing import (
    can_add_user,
    get_active_subscription,
    is_read_only,
    plan_has_module,
    subscription_allows_access,
)


User = get_user_model()


class LicensingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Licensed Co", slug="licensed-co", setup_completed=True
        )
        self.plan = Plan.objects.create(
            name="Trial", code="test_trial", user_limit=2, trial_days=14
        )
        PlanModuleEntitlement.objects.create(
            plan=self.plan, module_code="platform", is_enabled=True
        )
        PlanModuleEntitlement.objects.create(
            plan=self.plan, module_code="secret_mod", is_enabled=False
        )
        today = timezone.localdate()
        self.sub = Subscription.objects.create(
            company=self.company,
            plan=self.plan,
            status=Subscription.STATUS_TRIAL,
            start_date=today,
            trial_end_date=today + timedelta(days=14),
            end_date=today + timedelta(days=14),
        )
        self.u1 = User.objects.create_user("u1", password="Pass12345!")
        CompanyMembership.objects.create(
            user=self.u1, company=self.company, role="owner", is_active=True
        )

    def test_active_subscription_allows_access(self):
        self.assertTrue(subscription_allows_access(self.company))
        self.assertFalse(is_read_only(self.company))
        self.assertEqual(get_active_subscription(self.company), self.sub)

    def test_expired_subscription_read_only(self):
        self.sub.status = Subscription.STATUS_EXPIRED
        self.sub.save()
        self.assertFalse(subscription_allows_access(self.company))
        self.assertTrue(is_read_only(self.company))

    def test_trial_end_respected(self):
        self.sub.trial_end_date = timezone.localdate() - timedelta(days=1)
        self.sub.save()
        self.assertIsNone(get_active_subscription(self.company))

    def test_user_limit(self):
        self.assertTrue(can_add_user(self.company))
        u2 = User.objects.create_user("u2", password="Pass12345!")
        CompanyMembership.objects.create(
            user=u2, company=self.company, role="member", is_active=True
        )
        self.assertFalse(can_add_user(self.company))

    def test_plan_module_entitlement(self):
        self.assertTrue(plan_has_module(self.company, "platform"))
        self.assertFalse(plan_has_module(self.company, "secret_mod"))

    def test_superuser_not_checked_here(self):
        # Decorator bypasses; service layer is company-based only
        self.sub.status = Subscription.STATUS_EXPIRED
        self.sub.save()
        self.assertTrue(is_read_only(self.company))
