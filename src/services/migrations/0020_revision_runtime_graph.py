from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0019_service_configuration_domains"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerevision",
            name="secret_refs",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="source_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="build_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="runtime_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="environment_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="endpoint_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="volume_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="network_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="servicerevision",
            name="graph_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
