import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0007_deploymentstatus_cancelled")]

    operations = [
        migrations.AlterField(
            model_name="deploylog",
            name="deploy",
            field=models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="deploy.deploy", verbose_name="Deploy"),
        ),
        migrations.AlterField(
            model_name="deploylog",
            name="service",
            field=models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name="deployment_logs", to="services.service", verbose_name="Service"),
        ),
        migrations.AddField(model_name="deploylog", name="event_type", field=models.CharField(default="deployment.event", max_length=96, verbose_name="Event Type")),
        migrations.AddField(model_name="deploylog", name="exception_type", field=models.CharField(blank=True, default="", max_length=128, verbose_name="Exception Type")),
        migrations.AddField(model_name="deploylog", name="traceback", field=models.TextField(blank=True, default="", verbose_name="Traceback")),
    ]
