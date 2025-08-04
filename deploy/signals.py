from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from .models import Deploy
from .tasks import unzip_files, handle_deploy_start, handle_deploy_stop
import os

@receiver(signal=post_delete, sender=Deploy)
def delete_file_after_delete(sender, instance, **kwargs):
    if instance.zip_file and instance.zip_file.path:
        if os.path.isfile(instance.zip_file.path):
            os.remove(instance.zip_file.path)
    
@receiver(signal=post_save, sender=Deploy)
def deploy_task_triggered(sender, instance, created, **kwargs):
    if created:
        # making the server ready but not running it.
        # triggering a celery for unziping files and getting ready for running it.
        if instance.zip_file:
            unzip_files.delay(instance.zip_file.path)
        if instance.is_running:
            # run the server
            handle_deploy_start.delay(instance.id)
    else:
        if instance.is_running:
            # run the server
            handle_deploy_start.delay(instance.id)
        else:
            # stop the server
            handle_deploy_stop.delay(instance.id)        