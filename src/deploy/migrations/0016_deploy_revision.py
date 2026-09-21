from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0015_deploy_recovery_operation"),
        ("services", "0017_service_process_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="deployments",
                to="services.servicerevision",
            ),
        ),
    ]
