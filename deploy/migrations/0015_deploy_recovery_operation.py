from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0014_deploy_execution_ownership"),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="operation",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="deploy",
            name="operation_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deploy",
            name="operation_resource_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="deploy",
            name="operation_previous_resource_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="deploy",
            name="recovery_metadata",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
