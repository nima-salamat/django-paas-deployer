from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Deploy
import os

@receiver(signal=[post_delete], sender=Deploy)
def delete_file_after_delete(sender, instance, **kwargs):
    if instance.zip_file and instance.zip_file.path:
        if os.path.isfile(instance.zip_file.path):
            os.remove(instance.zip_file.path)
    