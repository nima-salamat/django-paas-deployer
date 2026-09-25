from django.test import SimpleTestCase


class DeployExportContracts(SimpleTestCase):
    def test_export_view_exists(self):
        from deploy.apis import deploy_logs_export_apiview
        self.assertTrue(callable(deploy_logs_export_apiview))

    def test_export_source_has_bounds_and_auth(self):
        import inspect
        from deploy import apis as mod
        src = inspect.getsource(mod.deploy_logs_export_apiview)
        self.assertIn("EXPORT_MAX_ROWS", src)
        self.assertIn("can_view_deploy_logs", src)
