from __future__ import annotations

import os

import pytest

if os.environ.get("DJANGO_FULL_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("requires the full Django application registry", allow_module_level=True)
pytestmark = pytest.mark.deployment_integration

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, TestCase

from core.app_cache import get_cache_ttl
from core.models import SystemSetting
from auth_users.wagtail_admin.models import LoginSettingsViewSet
from deploy.wagtail_admin.models import (
    BaseRuntimeImageLeaseViewSet,
    BaseRuntimeImageViewSet,
    DeployViewSet,
    DeployGroup,
)
from users.wagtail_admin.models import RuleViewSet
from app_catalog.wagtail_admin.models import ApplicationInstanceViewSet, ApplicationCatalogGroup


class WagtailExposureContractTests(SimpleTestCase):
    def test_runtime_and_sensitive_grant_records_are_read_only(self):
        user = SimpleNamespace(is_superuser=True, is_staff=True)
        for viewset in (DeployViewSet, BaseRuntimeImageLeaseViewSet, RuleViewSet, ApplicationInstanceViewSet):
            policy = viewset.permission_policy
            assert policy.user_has_permission(user, "add") is False
            assert policy.user_has_permission(user, "change") is False
            assert policy.user_has_permission(user, "delete") is False

    def test_base_runtime_image_is_changeable_but_not_creatable_or_deletable(self):
        user = SimpleNamespace(is_superuser=True, is_staff=True, has_perm=lambda name: True)
        policy = BaseRuntimeImageViewSet.permission_policy
        assert policy.user_has_permission(user, "view") is True
        assert policy.user_has_permission(user, "change") is True
        assert policy.user_has_permission(user, "add") is False
        assert policy.user_has_permission(user, "delete") is False

    def test_login_settings_is_changeable_but_not_creatable_or_deletable(self):
        user = SimpleNamespace(is_superuser=True, is_staff=True, has_perm=lambda name: True)
        policy = LoginSettingsViewSet.permission_policy
        assert policy.user_has_permission(user, "view") is True
        assert policy.user_has_permission(user, "change") is True
        assert policy.user_has_permission(user, "add") is False
        assert policy.user_has_permission(user, "delete") is False

    def test_explicit_groups_register_expected_surfaces(self):
        assert {viewset.model._meta.label for viewset in DeployGroup.items} == {
            "deploy.Deploy",
            "deploy.DeployLog",
            "deploy.BaseRuntimeImage",
            "deploy.BaseRuntimeImageLease",
            "deploy.SwarmCluster",
            "deploy.SwarmNode",
        }
        assert {viewset.model._meta.label for viewset in ApplicationCatalogGroup.items} == {
            "app_catalog.ApplicationInstance",
            "app_catalog.ApplicationInstanceService",
        }

    def test_ticket_wagtail_registration_is_disabled(self):
        source = (
            Path(__file__).resolve().parents[2] / "tickets" / "wagtail_hooks.py"
        ).read_text(encoding="utf-8")
        assert "_register_tickets" not in source

    def test_service_inspection_does_not_read_secret_payloads(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "services"
            / "wagtail_admin"
            / "views.py"
        ).read_text(encoding="utf-8")
        for token in ("ServiceSecretVersion", "ciphertext", "get_current_value", "resolve_value"):
            assert token not in source


class WagtailActionAuthorizationTests(SimpleTestCase):
    def _user(self, *, staff=True, perms=()):
        return SimpleNamespace(
            is_authenticated=True,
            is_staff=staff,
            is_superuser=False,
            has_perm=lambda name: name in set(perms),
        )

    def test_deployment_cancel_rejects_non_operator(self):
        from django.core.exceptions import PermissionDenied
        from deploy.wagtail_admin.views import deployment_cancel
        request = RequestFactory().post("/cancel/", {"next": "/wagtail/requests/"})
        request.user = self._user(staff=False)
        with pytest.raises(PermissionDenied):
            deployment_cancel(request, 1)

    def test_deployment_cancel_rejects_without_change_permission(self):
        from django.core.exceptions import PermissionDenied
        from deploy.wagtail_admin.views import deployment_cancel
        request = RequestFactory().post("/cancel/", {"next": "/wagtail/requests/"})
        request.user = self._user()
        with pytest.raises(PermissionDenied):
            deployment_cancel(request, 1)

    def test_application_cancel_rejects_without_change_permission(self):
        from django.core.exceptions import PermissionDenied
        from app_catalog.wagtail_admin.views import application_instance_cancel
        request = RequestFactory().post("/cancel/", {"next": "/wagtail/requests/"})
        request.user = self._user()
        with pytest.raises(PermissionDenied):
            application_instance_cancel(
                request, "00000000-0000-0000-0000-000000000001"
            )

    def test_deployment_cancel_uses_domain_use_case_once(self):
        from deploy.wagtail_admin.views import deployment_cancel

        deploy = SimpleNamespace(pk=1, name="demo", status="running")
        request = RequestFactory().post("/cancel/", {"next": "/wagtail/requests/"})
        request.user = self._user(perms={"deploy.change_deploy"})
        decision = SimpleNamespace(target_status=None)

        with patch("deploy.wagtail_admin.views.get_object_or_404", return_value=deploy),              patch("deploy.wagtail_admin.views.messages.success"),              patch("deploy.wagtail_admin.views.CancelDeploymentUseCase") as use_case_cls:
            use_case_cls.return_value.execute.return_value = SimpleNamespace(
                decision=decision
            )
            response = deployment_cancel(request, 1)

        assert response.status_code == 302
        use_case_cls.return_value.execute.assert_called_once_with(1)

    def test_application_cancel_uses_existing_coordinator_task_once(self):
        from app_catalog.models import ApplicationStatus
        from app_catalog.wagtail_admin.views import application_instance_cancel

        instance = SimpleNamespace(
            pk="00000000-0000-0000-0000-000000000001",
            name="demo",
            status=ApplicationStatus.DEPLOYING,
        )
        request = RequestFactory().post("/cancel/", {"next": "/wagtail/requests/"})
        request.user = self._user(perms={"app_catalog.change_applicationinstance"})

        with patch("app_catalog.wagtail_admin.views.get_object_or_404", return_value=instance),              patch("app_catalog.wagtail_admin.views.messages.success"),              patch("app_catalog.wagtail_admin.views.cancel_application_installation") as task:
            response = application_instance_cancel(request, instance.pk)

        assert response.status_code == 302
        task.delay.assert_called_once_with(
            str(instance.pk), "Application installation cancelled by operator."
        )


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
