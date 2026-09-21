from __future__ import annotations

import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from deploy.models import Deploy
from deployments.celery.tasks import deploy as deploy_task
from deployments.core.state.manager import StateManager
from core.global_settings.config import SERVICE_STATUS_CHOICES
from services.models import (
    Service,
    ServiceEnvironmentVariable,
    ServiceEndpoint,
    ServiceRevision,
    ServiceSecret,
    PrivateNetwork,
    ServiceNetworkAttachment,
    DatabaseResource,
    ServiceDatabaseBinding,
)
from services.revisioning import materialize_revision_config, _get_or_create_secret, redact_config
from services.share_permissions import assert_share_action, SharePermissionError
from services.ports import sync_endpoint_reservation, release_endpoint_port


class ServiceConfigBaseAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def service(self, request, service_id) -> Service:
        return get_object_or_404(Service.objects.select_related("plan", "network"), pk=service_id)

    def assert_access(self, request, service: Service, action: str, *, owner_only: bool = False):
        if str(service.user_id) == str(request.user.id):
            return None
        if owner_only:
            return Response({"error": "Only the service owner may perform this action."}, status=403)
        try:
            assert_share_action(service, request.user, action)
        except SharePermissionError as exc:
            return Response({"error": str(exc)}, status=403)
        return None

    @staticmethod
    def assert_mutable(service: Service):
        blocked = {
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.STOPPING,
            "queued",
            "deploying",
            "stopping",
        }
        if str(service.status).lower() in {str(x).lower() for x in blocked}:
            return Response(
                {
                    "error": "Service configuration cannot change while an operation is in progress.",
                    "code": "service_transition_in_progress",
                    "status": service.status,
                },
                status=409,
            )
        return None


class ServiceConfigurationAPIView(ServiceConfigBaseAPIView):
    """Read/update desired service configuration.

    Runtime changes are declarative. They become effective on the next
    deployment and are captured into an immutable ServiceRevision.
    """

    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        variables = ServiceEnvironmentVariable.objects.filter(service=service, enabled=True).order_by("key")
        return Response(
            {
                "service": str(service.pk),
                "source": {
                    "kind": service.source_kind,
                    "config": redact_config(service.source_config or {})[0],
                },
                "build": redact_config(service.build_config or {})[0],
                "runtime": redact_config(service.runtime_config or {})[0],
                "desired_state": service.desired_state,
                "environment": [
                    {
                        "key": row.key,
                        "scope": row.scope,
                        "is_secret": bool(row.secret_id),
                        "value": "***" if row.secret_id else row.value,
                    }
                    for row in variables
                ],
                "secrets": sorted(
                    (ServiceSecretRefSerializer(secret).data for secret in service.secrets.filter(enabled=True)),
                    key=lambda item: item["key"],
                ),
                "processes": [row.to_snapshot() for row in service.processes.all()],
                "endpoints": EndpointSerializer(service.endpoints.filter(enabled=True), many=True).data,
                "active_revision": (
                    str(service.active_revision_id) if service.active_revision_id else None
                ),
            }
        )

    def patch(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked

        data = request.data if isinstance(request.data, dict) else dict(request.data)

        def contains_sensitive_keys(value):
            sensitive = (
                "password", "secret", "token", "private_key",
                "api_key", "apikey", "signing_key", "authorization",
            )
            if isinstance(value, dict):
                for key, item in value.items():
                    lowered = str(key).lower()
                    if any(token in lowered for token in sensitive):
                        return True
                    if contains_sensitive_keys(item):
                        return True
            elif isinstance(value, list):
                return any(contains_sensitive_keys(item) for item in value)
            return False

        for field_name in ("source_config", "build_config", "runtime_config"):
            if field_name in data and contains_sensitive_keys(data[field_name]):
                return Response(
                    {
                        "error": f"Sensitive values must be stored through /secrets or secret-backed environment variables, not {field_name}.",
                        "code": "secret_requires_secret_resource",
                        "field": field_name,
                    },
                    status=400,
                )

        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=service.pk)
            if "source_kind" in data:
                source_kind = str(data["source_kind"]).strip()
                valid = {choice[0] for choice in Service.SourceKind.choices}
                if source_kind not in valid:
                    return Response({"error": "Invalid source_kind.", "allowed": sorted(valid)}, status=400)
                service.source_kind = source_kind
            if "source_config" in data:
                service.source_config = dict(data.get("source_config") or {})
            if "build_config" in data:
                service.build_config = dict(data.get("build_config") or {})
            if "runtime_config" in data:
                service.runtime_config = dict(data.get("runtime_config") or {})
            if "desired_state" in data:
                desired = str(data["desired_state"]).strip()
                if desired not in {"running", "stopped"}:
                    return Response({"error": "desired_state must be running or stopped."}, status=400)
                service.desired_state = desired
            service.save(update_fields=[
                "source_kind", "source_config", "build_config",
                "runtime_config", "desired_state", "updated_at",
            ])

        return Response({"status": "updated", "service": str(service.pk), "requires_deploy": True})


