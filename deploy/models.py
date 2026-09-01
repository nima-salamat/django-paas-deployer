from django.db import models
from django.core.exceptions import ValidationError
from core.base.BaseModel import BaseModel
from services.models import Service
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


def zip_file_path(instance, filename):
    user_id = getattr(getattr(instance.service, "user", None), "id", "unknown")
    return f"deployments/{user_id}/{instance.name}/{filename}"

class DeploymentStatusChoices(models.TextChoices):
    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    SUCCEEDED = "succeeded", _("Succeeded")
    FAILED = "failed", _("Failed")
    ROLLING_BACK = "rolling_back", _("Rolling back")
    ROLLED_BACK = "rolled_back", _("Rolled back")
    CANCELLED = "cancelled", _("Cancelled")


class RollbackStatusChoices(models.TextChoices):
    NOT_REQUIRED = "not_required", _("Not required")
    PENDING = "pending", _("Pending")
    SUCCEEDED = "succeeded", _("Succeeded")
    FAILED = "failed", _("Failed")



class Deploy(BaseModel):
    name = models.CharField(verbose_name=_("Name"), max_length=50, unique=True)
    service = models.ForeignKey(Service, verbose_name=_("Service"), on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        "users.User",
        verbose_name=_("Created by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_deploys",
        help_text=_("User who uploaded this deploy (for share permission scoping)."),
    )
    version = models.DecimalField(_("Version"), max_digits=5, decimal_places=2, default=0.00, help_text=_("Deployment version, e.g., 1.0"))
    zip_file = models.FileField(verbose_name=_("ZIP File"), upload_to=zip_file_path, blank=True, null=True)
    config = models.JSONField(verbose_name=_("Configuration"), blank=True, null=True)
    started_at = models.DateTimeField(verbose_name=_("Start Time"), blank=True, null=True, editable=False)
    completed_at = models.DateTimeField(verbose_name=_("Completion Time"), blank=True, null=True, editable=False)
    updated_file_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        _("Deployment Status"),
        max_length=32,
        choices=DeploymentStatusChoices.choices,
        default=DeploymentStatusChoices.PENDING,
    )
    stage = models.CharField(_("Deployment Stage"), max_length=64, blank=True, default="idle")
    progress = models.PositiveSmallIntegerField(_("Deployment Progress"), default=0)
    status_message = models.TextField(_("Status Message"), blank=True, default="")
    error_message = models.TextField(_("Error Message"), blank=True, default="")
    rollback_status = models.CharField(
        _("Rollback Status"),
        max_length=32,
        choices=RollbackStatusChoices.choices,
        default=RollbackStatusChoices.NOT_REQUIRED,
    )
    health_status = models.CharField(_("Health Status"), max_length=64, blank=True, default="")
    container_status = models.CharField(_("Container Status"), max_length=64, blank=True, default="")
    image_status = models.CharField(_("Image Status"), max_length=64, blank=True, default="")
    volume_status = models.CharField(_("Volume Status"), max_length=64, blank=True, default="")
    network_status = models.CharField(_("Network Status"), max_length=64, blank=True, default="")
    cancel_requested = models.BooleanField(_("Cancel Requested"), default=False)
    MAX_ZIP_SIZE_MB = 100
    # Set by admin API path to skip the zip size cap for staff/superuser uploads
    skip_zip_size_limit = False

    class Meta:
        verbose_name = _("Deploy")
        verbose_name_plural = _("Deploy")
    
    def clean(self):
        super().clean()
        if getattr(self, "skip_zip_size_limit", False):
            return
        if self.zip_file and self.zip_file.size > self.MAX_ZIP_SIZE_MB * 1024 * 1024:
            raise ValidationError({
                "zip_file": _(f"ZIP file size must be under {self.MAX_ZIP_SIZE_MB} MB.")
            })
    
    def save(self, *args, **kwargs):
        skip = bool(kwargs.pop("skip_zip_size_limit", False) or getattr(self, "skip_zip_size_limit", False))
        if skip:
            self.skip_zip_size_limit = True
        self.full_clean()
        
        file_changed = False
        if self.pk and Deploy.objects.filter(pk=self.pk).exists():
            old = Deploy.objects.get(pk=self.pk)
            if old.zip_file != self.zip_file:
                file_changed = True
        else:
            file_changed = bool(self.zip_file)

        if file_changed:
            self.updated_file_at = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} (v{self.version})"


