# Generated manually for StokSayimi HAZIR status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0132_genelayarlar_mail_ayarlari"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stoksayimi",
            name="durum",
            field=models.CharField(
                choices=[
                    ("HAZIR", "Oluşturuldu"),
                    ("DEVAM", "Devam ediyor"),
                    ("TAMAMLANDI", "Tamamlandı"),
                    ("IPTAL", "İptal"),
                ],
                default="HAZIR",
                max_length=15,
                verbose_name="Durum",
            ),
        ),
    ]
