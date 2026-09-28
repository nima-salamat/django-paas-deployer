from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_coresettings_base_image_timeout"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coresettings",
            name="build_max_cpu",
            field=models.FloatField(
                default=1.0,
                help_text="Operator-only relative Docker CPU scheduling weight. This is not a hard CPU quota.",
                verbose_name="Build CPU shares weight",
            ),
        ),
        migrations.AlterField(
            model_name="coresettings",
            name="monitor_stale_base_build_minutes",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Shared timeout for deployment waiting and monitor recovery of base-image builds.",
                verbose_name="Base-image build lifecycle timeout (minutes)",
            ),
        ),
    ]