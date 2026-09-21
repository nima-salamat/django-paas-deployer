from django.db import migrations, models

def revision_artifact_path(instance, filename):
    service_id = getattr(instance, "service_id", None) or "unknown"
    revision = getattr(instance, "revision_number", None) or "pending"
    safe = str(filename).replace("\\", "/").split("/")[-1]
    return f"service-revisions/{service_id}/r{revision}/{safe}"


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0021_service_port_reservation"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerevision",
            name="artifact_file",
            field=models.FileField(
                blank=True,
                help_text="Immutable source artifact captured for this revision.",
                null=True,
                upload_to=revision_artifact_path,
            ),
        ),
    ]
