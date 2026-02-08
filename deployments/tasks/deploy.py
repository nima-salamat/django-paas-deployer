from celery import shared_task
from deploy.models import Deploy
from deployments.core.deploy import Deploy as Deployer
from django.db import transaction
from core.global_settings.config import Config, default_ports
from django.conf import settings

@shared_task
def deploy(deploy_id):
    try:
        with transaction.atomic():
            deploy_item_ = (
                Deploy.objects
                .select_for_update()
                .get(pk=deploy_id)
            )
            deploy_item = (
                Deploy.objects
                .select_related("service", "service__plan", "service__network")
                .get(pk=deploy_id)
            )

            if deploy_item_.running:
                print(f"Deploy {deploy_id} already running, skipping.")
                return

            deploy_item_.running = True
            deploy_item_.save()
    except Deploy.DoesNotExist:
        return

    platform = deploy_item.service.plan.platform
    port = default_ports[platform]
    django_debug = settings.DEBUG
    dockerfile_text = getattr(Config, platform, "")
    if dockerfile_text is None: 
        return
  
    deployer = Deployer(
        name = deploy_item.service.name,
        tag = deploy_item.version,
        zip_filename = deploy_item.zip_file.path,
        dockerfile_text = dockerfile_text,
        max_cpu = deploy_item.service.plan.max_cpu,
        max_ram = deploy_item.service.plan.max_ram,
        networks = [(deploy_item.service.network.name, "bridge")],
        volumes = [],
        port = port,
        read_only= not django_debug,
        platform = platform
    )
    
    try:
        deployer.deploy()
    except:
        Deployer.remove_all(deploy_item.service.name)
        deploy_item_.running = False
        deploy_item_.save()

@shared_task
def stop(deploy_id):
    try:
        deploy_item = (
            Deploy.objects
            .select_related("service")
            .get(pk=deploy_id)
        )
    except:
        return
    Deployer.stop_container(deploy_item.service.name)
    deploy_item.running = False
    deploy_item.save()