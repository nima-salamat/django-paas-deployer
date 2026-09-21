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
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, verbose_name=_("Plan"), on_delete=models.CASCADE)
    network = models.ForeignKey(
        PrivateNetwork, verbose_name=_("Private Network"),
        on_delete=models.SET_NULL, null=True, related_name="Service",
    )
    read_only = models.BooleanField(_("Read only"), default=not settings.DEBUG)

    selected_deploy = models.OneToOneField(
        "deploy.Deploy", verbose_name=_("Selected Deploy"),
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    active_revision = models.ForeignKey(
        "ServiceRevision", verbose_name=_("Active Revision"),
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="active_for_services",
    )
    selected_deploy_at = models.DateTimeField(blank=True, null=True)
    deploy_started = models.DateTimeField(blank=True, null=True)
    deployed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        _("Deploy Status"), choices=SERVICE_STATUS_CHOICES.choices,
        default=SERVICE_STATUS_CHOICES.STOPPED,
    )
    task_id = models.CharField(_("Task ID"), max_length=64, unique=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        selected_deploy_changed = False
        if self.pk and Service.objects.filter(pk=self.pk).exists():
            old = Service.objects.get(pk=self.pk)
            selected_deploy_changed = old.selected_deploy != self.selected_deploy
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

    def get_storage_quota_mb(self) -> int:
        plan = None
        try:
            plan = self.plan
        except Exception:
            pass
        if plan is None and getattr(self, "plan_id", None):
            plan = Plan.objects.filter(pk=self.plan_id).only("max_storage").first()
        try:
            gb = float(getattr(plan, "max_storage", 0) or 0) if plan else 0.0
        except (TypeError, ValueError):
            gb = 0.0
        return max(0, int(gb * 1024))

    def get_used_storage_mb(self, *, exclude_volume_id=None) -> int:
        sid = str(self.pk)
        qs = Volume.objects.filter(Q(service_id=self.pk) | Q(service_attachments__has_key=sid)).distinct()
        if exclude_volume_id:
            qs = qs.exclude(pk=exclude_volume_id)
        return int(qs.aggregate(s=Sum("size_mb"))["s"] or 0)

    def get_remaining_storage_mb(self, *, exclude_volume_id=None) -> int:
        return max(0, self.get_storage_quota_mb() - self.get_used_storage_mb(exclude_volume_id=exclude_volume_id))

    def storage_quota_summary(self) -> dict:
        quota = self.get_storage_quota_mb()
        used = self.get_used_storage_mb()
        return {
            "quota_mb": quota, "used_mb": used, "remaining_mb": max(0, quota - used),
            "quota_gb": round(quota / 1024, 2) if quota else 0,
            "used_gb": round(used / 1024, 2) if used else 0,
            "remaining_gb": round(max(0, quota - used) / 1024, 2) if quota else 0,
        }

    def can_allocate_storage(self, size_mb: int, *, exclude_volume_id=None) -> tuple[bool, str]:
        try:
            size = int(size_mb)
        except (TypeError, ValueError):
            return False, "Volume size must be a positive integer (MB)."
        if size <= 0:
            return False, "Volume size must be greater than zero."
        remaining = self.get_remaining_storage_mb(exclude_volume_id=exclude_volume_id)
        if size > remaining:
            return False, f"Not enough storage on this service plan. Requested {size} MB, remaining {remaining} MB (plan limit {self.get_storage_quota_mb()} MB)."
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

    def to_snapshot(self) -> dict:
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
    """Immutable executable snapshot for a Service deployment."""

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
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-revision_number",)
        constraints = [
            models.UniqueConstraint(fields=("service", "revision_number"), name="uniq_service_revision_number")
        ]

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            old = type(self).objects.filter(pk=self.pk).values("config_snapshot", "process_snapshot", "secret_keys", "revision_number", "service_id").first()
            if old and any([
                old["config_snapshot"] != self.config_snapshot,
                old["process_snapshot"] != self.process_snapshot,
                old["secret_keys"] != self.secret_keys,
                old["revision_number"] != self.revision_number,
                old["service_id"] != self.service_id,
            ]):
                raise ValidationError("ServiceRevision is immutable after creation.")
        super().save(*args, **kwargs)


class Volume(BaseModel):
    name = models.CharField(unique=True, max_length=32)
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)
    service = models.ForeignKey(Service, verbose_name=_("Service"), related_name="volumes", on_delete=models.SET_NULL, null=True, blank=True)
    service_attachments = models.JSONField(_("Service Attachments"), default=dict, blank=True)
    default_bind = models.CharField(_("Default Bind Directory"), max_length=255, blank=True, default="")
    default_mode = models.CharField(_("Default Mode"), max_length=255, choices=VOLUME_MODE_CHOICES.choices, default=VOLUME_MODE_CHOICES.READ_WRITE, blank=True)
    size_mb = models.PositiveIntegerField()

    class Meta:
        verbose_name = _("Volume")
        verbose_name_plural = _("Volumes")

    def clean(self):
        super().clean()
        attachments = self.service_attachments or {}
        if self.service_id:
            sid = str(self.service_id)
            self.service_attachments = {sid: attachments[sid]} if sid in attachments else {}
            ok, msg = self.service.can_allocate_storage(self.size_mb, exclude_volume_id=self.pk)
            if not ok:
                raise ValidationError({"size_mb": msg})
        elif attachments:
            self.service_attachments = {}

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.service_id:
            sid = str(self.service_id)
            att = dict(self.service_attachments or {})
            self.service_attachments = {sid: att[sid]} if sid in att else {}
        else:
            self.service_attachments = {}
        super().save(*args, **kwargs)

    def attach_to_service(self, service: Service, bind: str = None, mode: str = None):
        if str(service.user_id) != str(self.user_id):
            raise ValidationError(_("Volume and service must belong to the same user."))
        if self.service_id and str(self.service_id) != str(service.id):
            raise ValidationError(_("This volume is already attached to another service. Volumes cannot be shared between services."))
        ok, msg = service.can_allocate_storage(self.size_mb, exclude_volume_id=self.pk)
        if not ok:
            raise ValidationError(msg)
        self.service = service
        self.service_attachments = {str(service.id): {"bind": bind or self.default_bind or "/data", "mode": mode or self.default_mode or "rw", "attached_at": timezone.now().isoformat()}}
        self.save()

    def detach_from_service(self, service: Service = None):
        if service is not None and self.service_id and str(self.service_id) != str(service.id):
            return
        Volume.objects.filter(pk=self.pk).update(service_attachments={})
        self.service_attachments = {}
        self.refresh_from_db(fields=["service_attachments"])

    def release_from_service(self, service: Service = None):
        if service is not None and self.service_id and str(self.service_id) != str(service.id):
            return
        self.service = None
        self.service_attachments = {}
        self.save(update_fields=["service", "service_attachments"])

    def get_attached_services(self):
        return Service.objects.filter(pk=self.service_id) if self.service_id else Service.objects.none()

    def get_bind_for_service(self, service: Service):
        if not service or str(service.id) != str(self.service_id or ""):
            return self.default_bind
        return (self.service_attachments or {}).get(str(service.id), {}).get("bind", self.default_bind)

    def get_mode_for_service(self, service: Service):
        if not service or str(service.id) != str(self.service_id or ""):
            return self.default_mode
        return (self.service_attachments or {}).get(str(service.id), {}).get("mode", self.default_mode)

    def is_attached_to_service(self, service: Service):
        return bool(service and str(service.id) == str(self.service_id or ""))

    def is_mounted_on_service(self, service: Service = None) -> bool:
        if not self.service_id:
            return False
        if service is not None and str(service.id) != str(self.service_id):
            return False
        return str(self.service_id) in (self.service_attachments or {})

    def get_docker_volume_name(self):
        return f"vol-{self.id.hex[:8]}-{self.name}"

    def __str__(self):
        return f"Volume: {self.name} ({self.size_mb} MB)"


