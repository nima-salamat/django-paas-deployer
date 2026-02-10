from celery import shared_task
from deploy.models import Deploy
from deployments.core.deploy import Deploy as Deployer
from deployments.core.manager.container_manager import Container
from django.db import transaction
from core.global_settings.config import Config, default_ports, SERVICE_STATUS_CHOICES
from django.conf import settings

@shared_task(bind=True)
def deploy(deploy_id):
    try:
        with transaction.atomic():
            deploy_item = (
                Deploy.objects
                .select_for_update()
                .select_related("service", "service__plan", "service__network")
                .get(pk=deploy_id)
            )

            if deploy_item.service.status != SERVICE_STATUS_CHOICES.QUEUED:
                return

            deploy_item.service.status = SERVICE_STATUS_CHOICES.DEPLOYING
            deploy_item.service.save()

    except Deploy.DoesNotExist:
        return

    name = deploy_item.service.name
    platform = deploy_item.service.plan.platform
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
        platform=platform
    )

    try:
        deployer.deploy()
    except Exception as e:
        Deployer.remove_all(name)
        deploy_item.service.status = SERVICE_STATUS_CHOICES.FAILED
        deploy_item.service.save()
        return

    if not Container.container_is_running(name):
        Deployer.remove_all(name)
        deploy_item.service.status = SERVICE_STATUS_CHOICES.FAILED
        deploy_item.service.save()
        return

    deploy_item.service.status = SERVICE_STATUS_CHOICES.SUCCEEDED
    deploy_item.service.save()

@shared_task
def stop(deploy_id):
    try:
        deploy_item = (
            Deploy.objects
            .select_related("service")
            .get(pk=deploy_id)
        )
    except Deploy.DoesNotExist:
        return

    name = deploy_item.service.name

    if Container.container_is_running(name):
        Deployer.stop_container(name)

    if not Container.container_is_running(name):
        deploy_item.service.status = SERVICE_STATUS_CHOICES.STOPPED
        deploy_item.service.save()
