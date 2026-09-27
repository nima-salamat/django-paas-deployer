from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0013_base_runtime_build_owner")]

    operations = [
        migrations.AddField(
            model_name="baseruntimeimage",
            name="definition_fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="baseruntimeimage",
            name="last_error_details",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
