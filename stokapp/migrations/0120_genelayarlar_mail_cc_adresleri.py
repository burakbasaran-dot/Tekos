from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0119_teklif_siparis_mektubu_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="genelayarlar",
            name="musteri_mail_cc_adresi",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Teklif ve sipariş onay e-postalarında otomatik CC adresi.",
                max_length=254,
                verbose_name="Müşteri gönderimleri CC adresi",
            ),
        ),
        migrations.AddField(
            model_name="genelayarlar",
            name="satinalma_mail_cc_adresi",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Tedarikçi teklif/sipariş/RFQ e-postalarında otomatik CC adresi.",
                max_length=254,
                verbose_name="Satınalma gönderimleri CC adresi",
            ),
        ),
    ]
