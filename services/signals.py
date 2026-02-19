from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Service
from deployments.core.deploy import Deploy as Deployer


@receiver(signal=pre_delete, sender=Service)
def delete_deploy_before_delete_service(sender, instance, **kwargs):
    Deployer.remove_all(instance.get_docker_service_name())