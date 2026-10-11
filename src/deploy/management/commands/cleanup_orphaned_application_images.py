from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from deploy.build_cache import (
    is_platform_application_image_ref,
    release_application_image_references,
)
from deploy.models import BaseRuntimeImage, BuildCacheArtifact, Deploy
from deployments.core.manager.client_manager import get_docker_client
from deployments.core.swarm import swarm_enabled
from services.models import Service


def _image_labels(image) -> dict[str, str]:
    attrs = getattr(image, "attrs", {}) or {}
    config = attrs.get("Config") or {}
    return dict(config.get("Labels") or attrs.get("Labels") or {})


def _image_tags(image) -> set[str]:
    attrs = getattr(image, "attrs", {}) or {}
    return {
        str(ref).strip()
        for ref in (getattr(image, "tags", None) or attrs.get("RepoTags") or [])
        if str(ref).strip()
    }


def _service_image_ref(service) -> str:
    attrs = getattr(service, "attrs", {}) or {}
    spec = attrs.get("Spec") or {}
    return str(
        ((spec.get("TaskTemplate") or {}).get("ContainerSpec") or {}).get("Image")
        or ""
    ).strip()


class Command(BaseCommand):
    help = (
        "Report or remove orphaned PassDeployer application images whose owning "
        "Service row no longer exists. Safe dry-run is the default; pass --apply "
        "only after reviewing the candidates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually remove verified orphan app-* image references. Default is dry-run.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum number of candidate images to inspect (default: 500).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        limit = max(1, int(options["limit"]))
        client = get_docker_client()

        # Fail closed: no destructive cleanup if Docker runtime inventory is unavailable.
        runtime_swarm_enabled = swarm_enabled()
        try:
            images = list(client.images.list(all=True))
            containers = list(client.containers.list(all=True))
            swarm_services = list(client.services.list()) if runtime_swarm_enabled else []
        except Exception as exc:
            raise CommandError(
                "Could not inspect Docker images, containers, and Swarm services; "
                "no images were changed."
            ) from exc

        live_container_ids = {
            str((getattr(container, "attrs", {}) or {}).get("Image") or "")
            for container in containers
        }
        live_container_ids.discard("")

        live_service_ids: set[str] = set()
        live_service_refs: set[str] = set()
        for runtime_service in swarm_services:
            image_ref = _service_image_ref(runtime_service)
            if not image_ref:
                continue
            live_service_refs.add(image_ref)
            live_service_refs.add(image_ref.split("@", 1)[0])
            try:
                live_service_ids.add(str(client.images.get(image_ref).id))
                continue
            except Exception:
                pass
            try:
                live_service_ids.add(str(client.images.get(image_ref.split("@", 1)[0]).id))
            except Exception:
                # Image may exist on another Swarm node; preserve the runtime ref.
                pass

        try:
            existing_service_ids = {
                str(value) for value in Service.objects.values_list("pk", flat=True)
            }
            protected_base_ids = {
                str(value)
                for value in BaseRuntimeImage.objects.exclude(image_id="")
                .values_list("image_id", flat=True)
                if value
            }
            active_cache_ids = {
                str(value)
                for value in BuildCacheArtifact.objects.filter(reclaimed_at__isnull=True)
                .values_list("image_id", flat=True)
                if value
            }
            deployment_refs_by_service: dict[str, set[str]] = {}
            for service_id, image_ref in Deploy.objects.exclude(image_ref="").values_list(
                "service_id", "image_ref"
            ):
                if service_id and image_ref:
                    deployment_refs_by_service.setdefault(str(service_id), set()).add(str(image_ref))
        except Exception as exc:
            raise CommandError(
                "Could not read Django image ownership records; no images were changed."
            ) from exc

        image_by_id = {
            str(getattr(image, "id", "") or ""): image
            for image in images
            if str(getattr(image, "id", "") or "")
        }
        tags_by_id = {image_id: _image_tags(image) for image_id, image in image_by_id.items()}

        deployment_image_ids: set[str] = set()
        for refs in deployment_refs_by_service.values():
            for ref in refs:
                try:
                    deployment_image_ids.add(str(client.images.get(ref).id))
                except Exception:
                    continue

        candidates = []
        skipped = Counter()
        for image_id, image in image_by_id.items():
            labels = _image_labels(image)
            owner_id = str(
                labels.get("io.passdeployer.service")
                or labels.get("passdeployer.service")
                or labels.get("service.id")
                or ""
            ).strip()
            deployment_id = str(
                labels.get("io.passdeployer.deployment")
                or labels.get("deployment.id")
                or ""
            ).strip()
            role = str(labels.get("io.passdeployer.cache.role") or "").strip().lower()
            tags = tags_by_id.get(image_id, set())
            app_tags = {tag for tag in tags if is_platform_application_image_ref(tag)}

            # Unlabelled historical images are left for manual review.
            if not owner_id or not deployment_id or (role and role != "application") or not app_tags:
                skipped["unproven_or_non_app"] += 1
                continue
            if owner_id in existing_service_ids:
                skipped["service_still_exists"] += 1
                continue
            if image_id in protected_base_ids:
                skipped["base_image"] += 1
                continue
            if image_id in live_container_ids or image_id in live_service_ids:
                skipped["runtime_reference"] += 1
                continue
            if image_id in active_cache_ids or image_id in deployment_image_ids:
                skipped["database_reference"] += 1
                continue

            foreign_live_tag = any(
                tag in live_service_refs or tag.split("@", 1)[0] in live_service_refs
                for tag in tags
            )
            foreign_deploy_ref = any(
                tag in refs
                for other_service_id, refs in deployment_refs_by_service.items()
                if other_service_id != owner_id
                for tag in app_tags
            )
            if foreign_live_tag or foreign_deploy_ref:
                skipped["other_runtime_reference"] += 1
                continue

            candidates.append({
                "image_id": image_id,
                "owner_id": owner_id,
                "deployment_id": deployment_id,
                "tags": sorted(app_tags),
                "size": int((getattr(image, "attrs", {}) or {}).get("Size") or 0),
            })
            if len(candidates) >= limit:
                break

        self.stdout.write(
            "Mode: " + ("APPLY (verified orphan removal)" if apply_changes else "DRY-RUN (no changes)")
        )
        self.stdout.write(
            f"Inspected {len(image_by_id)} local images; found {len(candidates)} verified orphan candidate(s)."
        )
        failed = 0
        for candidate in candidates:
            tags = ", ".join(candidate["tags"])
            size_mb = candidate["size"] / (1024 * 1024)
            if not apply_changes:
                self.stdout.write(
                    f"WOULD REMOVE owner={candidate['owner_id']} "
                    f"deployment={candidate['deployment_id']} image={candidate['image_id'][:19]} "
                    f"size={size_mb:.1f}MiB tags=[{tags}]"
                )
                continue

            ok, detail = release_application_image_references(
                candidate["image_id"],
                candidate["tags"],
                owner_service_ids=(candidate["owner_id"],),
                client=client,
            )
            if not ok:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"FAILED image={candidate['image_id']}: {detail}")
                )
                continue
            self.stdout.write(
                self.style.SUCCESS(
                    f"RELEASED image={candidate['image_id'][:19]} tags=[{tags}]: {detail}"
                )
            )

        if skipped:
            self.stdout.write(
                "Skipped by safety checks: "
                + ", ".join(f"{key}={value}" for key, value in sorted(skipped.items()))
            )
        if failed:
            raise CommandError(f"Failed to clean {failed} orphan application image(s).")
