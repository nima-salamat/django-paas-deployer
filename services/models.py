from django.db import models
from django.utils.translation import gettext_lazy as _
from plans.models import Plan
from users.models import User
from core.base.BaseModel import BaseModel

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
        related_name="Service"
    )


    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Service: {self.name}"


class Volume(BaseModel):
    # {"bind": "/data", "mode": "rw"}
    name = models.CharField(unique=True ,max_length=32)
    user = models.ForeignKey(
        User,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
    )
    service = models.ForeignKey(Service, verbose_name=_("Service"), related_name="volumes", on_delete=models.CASCADE)
    bind = models.CharField(_("Bind Directory"), max_length=255)
    mode = models.CharField(_("Mode Directory"), max_length=255)
    size_mb = models.PositiveIntegerField()
    
    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["bind", "service"], name="unique_bind_per_service"
            )
        ]
        