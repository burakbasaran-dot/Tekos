from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0002_subscription_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("login", "Login"), ("logout", "Logout"), ("create", "Create"), ("update", "Update"), ("delete", "Delete"), ("view", "View"), ("export", "Export"), ("import", "Import"), ("permission_change", "Permission change"), ("settings_change", "Settings change")], max_length=32)),
                ("model_name", models.CharField(blank=True, default="", max_length=120)),
                ("object_id", models.CharField(blank=True, default="", max_length=64)),
                ("object_repr", models.CharField(blank=True, default="", max_length=255)),
                ("old_values", models.JSONField(blank=True, default=dict)),
                ("new_values", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("request_path", models.CharField(blank=True, default="", max_length=512)),
                ("request_method", models.CharField(blank=True, default="", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="platform_audit_logs", to="core.company")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="platform_audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Platform audit log",
                "verbose_name_plural": "Platform audit logs",
                "db_table": "core_platform_audit_log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="platformauditlog",
            index=models.Index(fields=["company", "created_at"], name="core_platfo_company_0d9f2a_idx"),
        ),
        migrations.AddIndex(
            model_name="platformauditlog",
            index=models.Index(fields=["action", "created_at"], name="core_platfo_action_8c1e4b_idx"),
        ),
        migrations.AddIndex(
            model_name="platformauditlog",
            index=models.Index(fields=["model_name", "created_at"], name="core_platfo_model_n_4a2c7d_idx"),
        ),
    ]