class ServiceEnvironmentAPIView(ServiceConfigBaseAPIView):
    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = ServiceEnvironmentVariable.objects.filter(service=service, enabled=True).order_by("key")
        return Response(
            {
                "results": [
                    {
                        "key": row.key,
                        "scope": row.scope,
                        "is_secret": bool(row.secret_id),
                        "value": "***" if row.secret_id else row.value,
                    }
                    for row in rows
                ]
            }
        )

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked

        key = str(request.data.get("key") or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            return Response({"error": "Invalid environment variable key."}, status=400)
        scope = str(request.data.get("scope") or ServiceEnvironmentVariable.Scope.RUNTIME)
        if scope not in {choice[0] for choice in ServiceEnvironmentVariable.Scope.choices}:
            return Response({"error": "Invalid scope."}, status=400)
        is_secret = str(request.data.get("is_secret") or "").lower() in {"1", "true", "yes", "on"}
        value = str(request.data.get("value") or "")

        with transaction.atomic():
            row, _ = ServiceEnvironmentVariable.objects.select_for_update().get_or_create(
                service=service, key=key,
                defaults={"scope": scope},
            )
            row.scope = scope
            row.enabled = True
            if is_secret:
                secret, _version = _get_or_create_secret(service, key, value, created_by=request.user, note="Environment variable secret")
                row.secret = secret
                row.value = ""
            else:
                row.secret = None
                row.value = value
            row.save(update_fields=["scope", "secret", "value", "enabled", "updated_at"])

        return Response(
            {
                "key": row.key,
                "scope": row.scope,
                "is_secret": bool(row.secret_id),
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        key = str(request.query_params.get("key") or "").strip()
        if not key:
            return Response({"error": "key is required."}, status=400)
        deleted, _ = ServiceEnvironmentVariable.objects.filter(service=service, key=key).delete()
        if not deleted:
            return Response({"error": "Environment variable not found."}, status=404)
        return Response(status=204)


class ServiceSecretRefSerializer:
    def __init__(self, secret):
        self.secret = secret

    @property
    def data(self):
        return {
            "key": self.secret.key,
            "current_version": self.secret.current_version,
            "description": self.secret.description,
            "enabled": self.secret.enabled,
        }


class ServiceSecretsAPIView(ServiceConfigBaseAPIView):
    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view", owner_only=True)
        if denied:
            return denied
        return Response(
            {"results": [ServiceSecretRefSerializer(secret).data for secret in service.secrets.order_by("key")]}
        )

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config", owner_only=True)
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        key = str(request.data.get("key") or "").strip()
        value = request.data.get("value")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            return Response({"error": "Invalid secret key."}, status=400)
        if value is None:
            return Response({"error": "value is required."}, status=400)
        secret, version = _get_or_create_secret(
            service, key, str(value), created_by=request.user,
            note=str(request.data.get("note") or ""),
        )
        if "description" in request.data:
            secret.description = str(request.data.get("description") or "")[:255]
            secret.save(update_fields=["description", "updated_at"])
        return Response({"key": key, "current_version": version}, status=200)

    def delete(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config", owner_only=True)
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        key = str(request.query_params.get("key") or "").strip()
        secret = ServiceSecret.objects.filter(service=service, key=key).first()
        if not secret:
            return Response({"error": "Secret not found."}, status=404)
        secret.enabled = False
        secret.save(update_fields=["enabled", "updated_at"])
        return Response({"status": "disabled", "key": key})


class EndpointSerializer:
    def __init__(self, instance=None, many=False):
        self.instance = instance
        self.many = many

    @property
    def data(self):
        rows = self.instance if self.many else [self.instance]
        return [
            {
                "id": str(row.pk),
                "name": row.name,
                "process": str(row.process_id) if row.process_id else None,
                "target_port": row.target_port,
                "published_port": row.published_port,
                "protocol": row.protocol,
                "exposure": row.exposure,
                "hostname": row.hostname,
                "path": row.path,
                "tls": row.tls,
                "enabled": row.enabled,
                "metadata": row.metadata or {},
            }
            for row in rows
            if row is not None
        ]


class ServiceEndpointAPIView(ServiceConfigBaseAPIView):
    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        return Response({"results": EndpointSerializer(service.endpoints.order_by("name"), many=True).data})

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        data = request.data
        name = str(data.get("name") or "").strip()
        if not name:
            return Response({"error": "name is required."}, status=400)
        try:
            target = int(data.get("target_port"))
            if not 1 <= target <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "target_port must be between 1 and 65535."}, status=400)
        protocol = str(data.get("protocol") or ServiceEndpoint.Protocol.HTTP).lower()
        allowed_protocols = {choice[0] for choice in ServiceEndpoint.Protocol.choices}
        if protocol not in allowed_protocols:
            return Response({"error": "Invalid protocol.", "allowed": sorted(allowed_protocols)}, status=400)
        exposure = str(data.get("exposure") or ServiceEndpoint.Exposure.PUBLIC).lower()
        allowed_exposures = {choice[0] for choice in ServiceEndpoint.Exposure.choices}
        if exposure not in allowed_exposures:
            return Response({"error": "Invalid exposure.", "allowed": sorted(allowed_exposures)}, status=400)
        published = data.get("published_port")
        if published not in (None, ""):
            try:
                published = int(published)
                if not 1 <= published <= 65535:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({"error": "published_port must be between 1 and 65535."}, status=400)
        endpoint, _ = ServiceEndpoint.objects.update_or_create(
            service=service,
            name=name,
            defaults={
                "process_id": data.get("process") or None,
                "target_port": target,
                "published_port": published,
                "protocol": protocol,
                "exposure": exposure,
                "hostname": str(data.get("hostname") or ""),
                "path": str(data.get("path") or ""),
                "tls": bool(data.get("tls")),
                "enabled": bool(data.get("enabled", True)),
                "metadata": dict(data.get("metadata") or {}),
            },
        )
        return Response(EndpointSerializer(endpoint).data, status=200)

    def delete(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        name = str(request.query_params.get("name") or "").strip()
        endpoint = ServiceEndpoint.objects.filter(service=service, name=name).first()
        if endpoint is None:
            return Response({"error": "Endpoint not found."}, status=404)
        release_endpoint_port(endpoint)
        endpoint.delete()
        return Response(status=204)




class ServiceNetworksAPIView(ServiceConfigBaseAPIView):
    """Manage a Service's explicit network attachments."""

    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = ServiceNetworkAttachment.objects.filter(service=service).select_related("network").order_by("network__name")
        return Response({
            "results": [
                {
                    "id": str(row.pk),
                    "network": str(row.network_id),
                    "network_name": row.network.name,
                    "docker_name": row.network.get_docker_network_name(),
                    "alias": row.alias,
                    "internal": row.internal,
                    "metadata": row.metadata or {},
                }
                for row in rows
            ]
        })

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_network_change")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        network_id = request.data.get("network")
        network = get_object_or_404(PrivateNetwork, pk=network_id, user=service.user)
        row, _ = ServiceNetworkAttachment.objects.update_or_create(
            service=service,
            network=network,
            defaults={
                "alias": str(request.data.get("alias") or "")[:128],
                "internal": str(request.data.get("internal", False)).lower() in {"1", "true", "yes", "on"},
                "metadata": dict(request.data.get("metadata") or {}),
            },
        )
        return Response({
            "id": str(row.pk),
            "network": str(network.pk),
            "network_name": network.name,
            "docker_name": network.get_docker_network_name(),
            "alias": row.alias,
            "internal": row.internal,
            "metadata": row.metadata or {},
        }, status=200)

    def delete(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_network_change")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        network_id = request.query_params.get("network")
        deleted, _ = ServiceNetworkAttachment.objects.filter(service=service, network_id=network_id).delete()
        if not deleted:
            return Response({"error": "Network attachment not found."}, status=404)
        return Response(status=204)


class ServiceDatabaseBindingsAPIView(ServiceConfigBaseAPIView):
    """Expose managed DB resources and Service-to-DB bindings."""

    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = ServiceDatabaseBinding.objects.filter(service=service).select_related("database", "database__provider_service")
        return Response({
            "results": [
                {
                    "id": str(row.pk),
                    "database": str(row.database_id),
                    "database_name": row.database.name,
                    "engine": row.database.engine,
                    "host": row.database.host,
                    "port": row.database.port,
                    "database_name_runtime": row.database.database_name,
                    "alias": row.alias,
                    "env_prefix": row.env_prefix,
                    "access_mode": row.access_mode,
                    "provider_service": str(row.database.provider_service_id) if row.database.provider_service_id else None,
                }
                for row in rows
            ]
        })

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        database_id = request.data.get("database")
        database = get_object_or_404(
            DatabaseResource.objects.filter(owner=service.user),
            pk=database_id,
        )
        row, _ = ServiceDatabaseBinding.objects.update_or_create(
            service=service,
            database=database,
            alias=str(request.data.get("alias") or "default")[:64],
            defaults={
                "env_prefix": str(request.data.get("env_prefix") or "DB")[:32],
                "access_mode": str(request.data.get("access_mode") or "rw")[:16],
                "metadata": dict(request.data.get("metadata") or {}),
            },
        )
        return Response({
            "id": str(row.pk),
            "database": str(database.pk),
            "database_name": database.name,
            "engine": database.engine,
            "alias": row.alias,
            "env_prefix": row.env_prefix,
            "access_mode": row.access_mode,
        }, status=200)

    def delete(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        alias = str(request.query_params.get("alias") or "default")
        deleted, _ = ServiceDatabaseBinding.objects.filter(service=service, alias=alias).delete()
        if not deleted:
            return Response({"error": "Database binding not found."}, status=404)
        return Response(status=204)


class DatabaseResourceAPIView(ServiceConfigBaseAPIView):
    """List/create database resources from existing provider services."""

    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = DatabaseResource.objects.filter(owner=service.user).select_related("provider_service").order_by("name")
        return Response({
            "results": [
                {
                    "id": str(row.pk),
                    "name": row.name,
                    "engine": row.engine,
                    "host": row.host,
                    "port": row.port,
                    "database_name": row.database_name,
                    "provider_service": str(row.provider_service_id) if row.provider_service_id else None,
                    "status": row.status,
                    "access_policy": row.access_policy or {},
                }
                for row in rows
            ]
        })

    def post(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        provider_id = request.data.get("provider_service")
        provider = None
        if provider_id:
            provider = get_object_or_404(Service, pk=provider_id, user=service.user)
        name = str(request.data.get("name") or "").strip()
        engine = str(request.data.get("engine") or "").strip().lower()
        allowed = {choice[0] for choice in DatabaseResource.Engine.choices}
        if not name or engine not in allowed:
            return Response({"error": "name and a valid engine are required.", "allowed_engines": sorted(allowed)}, status=400)
        resource, _ = DatabaseResource.objects.update_or_create(
            owner=service.user,
            name=name,
            defaults={
                "engine": engine,
                "provider_service": provider,
                "host": str(request.data.get("host") or ""),
                "port": int(request.data["port"]) if request.data.get("port") not in (None, "") else None,
                "database_name": str(request.data.get("database_name") or ""),
                "access_policy": dict(request.data.get("access_policy") or {}),
                "metadata": dict(request.data.get("metadata") or {}),
                "status": str(request.data.get("status") or ("provisioned" if provider else "external")),
            },
        )
        return Response({
            "id": str(resource.pk),
            "name": resource.name,
            "engine": resource.engine,
            "provider_service": str(provider.pk) if provider else None,
            "status": resource.status,
        }, status=200)
\n\nclass ServiceRevisionAPIView(ServiceConfigBaseAPIView):
    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = ServiceRevision.objects.filter(service=service).order_by("-revision_number")
        return Response(
            {
                "results": [
                    {
                        "id": str(row.pk),
                        "revision": row.revision_number,
                        "state": row.state,
                        "created_at": row.created_at,
                        "activated_at": row.activated_at,
                        "source": row.source_snapshot,
                        "build": row.build_snapshot,
                        "runtime": row.runtime_snapshot,
                        "environment": {
                            key: {"scope": item.get("scope")}
                            for key, item in (row.environment_snapshot or {}).items()
                        },
                        "processes": row.process_snapshot,
                        "endpoints": row.endpoint_snapshot,
                        "volumes": row.volume_snapshot,
                        "networks": row.network_snapshot,
                        "secret_keys": row.secret_keys,
                    }
                    for row in rows
                ]
            }
        )


class ServiceRevisionDetailAPIView(ServiceConfigBaseAPIView):
    def get(self, request, service_id, revision_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        revision = get_object_or_404(ServiceRevision, pk=revision_id, service=service)
        return Response(
            {
                "id": str(revision.pk),
                "revision": revision.revision_number,
                "state": revision.state,
                "created_at": revision.created_at,
                "activated_at": revision.activated_at,
                "graph": revision.graph_snapshot,
                "secret_keys": revision.secret_keys,
                "config": revision.config_snapshot,
                "runtime_graph": {
                    "source": revision.source_snapshot,
                    "build": revision.build_snapshot,
                    "runtime": revision.runtime_snapshot,
                    "environment": revision.environment_snapshot,
                    "processes": revision.process_snapshot,
                    "endpoints": revision.endpoint_snapshot,
                    "volumes": revision.volume_snapshot,
                    "networks": revision.network_snapshot,
                },
            }
        )


class ServiceRevisionRollbackAPIView(ServiceConfigBaseAPIView):
    def post(self, request, service_id, revision_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_deploy_add")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked
        revision = get_object_or_404(
            ServiceRevision.objects.select_related("source_deploy"),
            pk=revision_id,
            service=service,
        )
        platform = str(getattr(service.plan, "platform", "") or "").lower()
        requires_source_artifact = platform not in {"mysql", "mariadb", "postgresql", "postgres", "mongodb", "mongo", "redis", "oracle"}
        if requires_source_artifact and (revision.source_deploy is None or not revision.source_deploy.zip_file):
            return Response(
                {"error": "This application revision has no deployable source artifact."},
                status=409,
            )

        current = service.selected_deploy_id
        name_base = f"{service.name}-rollback-{revision.revision_number}"
        name = name_base[:50]
        suffix = 2
        while Deploy.objects.filter(name=name).exists():
            tail = f"-{suffix}"
            name = f"{name_base[:50-len(tail)]}{tail}"
            suffix += 1

        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=service.pk)
            service_status = str(service.status).lower()
            if service_status in {"queued", "deploying", "stopping"}:
                return Response(
                    {"error": "Stop the service before requesting a revision rollback."},
                    status=409,
                )
            deploy = Deploy.objects.create(
                name=name,
                service=service,
                created_by=request.user,
                version=revision.revision_number,
                revision=revision,
                zip_file=(revision.source_deploy.zip_file.name if revision.source_deploy and revision.source_deploy.zip_file else None),
                config={"rollback_revision": str(revision.pk), "platform": getattr(service.plan, "platform", "docker")},
                previous_deploy_id=current,
            )
            now = __import__("django.utils.timezone", fromlist=["now"]).now()
            StateManager.transition_service(
                service.pk,
                SERVICE_STATUS_CHOICES.QUEUED,
                update_fields={"task_id": None, "deploy_started": now},
            )
            StateManager.transition_deploy(
                deploy.pk,
                "pending",
                update_fields={
                    "stage": "queued",
                    "progress": 0,
                    "status_message": f"Rollback to revision {revision.revision_number} queued.",
                    "previous_deploy_id": current,
                },
            )
            transaction.on_commit(lambda: deploy_task.delay(str(deploy.pk)))

        return Response(
            {
                "status": "queued",
                "deployment_id": str(deploy.pk),
                "revision": revision.revision_number,
            },
            status=202,
        )
