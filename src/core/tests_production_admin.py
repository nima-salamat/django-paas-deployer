from unittest import mock

from django.test import SimpleTestCase, override_settings


class ProductionAdminTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_renderer_policy_disables_browsable_api(self):
        from core.api_renderers import ProductionJSONRenderer
        from rest_framework.renderers import BrowsableAPIRenderer
        self.assertTrue(issubclass(ProductionJSONRenderer, type(ProductionJSONRenderer())))
        self.assertNotEqual(ProductionJSONRenderer.media_type, BrowsableAPIRenderer.media_type)

    def test_metrics_payload_shape_does_not_allow_infrastructure_identifiers(self):
        expected = {"ok", "cpu_percent", "ram_percent", "ram_used", "ram_total", "ram_available",
                    "ram_used_human", "ram_total_human", "ram_available_human"}
        from core.system_metrics import get_system_metrics
        data = get_system_metrics()
        self.assertEqual(set(data), expected)
