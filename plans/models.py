from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from uuid import uuid4

class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=50)
    platform = models.CharField(_("Platform"), max_length=20, choices=getattr(settings, "TECH_STACK_CHOICES", []))
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



# class PrivateNetworkSerializer(serializers.ModelSerializer):
#     plans = PlanSerializer(many=True, read_only=True)
#     combined = serializers.SerializerMethodField()

#     class Meta:
#         model = PrivateNetwork
#         fields = [
#             "id",
#             "name",
#             "plans",
#             "enabled",
#             "description",
#             "combined"
#         ]

#     def get_combined(self, obj):
#         return obj.combined_plan()