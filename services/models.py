from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from plans.models import Plan
from users.models import User
from core.base.BaseModel import BaseModel
from django.conf import settings

from core.global_settings.config import SERVICE_STATUS_CHOICES, VOLUME_MODE_CHOICES


class PrivateNetwork(BaseModel):
    name = models.CharField(_("Name"), max_length=50)
    user = models.ForeignKey(User, verbose_name=_("User Network"), on_delete=models.CASCADE)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("Private Network")
        verbose_name_plural = _("Private Networks")

    def __str__(self):
        return self.name

    def get_docker_network_name(self):
        return f"net-{self.id.hex[:8]}-{self.name}"


class Service(BaseModel):
    name = models.CharField(_("Name"), max_length=30, unique=True)
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
    )
    plan = models.ForeignKey(
        Plan,
        verbose_name=_("Plan"),
        on_delete=models.CASCADE,
    )
    network = models.ForeignKey(
        PrivateNetwork,
        verbose_name=_("Private Network"),
        on_delete=models.SET_NULL,
        null=True,
        related_name="Service",
    )

    read_only = models.BooleanField(_("Read only"), default=not (settings.DEBUG))

    selected_deploy = models.OneToOneField(
        "deploy.Deploy",
        verbose_name=_("Selected Deploy"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    selected_deploy_at = models.DateTimeField(blank=True, null=True)
    active_revision = models.ForeignKey(
        "ServiceRevision",
        verbose_name=_("Active Revision"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_services",
    )
    deploy_started = models.DateTimeField(blank=True, null=True)
    deployed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        _("Deploy Status"),
        choices=SERVICE_STATUS_CHOICES.choices,
        default=SERVICE_STATUS_CHOICES.STOPPED,
    )

    task_id = models.CharField(_("Task ID"), max_length=64, unique=True, null=True, blank=True)

    class SourceKind(models.TextChoices):
        ARCHIVE = "archive", _("Archive")
        GIT = "git", _("Git")
        DOCKERFILE = "dockerfile", _("Dockerfile")
        IMAGE = "image", _("Existing image")
        COMPOSE = "compose", _("Compose")
        CATALOG = "catalog", _("Catalog")
        GENERATED = "generated", _("Generated")

    source_kind = models.CharField(
        _("Source Kind"), max_length=20, choices=SourceKind.choices,
        default=SourceKind.ARCHIVE,
    )
    source_config = models.JSONField(
        _("Source Configuration"), default=dict, blank=True,
        help_text=_("Normalized source metadata. No runtime Docker state belongs here."),
    )
    build_config = models.JSONField(
        _("Build Configuration"), default=dict, blank=True,
    )
    runtime_config = models.JSONField(
        _("Runtime Configuration"), default=dict, blank=True,
    )
    desired_state = models.CharField(
        _("Desired State"), max_length=16,
        choices=(("stopped", _("Stopped")), ("running", _("Running")), ("deleted", _("Deleted"))),
        default="stopped",
    )

    def save(self, *args, **kwargs):
        self.full_clean()

        selected_deploy_changed = False

        if self.pk and Service.objects.filter(pk=self.pk).exists():
            old = Service.objects.get(pk=self.pk)
            if old.selected_deploy != self.selected_deploy:
                selected_deploy_changed = True
        else:
            selected_deploy_changed = bool(self.selected_deploy)

        if selected_deploy_changed:
            self.selected_deploy_at = timezone.now()
        super().save(*args, **kwargs)

    def get_docker_service_name(self):
        return f"app-{self.id.hex[:8]}-{self.name.lower()}"

    @property
    def get_service_name(self):
        return self.get_docker_service_name()

    # ------------------------------------------------------------------
    # Storage quota helpers (plan.max_storage is GB → MB)
    # ------------------------------------------------------------------

    def get_storage_quota_mb(self) -> int:
        """Plan max_storage is in GB. Convert to MiB (1024-based)."""
        plan = None
        try:
            plan = self.plan
        except Exception:
            plan = None
        if plan is None:
            try:
                plan_id = getattr(self, "plan_id", None)
                if plan_id:
                    from plans.models import Plan
                    plan = Plan.objects.filter(pk=plan_id).only("max_storage").first()
            except Exception:
                plan = None
        try:
            gb = float(getattr(plan, "max_storage", 0) or 0) if plan is not None else 0.0
        except (TypeError, ValueError):
            gb = 0.0
        return max(0, int(gb * 1024))

    def get_used_storage_mb(self, *, exclude_volume_id=None) -> int:
        """
        Sum of size_mb of EVERY volume owned by this service.

        CRITICAL quota rule (same as Railway / Render persistent disks):
          - Ownership is Volume.service_id == this.id.
          - Soft-detached volumes (service_attachments cleared, FK kept)
            STILL count toward the plan limit.
          - Only hard-release (service=None) or permanent delete frees quota.
          - Attach vs detach does NOT change the sum — both are included.
          - Also includes any legacy row that still lists this service in
            service_attachments.
        """
        from django.db.models import Q

        sid = str(self.pk)
        qs = Volume.objects.filter(
            Q(service_id=self.pk) | Q(service_attachments__has_key=sid)
        ).distinct()
        if exclude_volume_id:
            qs = qs.exclude(pk=exclude_volume_id)
        total = qs.aggregate(s=Sum("size_mb"))["s"]
        return int(total or 0)

    def get_remaining_storage_mb(self, *, exclude_volume_id=None) -> int:
        quota = self.get_storage_quota_mb()
        used = self.get_used_storage_mb(exclude_volume_id=exclude_volume_id)
        return max(0, quota - used)

    def storage_quota_summary(self) -> dict:
        quota = self.get_storage_quota_mb()
        used = self.get_used_storage_mb()
        remaining = max(0, quota - used)
        return {
            "quota_mb": quota,
            "used_mb": used,
            "remaining_mb": remaining,
            "quota_gb": round(quota / 1024, 2) if quota else 0,
            "used_gb": round(used / 1024, 2) if used else 0,
            "remaining_gb": round(remaining / 1024, 2) if remaining else 0,
        }

    def can_allocate_storage(self, size_mb: int, *, exclude_volume_id=None) -> tuple[bool, str]:
        """Return (ok, error_message)."""
        try:
            size = int(size_mb)
        except (TypeError, ValueError):
            return False, "Volume size must be a positive integer (MB)."
        if size <= 0:
            return False, "Volume size must be greater than zero."
        remaining = self.get_remaining_storage_mb(exclude_volume_id=exclude_volume_id)
        if size > remaining:
            return (
                False,
                (
                    f"Not enough storage on this service plan. "
                    f"Requested {size} MB, remaining {remaining} MB "
                    f"(plan limit {self.get_storage_quota_mb()} MB)."
                ),
            )
        return True, ""

    def __str__(self):
        return f"Service: {self.name}"




class ServiceProcess(BaseModel):
    """Mutable desired process definition owned by a Service."""
    service = models.ForeignKey(Service, related_name="processes", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    process_type = models.CharField(max_length=32, default="custom")
    command = models.TextField(blank=True, null=True)
    entrypoint = models.TextField(blank=True, null=True)
    replicas = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    environment = models.JSONField(default=dict, blank=True)
    healthcheck = models.JSONField(default=dict, blank=True)
    resources = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("created_at", "name")
        constraints = [
            models.UniqueConstraint(fields=("service", "name"), name="uniq_service_process_name")
        ]

    def to_snapshot(self):
        return {
            "name": self.name,
            "process_type": self.process_type,
            "command": self.command,
            "entrypoint": self.entrypoint,
            "replicas": self.replicas,
            "enabled": self.enabled,
            "environment": dict(self.environment or {}),
            "healthcheck": dict(self.healthcheck or {}),
            "resources": dict(self.resources or {}),
            "metadata": dict(self.metadata or {}),
        }


class ServiceRevision(BaseModel):
    """Immutable executable snapshot for a Service."""

    class State(models.TextChoices):
        CREATED = "created", _("Created")
        ACTIVE = "active", _("Active")
        SUPERSEDED = "superseded", _("Superseded")
        FAILED = "failed", _("Failed")

    service = models.ForeignKey(Service, related_name="revisions", on_delete=models.CASCADE)
    revision_number = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=State.choices, default=State.CREATED)
    source_deploy = models.ForeignKey(
        "deploy.Deploy", related_name="source_revisions",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_by = models.ForeignKey(
        User, related_name="service_revisions",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    config_snapshot = models.JSONField(default=dict)
    process_snapshot = models.JSONField(default=list)
    secret_keys = models.JSONField(default=list)
    secret_refs = models.JSONField(default=list, blank=True)
    source_snapshot = models.JSONField(default=dict, blank=True)
    build_snapshot = models.JSONField(default=dict, blank=True)
    runtime_snapshot = models.JSONField(default=dict, blank=True)
    environment_snapshot = models.JSONField(default=dict, blank=True)
    endpoint_snapshot = models.JSONField(default=list, blank=True)
    volume_snapshot = models.JSONField(default=list, blank=True)
    network_snapshot = models.JSONField(default=list, blank=True)
    graph_snapshot = models.JSONField(default=dict, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-revision_number",)
        constraints = [
            models.UniqueConstraint(fields=("service", "revision_number"), name="uniq_service_revision_number")
        ]

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            old = type(self).objects.filter(pk=self.pk).values(
                "config_snapshot", "process_snapshot", "secret_keys", "secret_refs",
                "source_snapshot", "build_snapshot", "runtime_snapshot",
                "environment_snapshot", "endpoint_snapshot", "volume_snapshot",
                "network_snapshot", "graph_snapshot", "revision_number", "service_id",
            ).first()
            if old and any([
                old["config_snapshot"] != self.config_snapshot,
                old["process_snapshot"] != self.process_snapshot,
                old["secret_keys"] != self.secret_keys,
                old["secret_refs"] != self.secret_refs,
                old["source_snapshot"] != self.source_snapshot,
                old["build_snapshot"] != self.build_snapshot,
                old["runtime_snapshot"] != self.runtime_snapshot,
                old["environment_snapshot"] != self.environment_snapshot,
                old["endpoint_snapshot"] != self.endpoint_snapshot,
                old["volume_snapshot"] != self.volume_snapshot,
                old["network_snapshot"] != self.network_snapshot,
                old["graph_snapshot"] != self.graph_snapshot,
                old["revision_number"] != self.revision_number,
                old["service_id"] != self.service_id,
            ]):
                raise ValidationError("ServiceRevision is immutable after creation.")
        super().save(*args, **kwargs)




class ServiceEnvironmentVariable(BaseModel):
    """Non-secret or secret-backed environment variable owned by a Service."""
    class Scope(models.TextChoices):
        BUILD = "build", _("Build")
        RUNTIME = "runtime", _("Runtime")
        BOTH = "both", _("Build and runtime")

    service = models.ForeignKey(Service, related_name="environment_variables", on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    value = models.TextField(blank=True, default="")
    secret = models.ForeignKey(
        "ServiceSecret", related_name="environment_variables",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.RUNTIME)
    enabled = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(fields=("service", "key"), name="uniq_service_environment_key")
        ]

    def resolve_value(self) -> str:
        if self.secret_id:
            return self.secret.get_current_value()
        return str(self.value or "")


class ServiceSecret(BaseModel):
    """Versioned encrypted secret container owned by a Service."""
    service = models.ForeignKey(Service, related_name="secrets", on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    current_version = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(fields=("service", "key"), name="uniq_service_secret_key")
        ]

    def get_current_value(self) -> str:
        version = self.versions.filter(version=self.current_version).first()
        if version is None:
            return ""
        return version.get_value()


class ServiceSecretVersion(BaseModel):
    """Immutable version of a ServiceSecret payload."""
    secret = models.ForeignKey(ServiceSecret, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    ciphertext = models.TextField()
    created_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_secret_versions",
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(fields=("secret", "version"), name="uniq_service_secret_version")
        ]

    def set_value(self, value: str):
        from services.secret_store import encrypt_secret
        self.ciphertext = encrypt_secret(str(value or ""))

    def get_value(self) -> str:
        from services.secret_store import decrypt_secret
        return decrypt_secret(self.ciphertext)


class ServiceEndpoint(BaseModel):
    """Desired endpoint declaration independent from Docker port publication."""
    class Exposure(models.TextChoices):
        PUBLIC = "public", _("Public")
        INTERNAL = "internal", _("Internal")

    class Protocol(models.TextChoices):
        HTTP = "http", _("HTTP")
        HTTPS = "https", _("HTTPS")
        TCP = "tcp", _("TCP")
        UDP = "udp", _("UDP")
        WS = "ws", _("WebSocket")

    service = models.ForeignKey(Service, related_name="endpoints", on_delete=models.CASCADE)
    process = models.ForeignKey(
        "ServiceProcess", related_name="endpoints",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    name = models.CharField(max_length=64)
    target_port = models.PositiveIntegerField()
    published_port = models.PositiveIntegerField(null=True, blank=True)
    protocol = models.CharField(max_length=16, choices=Protocol.choices, default=Protocol.HTTP)
    exposure = models.CharField(max_length=16, choices=Exposure.choices, default=Exposure.PUBLIC)
    hostname = models.CharField(max_length=255, blank=True, default="")
    path = models.CharField(max_length=255, blank=True, default="")
    tls = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("service", "name"), name="uniq_service_endpoint_name")
        ]

    @property
    def is_host_published(self) -> bool:
        return self.published_port is not None


class ServiceNetworkAttachment(BaseModel):
    """Many-to-many network attachment with an optional service alias."""
    service = models.ForeignKey(Service, related_name="network_attachments", on_delete=models.CASCADE)
    network = models.ForeignKey(PrivateNetwork, related_name="service_attachments", on_delete=models.CASCADE)
    alias = models.CharField(max_length=128, blank=True, default="")
    internal = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("service", "network"), name="uniq_service_network_attachment")
        ]


class DatabaseResource(BaseModel):
    """Managed database resource represented independently from workload Services."""
    class Engine(models.TextChoices):
        MYSQL = "mysql", _("MySQL")
        MARIADB = "mariadb", _("MariaDB")
        POSTGRESQL = "postgresql", _("PostgreSQL")
        MONGODB = "mongodb", _("MongoDB")
        REDIS = "redis", _("Redis")
        ORACLE = "oracle", _("Oracle")

    owner = models.ForeignKey(User, related_name="database_resources", on_delete=models.CASCADE)
    provider_service = models.OneToOneField(
        Service, related_name="database_resource", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    name = models.CharField(max_length=64)
    engine = models.CharField(max_length=32, choices=Engine.choices)
    host = models.CharField(max_length=255, blank=True, default="")
    port = models.PositiveIntegerField(null=True, blank=True)
    database_name = models.CharField(max_length=128, blank=True, default="")
    access_policy = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="provisioning")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("owner", "name"), name="uniq_database_resource_owner_name")
        ]


