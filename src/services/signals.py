import logging

import docker.errors

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models import Service, ServiceRevision, ServiceNetworkAttachment, Volume, PrivateNetwork
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import SwarmRuntime, swarm_enabled
from deployments.core.manager.volume_manager import Volume as DockerVolume
from deployments.core.manager.image_manager import Image
from deployments.core.manager.network_manager import Network
from core.global_settings.config import PlanTypeChoices

logger = logging.getLogger(__name__)


def _cancel_active_deployments_for_service(service: Service) -> None:
    """Request cancellation for every non-terminal deployment owned by a Service."""
    from deploy.models import Deploy, DeploymentStatusChoices
    from deployments.application.cancel import CancelDeploymentUseCase
    from deployments.infrastructure.django_cancellation import DjangoDeploymentCancellationGateway

    gateway = DjangoDeploymentCancellationGateway()
    deploys = list(
        Deploy.objects.filter(
            service_id=service.pk,
            status__in=(
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
                DeploymentStatusChoices.ROLLING_BACK,
            ),
        ).only("pk", "status", "cancel_requested")
    )
    for deploy in deploys:
        result = CancelDeploymentUseCase(gateway).execute(deploy.pk)
        logger.info(
            "Requested cancellation for deploy %s before Service %s deletion: %s",
            deploy.pk,
            service.pk,
            result.decision.action.value,
        )


def _remove_owned_volume_attachments(service: Service, docker_volume: DockerVolume, docker_name: str) -> None:
    """Remove only PassDeployer-owned containers still holding a service volume."""
    client = docker_volume.client
    try:
        containers = client.containers.list(all=True, filters={"volume": docker_name})
    except Exception as exc:
        raise RuntimeError(
            f"Unable to inspect containers using Docker volume '{docker_name}'."
        ) from exc

    expected_service = str(service.pk)
    for raw in containers:
        labels = dict(getattr(raw, "labels", {}) or {})
        managed = labels.get("managed-by") in {"django-paas-deployer", "passdeployer"}
        owner = str(labels.get("passdeployer.service") or labels.get("service.id") or "")
        if not managed or owner != expected_service:
            raise RuntimeError(
                f"Refusing to remove Docker container '{getattr(raw, 'name', raw.id)}' "
                f"while deleting service '{service.name}': the volume is attached to "
                "a container without matching PassDeployer ownership labels."
            )

        container_name = str(getattr(raw, "name", "") or raw.id)
        try:
            raw.reload()
        except Exception:
            pass

        if str(getattr(raw, "status", "") or "").lower() == "running":
            logger.info(
                "Stopping owned task container '%s' before removing volume '%s'.",
                container_name,
                service.name,
            )
            try:
                raw.stop(timeout=10)
            except Exception:
                logger.exception(
                    "Failed to stop owned container '%s' before volume cleanup; "
                    "trying forced removal.",
                    container_name,
                )

        try:
            raw.remove(force=True)
            logger.info(
                "Removed owned container '%s' still attached to volume '%s'.",
                container_name,
                service.name,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to remove owned container '{container_name}' while cleaning "
                f"volume '{docker_name}'."
            ) from exc


def _remove_owned_docker_volume(service: Service, docker_volume: DockerVolume, docker_name: str) -> None:
    """Remove a managed Docker volume, resolving stale owned task containers first."""
    try:
        docker_volume.remove()
        return
    except Exception as first_exc:
        if "volume is in use" not in str(first_exc).lower():
            raise

        _remove_owned_volume_attachments(service, docker_volume, docker_name)

        # Swarm task/container removal and volume release can race very briefly.
        # Retry the normal non-forced volume delete after the owned attachments
        # have been removed; never force-delete an attached volume.
        for attempt in range(5):
            try:
                docker_volume.remove()
                return
            except Exception as exc:
                if "volume is in use" not in str(exc).lower():
                    raise
                if attempt == 4:
                    raise
                import time
                time.sleep(0.5)


