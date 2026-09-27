from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0020_deploy_operation_and_more"),
    ]

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
