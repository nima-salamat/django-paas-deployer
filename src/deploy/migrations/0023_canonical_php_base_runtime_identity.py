from django.db import migrations


LEGACY_VARIANTS = {"apache-root", "apache-public"}


def forwards(apps, schema_editor):
    BaseRuntimeImage = apps.get_model("deploy", "BaseRuntimeImage")
    BaseRuntimeImageLease = apps.get_model("deploy", "BaseRuntimeImageLease")

    legacy_rows = BaseRuntimeImage.objects.filter(
        logical_runtime="php", variant__in=LEGACY_VARIANTS
    ).order_by("created_at", "pk")

    for legacy in legacy_rows:
        legacy_variant = legacy.variant
        legacy_image_ref = legacy.image_ref
        canonical = BaseRuntimeImage.objects.filter(
            logical_runtime="php",
            runtime_version=legacy.runtime_version,
            variant="apache",
            architecture=legacy.architecture,
            docker_host=legacy.docker_host,
        ).first()

        active_leases = BaseRuntimeImageLease.objects.filter(
            base_image_id=legacy.pk, released_at__isnull=True
        ).exists()
        active_build = bool(legacy.status == "building" or legacy.build_task_id)

        if canonical is None and not active_leases and not active_build:
            # Convert an inactive legacy row in place. The old Docker image is
            # deliberately not removed: it may still be referenced outside the
            # registry and fingerprint is cleared so it cannot be adopted as the
            # canonical definition without rebuilding/verification.
            legacy.variant = "apache"
            legacy.image_repository = "paas-base/php-apache"
            legacy.image_ref = f"{legacy.image_repository}:{legacy.image_tag}"
            legacy.definition_fingerprint = ""
            legacy.status = "pending"
            legacy.image_id = ""
            legacy.image_digest = ""
            legacy.rebuild_requested = False
            legacy.rebuild_requested_at = None
            legacy.last_error = "Legacy PHP base identity normalized to canonical apache variant; rebuild required."
            legacy.last_error_details = {
                "stage": "base_image",
                "legacy_variant": legacy_variant,
                "migration": "0023_canonical_php_base_runtime_identity",
                "docker_image_preserved": True,
            }
            legacy.save(update_fields=[
                "variant", "image_repository", "image_ref",
                "definition_fingerprint", "status", "image_id",
                "image_digest", "rebuild_requested", "rebuild_requested_at",
                "last_error", "last_error_details", "updated_at",
            ])
            continue

        if canonical is None:
            # An active build/lease cannot safely be moved while an older worker
            # may still publish the legacy image. Create a separate canonical
            # pending row so all new deployments use the stable name.
            canonical = BaseRuntimeImage.objects.create(
                logical_runtime="php",
                runtime_version=legacy.runtime_version,
                variant="apache",
                architecture=legacy.architecture,
                docker_host=legacy.docker_host,
                source_image=f"{legacy.source_image}",
                image_repository="paas-base/php-apache",
                image_tag=legacy.image_tag,
                image_ref=f"paas-base/php-apache:{legacy.image_tag}",
                status="pending",
                enabled=True,
                auto_build=legacy.auto_build,
                definition_fingerprint="",
                last_error_details={
                    "stage": "base_image",
                    "supersedes_legacy_identity": legacy.image_ref,
                    "migration": "0023_canonical_php_base_runtime_identity",
                },
            )

        # Never retarget active leases to a differently named Docker image.
        # The legacy row remains the compatibility owner until those leases
        # are released. New deployments resolve the canonical row.
        if not active_leases and not active_build:
            legacy.status = "disabled"
            legacy.enabled = False
            legacy.rebuild_requested = False
            legacy.last_error = f"Legacy PHP base identity superseded by {canonical.image_ref}."
            legacy.last_error_details = {
                "stage": "base_image",
                "superseded_by": canonical.image_ref,
                "legacy_image_ref": legacy_image_ref,
                "safe_to_remove_after_release": True,
                "migration": "0023_canonical_php_base_runtime_identity",
            }
            legacy.save(update_fields=[
                "status", "enabled", "rebuild_requested", "last_error",
                "last_error_details", "updated_at",
            ])


def backwards(apps, schema_editor):
    # Intentionally a no-op. Reintroducing legacy identities can recreate
    # duplicate Docker names and would be unsafe for active deployments.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0022_deploy_base_image_phase_timestamps"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]