from __future__ import annotations

import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication

from deploy.models import Deploy
from deployments.celery.tasks import deploy as deploy_task
from deployments.core.state.manager import StateManager
from core.global_settings.config import SERVICE_STATUS_CHOICES, PlanTypeChoices
from services.models import (
    Service,
    ServiceEnvironmentVariable,
    ServiceEndpoint,
    ServiceRevision,
    ServiceSecret,
    PrivateNetwork,
    ServiceNetworkAttachment,
    DatabaseResource,
    DatabaseCredential,
    ServiceDatabaseBinding,
)
from services.revisioning import materialize_revision_config, _get_or_create_secret, redact_config, get_active_deploy
from services.share_permissions import assert_share_action, SharePermissionError
from services.ports import sync_endpoint_reservation, release_endpoint_port


_DATABASE_SERVICE_PORTS = {
    "mysql": 3306, "mariadb": 3306, "postgres": 5432, "postgresql": 5432,
    "mongodb": 27017, "mongo": 27017, "redis": 6379, "oracle": 1521,
}


def _database_engine_for_service(service: Service) -> str:
    engine = str(getattr(getattr(service, "plan", None), "platform", "") or "").strip().lower()
    return {"postgres": "postgresql", "mongo": "mongodb"}.get(engine, engine)


def _database_service_port(engine: str):
    return _DATABASE_SERVICE_PORTS.get(str(engine or "").strip().lower())


def _service_network_ids(service: Service) -> set:
    network_ids = set()
    if getattr(service, "network_id", None):
        network_ids.add(service.network_id)
    if getattr(service, "pk", None):
        network_ids.update(
            ServiceNetworkAttachment.objects.filter(service_id=service.pk)
            .values_list("network_id", flat=True)
        )
    return network_ids


def _services_share_private_network(service: Service, provider: Service) -> bool:
    return bool(_service_network_ids(service) & _service_network_ids(provider))