class ServiceDatabaseBinding(BaseModel):
    """Connects a workload Service to a managed DatabaseResource."""
    service = models.ForeignKey(Service, related_name="database_bindings", on_delete=models.CASCADE)
    database = models.ForeignKey(DatabaseResource, related_name="bindings", on_delete=models.CASCADE)
    alias = models.CharField(max_length=64, default="default")
    env_prefix = models.CharField(max_length=32, default="DB")
    access_mode = models.CharField(max_length=16, default="rw")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("service", "database", "alias"), name="uniq_service_database_binding")
        ]

class Volume(BaseModel):
    """
    Docker volume owned by at most ONE service (exclusive).

    - Volumes do NOT share between services.
    - A service may have multiple volumes.
    - Total size_mb of volumes for a service must not exceed plan.max_storage (GB → MB).
    - service_attachments keeps bind/mode for the owning service only
      (single key = str(service.id)).
    """

    name = models.CharField(unique=True, max_length=32)
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
    )
    # Exclusive ownership — one service only (null = unused / orphan)
    service = models.ForeignKey(
        Service,
        verbose_name=_("Service"),
        related_name="volumes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Owning service. Volumes cannot be shared across services."),
    )
    # bind/mode for the owning service only: { "<service_id>": {"bind": "...", "mode": "rw"} }
    service_attachments = models.JSONField(
        _("Service Attachments"),
        default=dict,
        blank=True,
        help_text=_("Owning service ID → {bind, mode}. Only one service is allowed."),
    )
    default_bind = models.CharField(
        _("Default Bind Directory"), max_length=255, blank=True, default=""
    )
    default_mode = models.CharField(
        _("Default Mode"),
        max_length=255,
        choices=VOLUME_MODE_CHOICES.choices,
        default=VOLUME_MODE_CHOICES.READ_WRITE,
        blank=True,
    )
    size_mb = models.PositiveIntegerField()

    class Meta:
        verbose_name = _("Volume")
        verbose_name_plural = _("Volumes")

    def clean(self):
        super().clean()
        # Enforce exclusive ownership: attachments may only contain the owning service
        attachments = self.service_attachments or {}
        if self.service_id:
            sid = str(self.service_id)
            # Drop any foreign service keys; allow empty att = soft-detached
            if attachments:
                if sid in attachments:
                    self.service_attachments = {sid: attachments[sid]}
                else:
                    self.service_attachments = {}
            # Quota check when assigned to a service (mounted or soft-detached)
            ok, msg = self.service.can_allocate_storage(
                self.size_mb, exclude_volume_id=self.pk
            )
            if not ok:
                raise ValidationError({"size_mb": msg})
        else:
            # Unused volume: no attachments allowed
            if attachments:
                self.service_attachments = {}

    def save(self, *args, **kwargs):
        self.full_clean()
        # Keep attachments consistent with exclusive ownership.
        #
        # IMPORTANT: empty service_attachments + service_id set means
        # soft-detached (owned, counts toward quota, NOT mounted).
        # Do NOT auto-recreate attachment metadata on every save — that
        # made detach appear to succeed then immediately re-attach.
        if self.service_id:
            sid = str(self.service_id)
            att = dict(self.service_attachments or {})
            if att:
                # Keep only the owning service key; drop foreign keys
                if sid in att:
                    self.service_attachments = {sid: att[sid]}
                else:
                    # Stale keys only → treat as soft-detached
                    self.service_attachments = {}
            else:
                self.service_attachments = {}
        else:
            self.service_attachments = {}
        super().save(*args, **kwargs)

    def attach_to_service(self, service: Service, bind: str = None, mode: str = None):
        """
        Attach (or re-attach) exclusively to one service.
        Raises ValidationError if quota exceeded or ownership conflict.
        """
        if str(service.user_id) != str(self.user_id):
            raise ValidationError(_("Volume and service must belong to the same user."))

        # Already owned by a different service?
        if self.service_id and str(self.service_id) != str(service.id):
            raise ValidationError(
                _(
                    "This volume is already attached to another service. "
                    "Volumes cannot be shared between services."
                )
            )

        # Quota
        ok, msg = service.can_allocate_storage(
            self.size_mb, exclude_volume_id=self.pk
        )
        if not ok:
            raise ValidationError(msg)

        if bind is None:
            bind = self.default_bind or "/data"
        if mode is None:
            mode = self.default_mode or "rw"

        self.service = service
        self.service_attachments = {
            str(service.id): {
                "bind": bind,
                "mode": mode,
                "attached_at": timezone.now().isoformat(),
            }
        }
        self.save()

    def detach_from_service(self, service: Service = None):
        """
        Soft-detach: clear mount metadata but KEEP ownership (service FK).

        Quota is based on ownership, so size_mb still counts toward the
        service plan until the volume is released or deleted.

        Uses QuerySet.update to avoid any save()/clean() path that could
        re-populate service_attachments.
        """
        if service is not None and self.service_id and str(self.service_id) != str(service.id):
            return
        Volume.objects.filter(pk=self.pk).update(service_attachments={})
        self.service_attachments = {}
        # refresh in-memory
        try:
            self.refresh_from_db(fields=["service_attachments"])
        except Exception:
            pass

    def release_from_service(self, service: Service = None):
        """
        Hard-release: drop ownership so the volume no longer counts toward
        any service quota and can be attached elsewhere.
        """
        if service is not None and self.service_id and str(self.service_id) != str(service.id):
            return
        self.service = None
        self.service_attachments = {}
        self.save(update_fields=["service", "service_attachments"])

    def get_attached_services(self):
        """Return list of Service objects (0 or 1)."""
        if self.service_id:
            return Service.objects.filter(pk=self.service_id)
        return Service.objects.none()

    def get_bind_for_service(self, service: Service):
        if not service or str(service.id) != str(self.service_id or ""):
            return self.default_bind
        return (self.service_attachments or {}).get(str(service.id), {}).get(
            "bind", self.default_bind
        )

    def get_mode_for_service(self, service: Service):
        if not service or str(service.id) != str(self.service_id or ""):
            return self.default_mode
        return (self.service_attachments or {}).get(str(service.id), {}).get(
            "mode", self.default_mode
        )

    def is_attached_to_service(self, service: Service):
        """True if this service owns the volume (counts toward quota)."""
        return bool(service and str(service.id) == str(self.service_id or ""))

    def is_mounted_on_service(self, service: Service = None) -> bool:
        """True if mount metadata exists for the owner (or given) service."""
        if not self.service_id:
            return False
        if service is not None and str(service.id) != str(self.service_id):
            return False
        atts = self.service_attachments or {}
        return str(self.service_id) in atts

    def get_docker_volume_name(self):
        return f"vol-{self.id.hex[:8]}-{self.name}"

    def __str__(self):
        return f"Volume: {self.name} ({self.size_mb} MB)"


