from django.db import migrations
from django.utils import timezone


LEGACY_PHP_VARIANTS = {"apache-root", "apache-public"}
ACTIVE_DEPLOY_STATUSES = {"pending", "running", "rolling_back", "succeeded"}


def _deployment_references_image(config, image_ref):
    if not isinstance(config, dict):
        return False
    bases = config.get("base_images")
    if isinstance(bases, dict) and image_ref in {str(v) for v in bases.values()}:
        return True
    return False


def _row_is_referenced(row, Deploy, Lease):
    if Lease.objects.filter(base_image_id=row.pk, released_at__isnull=True).exists():
        return True
    for deploy in Deploy.objects.filter(status__in=ACTIVE_DEPLOY_STATUSES).only("config", "service_id").iterator():
        if _deployment_references_image(deploy.config, row.image_ref):
            return True
    return False


def forwards(apps, schema_editor):
    BaseRuntimeImage = apps.get_model("deploy", "BaseRuntimeImage")
    Deploy = apps.get_model("deploy", "Deploy")
    Lease = apps.get_model("deploy", "BaseRuntimeImageLease")
    now = timezone.now()
    legacy_rows = BaseRuntimeImage.objects.filter(
        logical_runtime="php",
        variant__in=LEGACY_PHP_VARIANTS,
    ).order_by("docker_host", "runtime_version", "variant", "created_at")

    for row in legacy_rows.iterator():
        # A running builder owns its historical definition. Never rewrite its
        # identity or Docker tag in-place while the task is active.
        if row.status == "building":
            continue
        if _row_is_referenced(row, Deploy, Lease):
            continue

        canonical = BaseRuntimeImage.objects.filter(
            logical_runtime="php",
            runtime_version=row.runtime_version,
            variant="apache",
            architecture=row.architecture,
            docker_host=row.docker_host,
        ).first()
        if canonical is not None:
            row.status = "disabled"
            row.enabled = False
            row.rebuild_requested = False
            row.last_error = "Superseded by the canonical php/apache base runtime identity."
            row.last_error_details = {
                "stage": "base_image_migration",
                "superseded_by": canonical.image_ref,
                "legacy_variant": row.variant,
                "safe_to_remove": True,
            }
            row.save(update_fields=[
                "status", "enabled", "rebuild_requested", "last_error",
                "last_error_details", "updated_at",
            ])
            continue

        legacy_variant = row.variant
        old_ref = row.image_ref
        row.variant = "apache"
        row.source_image = f"docker.io/php:{row.runtime_version}-apache"
        row.image_repository = "paas-base/php-apache"
        row.image_tag = row.image_tag or f"{row.runtime_version}-r1"
        row.image_ref = f"paas-base/php-apache:{row.image_tag}"
        row.status = "pending"
        row.enabled = True
        row.rebuild_requested = True
        row.rebuild_requested_at = now
        row.image_id = ""
        row.image_digest = ""
        row.definition_fingerprint = ""
        row.build_task_id = ""
        row.build_owner_deployment_id = ""
        row.build_started_at = None
        row.build_completed_at = None
        row.last_error = "Migrated from a legacy PHP base-image identity; canonical definition must be rebuilt."
        row.last_error_details = {
            "stage": "base_image_migration",
            "migrated_from": old_ref,
            "legacy_variant": legacy_variant,
            "rebuild_required": True,
            "safe_to_remove": True,
        }
        row.save()


def backwards(apps, schema_editor):
    # Identity migration is intentionally one-way. Reversing it could create
    # a second PHP identity pointing at an incompatible Dockerfile definition.
    return None


class Migration(migrations.Migration):
    dependencies = [("deploy", "0021_base_runtime_definition_and_error_details")]
    operations = [migrations.RunPython(forwards, backwards)]