"""Repair deployment-intent columns if an earlier migration was recorded prematurely.

Migration 0033 owns these fields in Django's migration state. This database-only
repair handles installations where the migration recorder says 0033 ran but
one or more columns are absent from the physical Deploy table.
"""

from django.db import migrations
from django.db.models import Q


DEPLOYMENT_INTENT_FIELDS = (
    "expected_lifecycle_generation",
    "expected_active_revision_id",
    "worker_recovery_attempts",
)


def repair_missing_deploy_intent_columns(apps, schema_editor):
    Deploy = apps.get_model("deploy", "Deploy")
    connection = schema_editor.connection
    alias = connection.alias
    table_name = Deploy._meta.db_table

    with connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    # Keep Django's migration state unchanged: 0033 already declares these
    # fields. Only repair the physical database schema when it has drifted.
    for field_name in DEPLOYMENT_INTENT_FIELDS:
        if field_name in existing_columns:
            continue
        schema_editor.add_field(Deploy, Deploy._meta.get_field(field_name))
        existing_columns.add(field_name)

    # 0033 normally backfills these values. Repeat only the missing-value part
    # so rows are safe even when 0033 was marked applied after a partial run.
    pending = (
        Deploy.objects.using(alias)
        .filter(
            Q(expected_lifecycle_generation__isnull=True)
            | Q(expected_active_revision_id="")
        )
        .select_related("service")
        .only(
            "pk",
            "expected_lifecycle_generation",
            "expected_active_revision_id",
            "service__lifecycle_generation",
            "service__active_revision_id",
        )
    )

    batch = []
    for deploy in pending.iterator(chunk_size=500):
        service = deploy.service
        if deploy.expected_lifecycle_generation is None:
            deploy.expected_lifecycle_generation = int(
                getattr(service, "lifecycle_generation", 0) or 0
            )
        if not deploy.expected_active_revision_id:
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
        ("deploy", "0034_alter_buildartifact_created_at_and_more"),
    ]

    operations = [
        migrations.RunPython(
            repair_missing_deploy_intent_columns,
            migrations.RunPython.noop,
        ),
    ]
