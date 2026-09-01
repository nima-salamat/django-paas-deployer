from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_core_settings")]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="auto_public_url_handling",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, app deployments receive a secure public URL/asset URL default behind the platform proxy. Disable to let the application manage its own URL scheme/path.",
                verbose_name="Automatic public/asset URL handling",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="default_public_url_prefix",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional operator default for public URL generation. Tenant custom values can override only when explicitly requested.",
                max_length=500,
                verbose_name="Default public URL prefix",
            ),
        ),
    ]
