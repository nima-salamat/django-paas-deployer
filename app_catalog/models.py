from django.db import models
import uuid
from users.models import User
from services.models import Service


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DEPLOYING = "deploying", "Deploying"
    RUNNING = "running", "Running"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ApplicationInstance(models.Model):
    """A catalog-installed application, distinct from its individual Services/Deploys."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="application_instances")
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    catalog_id = models.CharField(max_length=64)
    definition_version = models.CharField(max_length=32)
    software_version = models.CharField(max_length=64, default="unknown")
    variant_id = models.CharField(max_length=64)
    # Immutable catalog definition used by an installed application. This keeps
    # reconciles/recovery tied to the exact template that was installed even
    # after the external/bundled catalog is updated.
    definition_snapshot = models.JSONField(default=dict, blank=True)
    config = models.JSONField(default=dict, blank=True)
    secret_config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING)
    error_code = models.CharField(max_length=96, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(max_length=64, blank=True, default="pending")
    execution_task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    execution_deadline = models.DateTimeField(null=True, blank=True)
    cancel_requested = models.BooleanField(default=False)
    network = models.OneToOneField(
        "services.PrivateNetwork",
        on_delete=models.CASCADE,
        related_name="application_instance",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "slug"), name="uniq_application_instance_user_slug"),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} ({self.catalog_id})"


class ApplicationInstanceService(models.Model):
    instance = models.ForeignKey(ApplicationInstance, on_delete=models.CASCADE, related_name="services")
    service = models.OneToOneField(Service, on_delete=models.CASCADE, related_name="application_binding")
    deploy = models.OneToOneField(
        "deploy.Deploy",
        on_delete=models.CASCADE,
        related_name="application_binding",
    )
    service_key = models.CharField(max_length=64)
    sequence = models.PositiveIntegerField(default=0)
    dispatch_task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("instance", "service_key"), name="uniq_application_instance_service_key"),
        ]
        ordering = ("sequence", "service_key")

    def __str__(self):
        return f"{self.instance_id}:{self.service_key}"
