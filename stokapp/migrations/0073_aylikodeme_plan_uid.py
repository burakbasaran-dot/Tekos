# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0072_gayrimenkul_modulu"),
    ]

    operations = [
        migrations.AddField(
            model_name="aylikodeme",
            name="plan_uid",
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text="Aynı taksit planındaki kayıtlar bu kimlik ile gruplanır.",
                null=True,
                verbose_name="Tekrar planı kimliği",
            ),
        ),
    ]
