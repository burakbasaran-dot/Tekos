# Generated manually for KurulumDosyasi CNC ekipman M2M and Istasyon CNC grubu

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0098_remove_cncekipman_kurulum_m2m"),
    ]

    operations = [
        migrations.AddField(
            model_name="istasyon",
            name="cnc_makine_grubu",
            field=models.CharField(
                blank=True,
                choices=[
                    (
                        "",
                        "Belirtilmedi (kurulumda yalnızca ortak CNC ekipmanları)",
                    ),
                    ("cnc_lathe", "CNC Torna"),
                    ("cnc_mill", "CNC Freze"),
                ],
                default="",
                help_text="Kurulum dosyasında bu istasyon için torna veya freze ekipmanları ile birlikte ortak ekipmanlar listelenir. Boş bırakılırsa yalnızca ortak CNC ekipmanları seçilebilir.",
                max_length=20,
                verbose_name="CNC makine grubu",
            ),
        ),
        migrations.AddField(
            model_name="kurulumdosyasi",
            name="cnc_ekipmanlar",
            field=models.ManyToManyField(
                blank=True,
                help_text="Bu kurulum için kullanılacak CNC aparat / yardımcı ekipmanlar (istasyon ve ortak listeye göre filtrelenir).",
                related_name="kurulum_dosyalari",
                to="stokapp.cncekipman",
                verbose_name="CNC ekipmanları",
            ),
        ),
    ]
