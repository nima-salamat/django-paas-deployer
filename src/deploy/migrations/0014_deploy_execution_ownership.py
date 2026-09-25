from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0013_base_runtime_build_owner"),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="execution_task_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Celery task currently owning this deployment execution.",
                max_length=64,
                verbose_name="Execution Task ID",
            ),
        ),
        migrations.AddField(
            model_name="deploy",
            name="worker_heartbeat_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Last heartbeat from the worker that owns this deployment.",
                null=True,
                verbose_name="Worker Heartbeat",
            ),
        ),
        migrations.AddField(
            model_name="deploy",
            name="previous_deploy",
            field=models.ForeignKey(
                blank=True,
                help_text="Previously active deployment replaced by this deployment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replacement_deployments",
                to="deploy.deploy",
            ),
        ),
    ]
