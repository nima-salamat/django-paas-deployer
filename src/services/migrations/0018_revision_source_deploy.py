from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0017_service_process_revision"),
        ("deploy", "0016_deploy_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerevision",
            name="source_deploy",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="source_revisions",
                to="deploy.deploy",
            ),
        ),
    ]
