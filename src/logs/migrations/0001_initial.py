
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ServiceLogStream",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("service_id", models.UUIDField(db_index=True)),
                ("deploy_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("container_id", models.CharField(db_index=True, max_length=128)),
                ("container_name", models.CharField(blank=True, default="", max_length=255)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(db_index=True, default="active", max_length=16)),
                ("last_persisted_ts", models.DateTimeField(blank=True, null=True)),
                ("last_persisted_fingerprint", models.CharField(blank=True, default="", max_length=64)),
                ("last_seq", models.BigIntegerField(default=0)),
                ("owner_id", models.CharField(blank=True, default="", max_length=64)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.CharField(blank=True, default="", max_length=64)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ServiceLogEntry",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("service_id", models.UUIDField(db_index=True)),
                ("stream_id", models.BigIntegerField(db_index=True)),
                ("deploy_id", models.UUIDField(blank=True, null=True)),
                ("ts", models.DateTimeField(db_index=True)),
                ("seq", models.BigIntegerField()),
                ("stream", models.CharField(default="stdout", max_length=8)),
                ("level", models.CharField(blank=True, db_index=True, default="", max_length=16)),
                ("message", models.TextField()),
                ("byte_size", models.PositiveIntegerField(default=0)),
                ("truncated", models.BooleanField(default=False)),
                ("fingerprint", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="ServiceLogUsage",
            fields=[
                ("service_id", models.UUIDField(primary_key=True, serialize=False)),
                ("current_storage_bytes", models.BigIntegerField(default=0)),
                ("entry_count", models.BigIntegerField(default=0)),
                ("entries_dropped", models.BigIntegerField(default=0)),
                ("bytes_dropped", models.BigIntegerField(default=0)),
                ("last_ingestion_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="LogUsageDaily",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("service_id", models.UUIDField(db_index=True)),
                ("date", models.DateField(db_index=True)),
                ("bytes_ingested", models.BigIntegerField(default=0)),
                ("entries_ingested", models.BigIntegerField(default=0)),
                ("bytes_deleted", models.BigIntegerField(default=0)),
                ("entries_deleted", models.BigIntegerField(default=0)),
                ("entries_dropped", models.BigIntegerField(default=0)),
                ("bytes_dropped", models.BigIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="CollectorHeartbeat",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("instance_id", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(default="healthy", max_length=32)),
                ("last_heartbeat", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_successful_ingestion", models.DateTimeField(blank=True, null=True)),
                ("active_streams", models.PositiveIntegerField(default=0)),
                ("active_containers", models.PositiveIntegerField(default=0)),
                ("buffer_bytes", models.BigIntegerField(default=0)),
                ("dropped_entries", models.BigIntegerField(default=0)),
                ("dropped_bytes", models.BigIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("db_ok", models.BooleanField(default=True)),
                ("redis_ok", models.BooleanField(default=True)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="servicelogentry",
            constraint=models.UniqueConstraint(fields=("stream_id", "seq"), name="uniq_log_stream_seq"),
        ),
        migrations.AddIndex(
            model_name="servicelogentry",
            index=models.Index(fields=["service_id", "-ts", "-seq"], name="svc_log_ts_seq_idx"),
        ),
        migrations.AddConstraint(
            model_name="logusagedaily",
            constraint=models.UniqueConstraint(fields=("service_id", "date"), name="uniq_log_usage_daily"),
        ),
    ]
