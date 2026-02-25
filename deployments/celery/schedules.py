from celery import shared_task
from docker import from_env
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from celery.result import AsyncResult
from services.models import Service
from deployments.core.manager.container_manager import Container
from core.global_settings.config import SERVICE_STATUS_CHOICES, MAX_DEPLOY_TIME_MINUTE
import logging

logger = logging.getLogger(__name__)

@shared_task
def monitor_services():
    services = Service.objects.all()

    for service in services:
        try:

            with transaction.atomic():
                service = Service.objects.select_for_update().get(id=service.id)
                
                container = Container(service.get_docker_service_name())

                exists = container.exists()
                is_running = container.is_running() if exists else False

                if is_running and service.status == SERVICE_STATUS_CHOICES.STOPPED:
                    service.status = SERVICE_STATUS_CHOICES.SUCCEEDED
                    service.save(update_fields=["status"])
                
                if not is_running and service.status == SERVICE_STATUS_CHOICES.SUCCEEDED:
                    service.status = SERVICE_STATUS_CHOICES.FAILED
                    service.save(update_fields=["status"])
                
                if service.status == SERVICE_STATUS_CHOICES.DEPLOYING:
                    result = AsyncResult(service.task_id)
                    
                    if service.deploy_started is not None and \
                        timezone.now() - service.deploy_started >= timedelta(minutes=MAX_DEPLOY_TIME_MINUTE):
                        if not result.ready():  # still running
                            result.revoke(terminate=True)
                        service.status = SERVICE_STATUS_CHOICES.FAILED
                        service.save(update_fields=["status"])

                    elif result.ready():
                        service.status = SERVICE_STATUS_CHOICES.FAILED
                        service.save(update_fields=["status"])
                        
        except Exception:
            logger.exception(f"Monitor error for service {service.id}")
