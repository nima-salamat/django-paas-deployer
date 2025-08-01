from django.db import models
from django.utils.translation import gettext_lazy as _
from uuid import uuid4


class Service(models.Model):
    pass


class PrivateNetwork(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=50)
    plans = models.ManyToManyField(
        Service,
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