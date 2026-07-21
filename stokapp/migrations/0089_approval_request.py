from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0088_arge_rbac_yetkileri"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("create_sales_order", "Satış siparişi oluştur"),
                            ("create_purchase_request", "Satınalma talebi oluştur"),
                            ("send_supplier_quote_request", "Tedarikçiye teklif talebi gönder"),
                            ("approve_supplier_offer", "Tedarikçi teklifini onayla"),
                            ("create_purchase_order", "Satınalma siparişi oluştur"),
                            ("create_production_order", "Üretim emri oluştur"),
                            ("plan_payment", "Ödeme planla"),
                            ("send_customer_email", "Müşteriye e-posta gönder"),
                        ],
                        max_length=100,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("ai_summary", models.TextField()),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "risk_level",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                        default="medium",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Onay Bekliyor"),
                            ("approved", "Onaylandı"),
                            ("rejected", "Reddedildi"),
                            ("executed", "İşleme Alındı"),
                            ("failed", "Hatalı"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("email", "Email"),
                            ("stock", "Stok"),
                            ("purchase", "Satınalma"),
                            ("finance", "Finans"),
                            ("manual", "Manuel"),
                        ],
                        max_length=30,
                    ),
                ),
                ("approved_by", models.CharField(blank=True, max_length=150, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_by", models.CharField(blank=True, max_length=150, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("reject_reason", models.TextField(blank=True, null=True)),
                ("executed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "approval_requests",
                "ordering": ["-created_at"],
            },
        ),
    ]
