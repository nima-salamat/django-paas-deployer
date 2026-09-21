from django.db import migrations, models

import services.models


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
                upload_to=services.models.revision_artifact_path,
            ),
        ),
    ]
