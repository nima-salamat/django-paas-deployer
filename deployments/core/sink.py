"""Compatibility adapter for callers that still construct the original sink."""

import logging

from deploy.event_pipeline import DeploymentEventPipeline
from deploy.models import Deploy


logger = logging.getLogger(__name__)


class DBAndChannelEventSink:
    """Delegate event delivery to the dedicated deployment event pipeline."""

    def __init__(self, deployment_id):
        self.deployment_id = str(deployment_id)
        self.pipeline = None

    def __call__(self, event) -> None:
        try:
            if self.pipeline is None:
                deploy = Deploy.objects.select_related("service").get(pk=self.deployment_id)
                self.pipeline = DeploymentEventPipeline(deploy)
            self.pipeline.record(event)
        except Exception:
            logger.exception("Unable to process legacy deployment event for %s.", self.deployment_id)
