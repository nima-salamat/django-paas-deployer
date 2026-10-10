from pathlib import Path

from django.apps import apps
from django.contrib import admin
from django.test import SimpleTestCase


# Treat every app installed from this repository's source tree as project-owned.
# Discovering apps by path prevents this regression test from silently ignoring
# a newly added first-party app just because its label was not added to a list.
PROJECT_SOURCE_ROOT = Path(__file__).resolve().parents[2]


def project_app_labels():
    return {
        app_config.label
        for app_config in apps.get_app_configs()
        if Path(app_config.path).resolve().is_relative_to(PROJECT_SOURCE_ROOT)
    }


def concrete_project_models():
    labels = project_app_labels()
    return [
        model
        for model in apps.get_models()
        if model._meta.app_label in labels
        and not model._meta.abstract
        and not model._meta.proxy
    ]


class DjangoAdminModelCoverageTests(SimpleTestCase):
    def test_every_project_concrete_model_is_registered_in_django_admin(self):
        models = concrete_project_models()
        self.assertTrue(
            models,
            "No project models were discovered; check the source-root detection.",
        )

        missing = [
            f"{model._meta.app_label}.{model.__name__}"
            for model in models
            if model not in admin.site._registry
        ]

        self.assertEqual(
            missing,
            [],
            msg="Project models missing from Django Admin: "
            + ", ".join(sorted(missing)),
        )

    def test_every_project_model_has_explicit_admin_configuration(self):
        # Registration through admin.site.register(Model) with Django's bare
        # ModelAdmin is technically visible but does not express the project's
        # deliberate editing, audit, and secret-handling policy.
        unconfigured = []
        for model in concrete_project_models():
            model_admin = admin.site._registry.get(model)
            if model_admin is not None and type(model_admin) is admin.ModelAdmin:
                unconfigured.append(f"{model._meta.app_label}.{model.__name__}")

        self.assertEqual(
            unconfigured,
            [],
            msg="Project models using the unconfigured default ModelAdmin: "
            + ", ".join(sorted(unconfigured)),
        )

    def test_read_only_project_admins_cannot_mutate_or_delete_records(self):
        from core.django_admin import ReadOnlyProjectModelAdmin

        violations = []
        for model in concrete_project_models():
            model_admin = admin.site._registry.get(model)
            if not isinstance(model_admin, ReadOnlyProjectModelAdmin):
                continue
            for permission in (
                "has_add_permission",
                "has_change_permission",
                "has_delete_permission",
            ):
                if getattr(model_admin, permission)(None):
                    violations.append(f"{model._meta.label}.{permission}")

        self.assertEqual(
            violations,
            [],
            msg="Read-only Django Admin policies were weakened: "
            + ", ".join(sorted(violations)),
        )

    def test_wagtail_page_is_visible_in_django_admin_without_replacing_wagtail_editorial_role(self):
        from cms.models import HomePage

        model_admin = admin.site._registry[HomePage]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))

    def test_resource_plan_admin_covers_logging_fields(self):
        from plans.models import Plan

        model_admin = admin.site._registry[Plan]
        fields = {
            field
            for section in model_admin.fieldsets
            for field in section[1].get("fields", ())
        }
        self.assertTrue(
            {
                "name",
                "platform",
                "plan_type",
                "max_cpu",
                "max_ram",
                "max_storage",
                "storage_type",
                "price_per_hour",
                "log_retention_days",
                "log_storage_mb",
                "log_ingest_bytes_per_sec",
                "persistent_logging",
                "realtime_logging",
                "log_quota_behavior",
            }.issubset(fields)
        )

    def test_resource_plan_wagtail_uses_product_rule_permissions(self):
        from plans.wagtail_admin.models import PlansPermissionPolicy

        policy = PlansPermissionPolicy(None)

        def user(*, staff=False, superuser=False, rules=()):
            return type(
                "PolicyUser",
                (),
                {
                    "is_authenticated": True,
                    "is_staff": staff,
                    "is_superuser": superuser,
                    "rule": type("Rule", (), {"rules": list(rules)})(),
                },
            )()

        viewer = user(staff=True, rules=("plans.view",))
        manager = user(staff=True, rules=("plans.manage",))
        outsider = user(staff=True, rules=())
        superuser = user(staff=True, superuser=True)

        self.assertTrue(policy.user_has_permission(viewer, "view"))
        self.assertFalse(policy.user_has_permission(viewer, "change"))
        self.assertFalse(policy.user_has_permission(viewer, "delete"))

        self.assertTrue(policy.user_has_permission(manager, "view"))
        self.assertTrue(policy.user_has_permission(manager, "add"))
        self.assertTrue(policy.user_has_permission(manager, "change"))
        self.assertTrue(policy.user_has_permission(manager, "delete"))

        self.assertFalse(policy.user_has_permission(outsider, "view"))
        self.assertFalse(policy.user_has_permission(outsider, "add"))
        self.assertTrue(policy.user_has_permission(superuser, "change"))
