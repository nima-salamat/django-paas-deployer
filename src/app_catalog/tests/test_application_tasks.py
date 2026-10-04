from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from app_catalog import tasks


class ApplicationTaskDispatchTests(SimpleTestCase):
    def test_schedule_next_dispatches_child_deploy_directly(self):
        dispatch = SimpleNamespace(
            binding_id=11,
            deploy_id=22,
            instance_id="instance-1",
            service_key="mariadb",
            task_id="child-task-1",
        )

        with patch("app_catalog.tasks.ApplicationStackExecutor") as executor_cls,              patch("app_catalog.tasks.deploy_task.apply_async") as apply_async:
            executor_cls.return_value.reconcile.return_value = [dispatch]

            tasks._schedule_next("instance-1")

        apply_async.assert_called_once()
        kwargs = apply_async.call_args.kwargs
        assert apply_async.call_args.args == ()
        assert kwargs["args"] == ["22"]
        assert kwargs["task_id"] == "child-task-1"
        assert kwargs["queue"] == "deployments"
        assert kwargs["link"].args == ("instance-1", "mariadb", "child-task-1")
        assert kwargs["link_error"].args == ("instance-1", "mariadb", "child-task-1")

    def test_schedule_next_clears_claim_when_child_publish_fails(self):
        dispatch = SimpleNamespace(
            binding_id=11,
            deploy_id=22,
            instance_id="instance-1",
            service_key="mariadb",
            task_id="child-task-1",
        )

        with patch("app_catalog.tasks.ApplicationStackExecutor") as executor_cls,              patch(
                 "app_catalog.tasks.deploy_task.apply_async",
                 side_effect=RuntimeError("broker unavailable"),
             ),              patch("app_catalog.tasks.ApplicationInstanceService.objects.filter") as filter_mock:
            filter_mock.return_value.update.return_value = 1
            executor_cls.return_value.reconcile.return_value = [dispatch]

            tasks._schedule_next("instance-1")

        filter_mock.assert_called_once_with(
            pk=11,
            dispatched_at__isnull=False,
        )
        filter_mock.return_value.update.assert_called_once_with(
            dispatched_at=None,
            dispatch_task_id="",
        )
