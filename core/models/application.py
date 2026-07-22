from django.conf import settings
from django.db import models

from core.constants import (
    COMPANY_SIZE_CHOICES,
    EXPERIENCE_LEVEL_CHOICES,
    INDUSTRY_CHOICES,
    WORK_STYLE_CHOICES,
)
from core.models.company import Company
from core.models.subscription import Subscription


class SignupApplication(models.Model):
    TYPE_TRIAL = "trial"
    TYPE_DEVELOPER = "developer"
    TYPE_CHOICES = [
        (TYPE_TRIAL, "Ücretsiz Deneme"),
        (TYPE_DEVELOPER, "Geliştirici Başvurusu"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_EMAIL_VERIFICATION_PENDING = "email_verification_pending"
    STATUS_SUBMITTED = "submitted"
    STATUS_PROVISIONING = "provisioning"
    STATUS_ACTIVE = "active"
    STATUS_REVIEW_PENDING = "review_pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_FAILED = "failed"
    STATUS_DUPLICATE = "duplicate"
    STATUS_CONVERTED = "converted"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Taslak"),
        (STATUS_EMAIL_VERIFICATION_PENDING, "E-posta doğrulama bekliyor"),
        (STATUS_SUBMITTED, "Gönderildi"),
        (STATUS_PROVISIONING, "Hesap oluşturuluyor"),
        (STATUS_ACTIVE, "Aktif"),
        (STATUS_REVIEW_PENDING, "İnceleme bekliyor"),
        (STATUS_APPROVED, "Onaylandı"),
        (STATUS_REJECTED, "Reddedildi"),
        (STATUS_EXPIRED, "Süresi doldu"),
        (STATUS_CANCELLED, "İptal"),
        (STATUS_FAILED, "Başarısız"),
        (STATUS_DUPLICATE, "Yinelenen"),
        (STATUS_CONVERTED, "Müşteriye dönüştürüldü"),
    ]

    application_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=40, blank=True, default="")
    company_name = models.CharField(max_length=200, blank=True, default="")
    job_title = models.CharField(max_length=120, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    country = models.CharField(max_length=80, blank=True, default="Türkiye")
    company_size = models.CharField(
        max_length=20, choices=COMPANY_SIZE_CHOICES, blank=True, default=""
    )
    industry = models.CharField(
        max_length=40, choices=INDUSTRY_CHOICES, blank=True, default=""
    )
    message = models.TextField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    username_preference = models.CharField(max_length=150, blank=True, default="")
    trial_modules = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=40, blank=True, default="")
    utm_source = models.CharField(max_length=80, blank=True, default="")
    utm_medium = models.CharField(max_length=80, blank=True, default="")
    utm_campaign = models.CharField(max_length=120, blank=True, default="")
    referrer_url = models.URLField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="tr")
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    kvkk_accepted = models.BooleanField(default=False)
    terms_accepted = models.BooleanField(default=False)
    commercial_communication_accepted = models.BooleanField(default=False)
    legal_document_versions = models.JSONField(default=dict, blank=True)
    developer_profile = models.JSONField(default=dict, blank=True)
    provisioning_idempotency_key = models.CharField(
        max_length=64, blank=True, default="", unique=True, null=True
    )
    failure_summary = models.CharField(max_length=500, blank=True, default="")
    internal_notes = models.TextField(blank=True, default="")
    rejection_reason = models.CharField(max_length=500, blank=True, default="")
    created_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_applications_created",
    )
    created_company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_applications",
    )
    created_subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_applications",
    )
    assigned_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_signup_applications",
    )
    trial_notification_flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["application_type", "status"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        return f"{self.get_application_type_display()} — {self.email} ({self.status})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class ApplicationStatusHistory(models.Model):
    application = models.ForeignKey(
        SignupApplication, on_delete=models.CASCADE, related_name="status_history"
    )
    old_status = models.CharField(max_length=32, blank=True, default="")
    new_status = models.CharField(max_length=32)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application_status_changes",
    )
    note = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application_id}: {self.old_status} → {self.new_status}"


class EmailVerificationToken(models.Model):
    application = models.ForeignKey(
        SignupApplication, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token_hash = models.CharField(max_length=128, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Token for application {self.application_id}"


class LegalDocument(models.Model):
    DOC_KVKK = "kvkk"
    DOC_TERMS = "terms"
    DOC_CHOICES = [
        (DOC_KVKK, "KVKK Aydınlatma Metni"),
        (DOC_TERMS, "Kullanım Koşulları"),
    ]

    doc_type = models.CharField(max_length=20, choices=DOC_CHOICES, db_index=True)
    version = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["doc_type", "version"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} v{self.version}"


def application_upload_path(instance, filename):
    import os
    from django.utils.text import get_valid_filename

    safe = get_valid_filename(os.path.basename(filename))
    return f"applications/{instance.application_id}/{safe}"


class ApplicationUpload(models.Model):
    application = models.ForeignKey(
        SignupApplication, on_delete=models.CASCADE, related_name="uploads"
    )
    file = models.FileField(upload_to=application_upload_path)
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=100, blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name or str(self.file)
