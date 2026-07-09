import logging
from celery import shared_task
from .services.deploy_service import DeployService
from .services.stop_service import StopService
from .exceptions import InvalidServiceStateError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def deploy(self, deploy_id: int) -> None:
    logger.info("Initializing background processing block for deploy_id: %s", deploy_id)
    try:
        DeployService().execute(deploy_id)
    except InvalidServiceStateError:
        # Pre-execution checks failed (e.g. status was not QUEUED); skip retries entirely
        pass
    except Exception as exc:
        logger.warning("Deploy execution encountered an exception. Re-enqueueing task... (ID: %s)", deploy_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def stop(self, service_id: int) -> None:
    logger.info("Initializing background processing block for stop request on service_id: %s", service_id)
    try:
        StopService().execute(service_id)
    except InvalidServiceStateError:
        # Service configuration or existence checks failed; skip retries entirely
        pass
    except Exception as exc:
        logger.warning("Stop execution encountered an exception. Re-enqueueing task... (ID: %s)", service_id)
        raise self.retry(exc=exc)