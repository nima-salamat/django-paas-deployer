from django.db import models
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
        related_name="Service"
    )
    
    read_only = models.BooleanField(_("Read only"), default=not(settings.DEBUG))
    
    selected_deploy = models.OneToOneField("deploy.Deploy", verbose_name=_("Selected Deploy"), on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    selected_deploy_at = models.DateTimeField(blank=True, null=True)
    deploy_started = models.DateTimeField(blank=True, null=True)
    deployed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(_("Deploy Status"), choices=SERVICE_STATUS_CHOICES.choices, default=SERVICE_STATUS_CHOICES.STOPPED)

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
    def __str__(self):
        return f"Service: {self.name}"


class Volume(BaseModel):
    """
    Docker volume that can be attached to multiple services owned by the same user.
    
    The 'service_attachments' JSON field stores bind/mode configurations per service:
    {
        "service_id_1": {"bind": "/data", "mode": "rw"},
        "service_id_2": {"bind": "/storage", "mode": "ro"},
        ...
    }
    """
    name = models.CharField(unique=True ,max_length=32)
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
    )
    # Legacy field for backward compatibility (single service attachment)
    service = models.ForeignKey(
        Service,
        verbose_name=_("Legacy Service"),
        related_name="legacy_volumes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # JSON mapping service_id → {bind, mode}
    service_attachments = models.JSONField(
        _("Service Attachments"),
        default=dict,
        blank=True,
        help_text=_("Service ID → {bind, mode} mappings"),
    )
    # Default bind and mode for new attachments
    default_bind = models.CharField(_("Default Bind Directory"), max_length=255, blank=True, default="")
    default_mode = models.CharField(_("Default Mode"), max_length=255, choices=VOLUME_MODE_CHOICES.choices, default=VOLUME_MODE_CHOICES.READ_WRITE, blank=True)
    size_mb = models.PositiveIntegerField()
    
    class Meta:
        verbose_name = _("Volume")
        verbose_name_plural = _("Volumes")
    
    def attach_to_service(self, service: Service, bind: str = None, mode: str = None):
        """Attach this volume to a service with optional custom bind/mode."""
        if str(service.user_id) != str(self.user_id):
            raise ValueError("Volume and service must belong to the same user")
        
        if bind is None:
            bind = self.default_bind
        if mode is None:
            mode = self.default_mode
        
        # Update JSON attachments
        attachments = self.service_attachments.copy()
        attachments[str(service.id)] = {
            "bind": bind,
            "mode": mode,
            "attached_at": timezone.now().isoformat(),
        }
        self.service_attachments = attachments
        
        # Keep legacy field for backward compatibility
        if not self.service:
            self.service = service
        
        self.save()
    
    def detach_from_service(self, service: Service):
        """Remove attachment to a service."""
        attachments = self.service_attachments.copy()
        if str(service.id) in attachments:
            del attachments[str(service.id)]
            self.service_attachments = attachments
        
        # If this was the legacy service, clear it
        if self.service_id == service.id:
            self.service = None
        
        self.save()
    
    def get_attached_services(self):
        """Return list of Service objects this volume is attached to."""
        service_ids = [sid for sid in self.service_attachments.keys() if sid]
        return Service.objects.filter(id__in=service_ids)
    
    def get_bind_for_service(self, service: Service):
        """Return bind path for a specific service."""
        return self.service_attachments.get(str(service.id), {}).get("bind", self.default_bind)
    
    def get_mode_for_service(self, service: Service):
        """Return mode for a specific service."""
        return self.service_attachments.get(str(service.id), {}).get("mode", self.default_mode)
    
    def is_attached_to_service(self, service: Service):
        """Check if volume is attached to a service."""
        return str(service.id) in self.service_attachments
    
    def __str__(self):
        return f"Volume: {self.name} ({self.size_mb} MB)"
        