def _database_service_configuration(service: Service) -> dict:
    """Read the active DB deploy's config server-side; callers must redact credentials."""
    from deployments.common.config import parse_config

    deployment = get_active_deploy(service) or getattr(service, "selected_deploy", None)
    if deployment is None:
        return {}
    parsed = parse_config(getattr(deployment, "config", None))
    return parsed if isinstance(parsed, dict) else {}


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

        if service.source_kind == Service.SourceKind.CATALOG:
            protected = {"source_kind", "source_config"}
            changed = protected.intersection(data.keys())
            if changed:
                return Response(
                    {
                        "error": "Catalog-managed service provenance is controlled by its Ready App.",
                        "code": "catalog_service_managed",
                        "fields": sorted(changed),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

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
                from services.lifecycle import bump_lifecycle
                lifecycle_generation = bump_lifecycle(service.pk, desired_state=desired)
                service.desired_state = desired
                service.lifecycle_generation = lifecycle_generation
            service.save(update_fields=[
                "source_kind", "source_config", "build_config",
                "runtime_config", "desired_state", "lifecycle_generation", "updated_at",
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
        try:
            with transaction.atomic():
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
                        "enabled": str(data.get("enabled", True)).lower() in {"1", "true", "yes", "on"},
                        "metadata": dict(data.get("metadata") or {}),
                    },
                )
                sync_endpoint_reservation(endpoint)
        except Exception as exc:
            return Response(
                {"error": str(exc), "code": "host_port_unavailable"},
                status=409,
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
    """Expose managed DB bindings and Ready App database dependencies."""

    @staticmethod
    def _catalog_database_dependencies(request, service):
        """Describe DB child services that the installed Ready App already wires.

        Catalog applications intentionally use their declared service graph and
        runtime environment for in-app database connections. Those relationships
        are not ServiceDatabaseBinding rows, so expose safe metadata separately
        instead of incorrectly telling users that the app has no database.
        """
        if service.source_kind != Service.SourceKind.CATALOG:
            return []
        if str(service.user_id) != str(request.user.id):
            # Do not reveal sibling service topology to shared-service viewers.
            return []

        try:
            from app_catalog.models import ApplicationInstanceService
        except ImportError:
            return []

        app_service = (
            ApplicationInstanceService.objects
            .filter(service=service)
            .select_related("instance")
            .first()
        )
        if app_service is None:
            return []

        snapshot = app_service.instance.definition_snapshot or {}
        orchestration = snapshot.get("_application_orchestration") or {}
        specs = orchestration.get("services") or []
        current_spec = next(
            (
                item for item in specs
                if isinstance(item, dict)
                and str(item.get("key") or "") == str(app_service.service_key)
            ),
            None,
        )
        if not current_spec:
            return []

        dependency_keys = {
            str(key)
            for key in (current_spec.get("depends_on") or [])
            if str(key)
        }
        if not dependency_keys:
            return []

        engine_ports = {
            "mysql": 3306,
            "mariadb": 3306,
            "postgres": 5432,
            "postgresql": 5432,
            "mongodb": 27017,
            "redis": 6379,
            "oracle": 1521,
        }
        dependencies = (
            ApplicationInstanceService.objects
            .filter(
                instance=app_service.instance,
                service_key__in=dependency_keys,
                service__plan__plan_type=PlanTypeChoices.DB,
            )
            .select_related("service", "service__plan")
            .order_by("sequence", "service_key")
        )
        result = []
        for dependency in dependencies:
            database_service = dependency.service
            engine = str(database_service.plan.platform or "").strip().lower()
            env = {
                row.key.upper(): row
                for row in ServiceEnvironmentVariable.objects.filter(
                    service=database_service,
                    enabled=True,
                )
            }
            database_name = ""
            database_name_keys = {
                "mysql": ("MYSQL_DATABASE", "MARIADB_DATABASE"),
                "mariadb": ("MYSQL_DATABASE", "MARIADB_DATABASE"),
                "postgres": ("POSTGRES_DB",),
                "postgresql": ("POSTGRES_DB",),
                "mongodb": ("MONGO_INITDB_DATABASE",),
            }.get(engine, ())
            for key in database_name_keys:
                row = env.get(key)
                # Database names are metadata, not credentials. Never resolve a
                # secret-backed variable merely to display this information.
                if row is not None and not row.secret_id and str(row.value or "").strip():
                    database_name = str(row.value).strip()
                    break

            result.append({
                "service_id": str(database_service.pk),
                "service_key": dependency.service_key,
                "name": dependency.service_key,
                "engine": engine,
                # Ready App definitions use the service key as the internal DNS
                # alias (e.g. "mariadb" for WordPress's WORDPRESS_DB_HOST).
                "host": dependency.service_key,
                "port": engine_ports.get(engine),
                "database_name": database_name,
                "status": str(database_service.status or "unknown"),
                "connection_type": "ready_app_dependency",
                "managed_by": "ready_app",
            })
        return result

    def get(self, request, service_id):
        service = self.service(request, service_id)
        denied = self.assert_access(request, service, "can_view")
        if denied:
            return denied
        rows = (
            ServiceDatabaseBinding.objects.filter(service=service)
            .select_related("database", "database__provider_service")
            .order_by("alias")
        )
        return Response({
            "results": [
                {
                    "id": str(row.pk),
                    "database": str(row.database_id),
                    "database_name": row.database.name,
                    "engine": row.database.engine,
                    "host": row.database.host or (
                        row.database.provider_service.get_docker_service_name()
                        if row.database.provider_service_id else ""
                    ),
                    "port": row.database.port or (
                        _database_service_port(_database_engine_for_service(row.database.provider_service))
                        if row.database.provider_service_id else None
                    ),
                    "database_name_runtime": row.database.database_name,
                    "alias": row.alias,
                    "env_prefix": row.env_prefix,
                    "access_mode": row.access_mode,
                    "status": row.database.status,
                    "connection_type": "managed_binding",
                    "binding_status": "configured_unverified",
                    "provider_service": str(row.database.provider_service_id) if row.database.provider_service_id else None,
                }
                for row in rows
            ],
            "catalog_dependencies": self._catalog_database_dependencies(request, service),
        })
    @transaction.atomic
    def post(self, request, service_id):
        service = get_object_or_404(
            Service.objects.select_for_update(),
            pk=service_id,
        )
        denied = self.assert_access(request, service, "can_change_config")
        if denied:
            return denied
        blocked = self.assert_mutable(service)
        if blocked:
            return blocked

        database_ref = str(request.data.get("database") or "").strip()
        if not database_ref:
            return Response({"error": "database is required."}, status=400)

        alias = str(request.data.get("alias") or "default").strip()
        env_prefix = str(request.data.get("env_prefix") or "DB").strip().upper()
        access_mode = str(request.data.get("access_mode") or "rw").strip().lower()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", alias):
            return Response({"error": "Alias must start with a letter and contain only letters, digits, '_' or '-'."}, status=400)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", env_prefix):
            return Response({"error": "Environment prefix must start with a letter and contain only A-Z, digits or '_'."}, status=400)
        if access_mode not in {"rw", "ro"}:
            return Response({"error": "access_mode must be 'rw' or 'ro'."}, status=400)

        if ServiceDatabaseBinding.objects.filter(
            service=service,
            env_prefix=env_prefix,
        ).exclude(alias=alias).exists():
            return Response({
                "error": "That environment prefix is already used by another database binding on this service.",
                "code": "database_env_prefix_conflict",
            }, status=409)

        provider = None
        database = None
        if database_ref.startswith("service:"):
            from uuid import UUID
            from deployments.core.db_deployer import DB_PLATFORMS

            try:
                provider_id = UUID(database_ref.partition(":")[2])
            except (ValueError, TypeError, AttributeError):
                return Response({"error": "Invalid database service reference."}, status=400)

            provider = get_object_or_404(
                Service.objects.select_related("plan", "selected_deploy").filter(
                    user=service.user,
                    plan__plan_type=PlanTypeChoices.DB,
                ),
                pk=provider_id,
            )
            engine = _database_engine_for_service(provider)
            if provider.pk == service.pk:
                return Response({"error": "A service cannot use itself as its database."}, status=400)
            if provider.source_kind == Service.SourceKind.CATALOG:
                return Response({
                    "error": "This database is owned by a Ready App. Use the Ready App's declared dependency instead.",
                    "code": "ready_app_database_managed",
                }, status=409)
            if engine not in DB_PLATFORMS:
                return Response({"error": "The selected service does not use a supported database platform."}, status=400)
            if not _services_share_private_network(service, provider):
                return Response({
                    "error": "The application and database service must share a private network before they can be connected.",
                    "code": "database_network_mismatch",
                }, status=409)

            provider_config = _database_service_configuration(provider)
            database = DatabaseResource.objects.filter(provider_service=provider).first()
            if database is not None and database.owner_id != service.user_id:
                return Response({"error": "The selected database resource is not available to this service."}, status=404)

            if database is None:
                base_name = str(provider.name or "database").strip()[:64] or "database"
                resource_name = base_name
                if DatabaseResource.objects.filter(owner=service.user, name=resource_name).exists():
                    suffix = str(provider.pk).replace("-", "")[:8]
                    resource_name = f"{base_name[:64 - len(suffix) - 1]}-{suffix}"
                database = DatabaseResource.objects.create(
                    owner=service.user,
                    provider_service=provider,
                    name=resource_name,
                    engine=engine,
                    host=provider.get_docker_service_name(),
                    port=_database_service_port(engine),
                    database_name=str(provider_config.get("database") or "")[:128],
                    status=str(provider.status or "unknown")[:20],
                    metadata={"source": "database_service_binding"},
                )
        else:
            database = get_object_or_404(
                DatabaseResource.objects.select_related("provider_service"),
                owner=service.user,
                pk=database_ref,
            )
            provider = database.provider_service

        if provider is not None and provider.source_kind == Service.SourceKind.CATALOG:
            return Response({
                "error": "This database is owned by a Ready App. Use the Ready App's declared dependency instead.",
                "code": "ready_app_database_managed",
            }, status=409)
        if provider is not None:
            from deployments.core.db_deployer import DB_PLATFORMS
            if provider.user_id != service.user_id:
                return Response({"error": "The selected database provider is not owned by this service owner."}, status=404)
            if provider.plan.plan_type != PlanTypeChoices.DB or _database_engine_for_service(provider) not in DB_PLATFORMS:
                return Response({"error": "The selected resource provider is not a supported database service."}, status=400)

        if not database.host and not provider:
            return Response({"error": "The selected database resource has no host configured."}, status=400)
        if provider and not _services_share_private_network(service, provider):
            return Response({
                "error": "The application and database service must share a private network before they can be connected.",
                "code": "database_network_mismatch",
            }, status=409)

        policy = dict(database.access_policy or {})
        allowed = policy.get("allowed_service_ids") or policy.get("allowed_services")
        if allowed and str(service.pk) not in {str(item) for item in allowed}:
            return Response({"error": "This database resource does not allow this service."}, status=403)
        if bool(policy.get("read_only")) and access_mode == "rw":
            return Response({"error": "This database resource only permits read-only access."}, status=400)

        # The active database deployment is the credential source of truth even
        # when this provider already had a DatabaseResource row before binding.
        if provider is not None:
            provider_config = _database_service_configuration(provider)
            engine = _database_engine_for_service(provider)
            database.engine = engine
            database.host = provider.get_docker_service_name()
            database.port = _database_service_port(engine)
            configured_name = str(provider_config.get("database") or "").strip()
            if configured_name:
                database.database_name = configured_name[:128]
            database.status = str(provider.status or database.status or "unknown")[:20]
            database.save(update_fields=["engine", "host", "port", "database_name", "status", "updated_at"])

            username = str(provider_config.get("username") or "")
            password = str(provider_config.get("password") or "")
            if username or password:
                credential, created = DatabaseCredential.objects.get_or_create(database=database)
                credential.username = username or credential.username
                if password and (created or credential.get_password() != password):
                    credential.set_password(password)
                    if not created:
                        credential.version += 1
                credential.save(update_fields=["username", "password_ciphertext", "version", "updated_at"])

        with transaction.atomic():
            Service.objects.select_for_update().get(pk=service.pk)
            existing = (
                ServiceDatabaseBinding.objects.select_for_update()
                .filter(service=service, alias=alias)
                .first()
            )
            if existing:
                ServiceDatabaseBinding.objects.filter(
                    service=service, alias=alias,
                ).exclude(pk=existing.pk).delete()
                existing.database = database
                existing.env_prefix = env_prefix
                existing.access_mode = access_mode
                existing.save(update_fields=["database", "env_prefix", "access_mode", "updated_at"])
                row = existing
            else:
                row = ServiceDatabaseBinding.objects.create(
                    service=service,
                    database=database,
                    alias=alias,
                    env_prefix=env_prefix,
                    access_mode=access_mode,
                )

        return Response({
            "id": str(row.pk),
            "database": str(database.pk),
            "database_name": database.name,
            "engine": database.engine,
            "host": database.host or (provider.get_docker_service_name() if provider else ""),
            "port": database.port or (_database_service_port(_database_engine_for_service(provider)) if provider else None),
            "alias": row.alias,
            "env_prefix": row.env_prefix,
            "access_mode": row.access_mode,
            "provider_service": str(provider.pk) if provider else None,
            "status": database.status,
            "binding_status": "configured_unverified",
        })
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

        from deployments.core.db_deployer import DB_PLATFORMS

        rows = (
            DatabaseResource.objects.filter(owner=service.user)
            .select_related("provider_service", "provider_service__plan")
            .order_by("name")
        )
        results = []
        existing_provider_ids = set()
        for row in rows:
            provider = row.provider_service
            if provider is not None and (
                provider.user_id != service.user_id
                or provider.source_kind == Service.SourceKind.CATALOG
                or provider.plan.plan_type != PlanTypeChoices.DB
            ):
                # Do not offer invalid or Ready-App-owned providers as manual resources.
                continue
            if provider is not None:
                existing_provider_ids.add(str(provider.pk))
            host = row.host or (provider.get_docker_service_name() if provider else "")
            port = row.port or (_database_service_port(_database_engine_for_service(provider)) if provider else None)
            connectable = bool(host) and (
                provider is None or _services_share_private_network(service, provider)
            )
            results.append({
                "id": str(row.pk),
                "name": row.name,
                "engine": row.engine,
                "host": host,
                "port": port,
                "database_name": row.database_name,
                "provider_service": str(row.provider_service_id) if row.provider_service_id else None,
                "status": str(provider.status if provider else row.status or "unknown"),
                "access_policy": row.access_policy or {},
                "resource_type": "managed_resource",
                "connectable": connectable,
                "connection_issue": (
                    "Attach this service and the database service to the same private network before connecting."
                    if provider is not None and not connectable
                    else "The database resource has no host configured."
                    if not host else ""
                ),
            })

        db_services = (
            Service.objects.filter(user=service.user, plan__plan_type=PlanTypeChoices.DB)
            .exclude(pk=service.pk)
            .exclude(source_kind=Service.SourceKind.CATALOG)
            .select_related("plan", "selected_deploy")
            .order_by("name")
        )
        for provider in db_services:
            engine = _database_engine_for_service(provider)
            if engine not in DB_PLATFORMS or str(provider.pk) in existing_provider_ids:
                continue
            config = _database_service_configuration(provider)
            host = provider.get_docker_service_name()
            connectable = _services_share_private_network(service, provider)
            results.append({
                "id": f"service:{provider.pk}",
                "name": provider.name,
                "engine": engine,
                "host": host,
                "port": _database_service_port(engine),
                "database_name": str(config.get("database") or ""),
                "provider_service": str(provider.pk),
                "status": str(provider.status or "unknown"),
                "resource_type": "database_service",
                "connectable": connectable,
                "connection_issue": (
                    ""
                    if connectable
                    else "Attach this service and the database service to the same private network before connecting."
                ),
            })
        results.sort(key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")))
        # Preserve the historical array response shape used by existing clients.
        return Response(results)
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
            provider = get_object_or_404(
                Service.objects.select_related("plan"),
                pk=provider_id,
                user=service.user,
            )
            if provider.source_kind == Service.SourceKind.CATALOG:
                return Response({
                    "error": "Ready App database dependencies are managed by the app catalog.",
                    "code": "ready_app_database_managed",
                }, status=409)
            from deployments.core.db_deployer import DB_PLATFORMS
            if provider.plan.plan_type != PlanTypeChoices.DB or _database_engine_for_service(provider) not in DB_PLATFORMS:
                return Response({"error": "provider_service must reference a supported database service."}, status=400)
        name = str(request.data.get("name") or "").strip()
        engine = str(request.data.get("engine") or "").strip().lower()
        allowed = {choice[0] for choice in DatabaseResource.Engine.choices}
        if not name or engine not in allowed:
            return Response({"error": "name and a valid engine are required.", "allowed_engines": sorted(allowed)}, status=400)
        if provider is not None and engine != _database_engine_for_service(provider):
            return Response({"error": "The resource engine must match the provider database service platform."}, status=400)
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

class ServiceRevisionAPIView(ServiceConfigBaseAPIView):
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
        if requires_source_artifact and not revision.artifact_file:
            return Response(
                {"error": "This application revision has no deployable source artifact."},
                status=409,
            )

        active_deploy = get_active_deploy(service)
        current = active_deploy.pk if active_deploy else None
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
                zip_file=(revision.artifact_file.name if revision.artifact_file else None),
                config={"rollback_revision": str(revision.pk), "platform": getattr(service.plan, "platform", "docker")},
                previous_deploy_id=current,
            )
            now = __import__("django.utils.timezone", fromlist=["now"]).now()
            from services.lifecycle import bump_lifecycle
            lifecycle_generation = bump_lifecycle(service.pk, desired_state="running")
            service.desired_state = "running"
            service.lifecycle_generation = lifecycle_generation

            StateManager.transition_service(
                service.pk,
                SERVICE_STATUS_CHOICES.QUEUED,
                update_fields={
                    "task_id": None,
                    "deploy_started": now,
                    "desired_state": "running",
                    "lifecycle_generation": lifecycle_generation,
                },
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
