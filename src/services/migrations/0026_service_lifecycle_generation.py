from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0025_service_process_replica_minimum"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="lifecycle_generation",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Monotonic fence for desired_state. Incremented on every lifecycle "
                    "intent (deploy/stop/delete). Stale workers must not overwrite a newer intent."
                ),
                verbose_name="Lifecycle Generation",
            ),
        ),
    ]
