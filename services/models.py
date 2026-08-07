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
    deploy_started = models.DateTimeField(blank=True, null=True)
    deployed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        _("Deploy Status"),
        choices=SERVICE_STATUS_CHOICES.choices,
        default=SERVICE_STATUS_CHOICES.STOPPED,
    )

    task_id = models.CharField(_("Task ID"), max_length=64, unique=True, null=True, blank=True)

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
        try:
            gb = float(getattr(self.plan, "max_storage", 0) or 0)
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
            # Drop any other keys
            if set(attachments.keys()) - {sid}:
                self.service_attachments = {
                    sid: attachments.get(sid)
                    or {
                        "bind": self.default_bind or "/data",
                        "mode": self.default_mode or "rw",
                    }
                }
            # Quota check when assigned to a service
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
        # Keep attachments consistent with exclusive ownership
        if self.service_id:
            sid = str(self.service_id)
            att = dict(self.service_attachments or {})
            if sid not in att:
                att = {
                    sid: {
                        "bind": self.default_bind or "/data",
                        "mode": self.default_mode or "rw",
                        "attached_at": timezone.now().isoformat(),
                    }
                }
            else:
                # Keep only this service key
                att = {sid: att[sid]}
            self.service_attachments = att
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
        """
        if service is not None and self.service_id and str(self.service_id) != str(service.id):
            return
        # Keep self.service — ownership & quota stay on this service
        self.service_attachments = {}
        self.save(update_fields=["service_attachments"])

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