def cleanup_service_resources(service: Service) -> None:
    """Remove all Docker/log/volume resources owned by a Service, without deleting its DB row."""
    service_name = service.get_docker_service_name()
    _cancel_active_deployments_for_service(service)
    logger.info(
        "Cleaning Docker resources for service '%s' (%s)",
        service.name,
        service_name,
    )

    plan_platform = str(getattr(getattr(service, "plan", None), "platform", "") or "").strip().lower()
    from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer

    if plan_platform in DB_PLATFORMS:
        DBDeployer().remove(service_name)
    elif swarm_enabled():
        try:
            SwarmRuntime().remove_service_group(str(service.pk))
        except Exception as exc:
            logger.exception(
                "Failed cleaning Docker Swarm services for service '%s'.",
                service.name,
            )
            raise RuntimeError(
                f"Failed to remove Swarm runtime for service '{service.name}'."
            ) from exc

    container = Container(name=service_name)
    if container.exists():
        raw = container.client.containers.get(service_name)
        labels = dict(getattr(raw, "labels", {}) or {})
        expected_service = str(service.pk)
        expected_deploy = str(getattr(service.selected_deploy, "pk", "") or "")
        managed = labels.get("managed-by") in {"django-paas-deployer", "passdeployer"}
        owns_service = managed and labels.get("service.id") == expected_service
        owns_selected_deploy = expected_deploy and labels.get("deployment.id") == expected_deploy
        if not (owns_service or owns_selected_deploy):
            raise RuntimeError(
                f"Refusing to delete service '{service.name}': "
                f"container '{service_name}' exists but is not owned by PassDeployer."
            )

        if container.is_running():
            logger.info("Stopping running container '%s'...", service_name)
            try:
                container.stop(timeout=10)
            except Exception:
                logger.exception(
                    "Failed to stop container '%s' (continuing with remove)",
                    service_name,
                )

        logger.info("Removing owned container '%s'...", service_name)
        try:
            container.remove(force=True)
        except Exception:
            logger.exception("Failed to remove owned container '%s'", service_name)
            raise

    if getattr(service, "plan", None) and getattr(
        service.plan, "plan_type", None
    ) != PlanTypeChoices.DB:
        Image.remove_by_name(service_name)
        Image.remove_by_name(f"{service_name}:latest")

    _cleanup_service_cache_images(service)
    _cleanup_service_volumes(service)


@receiver(pre_delete, sender=Service)
def delete_deploy_before_delete_service(sender, instance: Service, **kwargs):
    """Remove Docker resources before the Service row is deleted."""
    cleanup_service_resources(instance)

def _cleanup_service_cache_images(service: Service) -> None:
    """Remove unshared application images owned by a deleting Service."""
    from deploy.build_cache import BuildCacheArtifact
    from deploy.models import BaseRuntimeImage
    from deployments.core.manager.client_manager import get_docker_client
    from docker.errors import ImageNotFound

    rows = list(
        BuildCacheArtifact.objects.filter(
            service_id=service.pk,
            reclaimed_at__isnull=True,
        ).values_list("image_id", "image_ref")
    )
    image_ids = {str(image_id) for image_id, _ref in rows if image_id}
    if not image_ids:
        return

    other_refs = set(
        str(value)
        for value in BuildCacheArtifact.objects.filter(
            image_id__in=image_ids,
            reclaimed_at__isnull=True,
        )
        .exclude(service_id=service.pk)
        .values_list("image_id", flat=True)
        if value
    )
    protected_base_ids = set(
        str(value)
        for value in BaseRuntimeImage.objects.filter(
            image_id__in=image_ids
        ).values_list("image_id", flat=True)
        if value
    )

    client = get_docker_client()
    running_ids = set()
    for container in client.containers.list():
        image = getattr(container, "image", None)
        image_id = str(getattr(image, "id", "") or "")
        if image_id:
            running_ids.add(image_id)

    for image_id in sorted(image_ids - other_refs - protected_base_ids - running_ids):
        try:
            client.images.remove(image_id, force=False)
            logger.info(
                "Removed unshared application cache image '%s' for deleted service '%s'.",
                image_id,
                service.name,
            )
        except ImageNotFound:
            logger.info(
                "Application cache image '%s' for deleted service '%s' is already absent.",
                image_id,
                service.name,
            )
        except Exception as exc:
            logger.exception(
                "Failed to remove application cache image '%s' for deleted service '%s'.",
                image_id,
                service.name,
            )
            raise RuntimeError(
                f"Failed to remove application cache image '{image_id}' "
                f"for service '{service.name}'."
            ) from exc


def _cleanup_service_volumes(service: Service) -> None:
    """
    With exclusive ownership, every volume with service_id == this service
    is deleted (Docker volume + DB row). There is no multi-service sharing.
    """
    volumes = list(Volume.objects.filter(service_id=service.pk))

    for volume in volumes:
        # Remove Docker volume first
        docker_name = volume.get_docker_volume_name()
        try:
            docker_volume = DockerVolume(docker_name)
            try:
                raw_volume = docker_volume.client.volumes.get(docker_name)
            except docker.errors.NotFound:
                raw_volume = None
            if raw_volume is not None:
                labels = dict(getattr(raw_volume, "attrs", {}).get("Labels") or {})
                if labels.get("managed-by") != "django-paas-deployer":
                    raise RuntimeError(
                        f"Refusing to remove Docker volume '{volume.name}': ownership label is missing or unexpected."
                    )
                _remove_owned_docker_volume(
                    service,
                    docker_volume,
                    docker_name,
                )
                logger.info(
                    "Removed Docker volume '%s' for deleted service '%s'.",
                    volume.name,
                    service.name,
                )
        except docker.errors.NotFound:
            pass
        except Exception:
            logger.exception(
                "Failed removing Docker volume '%s'; DB record will be retained to prevent invisible storage drift.",
                volume.name,
            )
            raise

        volume.delete()
        logger.info(
            "Deleted Volume record '%s' owned by service '%s'.",
            volume.name,
            service.name,
        )


