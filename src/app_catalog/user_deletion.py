"""User hard-delete preparation for catalog-owned application graphs."""

from __future__ import annotations

from django.db import transaction

from services.lifecycle import mark_deleted
from services.models import ServiceNetworkAttachment

from .models import ApplicationInstance, ApplicationInstanceService


@transaction.atomic
def prepare_user_hard_delete(user) -> None:
    """Remove catalog protection blockers before the owning User row is deleted.

    ApplicationInstanceService intentionally uses PROTECT for direct child
    Service/Deploy deletion. User hard deletion is a higher-level destructive
    operation, so this coordinator removes each binding first, fences its
    Service, and lets the Service deletion signal own runtime cleanup.
    """
    instances = list(
        ApplicationInstance.objects.filter(user_id=user.pk)
        .prefetch_related("services__service", "services__deploy")
    )

    for instance in instances:
        bindings = list(
            ApplicationInstanceService.objects
            .select_related("service", "deploy")
            .filter(instance_id=instance.pk)
        )

        for binding in bindings:
            service = binding.service
            deploy = binding.deploy

            # Fence every in-flight child before deleting its durable row.
            mark_deleted(service.pk)
            if deploy is not None and getattr(deploy, "cancel_requested", False) is False:
                deploy.cancel_requested = True
                deploy.save(update_fields=["cancel_requested", "updated_at"])

            # PROTECT exists specifically to prevent direct child deletion.
            # Remove the coordinator binding first because this entire
            # application graph is owned by the user being hard-deleted.
            binding.delete()

            # Service deletion owns runtime/volume/log/artifact cleanup.
            service.delete()

        # Application networks are dedicated to the installation. After child
        # Service deletion their explicit attachment rows should be gone.
        network = getattr(instance, "network", None)
        if network is not None:
            remaining = ServiceNetworkAttachment.objects.filter(
                network_id=network.pk
            ).exists()
            if remaining:
                raise RuntimeError(
                    f"Cannot hard-delete user {user.pk}: application network "
                    f"{network.pk} is still attached to another service."
                )
            network.delete()
