"""Aggregate child Service lifecycle into its owning Ready App status."""

from __future__ import annotations

import logging

from django.db import transaction

from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus

logger = logging.getLogger(__name__)


def sync_application_status_for_service(service_id: str | int) -> str | None:
    """Synchronize the Ready App parent after a managed child Service changes.

    This deliberately uses persisted lifecycle state only; the runtime monitor
    remains responsible for Docker/Swarm observation and repair.
    """
    instance_id = (
        ApplicationInstanceService.objects
        .filter(service_id=service_id)
        .values_list("instance_id", flat=True)
        .first()
    )
    if instance_id is None:
        return None

    with transaction.atomic():
        instance = (
            ApplicationInstance.objects
            .select_for_update()
            .filter(pk=instance_id)
            .first()
        )
        if instance is None or instance.stage == "deletion_pending":
            return None

        # Installation orchestration owns PENDING/DEPLOYING; structural or
        # terminal failures and user cancellation must not be overwritten.
        if instance.status in {
            ApplicationStatus.PENDING,
            ApplicationStatus.DEPLOYING,
            ApplicationStatus.FAILED,
            ApplicationStatus.CANCELLED,
        }:
            return str(instance.status)

        bindings = list(
            ApplicationInstanceService.objects
            .select_related("service", "deploy")
            .filter(instance_id=instance.pk)
            .order_by("sequence", "service_key")
        )
        if not bindings:
            return str(instance.status)

        all_stopped = all(
            str(binding.service.status or "").lower() == "stopped"
            and str(binding.service.desired_state or "").lower() == "stopped"
            for binding in bindings
        )
        all_running = all(
            str(binding.service.status or "").lower() in {"running", "succeeded"}
            and str(binding.service.desired_state or "").lower() == "running"
            and str(binding.deploy.status or "").lower() == "succeeded"
            for binding in bindings
        )

        if all_stopped:
            target = ApplicationStatus.STOPPED
            stage = "application_stopped"
            error_code = ""
            error_message = ""
        elif all_running:
            target = ApplicationStatus.RUNNING
            stage = "application_ready"
            error_code = ""
            error_message = ""
        else:
            target = ApplicationStatus.DEGRADED
            stage = "runtime_reconciling"
            issues = [
                f"{binding.service_key} ({binding.service.status})"
                for binding in bindings
                if (
                    str(binding.service.status or "").lower() not in {"running", "succeeded"}
                    or str(binding.service.desired_state or "").lower() != "running"
                    or str(binding.deploy.status or "").lower() != "succeeded"
                )
            ]
            error_code = "APPLICATION_RUNTIME_DEGRADED"
            error_message = (
                "Ready App is degraded because one or more child services are not "
                "running as requested: " + ", ".join(issues[:8])
            )

        if (
            instance.status != target
            or instance.stage != stage
            or instance.error_code != error_code
            or instance.error_message != error_message
        ):
            instance.status = target
            instance.stage = stage
            instance.error_code = error_code
            instance.error_message = error_message
            instance.save(update_fields=[
                "status", "stage", "error_code", "error_message", "updated_at",
            ])
        return str(target)
