from django.db import models
from django.utils.translation import gettext_lazy as _
from plans.models import Plan
from users.models import User
from core.base.BaseModel import BaseModel

class PrivateNetwork(BaseModel):
    name = models.CharField(_("Name"), max_length=50)
    user = models.ForeignKey(User, verbose_name=_("User Network"), on_delete=models.CASCADE)
    # enabled = models.BooleanField(_("Enabled"), default=False)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("Private Network")
        verbose_name_plural = _("Private Networks")

    def all_containers_summary(self):
        containers = self.container.select_related("plan").all()
        plans = [container.plan for container in containers]

        return {
            "total_max_apps": sum(plan.max_apps for plan in plans),
            "total_max_cpu": sum(plan.max_cpu for plan in plans),
            "total_max_ram": sum(plan.max_ram for plan in plans),
            "total_max_storage": sum(plan.max_storage for plan in plans),
        }
    
    def __str__(self):
        # status = _("Enabled") if self.enabled else _("Disabled")
        # containers = self.containers.select_related("plan").all()
        # display_names = [
        #     f"{s.name}({s.plan.name})" for s in containers[:3]
        # ]
        # display = ", ".join(display_names)
        # if containers.count() > 3:
        #     display += "..."
        # return f"{status} Private Network with Container: {display or 'None'}"
        return self.name



class Container(BaseModel):
    name = models.CharField(_("Name"), max_length=30, unique=True)
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
        # null=True,
        # blank=True,
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
        # blank=True,
        related_name="Container"
    )
    volumes = models.ManyToManyField("services.Volume", related_name="volumes", related_query_name="containers")
    # user_email = models.EmailField(_("User Email"), blank=True, editable=False)
    # user_username = models.CharField(_("User Username"), max_length=50, blank=True, editable=False)
    # network_name = models.CharField(_("Network Name"), max_length=50, blank=True, editable=False)

    def save(self, *args, **kwargs):
        # if self.user:
        #     if self.user.email:
        #         self.user_email = self.user.email
        #     if self.user.username:
        #         self.user_username = self.user.username
        # if self.network:
        #     self.network_name = self.network.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Service: {self.name}"


class Volume(BaseModel):
    # {"bind": "/data", "mode": "rw"}
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
    )
    bind = models.CharField(_("Bind Directory"), max=255)
    mode = models.CharField(_("Mode Directory"), max=255)
    size_mb = models.PositiveIntegerField()
    