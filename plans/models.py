from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from users.models import User


class Plan(models.Model):
    name = models.CharField(_("Name"), max_length=50)
    user = models.ForeignKey(User, verbose_name=_("User"), on_delete=models.CASCADE)
    max_apps = models.IntegerField(_("Maximum Applications"), default=getattr(settings, "DEFAULT_MAX_APPS"))
    max_cpu = models.IntegerField(_("Maximum CPU (vCPU)"))
    max_ram = models.IntegerField(_("Maximum RAM (MB)"))
    max_storage = models.IntegerField(_("Maximum Storage (GB)"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")

    def __str__(self):
        return self.name


class PrivateNetwork(models.Model):
    plans = models.ManyToManyField(
        Plan,
        verbose_name=_("Related Plans"),
        related_name="private_networks",
        blank=True,
    )
    enabled = models.BooleanField(_("Enabled"), default=False)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("Private Network")
        verbose_name_plural = _("Private Networks")

    def combined_plan(self):
        plans = self.plans.all()
        total_max_apps = sum(plan.max_apps for plan in plans)
        total_max_cpu = sum(plan.max_cpu for plan in plans)
        total_max_ram = sum(plan.max_ram for plan in plans)
        total_max_storage = sum(plan.max_storage for plan in plans)

        return {
            "max_apps": total_max_apps,
            "max_cpu": total_max_cpu,
            "max_ram": total_max_ram,
            "max_storage": total_max_storage,
        }
    
    def __str__(self):
        status = _("Enabled") if self.enabled else _("Disabled")
        plan_names = [plan.name for plan in self.plans.all()[:3]]
        display_names = ", ".join(plan_names) + ("..." if self.plans.count() > 3 else "")
        return f"{status} Private Network for Plans: {display_names or 'None'}"
