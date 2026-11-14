from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.core.sink import DBAndChannelEventSink


def test_event_sink_loads_only_deploy_identity_columns():
    deploy = SimpleNamespace(
        pk="deploy-1",
        service_id="service-1",
        revision_id="revision-1",
        execution_task_id="task-1",
    )
    manager = MagicMock()
    manager.only.return_value.get.return_value = deploy

    with patch("deployments.core.sink.Deploy.objects", manager):
        sink = DBAndChannelEventSink("deploy-1")
        assert sink._get_deploy() is deploy

    manager.only.assert_called_once_with(
        "pk",
        "service_id",
        "revision_id",
        "execution_task_id",
    )
    manager.only.return_value.get.assert_called_once_with(pk="deploy-1")
