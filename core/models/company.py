from django.conf import settings
from django.db import models
from django.utils.text import slugify

from core.managers import TenantManager


class Company(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    setup_completed = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    demo_seed_completed = models.BooleanField(default=False)
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Reserved for future custom domain routing (not active yet).",
    )
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    # Optional profile fields filled by setup wizard
    short_name = models.CharField(max_length=80, blank=True, default="")
    tax_office = models.CharField(max_length=120, blank=True, default="")
    tax_number = models.CharField(max_length=40, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    currency = models.CharField(max_length=10, blank=True, default="TRY")
    timezone = models.CharField(max_length=64, blank=True, default="Europe/Istanbul")
    language = models.CharField(max_length=16, blank=True, default="tr")
    date_format = models.CharField(max_length=32, blank=True, default="%d.%m.%Y")
    default_vat = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:70] or "company"
            slug = base
            n = 1
            while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)


class CompanyMembership(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company membership"
        verbose_name_plural = "Company memberships"
        unique_together = [["user", "company"]]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default and self.is_active:
            (
                CompanyMembership.objects.filter(user=self.user, is_default=True)
                .exclude(pk=self.pk)
                .update(is_default=False)
            )


class Department(models.Model):
    """Company-scoped department for setup wizard (not tied to stokapp)."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="departments"
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        unique_together = [["company", "name"]]
        ordering = ["name"]

    def __str__(self):
        return f"{self.company.slug}:{self.name}"


class CompanySetupDraft(models.Model):
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="setup_draft"
    )
    current_step = models.PositiveSmallIntegerField(default=1)
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Setup draft for {self.company} (step {self.current_step})"
