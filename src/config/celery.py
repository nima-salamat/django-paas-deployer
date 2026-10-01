import os
from celery import Celery
import logging

logger = logging.getLogger(__name__)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


app = Celery('config')


app.config_from_object('django.conf:settings', namespace='CELERY')

try:
    from deployments.observability import configure
    configure()
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    CeleryInstrumentor().instrument()
except Exception:
    logger.debug("Optional deployment tracing instrumentation is unavailable.", exc_info=True)

# Explicit imports prevent deployment tasks from disappearing when Celery
# autodiscovery is affected by package layout/import-order issues.
app.conf.imports = tuple(dict.fromkeys((
    *(tuple(getattr(app.conf, 'imports', ()) or ())),
    'deployments.celery.tasks',
    'app_catalog.tasks',
    'core.tasks.email',
    'custom_emails.tasks',
    'messenger.tasks',
    'logs.tasks',
)))

app.autodiscover_tasks(['deployments.celery', 'app_catalog', 'logs', 'core.tasks.email', 'custom_emails.tasks', 'messenger.tasks'])


@app.task(bind=True)
def debug_task(self):
    logger.info(f'Request: {self.request!r}')
