from __future__ import annotations

from django.contrib import admin
from django.test import SimpleTestCase

from cms.models import HomePage


class CMSModelContractTests(SimpleTestCase):
    def test_home_page_is_structural_root_and_not_an_editorial_crud_surface_in_django_admin(self):
        self.assertEqual(HomePage.subpage_types, [])
        self.assertIn("wagtailcore.Page", HomePage.parent_page_types)

        model_admin = admin.site._registry[HomePage]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))

    def test_home_page_contains_body_in_content_panels(self):
        panel_names = {
            getattr(panel, "field_name", None)
            for panel in HomePage.content_panels
            if getattr(panel, "field_name", None)
        }
        self.assertIn("body", panel_names)
