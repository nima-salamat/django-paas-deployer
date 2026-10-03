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