class ServiceShare(BaseModel):
    service = models.ForeignKey(Service, verbose_name=_("Service"), related_name="shares", on_delete=models.CASCADE)
    group = models.ForeignKey("messenger.Conversation", verbose_name=_("Shared with Group"), related_name="shared_services", on_delete=models.CASCADE, null=True, blank=True)
    target_user = models.ForeignKey(User, verbose_name=_("Shared with User"), related_name="received_service_shares", on_delete=models.CASCADE, null=True, blank=True)
    shared_by = models.ForeignKey(User, verbose_name=_("Shared by"), related_name="created_service_shares", on_delete=models.CASCADE)
    rules = models.JSONField(_("Permission Rules"), default=dict, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)
    note = models.CharField(_("Note"), max_length=255, blank=True, default="")
    expires_at = models.DateTimeField(_("Expires at"), null=True, blank=True)
    admin_only = models.BooleanField(_("Admins only"), default=False)
    preset = models.CharField(_("Preset"), max_length=32, blank=True, default="")

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
            raise ValidationError(_("Exactly one of group or target_user must be set."))
        if self.service_id and self.shared_by_id and str(self.service.user_id) != str(self.shared_by_id):
            raise ValidationError(_("Only the service owner can create a share."))

    def save(self, *args, **kwargs):
        self.full_clean()
        from services.share_permissions import normalize_rules
        self.rules = normalize_rules(self.rules)
        super().save(*args, **kwargs)

    def allows(self, action: str) -> bool:
        from services.share_permissions import normalize_rules
        rules = normalize_rules(self.rules or {})
        if action == "daily_deploy_limit":
            return int(rules.get(action) or 0) > 0
        return bool(rules.get(action, False))

    def __str__(self):
        target = self.group_id or self.target_user_id
        return f"Share({self.service_id} → {target})"


class ServiceShareMember(BaseModel):
    share = models.ForeignKey(ServiceShare, verbose_name=_("Share"), related_name="member_rules", on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name=_("Member"), related_name="service_share_member_rules", on_delete=models.CASCADE)
    rules = models.JSONField(_("Permission Rules"), default=dict, blank=True)
    is_enabled = models.BooleanField(_("Enabled"), default=True)

    class Meta:
        verbose_name = _("Service Share Member Rule")
        verbose_name_plural = _("Service Share Member Rules")
        constraints = [
            models.UniqueConstraint(fields=("share", "user"), name="service_share_member_unique_user"),
        ]

    def clean(self):
        super().clean()
        if self.share_id and self.user_id:
            share = self.share
            if share.group_id:
                from services.api.sharing import _group_member_ids
                if str(self.user_id) not in {str(uid) for uid in _group_member_ids(share.group_id)}:
                    raise ValidationError(_("Selected user is not a member of the shared group."))

    def save(self, *args, **kwargs):
        self.full_clean()
        from services.share_permissions import normalize_rules
        self.rules = normalize_rules(self.rules or {})
        super().save(*args, **kwargs)


# Keep legacy shell/session models and any additional models below this point.
