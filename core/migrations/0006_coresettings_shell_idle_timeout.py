from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0005_merge_core_settings")]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="shell_idle_timeout_minutes",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Close inactive shell sessions after this many minutes. Commands and file operations refresh activity.",
                verbose_name="Restricted shell idle timeout (minutes)",
            ),
        ),
    ]
