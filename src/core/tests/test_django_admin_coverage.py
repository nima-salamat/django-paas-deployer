from django.apps import apps
from django.contrib import admin
from django.test import SimpleTestCase


PROJECT_APP_LABELS = {
    "agent",
    "app_catalog",
    "auth_users",
    "cms",
    "core",
    "custom_emails",
    "deploy",
    "docs",
    "logs",
    "messenger",
    "plans",
    "services",
    "tickets",
    "users",
}


class DjangoAdminModelCoverageTests(SimpleTestCase):
    def test_every_project_concrete_model_is_registered_in_django_admin(self):
        missing = []

        for model in apps.get_models():
            if model._meta.app_label not in PROJECT_APP_LABELS:
                continue
            if model._meta.abstract or model._meta.proxy:
                continue
            if model not in admin.site._registry:
                missing.append(f"{model._meta.app_label}.{model.__name__}")

        self.assertEqual(
            missing,
            [],
            msg="Project models missing from Django Admin: " + ", ".join(sorted(missing)),
        )

    def test_wagtail_page_is_visible_in_django_admin_without_replacing_wagtail_editorial_role(self):
        from cms.models import HomePage

        model_admin = admin.site._registry[HomePage]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))

    
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
    