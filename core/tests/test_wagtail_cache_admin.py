from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from core.app_cache import get_cache_ttl
from core.models import SystemSetting
from core.wagtail_admin.universal_models import BESPOKE, MODEL_LABELS, READ_ONLY_MODELS, UniversalModelsGroup


class UniversalWagtailAdminTests(SimpleTestCase):
    def test_every_registered_model_is_either_bespoke_or_universal(self):
        generic = {label for label in MODEL_LABELS if label not in BESPOKE}
        self.assertTrue(generic)
        self.assertIn("core.SystemSetting", generic)
        self.assertIn("app_catalog.ApplicationInstance", generic)
        self.assertIn("logs.ServiceLogEntry", READ_ONLY_MODELS)
        self.assertEqual(
            len(UniversalModelsGroup.items),
            len(generic),
        )

    def test_generated_audit_models_are_read_only(self):
        names = {
            viewset.model._meta.label
            for viewset in UniversalModelsGroup.items
        }
        self.assertNotIn("logs.ServiceLogEntry", names)
        self.assertNotIn("logs.CollectorHeartbeat", names)


class CachePolicyTests(TestCase):
    def test_cache_ttl_reads_operator_setting(self):
        SystemSetting.objects.update_or_create(
            key="cache.plan_ttl",
            defaults={
                "value": "123",
                "value_type": "integer",
                "category": "general",
                "label": "Plan cache TTL",
                "is_editable": True,
            },
        )
        self.assertEqual(get_cache_ttl("plan"), 123)

    def test_cache_ttl_is_bounded(self):
        SystemSetting.objects.update_or_create(
            key="cache.plan_ttl",
            defaults={
                "value": "999999999",
                "value_type": "integer",
                "category": "general",
                "label": "Plan cache TTL",
                "is_editable": True,
            },
        )
        self.assertEqual(get_cache_ttl("plan"), 7 * 24 * 3600)