class DeployLog(BaseModel):
    # The event store lives in a separate database, so these identifiers must
    # not create cross-database foreign-key constraints.
    deploy = models.ForeignKey(Deploy, verbose_name=_("Deploy"), related_name="logs", on_delete=models.CASCADE, db_constraint=False)
    service = models.ForeignKey(Service, verbose_name=_("Service"), related_name="deployment_logs", on_delete=models.CASCADE, db_constraint=False)
    stage = models.CharField(_("Stage"), max_length=64)
    event_type = models.CharField(_("Event Type"), max_length=96, default="deployment.event")
    level = models.CharField(_("Level"), max_length=16, default="info")
    message = models.TextField(_("Message"))
    progress = models.PositiveSmallIntegerField(_("Progress"), blank=True, null=True)
    details = models.JSONField(_("Details"), blank=True, null=True)
    exception_type = models.CharField(_("Exception Type"), max_length=128, blank=True, default="")
    traceback = models.TextField(_("Traceback"), blank=True, default="")

    class Meta:
        verbose_name = _("Deploy Log")
        verbose_name_plural = _("Deploy Logs")
        ordering = ("created_at",)

    def __str__(self):
        return f"Deployment {self.deploy_id}: {self.stage} - {self.level}"



class BaseRuntimeImageLease(BaseModel):
    """Active deployment lease protecting a shared base image from cleanup."""

    base_image = models.ForeignKey(
        "deploy.BaseRuntimeImage",
        on_delete=models.CASCADE,
        related_name="leases",
    )
    deployment_id = models.CharField(max_length=255, db_index=True)
    acquired_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Base runtime image lease")
        verbose_name_plural = _("Base runtime image leases")
        constraints = [
            models.UniqueConstraint(
                fields=("base_image", "deployment_id"),
                name="uniq_base_image_deployment_lease",
            )
        ]
        indexes = [
            models.Index(fields=("base_image", "released_at")),
        ]

    def __str__(self):
        return f"{self.base_image_id} -> {self.deployment_id}"


class BaseRuntimeImage(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        BUILDING = "building", _("Building")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")
        DISABLED = "disabled", _("Disabled")

    logical_runtime = models.CharField(max_length=32)
    runtime_version = models.CharField(max_length=32)
    variant = models.CharField(max_length=32, default="default")
    architecture = models.CharField(max_length=32, blank=True, default="")
    docker_host = models.CharField(max_length=255, blank=True, default="")
    source_image = models.CharField(max_length=255)
    image_repository = models.CharField(max_length=255)
    image_tag = models.CharField(max_length=128)
    image_ref = models.CharField(max_length=384)
    image_id = models.CharField(max_length=255, blank=True, default="")
    image_digest = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    enabled = models.BooleanField(default=True)
    auto_build = models.BooleanField(default=True)
    rebuild_requested = models.BooleanField(default=False)
    rebuild_requested_at = models.DateTimeField(null=True, blank=True)
    build_started_at = models.DateTimeField(null=True, blank=True)
    build_completed_at = models.DateTimeField(null=True, blank=True)
    build_count = models.PositiveIntegerField(default=0)
    build_task_id = models.CharField(max_length=255, blank=True, default="")
    build_owner_deployment_id = models.CharField(max_length=255, blank=True, default="")
    last_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = _("Base runtime image")
        verbose_name_plural = _("Base runtime images")
        constraints = [
            models.UniqueConstraint(
                fields=("logical_runtime", "runtime_version", "variant", "architecture", "docker_host"),
                name="uniq_base_runtime_image_host",
            )
        ]
        ordering = ("logical_runtime", "runtime_version", "variant")

    def __str__(self):
        return f"{self.logical_runtime} {self.runtime_version} ({self.variant}) — {self.status}"
