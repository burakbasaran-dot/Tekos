from django.db import migrations, models
import django.db.models.deletion


def migrate_belge_pdf_to_dosyalar(apps, schema_editor):
    AracBelgesi = apps.get_model("stokapp", "AracBelgesi")
    AracBelgesiDosya = apps.get_model("stokapp", "AracBelgesiDosya")
    for belge in AracBelgesi.objects.exclude(belge_pdf="").exclude(belge_pdf__isnull=True):
        if belge.belge_pdf:
            AracBelgesiDosya.objects.create(belge_id=belge.pk, dosya=belge.belge_pdf)


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0127_aracbelgeturu"),
    ]

    operations = [
        migrations.CreateModel(
            name="AracBelgesiDosya",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dosya", models.FileField(upload_to="arac_belgeler/%Y/%m/%d/", verbose_name="Dosya")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "belge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dosyalar",
                        to="stokapp.aracbelgesi",
                        verbose_name="Belge",
                    ),
                ),
            ],
            options={
                "verbose_name": "Araç Belgesi Dosyası",
                "verbose_name_plural": "Araç Belgesi Dosyaları",
                "ordering": ["id"],
            },
        ),
        migrations.RunPython(migrate_belge_pdf_to_dosyalar, migrations.RunPython.noop),
    ]
