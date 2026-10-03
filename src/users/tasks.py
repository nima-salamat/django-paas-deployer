from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from users.models import User

logger = logging.getLogger("users.deletion")


ACTIVE_DEPLOYMENT_STATUSES = {
    "pending",
    "running",
    "rolling_back",
}


def _active_deployments_for_user(user_id):
    from deploy.models import Deploy
    return Deploy.objects.filter(
        service__user_id=user_id,
        status__in=ACTIVE_DEPLOYMENT_STATUSES,
    ).only("pk", "service_id", "status", "cancel_requested")


def request_user_deletion_convergence(user_id: int) -> int:
    """Durably fence a user and request canonical cancellation for active Deploys."""
    from deployments.application.cancel import CancelDeploymentUseCase
    from deployments.infrastructure.django_cancellation import DjangoDeploymentCancellationGateway
    from services.lifecycle import mark_deleted

    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(pk=user_id, deletion_requested_at__isnull=False)
            .first()
        )
        if user is None:
            return 0

        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active", "updated_at"])

        service_ids = list(
            user.services.values_list("pk", flat=True)
        )
        for service_id in service_ids:
            mark_deleted(service_id)

        deploy_ids = list(
            _active_deployments_for_user(user.pk).values_list("pk", flat=True)
        )

        # Session revocation is durable and its Redis cleanup is on_commit.
        from auth_users.session_auth import invalidate_all_sessions
        invalidate_all_sessions(user.pk)

    gateway = DjangoDeploymentCancellationGateway()
    use_case = CancelDeploymentUseCase(gateway)
    for deploy_id in deploy_ids:
        try:
            use_case.execute(deploy_id)
        except Exception:
            logger.exception(
                "Failed to request cancellation for deploy=%s during user deletion.",
                deploy_id,
            )

    return len(deploy_ids)


@shared_task(bind=True, max_retries=None, acks_late=True)
def finalize_user_deletion(self, user_id: int, *, retry_seconds: int = 10):
    """Delete the account only after every owned deployment is terminal."""
    user = (
        User.objects.filter(
            pk=user_id,
            deletion_requested_at__isnull=False,
        )
        .only("pk", "is_active", "deletion_requested_at")
        .first()
    )
    if user is None:
        return {"status": "gone", "user_id": user_id}

    active = list(
        _active_deployments_for_user(user.pk).values_list("pk", "status")
    )
    if active:
        request_user_deletion_convergence(user.pk)
        raise self.retry(
            countdown=max(2, int(retry_seconds)),
            kwargs={"retry_seconds": retry_seconds},
        )

    # No active Deploy remains. The User pre_delete signal performs the final
    # ownership cleanup and will fail closed if a runtime/storage invariant is
    # still violated.
    user.delete()
    logger.info("User deletion finalized user=%s", user_id)
    return {"status": "deleted", "user_id": user_id}
