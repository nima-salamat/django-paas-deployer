from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        # Apply the aggregate lifecycle choices before adding runtime-operation
        # fields and the final ``stopping`` status choice. This keeps one
        # linear migration leaf instead of creating a conflicting 0010 branch.
        ("app_catalog", "0010_application_aggregate_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="applicationinstance",
            name="runtime_operation",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="runtime_operation_generation",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="applicationinstance",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("deploying", "Deploying"),
                    ("running", "Running"),
                    ("degraded", "Degraded"),
                    ("stopped", "Stopped"),
                    ("stopping", "Stopping"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
