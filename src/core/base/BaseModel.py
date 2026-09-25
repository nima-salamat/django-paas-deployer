from django.db import models
from uuid import uuid4
from django.utils.translation import gettext_lazy as _

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name=_("ID"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        abstract = True
