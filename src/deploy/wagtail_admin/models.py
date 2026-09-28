"""Wagtail admin (snippet) registration for the deploy app."""
from __future__ import annotations

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for, read_only_panels
from deploy.models import (
    Deploy,
    DeployLog,
    BaseRuntimeImage,
    BaseRuntimeImageLease,
    SwarmCluster,
    SwarmNode,
)
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class ReadOnlyModelPermissionPolicy(ModelPermissionPolicy):
    """Permission policy that only allows listing/reading, never mutating."""

    def user_has_permission(self, user, action):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        actions = {a for a in actions if a not in {"add", "change", "delete"}}
        return super().user_has_any_permission(user, actions)


class DeployViewSet(SnippetViewSet):
    model = Deploy
    permission_policy = ReadOnlyModelPermissionPolicy(Deploy)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "upload"
    menu_label = _("Deployments")
    menu_order = 104
    list_display = ["name", "service", "version", "status", "stage", "progress", "started_at", "created_at"]
    list_filter = ["status", "rollback_status", "service"]
    search_fields = ["name", "service__name", "status_message", "error_message"]
    ordering = ["-created_at"]
    list_per_page = 50
    panels = panels_for(
        editable=[],
        read_only=[
            "id", "name", "service", "version", "zip_file", "config",
            "started_at", "completed_at", "updated_file_at", "status", "stage",
            "progress", "status_message", "error_message", "rollback_status",
            "health_status", "container_status", "image_status", "volume_status",
            "network_status", "cancel_requested", "created_at", "updated_at",
        ],
    )


class BaseRuntimeImageOperatorPermissionPolicy(ModelPermissionPolicy):
    """Base-image rows are registered state; only existing operator fields may change."""

    def user_has_permission(self, user, action):
        if action in {"add", "delete"}:
            return False
        return super().user_has_permission(user, action)


class BaseRuntimeImageViewSet(SnippetViewSet):
    model = BaseRuntimeImage
    permission_policy = BaseRuntimeImageOperatorPermissionPolicy(BaseRuntimeImage)
    icon = "cogs"
    menu_label = _("Base runtime images")
    menu_order = 106
    list_display = [
        "logical_runtime", "runtime_version", "variant", "status", "enabled",
        "auto_build", "image_ref", "docker_host", "build_count", "build_completed_at",
    ]
    list_filter = ["logical_runtime", "status", "enabled", "auto_build", "docker_host"]
    search_fields = ["logical_runtime", "runtime_version", "image_ref", "source_image", "docker_host"]
    ordering = ["logical_runtime", "runtime_version", "variant"]
    panels = panels_for(
        editable=["enabled", "auto_build"],
        read_only=[
            "id", "logical_runtime", "runtime_version", "variant", "architecture",
            "source_image", "image_repository", "image_tag", "image_ref", "image_id",
            "image_digest", "docker_host", "status", "rebuild_requested",
            "rebuild_requested_at", "build_started_at", "build_completed_at",
            "build_count", "build_task_id", "build_owner_deployment_id",
            "definition_fingerprint", "last_error", "created_at", "updated_at",
        ],
    )


class BaseRuntimeImageLeaseViewSet(SnippetViewSet):
    model = BaseRuntimeImageLease
    permission_policy = ReadOnlyModelPermissionPolicy(BaseRuntimeImageLease)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "lock"
    menu_label = _("Base image leases")
    menu_order = 109
    list_display = ["base_image", "deployment_id", "acquired_at", "released_at"]
    list_filter = ["released_at", "acquired_at"]
    search_fields = ["deployment_id", "base_image__image_ref"]
    ordering = ["-acquired_at"]
    list_per_page = 50
    panels = read_only_panels([
        "id", "base_image", "deployment_id", "acquired_at", "released_at",
        "created_at", "updated_at",
    ])


class SwarmInfrastructurePermissionPolicy(ModelPermissionPolicy):
    """Infrastructure records are discovered from Docker; operators edit desired state only."""

    def user_has_permission(self, user, action):
        if action in {"add", "delete"}:
            return False
        return super().user_has_permission(user, action)


class SwarmClusterViewSet(SnippetViewSet):
    model = SwarmCluster
    permission_policy = SwarmInfrastructurePermissionPolicy(SwarmCluster)
    icon = "site"
    menu_label = _("Docker Swarm clusters")
    menu_order = 107
    list_display = ["name", "enabled", "manager_endpoint", "last_synced_at", "last_error"]
    list_filter = ["enabled"]
    search_fields = ["name", "manager_endpoint", "last_error"]
    ordering = ["name"]
    panels = panels_for(
        editable=["enabled"],
        read_only=["id", "name", "manager_endpoint", "last_synced_at", "last_error", "created_at", "updated_at"],
    )


class SwarmNodeViewSet(SnippetViewSet):
    model = SwarmNode
    permission_policy = SwarmInfrastructurePermissionPolicy(SwarmNode)
    icon = "site"
    menu_label = _("Docker Swarm nodes")
    menu_order = 108
    list_display = [
        "hostname", "cluster", "role", "desired_availability",
        "observed_availability", "observed_state", "cpus", "manager_reachable",
        "last_synced_at",
    ]
    list_filter = ["cluster", "role", "desired_availability", "observed_availability", "observed_state", "manager_reachable"]
    search_fields = ["hostname", "docker_id", "address", "last_error"]
    ordering = ["hostname"]
    panels = panels_for(
        editable=["desired_availability", "desired_labels"],
        read_only=[
            "id", "cluster", "docker_id", "hostname", "role", "observed_availability",
            "observed_state", "address", "labels", "cpus", "memory_bytes",
            "manager_reachable", "last_synced_at", "last_error", "created_at", "updated_at",
        ],
    )


class DeployLogViewSet(SnippetViewSet):
    model = DeployLog
    icon = "doc-full-inverse"
    menu_label = _("Deploy logs")
    menu_order = 105
    permission_policy = ReadOnlyModelPermissionPolicy(DeployLog)
    list_display = ["deploy_id", "service_id", "stage", "event_type", "level", "progress", "created_at"]
    list_filter = ["stage", "level", "event_type", "created_at"]
    search_fields = ["message", "event_type", "exception_type", "traceback"]
    ordering = ["-created_at"]
    list_per_page = 50
    panels = read_only_panels([
        "id", "deploy", "service", "stage", "event_type", "level", "message",
        "progress", "details", "exception_type", "traceback", "created_at", "updated_at",
    ])

    def get_queryset(self, request):
        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
        return DeployLog.objects.using(alias).all()


class DeployGroup(SnippetViewSetGroup):
    items = (
        DeployViewSet,
        DeployLogViewSet,
        BaseRuntimeImageViewSet,
        BaseRuntimeImageLeaseViewSet,
        SwarmClusterViewSet,
        SwarmNodeViewSet,
    )
    menu_label = _("Deploy")
    menu_icon = "upload"
    menu_order = 104
