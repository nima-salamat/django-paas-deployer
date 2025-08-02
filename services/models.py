from django.db import models
from django.utils.translation import gettext_lazy as _
from uuid import uuid4
from plans.models import Plan
from users.models import User


class PrivateNetwork(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=50, unique=True)
    enabled = models.BooleanField(_("Enabled"), default=False)
    description = models.TextField(_("Description"), blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Private Network")
        verbose_name_plural = _("Private Networks")

    def all_services_summary(self):
        services = self.services.select_related("plan").all()
        plans = [service.plan for service in services]

        return {
            "total_max_apps": sum(plan.max_apps for plan in plans),
            "total_max_cpu": sum(plan.max_cpu for plan in plans),
            "total_max_ram": sum(plan.max_ram for plan in plans),
            "total_max_storage": sum(plan.max_storage for plan in plans),
        }
    
    def __str__(self):
        status = _("Enabled") if self.enabled else _("Disabled")
        services = self.services.select_related("plan").all()
        display_names = [
            f"{s.name}({s.plan.name})" for s in services[:3]
        ]
        display = ", ".join(display_names)
        if services.count() > 3:
            display += "..."
        return f"{status} Private Network with Services: {display or 'None'}"


class Service(models.Model):
    id = models.UUIDField(_("ID"), primary_key=True, default=uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=30, unique=True)

    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
        blank=True,
        related_name="services"
    )

    previous_user_email = models.EmailField(_("Previous User Email"), blank=True, editable=False)
    previous_user_username = models.CharField(_("Previous User Username"), max_length=50, blank=True, editable=False)
    previous_network_name = models.CharField(_("Previous Network Name"), max_length=50, blank=True, editable=False)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def save(self, *args, **kwargs):
        if self.user:
            if self.user.email:
                self.previous_user_email = self.user.email
            if self.user.username:
                self.previous_user_username = self.user.username
        if self.network:
            self.previous_network_name = self.network.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Service: {self.name}"
