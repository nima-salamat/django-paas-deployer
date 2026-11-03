from django.db import migrations, models
import django.db.models.deletion


def backfill_deployment_intent(apps, schema_editor):
    Deploy = apps.get_model("deploy", "Deploy")
    alias = schema_editor.connection.alias
    batch = []
    for deploy in (
        Deploy.objects.using(alias)
        .select_related("service")
        .only(
            "pk",
            "expected_lifecycle_generation",
            "expected_active_revision_id",
            "service__lifecycle_generation",
            "service__active_revision_id",
        )
        .iterator(chunk_size=500)
    ):
        service = deploy.service
        deploy.expected_lifecycle_generation = int(
            getattr(service, "lifecycle_generation", 0) or 0
        )
        deploy.expected_active_revision_id = str(
            getattr(service, "active_revision_id", "") or ""
        )
        batch.append(deploy)
        if len(batch) >= 500:
            Deploy.objects.using(alias).bulk_update(
                batch,
                ["expected_lifecycle_generation", "expected_active_revision_id"],
                batch_size=500,
            )
            batch.clear()
    if batch:
        Deploy.objects.using(alias).bulk_update(
            batch,
            ["expected_lifecycle_generation", "expected_active_revision_id"],
            batch_size=500,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0032_release_and_build_artifact"),
        ("services", "0031_service_process_replicas"),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="expected_lifecycle_generation",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Lifecycle generation captured when this deployment intent was queued.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="deploy",
            name="expected_active_revision_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Active revision observed when this deployment intent was queued.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="deploy",
            name="worker_recovery_attempts",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Bounded number of same-task recoveries after a lost Celery worker process.",
            ),
        ),
        migrations.RunPython(backfill_deployment_intent, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="deploymenteventoutbox",
            name="deployment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="event_outbox",
                to="deploy.deploy",
            ),
        ),
    ]
