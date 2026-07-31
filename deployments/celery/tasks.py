
import logging
from celery import shared_task
from .services.deploy_service import DeployService
from .services.stop_service import StopService
from .exceptions import (
    ContainerTimeoutError,
    DeploymentValidationError,
    InvalidServiceStateError,
    OrchestratorDeploymentError,
)
from .schedules import monitor_services
from deployments.core.db_deployer import DB_PLATFORMS
from deploy.models import Deploy

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def deploy(self, deploy_id) -> None:
    logger.info("Initializing background processing for deploy_id: %s", deploy_id)

    # Guard: never run the app/zip pipeline for DB platforms
    try:
        deploy_item = (
            Deploy.objects
            .select_related("service", "service__plan")
            .filter(pk=deploy_id)
            .first()
        )
        if deploy_item is not None:
            cfg = deploy_item.config if isinstance(deploy_item.config, dict) else {}
            platform = (
                (cfg.get("platform") or "")
                or getattr(getattr(deploy_item.service, "plan", None), "platform", "")
                or ""
            )
            platform = str(platform).lower().strip()
            if platform in DB_PLATFORMS:
                from deploy.tasks import run_db_deploy
                logger.warning(
                    "deploy task received DB platform '%s' for deploy_id=%s; redirecting to run_db_deploy",
                    platform,
                    deploy_id,
                )
                run_db_deploy.delay(str(deploy_id))
                return
    except Exception:
        logger.exception("DB platform guard failed for deploy_id=%s; continuing app path", deploy_id)

    try:
        DeployService().execute(deploy_id)
    except (InvalidServiceStateError, DeploymentValidationError, OrchestratorDeploymentError, ContainerTimeoutError):
        logger.exception("Deployment did not complete for deploy_id: %s", deploy_id)
    except Exception as exc:
        logger.warning("Deploy execution error; re-enqueueing (ID: %s)", deploy_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def stop(self, service_id) -> None:
    logger.info("Initializing stop for service_id: %s", service_id)
    try:
        StopService().execute(service_id)
    except InvalidServiceStateError:
        pass
    except Exception as exc:
        logger.warning("Stop error; re-enqueueing (ID: %s)", service_id)
        raise self.retry(exc=exc)
