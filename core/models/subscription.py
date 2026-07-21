from django.db import models
from django.utils import timezone

from core.models.company import Company


class Plan(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=60, unique=True)
    description = models.TextField(blank=True, default="")
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    yearly_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="TRY")
    user_limit = models.PositiveIntegerField(default=5)
    storage_limit = models.PositiveIntegerField(
        default=1024, help_text="Storage limit in MB"
    )
    is_active = models.BooleanField(default=True)
    trial_days = models.PositiveIntegerField(default=14)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Subscription(models.Model):
    STATUS_TRIAL = "trial"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_SUSPENDED = "suspended"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_TRIAL, "Trial"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    RENEWAL_MONTHLY = "monthly"
    RENEWAL_YEARLY = "yearly"
    RENEWAL_CHOICES = [
        (RENEWAL_MONTHLY, "Monthly"),
        (RENEWAL_YEARLY, "Yearly"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    trial_end_date = models.DateField(null=True, blank=True)
    renewal_type = models.CharField(
        max_length=20, choices=RENEWAL_CHOICES, default=RENEWAL_MONTHLY
    )
    is_auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} — {self.plan.code} ({self.status})"


class PlanModuleEntitlement(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="entitlements")
    module_code = models.CharField(max_length=80)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [["plan", "module_code"]]
        ordering = ["plan", "module_code"]

    def __str__(self):
        state = "on" if self.is_enabled else "off"
        return f"{self.plan.code}:{self.module_code}={state}"
