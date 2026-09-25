from __future__ import annotations

import os

import pytest

if os.environ.get("DJANGO_FULL_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("requires the full Django application registry", allow_module_level=True)
pytestmark = pytest.mark.deployment_integration

from pathlib import Path

from django.core.cache import cache
from django.template.loader import get_template
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
        self.assertIn("messenger.CallSessionParticipant", BESPOKE)
        self.assertNotIn("messenger.CallSessionParticipant", MODEL_LABELS)
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
        self.assertIn("logs.ServiceLogEntry", names)
        self.assertIn("logs.CollectorHeartbeat", names)
        readonly_models = {
            viewset.model._meta.label
            for viewset in UniversalModelsGroup.items
            if getattr(viewset, "permission_policy", None).__class__.__name__
            == "ReadOnlyGeneratedPolicy"
        }
        self.assertIn("logs.ServiceLogEntry", readonly_models)
        self.assertIn("logs.CollectorHeartbeat", readonly_models)


class CacheTemplateTests(SimpleTestCase):
    def test_cache_dashboard_template_compiles(self):
        get_template("core/wagtail/cache_dashboard.html")

    def test_custom_wagtail_templates_use_theme_surface_tokens(self):
        root = Path(__file__).resolve().parents[1] / "templates"
        cache_template = (root / "core" / "wagtail" / "cache_dashboard.html").read_text()
        gauges_template = (root / "wagtailadmin" / "home" / "system_gauges.html").read_text()

        for source in (cache_template, gauges_template):
            self.assertNotIn("w-color-surface-panel,", source)
            self.assertNotIn("w-color-surface-panels,", source)
            self.assertIn("w-color-surface-dashboard-panel", source)
            self.assertIn("w-color-text-label", source)
            self.assertIn("w-color-text-context", source)


class CachePolicyTests(TestCase):
    def test_cache_ttl_reads_operator_setting(self):
        cache.delete("syssetting:cache.plan_ttl")
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
        cache.delete("syssetting:cache.plan_ttl")
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
