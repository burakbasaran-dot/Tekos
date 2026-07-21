from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0062_uretimemri_production_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonelIzin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("izin_tipi", models.CharField(choices=[("YILLIK", "Yıllık İzin"), ("RAPOR", "Raporlu"), ("MAZERET", "Mazeret İzni"), ("DIGER", "Diğer")], default="DIGER", max_length=15, verbose_name="İzin Tipi")),
                ("baslangic_zamani", models.DateTimeField(verbose_name="Başlangıç Tarih/Saat")),
                ("bitis_zamani", models.DateTimeField(verbose_name="Bitiş Tarih/Saat")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("personel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="izin_kayitlari", to="stokapp.personel", verbose_name="Personel")),
            ],
            options={
                "verbose_name": "Personel İzin",
                "verbose_name_plural": "Personel İzinleri",
                "ordering": ["-baslangic_zamani", "personel"],
            },
        ),
    ]
