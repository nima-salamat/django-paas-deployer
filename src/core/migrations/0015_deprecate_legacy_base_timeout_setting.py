from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_coresettings_volume_release_retention"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coresettings",
            name="monitor_stale_base_build_minutes",
            field=models.PositiveIntegerField(
                default=30,
                help_text=(
                    "Deprecated compatibility field. Base-image lifecycle timing is controlled "
                    "by base_image_build_timeout_minutes and this field no longer provides an independent timeout."
                ),
                verbose_name="Legacy base-image timeout setting",
            ),
        ),
    ]
