from django.conf import settings
from django.db import models

from core.models.company import Company


class PlatformAuditLog(models.Model):
    """Platform-level audit trail (distinct from stokapp.AuditLog)."""

    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_VIEW = "view"
    ACTION_EXPORT = "export"
    ACTION_IMPORT = "import"
    ACTION_PERMISSION_CHANGE = "permission_change"
    ACTION_SETTINGS_CHANGE = "settings_change"
    ACTION_SIGNUP = "signup"
    ACTION_CHOICES = [
        (ACTION_LOGIN, "Login"),
        (ACTION_LOGOUT, "Logout"),
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_VIEW, "View"),
        (ACTION_EXPORT, "Export"),
        (ACTION_IMPORT, "Import"),
        (ACTION_PERMISSION_CHANGE, "Permission change"),
        (ACTION_SETTINGS_CHANGE, "Settings change"),
        (ACTION_SIGNUP, "Signup"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_audit_logs",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=120, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    object_repr = models.CharField(max_length=255, blank=True, default="")
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    request_path = models.CharField(max_length=512, blank=True, default="")
    request_method = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "core_platform_audit_log"
        ordering = ["-created_at"]
        verbose_name = "Platform audit log"
        verbose_name_plural = "Platform audit logs"
        indexes = [
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["model_name", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.model_name}#{self.object_id} @ {self.created_at}"
