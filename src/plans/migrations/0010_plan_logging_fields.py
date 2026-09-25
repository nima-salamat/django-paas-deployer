
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0005_alter_plan_max_cpu_alter_plan_max_ram"),
    ]
    operations = [
        migrations.AddField(model_name="plan", name="log_retention_days", field=models.PositiveIntegerField(blank=True, help_text="Null inherits platform default.", null=True, verbose_name="Log retention (days)")),
        migrations.AddField(model_name="plan", name="log_storage_mb", field=models.PositiveIntegerField(blank=True, help_text="Per-service persistent log storage. Null inherits platform default.", null=True, verbose_name="Log storage quota (MB)")),
        migrations.AddField(model_name="plan", name="log_ingest_bytes_per_sec", field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Log ingest limit (bytes/sec)")),
        migrations.AddField(model_name="plan", name="persistent_logging", field=models.BooleanField(blank=True, help_text="Null inherits platform default.", null=True, verbose_name="Persistent logging")),
        migrations.AddField(model_name="plan", name="realtime_logging", field=models.BooleanField(blank=True, null=True, verbose_name="Realtime logging")),
        migrations.AddField(model_name="plan", name="log_quota_behavior", field=models.CharField(blank=True, default="", help_text="fifo_delete | drop_new | realtime_only; blank inherits platform.", max_length=32, verbose_name="Log quota behavior")),
    ]
