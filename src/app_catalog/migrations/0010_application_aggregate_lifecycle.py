# Generated for the Ready App aggregate lifecycle states.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_catalog", "0009_catalogpublication"),
    ]

    operations = [
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
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
