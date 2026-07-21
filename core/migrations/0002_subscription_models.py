# Generated for subscription models

from datetime import timedelta

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("core", "Plan")
    PlanModuleEntitlement = apps.get_model("core", "PlanModuleEntitlement")
    Subscription = apps.get_model("core", "Subscription")
    Company = apps.get_model("core", "Company")

    trial, _ = Plan.objects.get_or_create(
        code="free_trial",
        defaults={
            "name": "Free Trial",
            "description": "Default trial plan",
            "monthly_price": 0,
            "yearly_price": 0,
            "currency": "TRY",
            "user_limit": 10,
            "storage_limit": 2048,
            "is_active": True,
            "trial_days": 14,
        },
    )
    standard, _ = Plan.objects.get_or_create(
        code="standard",
        defaults={
            "name": "Standard",
            "description": "Standard subscription",
            "monthly_price": 0,
            "yearly_price": 0,
            "currency": "TRY",
            "user_limit": 50,
            "storage_limit": 10240,
            "is_active": True,
            "trial_days": 14,
        },
    )
    for plan in (trial, standard):
        for module in ("platform", "stok", "uretim"):
            PlanModuleEntitlement.objects.get_or_create(
                plan=plan,
                module_code=module,
                defaults={"is_enabled": True},
            )

    today = django.utils.timezone.localdate()
    for company in Company.objects.all():
        if Subscription.objects.filter(company=company).exists():
            continue
        Subscription.objects.create(
            company=company,
            plan=trial,
            status="trial",
            start_date=today,
            trial_end_date=today + timedelta(days=14),
            end_date=today + timedelta(days=14),
            renewal_type="monthly",
            is_auto_renew=False,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.SlugField(max_length=60, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("monthly_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("yearly_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("currency", models.CharField(default="TRY", max_length=10)),
                ("user_limit", models.PositiveIntegerField(default=5)),
                ("storage_limit", models.PositiveIntegerField(default=1024, help_text="Storage limit in MB")),
                ("is_active", models.BooleanField(default=True)),
                ("trial_days", models.PositiveIntegerField(default=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("trial", "Trial"), ("active", "Active"), ("past_due", "Past due"), ("suspended", "Suspended"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="trial", max_length=20)),
                ("start_date", models.DateField(default=django.utils.timezone.localdate)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("trial_end_date", models.DateField(blank=True, null=True)),
                ("renewal_type", models.CharField(choices=[("monthly", "Monthly"), ("yearly", "Yearly")], default="monthly", max_length=20)),
                ("is_auto_renew", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="core.company")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="core.plan")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PlanModuleEntitlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_code", models.CharField(max_length=80)),
                ("is_enabled", models.BooleanField(default=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entitlements", to="core.plan")),
            ],
            options={"ordering": ["plan", "module_code"], "unique_together": {("plan", "module_code")}},
        ),
        migrations.RunPython(seed_plans, noop),
    ]
