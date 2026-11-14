"""Repair deployment-intent columns even on databases that recorded 0035 early.

0035 repairs partial runs of migration 0033. Some installations may already
have recorded 0035 as applied while the physical Deploy table still lacks
columns (for example after a manual restore or an interrupted schema repair).
This follow-up is deliberately idempotent and checks the actual table before
adding each column.
"""

from django.db import migrations
from django.db.models import Q


FIELD_NAMES = (
    "expected_lifecycle_generation",
    "expected_active_revision_id",
    "worker_recovery_attempts",
)


def repair_deploy_intent_schema_drift(apps, schema_editor):
    Deploy = apps.get_model("deploy", "Deploy")
    connection = schema_editor.connection
    alias = connection.alias
    table_name = Deploy._meta.db_table

    with connection.cursor() as cursor:
        existing = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    # Django's migration state already contains these fields via 0033.
    # Repair only the physical schema; do not mutate migration state again.
    for name in FIELD_NAMES:
        if name not in existing:
            schema_editor.add_field(Deploy, Deploy._meta.get_field(name))
            existing.add(name)

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
        ("deploy", "0035_repair_missing_deploy_intent_columns"),
    ]

    operations = [
        migrations.RunPython(
            repair_deploy_intent_schema_drift,
            migrations.RunPython.noop,
        ),
    ]
