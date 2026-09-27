from django.core import validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0011_merge_storage_settings_leaves")]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="base_image_build_timeout_minutes",
            field=models.PositiveIntegerField(
                default=10,
                validators=[validators.MinValueValidator(1), validators.MaxValueValidator(1440)],
                verbose_name="Base image build/wait timeout (minutes)",
                help_text=(
                    "Dedicated lifecycle budget for a base-image build or shared wait. "
                    "It is separate from the application deployment timeout."
                ),
            ),
        ),
    ]