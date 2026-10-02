from django.db.models.deletion import DO_NOTHING
from django.test import SimpleTestCase


class ServiceDeleteContractTests(SimpleTestCase):
    def test_deploylog_is_not_a_cascade_dependency_of_service_or_deploy(self):
        from deploy.models import DeployLog

        self.assertIs(
            DeployLog._meta.get_field("service").remote_field.on_delete,
            DO_NOTHING,
        )
        self.assertIs(
            DeployLog._meta.get_field("deploy").remote_field.on_delete,
            DO_NOTHING,
        )

    def test_service_viewset_imports_runtime_purge_helper(self):
        from services.api.common import _purge_service_runtime
        from services.api.user_services import _purge_service_runtime as imported_helper

        self.assertIs(imported_helper, _purge_service_runtime)
