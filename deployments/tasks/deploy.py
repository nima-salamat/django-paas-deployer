from celery import shared_task
from deploy.models import Deploy
from deployments.core.deploy import Deploy as Deployer
from core.global_settings.config import Config, default_ports
from django.conf import settings
import zipfile

@shared_task
def deploy(deploy_id):
    try:
        deploy_item = (
            Deploy.objects
            .select_related("service", "service__plan", "service__network")
            .get(pk=deploy_id)
        )
    except:
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
    
    deployer.deploy()