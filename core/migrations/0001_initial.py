# Generated manually for core company models bootstrap

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def bootstrap_default_company(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    CompanyMembership = apps.get_model("core", "CompanyMembership")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    GenelAyarlar = apps.get_model("stokapp", "GenelAyarlar")

    if Company.objects.exists():
        return

    name = "Default Company"
    ayar = GenelAyarlar.objects.filter(pk=1).first()
    if ayar and (getattr(ayar, "firma_ismi", None) or "").strip():
        name = ayar.firma_ismi.strip()

    company = Company.objects.create(
        name=name,
        slug="default-company",
        setup_completed=True,
        is_active=True,
    )
    for user in User.objects.all():
        CompanyMembership.objects.get_or_create(
            user=user,
            company=company,
            defaults={
                "role": "owner",
                "is_active": True,
                "is_default": True,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("stokapp", "0135_musteri_kategoriler"),
    ]

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("setup_completed", models.BooleanField(default=False)),
                ("is_demo", models.BooleanField(default=False)),
                ("custom_domain", models.CharField(blank=True, default="", help_text="Reserved for future custom domain routing (not active yet).", max_length=255)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="company_logos/")),
                ("short_name", models.CharField(blank=True, default="", max_length=80)),
                ("tax_office", models.CharField(blank=True, default="", max_length=120)),
                ("tax_number", models.CharField(blank=True, default="", max_length=40)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("website", models.URLField(blank=True, default="")),
                ("address", models.TextField(blank=True, default="")),
                ("currency", models.CharField(blank=True, default="TRY", max_length=10)),
                ("timezone", models.CharField(blank=True, default="Europe/Istanbul", max_length=64)),
                ("language", models.CharField(blank=True, default="tr", max_length=16)),
                ("date_format", models.CharField(blank=True, default="%d.%m.%Y", max_length=32)),
                ("default_vat", models.DecimalField(decimal_places=2, default=20, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Company",
                "verbose_name_plural": "Companies",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="CompanySetupDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("current_step", models.PositiveSmallIntegerField(default=1)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="setup_draft", to="core.company")),
            ],
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="departments", to="core.company")),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("company", "name")},
            },
        ),
        migrations.CreateModel(
            name="CompanyMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner", "Owner"), ("admin", "Admin"), ("member", "Member")], default="member", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="core.company")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="company_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Company membership",
                "verbose_name_plural": "Company memberships",
                "unique_together": {("user", "company")},
                "indexes": [models.Index(fields=["user", "is_active"], name="core_compan_user_id_7a31a1_idx")],
            },
        ),
        migrations.RunPython(bootstrap_default_company, noop_reverse),
    ]
