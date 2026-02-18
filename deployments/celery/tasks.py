from celery import shared_task
from deploy.models import Deploy
from services.models import Service
from deployments.core.deploy import Deploy as Deployer
from deployments.core.manager.container_manager import Container
from django.db import transaction
from core.global_settings.config import Config, default_ports, SERVICE_STATUS_CHOICES
from django.conf import settings
import time
from deployments.celery.schedules import monitor_services





import time
from celery import shared_task
from django.db import transaction

@shared_task
def deploy(deploy_id):
    try:
        with transaction.atomic():
            _deploy_item = Deploy.objects.select_for_update().get(pk=deploy_id)
            deploy_item = Deploy.objects.select_related(
                "service", "service__plan", "service__network"
            ).get(pk=deploy_id)

            if deploy_item.service.status != SERVICE_STATUS_CHOICES.QUEUED:
                return

            deploy_item.service.status = SERVICE_STATUS_CHOICES.DEPLOYING
            deploy_item.service.save()

    except Deploy.DoesNotExist:
        return

    name = deploy_item.service.get_docker_service_name()
    platform = deploy_item.service.plan.platform
    platform_type = deploy_item.service.plan.plan_type
    port = default_ports.get(platform)
    dockerfile_text = getattr(Config, platform, None)

    if not dockerfile_text:
        deploy_item.service.status = SERVICE_STATUS_CHOICES.FAILED
        deploy_item.service.save()
        return

    deployer = Deployer(
        name=name,
        tag=deploy_item.version,
        zip_filename=deploy_item.zip_file.path,
        dockerfile_text=dockerfile_text,
        max_cpu=deploy_item.service.plan.max_cpu,
        max_ram=deploy_item.service.plan.max_ram,
        networks=[(deploy_item.service.network.name, "bridge")],
        volumes=[],
        port=port,
        read_only=not settings.DEBUG,
        platform=platform,
        platform_type=platform_type
    )

    try:
        errors = deployer.deploy()
        if errors:
            raise 
    except Exception as e:
        Deployer.remove_all(name)
        deploy_item.service.status = SERVICE_STATUS_CHOICES.FAILED
        deploy_item.service.save()
        return

    for _ in range(20):
        if Container.container_is_running(name):
            break
        time.sleep(0.5)

    if not Container.container_is_running(name):
        Deployer.remove_all(name)
        deploy_item.service.status = SERVICE_STATUS_CHOICES.FAILED
        deploy_item.service.save()
        return

    deploy_item.service.status = SERVICE_STATUS_CHOICES.SUCCEEDED
    deploy_item.service.save()



@shared_task
def stop(service_id):
    with transaction.atomic():
        service_item = Service.objects.select_for_update().get(id=service_id)
        service_item.status = SERVICE_STATUS_CHOICES.STOPPING
        name = service_item.get_docker_service_name()

        if Container.container_is_running(name):
            Deployer.stop_container(name)

        for _ in range(10):
            if not Container.container_is_running(name):
                break
            time.sleep(0.5)

        service_item.status = SERVICE_STATUS_CHOICES.STOPPED
        service_item.save()