# ---------------------------------------------------------------------------
# Service Sharing (group / user sharing with fine-grained rules)
# ---------------------------------------------------------------------------

class ServiceShare(BaseModel):
    """
    Share a service with a messenger group (Conversation) or directly with a user.
    The owner retains full control; members can only perform actions allowed by `rules`.
    """
    service = models.ForeignKey(
        Service,
        verbose_name=_("Service"),
        related_name="shares",
        on_delete=models.CASCADE,
    )
    # Exactly one of group / target_user should be set
    group = models.ForeignKey(
        "messenger.Conversation",
        verbose_name=_("Shared with Group"),
        related_name="shared_services",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Messenger group this service is shared into."),
    )
    target_user = models.ForeignKey(
        User,
        verbose_name=_("Shared with User"),
        related_name="received_service_shares",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    shared_by = models.ForeignKey(
        User,
        verbose_name=_("Shared by"),
        related_name="created_service_shares",
        on_delete=models.CASCADE,
    )
    # Fine-grained permissions the recipients may exercise.
    # Example:
    # {
    #   "can_view": true,
    #   "can_start": true,
    #   "can_stop": true,
    #   "can_restart": false,
    #   "can_deploy": false,
    #   "can_view_logs": true,
    #   "can_view_metrics": true,
    #   "can_attach_volume": false,
    #   "can_change_config": false
    # }
    rules = models.JSONField(
        _("Permission Rules"),
        default=dict,
        blank=True,
        help_text=_("JSON map of allowed actions for recipients of this share."),
    )
    is_active = models.BooleanField(_("Active"), default=True)
    note = models.CharField(_("Note"), max_length=255, blank=True, default="")
    # Optional expiry — after this time the share is treated as inactive
    expires_at = models.DateTimeField(
        _("Expires at"),
        null=True,
        blank=True,
        help_text=_("When set, share stops applying after this timestamp."),
    )
    # When True, only group owner/admin may use the shared service (members see it but cannot act)
    admin_only = models.BooleanField(
        _("Admins only"),
        default=False,
        help_text=_("If set, only group owner/admin participants may exercise rules."),
    )
    preset = models.CharField(
        _("Preset"),
        max_length=32,
        blank=True,
        default="",
        help_text=_("Optional preset name: viewer, operator, developer, ops."),
    )

    class Meta:
        verbose_name = _("Service Share")
        verbose_name_plural = _("Service Shares")
        indexes = [
            models.Index(fields=["service", "is_active"]),
            models.Index(fields=["group", "is_active"]),
            models.Index(fields=["target_user", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(group__isnull=False, target_user__isnull=True)
                    | models.Q(group__isnull=True, target_user__isnull=False)
                ),
                name="service_share_exactly_one_target",
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.group_id) == bool(self.target_user_id):
            raise ValidationError(
                _("Exactly one of group or target_user must be set.")
            )
        if self.service_id and self.shared_by_id:
            if str(self.service.user_id) != str(self.shared_by_id):
                raise ValidationError(
                    _("Only the service owner can create a share.")
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        from services.share_permissions import normalize_rules
        self.rules = normalize_rules(self.rules)
        super().save(*args, **kwargs)

    def allows(self, action: str) -> bool:
        """Return True if the given action key is permitted by rules."""
        from services.share_permissions import normalize_rules
        rules = normalize_rules(self.rules or {})
        if action == "daily_deploy_limit":
            return int(rules.get(action) or 0) > 0
        return bool(rules.get(action, False))

    def __str__(self):
        target = self.group_id or self.target_user_id
        return f"Share({self.service_id} → {target})"



class ServiceShareMember(BaseModel):
    """
    Per-member permission overrides inside a group share.
    If no row exists for a participant, the parent ServiceShare.rules apply.
    """
    share = models.ForeignKey(
        ServiceShare,
        verbose_name=_("Share"),
        related_name="member_rules",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        User,
        verbose_name=_("Member"),
        related_name="service_share_member_rules",
        on_delete=models.CASCADE,
    )
    rules = models.JSONField(
        _("Permission Rules"),
        default=dict,
        blank=True,
        help_text=_("Overrides parent share rules for this member only."),
    )
    is_enabled = models.BooleanField(
        _("Enabled"),
        default=True,
        help_text=_("If false, this member has no access despite being in the group."),
    )

    class Meta:
        verbose_name = _("Service Share Member Rule")
        verbose_name_plural = _("Service Share Member Rules")
        unique_together = ("share", "user")
        indexes = [
            models.Index(fields=["share", "user"]),
        ]

    def __str__(self):
        return f"ShareMember {self.share_id} → {self.user_id}"

    def effective_rules(self):
        from services.share_permissions import normalize_rules
        base = normalize_rules(self.share.rules if self.share_id else {})
        if not self.is_enabled:
            return {k: False for k in base}
        over = normalize_rules(self.rules or {})
        # Member override wins for keys they set; we store full map usually
        return over if self.rules else base


class ServiceShareEvent(BaseModel):
    """
    Audit / activity events for a shared service.
    These are also posted as system messages into the messenger group.
    """
    share = models.ForeignKey(
        ServiceShare,
        related_name="events",
        on_delete=models.CASCADE,
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=64)  # start, stop, deploy, share, unshare, ...
    message = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Service Share Event")
        verbose_name_plural = _("Service Share Events")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.action} on share {self.share_id}"


class ShellSession(BaseModel):
    """Short-lived, single-user restricted shell session for a service."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        CLOSED = "closed", _("Closed")
        EXPIRED = "expired", _("Expired")

    service = models.ForeignKey("services.Service", on_delete=models.CASCADE, related_name="shell_sessions")
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="shell_sessions")
    token_hash = models.CharField(max_length=64, unique=True)
    platform = models.CharField(max_length=32)
    root_path = models.CharField(max_length=512, default="/app")
    workdir = models.CharField(max_length=512, default="/app")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("service", "status", "expires_at"))]
        # Concurrent active sessions are limited in application code via
        # SystemSetting ``shell.max_concurrent_sessions_per_service`` (Wagtail).

    def __str__(self):
        return f"Shell {self.service_id} / {self.user_id} / {self.status}"


class ShellAuditEvent(BaseModel):
    """Unified audit trail for every restricted-shell action.

    Commands, file edits, session lifecycle, and interactive PTY events all
    land here so the UI can show one chronological activity log.
    """

    class Action(models.TextChoices):
        SESSION_OPEN = "session_open", _("Session open")
        SESSION_CLOSE = "session_close", _("Session close")
        SESSION_REPLACE = "session_replace", _("Session replace")
        COMMAND = "command", _("Command")
        COMMAND_DRY_RUN = "command_dry_run", _("Command dry-run")
        FILE_READ = "file_read", _("File read")
        FILE_WRITE = "file_write", _("File write")
        FILE_DELETE = "file_delete", _("File delete")
        FILE_RENAME = "file_rename", _("File rename")
        FILE_MKDIR = "file_mkdir", _("File mkdir")
        INTERACTIVE_START = "interactive_start", _("Interactive start")
        INTERACTIVE_EXIT = "interactive_exit", _("Interactive exit")
        ENV_VIEW = "env_view", _("Env view")
        HEALTH_VIEW = "health_view", _("Health view")
        AUDIT_SEARCH = "audit_search", _("Audit search")
        AUDIT_DOWNLOAD = "audit_download", _("Audit download")

    service = models.ForeignKey(
        "services.Service", on_delete=models.CASCADE, related_name="shell_audit_events"
    )
    user = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="shell_audit_events"
    )
    session = models.ForeignKey(
        "services.ShellSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    command = models.TextField(blank=True, default="")
    path = models.CharField(max_length=1024, blank=True, default="")
    cwd = models.CharField(max_length=512, blank=True, default="")
    exit_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=True)
    detail = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)
    # Short stdout/stderr preview for forensics (not full output).
    output_preview = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("service", "-created_at")),
            models.Index(fields=("service", "action", "-created_at")),
            models.Index(fields=("user", "-created_at")),
        ]

    def __str__(self):
        return f"ShellAudit {self.action} service={self.service_id}"

