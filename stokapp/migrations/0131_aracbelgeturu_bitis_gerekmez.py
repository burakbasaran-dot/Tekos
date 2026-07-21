from django.db import migrations, models


def set_bitis_tarihi_gerekmez(apps, schema_editor):
    AracBelgeTuru = apps.get_model("stokapp", "AracBelgeTuru")
    AracBelgesi = apps.get_model("stokapp", "AracBelgesi")

    AracBelgeTuru.objects.filter(kod="HASAR").update(bitis_tarihi_gerekmez=True)

    for tur in AracBelgeTuru.objects.all():
        if "tescil" in tur.ad.lower():
            tur.bitis_tarihi_gerekmez = True
            tur.save(update_fields=["bitis_tarihi_gerekmez"])

    for belge in AracBelgesi.objects.all():
        if AracBelgeTuru.objects.filter(kod=belge.belge_turu, bitis_tarihi_gerekmez=True).exists():
            if belge.gecerlilik_bitis:
                belge.gecerlilik_bitis = None
                belge.save(update_fields=["gecerlilik_bitis"])


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0130_aracbelgesi_bitis_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="aracbelgeturu",
            name="bitis_tarihi_gerekmez",
            field=models.BooleanField(
                default=False,
                help_text="Hasar tutanağı, araç tescil belgesi gibi süresiz belgeler için.",
                verbose_name="Bitiş Tarihi Gerekmez",
            ),
        ),
        migrations.RunPython(set_bitis_tarihi_gerekmez, migrations.RunPython.noop),
    ]
