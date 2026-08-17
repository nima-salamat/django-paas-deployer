import os
from celery import Celery
import logging

logger = logging.getLogger(__name__)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


app = Celery('config')


app.config_from_object('django.conf:settings', namespace='CELERY')

# Explicit imports prevent deployment tasks from disappearing when Celery
# autodiscovery is affected by package layout/import-order issues.
app.conf.imports = tuple(dict.fromkeys((
    *(tuple(getattr(app.conf, 'imports', ()) or ())),
    'deployments.celery.tasks',
    'deploy.tasks',
    'core.tasks.email',
    'custom_emails.tasks',
    'messenger.tasks',
)))

app.autodiscover_tasks(['deploy.tasks', 'deployments.celery', 'core.tasks.email', 'custom_emails.tasks', 'messenger.tasks'])


@app.task(bind=True)
def debug_task(self):
    logger.info(f'Request: {self.request!r}')
