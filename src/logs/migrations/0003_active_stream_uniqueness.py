from django.db import migrations, models
from django.utils import timezone


def collapse_duplicate_active_streams(apps, schema_editor):
    Stream = apps.get_model("logs", "ServiceLogStream")
    alias = schema_editor.connection.alias
    seen = set()
    qs = (
        Stream.objects.using(alias)
        .filter(status="active")
        .order_by("service_id", "container_id", "pk")
    )
    for stream in qs.iterator():
        key = (str(stream.service_id), stream.container_id)
        if key in seen:
            Stream.objects.using(alias).filter(pk=stream.pk).update(
                status="lost",
                ended_at=timezone.now(),
                owner_id="",
                lease_until=None,
                lease_token="",
                heartbeat_at=None,
            )
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("logs", "0002_alter_servicelogentry_stream_and_more"),
    ]

    operations = [
        migrations.RunPython(
            collapse_duplicate_active_streams,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="servicelogstream",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="active"),
                fields=("service_id", "container_id"),
                name="uniq_active_log_stream_service_container",
            ),
        ),
    ]
