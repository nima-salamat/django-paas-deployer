from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from deploy.models import Deploy
from services.models import (
    Service, ServiceProcess, ServiceEnvironmentVariable, ServiceSecret,
    ServiceEndpoint, ServicePortReservation, ServiceNetworkAttachment,
    ServiceDatabaseBinding, Volume, ServiceShare, ServiceRevision,
    ShellAuditEvent,
)


def _operator_can_view(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
        and (getattr(user, "is_superuser", False) or user.has_perm("services.view_service"))
    )


@require_GET
def service_inspect(request, pk):
    if not _operator_can_view(getattr(request, "user", None)):
        raise PermissionDenied

    service = get_object_or_404(
        Service.objects.select_related("user", "plan", "network", "active_revision").prefetch_related(
            Prefetch("processes", queryset=ServiceProcess.objects.order_by("name")),
            Prefetch("environment_variables", queryset=ServiceEnvironmentVariable.objects.select_related("secret").order_by("key")),
            Prefetch("secrets", queryset=ServiceSecret.objects.order_by("key")),
            Prefetch("endpoints", queryset=ServiceEndpoint.objects.select_related("process").order_by("name")),
            Prefetch("port_reservations", queryset=ServicePortReservation.objects.select_related("endpoint").order_by("host_port")),
            Prefetch("network_attachments", queryset=ServiceNetworkAttachment.objects.select_related("network").order_by("network__name")),
            Prefetch("database_bindings", queryset=ServiceDatabaseBinding.objects.select_related("database").order_by("alias")),
            Prefetch("volumes", queryset=Volume.objects.order_by("name")),
            Prefetch("shares", queryset=ServiceShare.objects.select_related("group", "target_user", "shared_by").order_by("-created_at")),
            Prefetch("revisions", queryset=ServiceRevision.objects.select_related("source_deploy", "created_by").order_by("-revision_number")),
            Prefetch("shell_audit_events", queryset=ShellAuditEvent.objects.select_related("user").order_by("-created_at")[:50]),
        ),
        pk=pk,
    )
    deployment_history = list(
        Deploy.objects.filter(service=service)
        .only("pk", "name", "status", "stage", "progress", "status_message", "error_message", "created_at", "started_at", "completed_at")
        .order_by("-created_at")[:50]
    )
    return render(request, "services/wagtail/service_inspect.html", {
        "service": service,
        "deployment_history": deployment_history,
        "storage_summary": service.storage_quota_summary(),
        "processes": list(service.processes.all()),
        "environment_variables": list(service.environment_variables.all()),
        "secrets": list(service.secrets.all()),
        "endpoints": list(service.endpoints.all()),
        "port_reservations": list(service.port_reservations.all()),
        "network_attachments": list(service.network_attachments.all()),
        "database_bindings": list(service.database_bindings.all()),
        "volumes": list(service.volumes.all()),
        "shares": list(service.shares.all()),
        "revisions": list(service.revisions.all()),
        "shell_audit_events": list(service.shell_audit_events.all()),
    })
