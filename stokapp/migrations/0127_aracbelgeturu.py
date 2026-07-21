from django.db import migrations, models


def seed_arac_belge_turleri(apps, schema_editor):
    AracBelgeTuru = apps.get_model("stokapp", "AracBelgeTuru")
    defaults = [
        ("TUVTURK", "TÜVTÜRK Muayene"),
        ("EGZOZ", "Egzoz Emisyon"),
        ("TRAFIK_SIGORTA", "Zorunlu Trafik Sigortası"),
        ("KASKO", "Kasko"),
        ("MTV", "MTV Ödeme"),
        ("SRC", "SRC Belgesi"),
        ("PSIKOTEKNIK", "Psikoteknik Belgesi"),
        ("K_BELGESI", "K Belgesi"),
        ("SERVIS", "Servis Formu"),
        ("HASAR", "Hasar Tutanağı"),
    ]
    for sira, (kod, ad) in enumerate(defaults, start=1):
        AracBelgeTuru.objects.get_or_create(kod=kod, defaults={"ad": ad, "sira": sira, "aktif": True})


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0126_stokhareketi_uretim_iade"),
    ]

    operations = [
        migrations.CreateModel(
            name="AracBelgeTuru",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kod", models.CharField(max_length=20, unique=True, verbose_name="Kod")),
                ("ad", models.CharField(max_length=120, verbose_name="Ad")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Araç Belge Türü",
                "verbose_name_plural": "Araç Belge Türleri",
                "ordering": ["sira", "ad"],
            },
        ),
        migrations.AlterField(
            model_name="aracbelgesi",
            name="belge_turu",
            field=models.CharField(max_length=20, verbose_name="Belge Türü"),
        ),
        migrations.RunPython(seed_arac_belge_turleri, migrations.RunPython.noop),
    ]
