from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_merge_core_settings_shell")]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="volume_usage_warning_percent",
            field=models.FloatField(
                default=90.0,
                verbose_name="Volume usage warning threshold (%)",
                help_text=(
                    "Warn users when actual Docker volume usage reaches this "
                    "percentage of declared logical capacity."
                ),
            ),
        ),
    ]