import os
from celery import Celery
import logging

logger = logging.getLogger(__name__)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


app = Celery('config')


app.config_from_object('django.conf:settings', namespace='CELERY')


app.autodiscover_tasks(['deploy.tasks', 'core.tasks.email'])


@app.task(bind=True)
def debug_task(self):
    logger.info(f'Request: {self.request!r}')