from django.db import models
from django.utils.translation import gettext_lazy as _


class Plan(models.Model):
    name = models.CharField(_("Name"), max_length=50)
    max_apps = models.IntegerField(_("Maximum Applications"))
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

    def __str__(self):
        status = _("Enabled") if self.enabled else _("Disabled")
        plan_names = [plan.name for plan in self.plans.all()[:3]]
        display_names = ", ".join(plan_names) + ("..." if self.plans.count() > 3 else "")
        return f"{status} Private Network for Plans: {display_names or 'None'}"