@receiver(pre_delete, sender=Volume)
def cleanup_volume_on_delete(sender, instance: Volume, **kwargs):
    """Remove the underlying Docker volume when a Volume row is deleted."""
    logger.info(
        "pre_delete Volume '%s' → removing Docker volume", instance.name
    )
    try:
        docker_volume = DockerVolume(instance.get_docker_volume_name())
        try:
            raw_volume = docker_volume.client.volumes.get(instance.get_docker_volume_name())
        except docker.errors.NotFound:
            logger.info("Docker volume '%s' is already absent.", instance.name)
            return
        labels = dict(getattr(raw_volume, "attrs", {}).get("Labels") or {})
        if labels.get("managed-by") != "django-paas-deployer":
            raise RuntimeError(
                f"Refusing to remove Docker volume '{instance.name}': ownership label is missing or unexpected."
            )
        docker_volume.remove()
        logger.info("Docker volume '%s' removed successfully", instance.name)
    except docker.errors.NotFound:
        return
    except Exception:
        logger.exception(
            "Failed to remove Docker volume '%s' during Volume pre_delete; refusing to delete the DB row.",
            instance.name,
        )
        raise


@receiver(pre_delete, sender=PrivateNetwork)
def cleanup_network_on_delete(sender, instance: PrivateNetwork, **kwargs):
    """Remove an owned Docker network without deleting a still-used network."""
    logger.info(
        "pre_delete PrivateNetwork '%s' → removing owned Docker network",
        instance.name,
    )

    if Service.objects.filter(network_id=instance.pk).exists() or ServiceNetworkAttachment.objects.filter(network_id=instance.pk).exists():
        raise RuntimeError(
            f"Cannot delete private network '{instance.name}': "
            "one or more services still have an explicit network attachment."
        )

    docker_name = instance.get_docker_network_name()
    if not Network.network_exists(docker_name):
        logger.info(
            "Owned Docker network '%s' does not exist; nothing to remove",
            docker_name,
        )
        return

    try:
        docker_network = Network(name=docker_name)
        raw = docker_network.client.networks.get(docker_name)
        labels = dict(getattr(raw, "attrs", {}).get("Labels") or {})
        if labels.get("managed-by") != "django-paas-deployer":
            raise RuntimeError(
                f"Refusing to remove Docker network '{docker_name}': "
                "ownership label is missing or unexpected."
            )
        docker_network.remove()
        logger.info("Owned Docker network '%s' removed successfully", docker_name)
    except Exception as exc:
        logger.exception(
            "Failed to remove owned Docker network for PrivateNetwork '%s'",
            instance.name,
        )
        raise RuntimeError(
            f"Failed to remove Docker network '{docker_name}'."
        ) from exc


@receiver(pre_delete, sender=ServiceRevision)
def cleanup_revision_artifact_on_delete(sender, instance: ServiceRevision, **kwargs):
    """Delete the revision-owned source artifact before its DB row disappears."""
    artifact = getattr(instance, "artifact_file", None)
    name = str(getattr(artifact, "name", "") or "")
    if not name:
        return

    try:
        artifact.delete(save=False)
        logger.info(
            "Deleted ServiceRevision artifact '%s' for revision %s.",
            name,
            instance.pk,
        )
    except Exception as exc:
        logger.exception(
            "Failed to delete ServiceRevision artifact '%s' for revision %s.",
            name,
            instance.pk,
        )
        raise RuntimeError(
            f"Failed to remove revision artifact '{name}'."
        ) from exc


def _cleanup_service_log_records(service_id):
    """Delete service-scoped logs stored in the separate deployment-log DB."""
    from django.conf import settings
    from django.db import transaction
    from deploy.models import DeployLog
    from logs.models import (
        LogUsageDaily,
        ServiceLogEntry,
        ServiceLogStream,
        ServiceLogUsage,
    )

    alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"
    sid = str(service_id)
    deleted = {}

    with transaction.atomic(using=alias):
        for name, model in (
            ("deployment_logs", DeployLog),
            ("runtime_log_entries", ServiceLogEntry),
            ("runtime_log_streams", ServiceLogStream),
            ("runtime_log_usage", ServiceLogUsage),
            ("runtime_log_daily_usage", LogUsageDaily),
        ):
            deleted[name] = int(
                model.objects.using(alias).filter(service_id=sid).delete()[0]
            )

    return deleted


@receiver(post_delete, sender=Service)
def cleanup_service_external_state(sender, instance: Service, **kwargs):
    """
    Remove service-owned data that cannot be handled by the primary DB cascade.

    DeployLog and runtime logs intentionally use scalar service ids because they
    live on a separate database. Revision artifacts live in file storage and
    are handled by ServiceRevision.pre_delete.
    """
    try:
        deleted = _cleanup_service_log_records(instance.pk)
        logger.info(
            "Deleted service-owned log records for service %s: %s",
            instance.pk,
            deleted,
        )
    except Exception:
        logger.exception(
            "Failed to delete service-owned log records after Service %s deletion.",
            instance.pk,
        )
