from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_core_settings"),
    ]

    operations = [
        migrations.AddField(model_name="coresettings", name="build_parallelism", field=models.PositiveSmallIntegerField(default=1, verbose_name="Maximum concurrent Docker builds", help_text="Global build concurrency across workers.")),
        migrations.AddField(model_name="coresettings", name="build_wait_minutes", field=models.PositiveSmallIntegerField(default=5, verbose_name="Build slot wait timeout (minutes)", help_text="Maximum time a deployment waits for a Docker build slot.")),
        migrations.AddField(model_name="coresettings", name="build_max_cpu", field=models.FloatField(default=1.0, verbose_name="Maximum build CPU", help_text="Operator-only Docker build CPU ceiling.")),
        migrations.AddField(model_name="coresettings", name="build_max_ram_mb", field=models.PositiveIntegerField(default=1024, verbose_name="Maximum build RAM (MB)", help_text="Operator-only Docker build memory ceiling.")),
        migrations.AddField(model_name="coresettings", name="build_slot_lease_seconds", field=models.PositiveIntegerField(default=900, verbose_name="Build slot lease (seconds)", help_text="Lease duration used to recover abandoned build slots.")),
        migrations.AddField(model_name="coresettings", name="deploy_timeout_minutes", field=models.PositiveIntegerField(default=10, verbose_name="Deployment timeout (minutes)", help_text="Maximum time for an active deployment pipeline.")),
        migrations.AddField(model_name="coresettings", name="queued_timeout_minutes", field=models.PositiveIntegerField(default=10, verbose_name="Queued/deploying timeout (minutes)", help_text="Maximum time a service may remain queued or deploying.")),
        migrations.AddField(model_name="coresettings", name="stop_timeout_minutes", field=models.PositiveIntegerField(default=5, verbose_name="Stop timeout (minutes)", help_text="Maximum time allowed for an intentional service stop.")),
        migrations.AddField(model_name="coresettings", name="unexpected_death_grace_seconds", field=models.PositiveIntegerField(default=15, verbose_name="Unexpected container death grace (seconds)")),
        migrations.AddField(model_name="coresettings", name="monitor_enabled", field=models.BooleanField(default=True, verbose_name="Enable deployment monitor", help_text="Run automatic reconciliation and recovery.")),
        migrations.AddField(model_name="coresettings", name="monitor_interval_seconds", field=models.PositiveIntegerField(default=30, verbose_name="Monitor interval (seconds)", help_text="Actual monitor cadence. Celery Beat provides a lightweight pulse.")),
        migrations.AddField(model_name="coresettings", name="monitor_batch_size", field=models.PositiveIntegerField(default=100, verbose_name="Monitor batch size", help_text="Maximum deployments/services inspected per monitor tick.")),
        migrations.AddField(model_name="coresettings", name="monitor_recovery_enabled", field=models.BooleanField(default=True, verbose_name="Enable automatic recovery")),
        migrations.AddField(model_name="coresettings", name="monitor_max_recovery_attempts", field=models.PositiveSmallIntegerField(default=3, verbose_name="Maximum recovery attempts")),
        migrations.AddField(model_name="coresettings", name="monitor_stale_base_build_minutes", field=models.PositiveIntegerField(default=30, verbose_name="Stale base build timeout (minutes)")),
        migrations.AddField(model_name="coresettings", name="monitor_stale_worker_seconds", field=models.PositiveIntegerField(default=90, verbose_name="Stale worker heartbeat (seconds)")),
        migrations.AddField(model_name="coresettings", name="monitor_scheduler_lock_seconds", field=models.PositiveIntegerField(default=20, verbose_name="Monitor scheduler lock (seconds)")),
    ]
