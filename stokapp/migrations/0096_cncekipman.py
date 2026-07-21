# Generated manually for CNC ekipman kataloğu

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("stokapp", "0095_cncdosyaagaciklasor_cncprogram_dosya_konumu_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CncEkipman",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "machine_scope",
                    models.CharField(
                        choices=[
                            ("cnc_lathe", "CNC Torna"),
                            ("cnc_mill", "CNC Freze"),
                            ("cnc_common", "Ortak (Torna ve Freze)"),
                        ],
                        help_text="Yalnızca tornada, yalnızca frezede veya her iki makine grubunda kullanılabilir.",
                        max_length=20,
                        verbose_name="Kapsam",
                    ),
                ),
                (
                    "ekipman_numarasi",
                    models.CharField(blank=True, default="", max_length=100, verbose_name="Ekipman numarası"),
                ),
                ("ad", models.CharField(max_length=200, verbose_name="Ekipman adı")),
                ("marka", models.CharField(blank=True, default="", max_length=120, verbose_name="Marka")),
                (
                    "model_kodu",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Üretici model / tip kodu",
                        max_length=120,
                        verbose_name="Model",
                    ),
                ),
                (
                    "aciklama",
                    models.TextField(
                        blank=True,
                        help_text="Kullanım yeri, montaj notu veya kurulum talimatına bağlanırken kullanılacak notlar.",
                        verbose_name="Açıklama",
                    ),
                ),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("sira", models.IntegerField(default=0, verbose_name="Sıra")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Güncellenme")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cnc_ekipmanlari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "CNC ekipmanı",
                "verbose_name_plural": "CNC ekipmanları",
                "ordering": ["machine_scope", "sira", "ekipman_numarasi", "ad"],
            },
        ),
        migrations.AddIndex(
            model_name="cncekipman",
            index=models.Index(fields=["machine_scope", "aktif"], name="stokapp_cnc_machine_scope_idx"),
        ),
        migrations.AddIndex(
            model_name="cncekipman",
            index=models.Index(fields=["aktif", "sira"], name="stokapp_cnc_aktif_sira_idx"),
        ),
    ]
