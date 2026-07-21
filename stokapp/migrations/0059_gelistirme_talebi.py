from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0058_uretim_asamasi_planlama"),
    ]

    operations = [
        migrations.CreateModel(
            name="GelistirmeTalebi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslik", models.CharField(max_length=200, verbose_name="Başlık")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("durum", models.CharField(choices=[("ACIK", "Açık"), ("TAMAMLANDI", "Tamamlandı")], default="ACIK", max_length=20, verbose_name="Durum")),
                ("tamamlanma_zamani", models.DateTimeField(blank=True, null=True, verbose_name="Tamamlanma Zamanı")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")),
            ],
            options={
                "verbose_name": "Geliştirme Talebi",
                "verbose_name_plural": "Geliştirme Talepleri",
                "ordering": ["-created_at"],
            },
        ),
    ]
