from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0129_aracbelgesi_arsiv"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aracbelgesi",
            name="gecerlilik_bitis",
            field=models.DateField(blank=True, null=True, verbose_name="Geçerlilik Bitiş Tarihi"),
        ),
    ]
