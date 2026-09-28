from django.core import validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_alter_coresettings_build_max_cpu_and_base_timeout"),
    ]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="volume_release_retention_days",
            field=models.PositiveIntegerField(
                default=30,
                validators=[
                    validators.MinValueValidator(1),
                    validators.MaxValueValidator(3650),
                ],
                verbose_name="Released volume retention (days)",
                help_text=(
                    "How long released volume data remains physically retained after "
                    "logical Service quota is freed. Expired released volumes are reclaimed automatically."
                ),
            ),
        ),
    ]
