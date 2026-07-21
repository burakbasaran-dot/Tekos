from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0057_document_documenttype_documentreminder_document_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="uretimasamasi",
            name="atanan_personel",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uretim_asamalari", to="stokapp.personel", verbose_name="Atanan Personel"),
        ),
        migrations.AddField(
            model_name="uretimasamasi",
            name="planlanan_baslama",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Planlanan Başlama"),
        ),
        migrations.AddField(
            model_name="uretimasamasi",
            name="planlanan_bitis",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Planlanan Bitiş"),
        ),
    ]
