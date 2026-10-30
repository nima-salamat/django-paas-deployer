from types import SimpleNamespace
from unittest.mock import patch
import json

from django.test import SimpleTestCase
from rest_framework.response import Response

from core.api_renderers import ProductionJSONRenderer, _localize_api_payload
from users.admin_tables_api import _serialize_row


class ApiLocalizationTests(SimpleTestCase):
    translations = {
        "success::user found.": "success::اطلاعات کاربر دریافت شد.",
        "Users": "کاربران",
        "username": "نام کاربری",
        "Active": "فعال",
        "Invalid credentials.": "اطلاعات ورود نادرست است.",
        "This field is required.": "تکمیل این فیلد الزامی است.",
    }

    def translate(self, value):
        return self.translations.get(str(value), str(value))

    def test_success_envelopes_translate_messages_and_schema_without_changing_values(self):
        payload = {
            "success": True,
            "message": "success::user found.",
            "data": {
                "tables": [{
                    "key": "users.User",
                    "label": "Users",
                    "fields": [{
                        "name": "username",
                        "label": "username",
                        "type": "CharField",
                        "choices": [{"value": "active", "label": "Active"}],
                    }],
                    "rows": [{"username": "nima", "status": "active"}],
                    "profile": {"label": "Active", "description": "An Active user-owned label."},
                }],
            },
        }
        with patch("core.api_renderers._", side_effect=self.translate):
            localized = _localize_api_payload(payload, 200)

        table = localized["data"]["tables"][0]
        self.assertEqual(localized["message"], "success::اطلاعات کاربر دریافت شد.")
        self.assertEqual(table["label"], "کاربران")
        self.assertEqual(table["key"], "users.User")
        self.assertEqual(table["fields"][0]["name"], "username")
        self.assertEqual(table["fields"][0]["label"], "نام کاربری")
        self.assertEqual(table["fields"][0]["choices"][0]["value"], "active")
        self.assertEqual(table["fields"][0]["choices"][0]["label"], "فعال")
        self.assertEqual(table["rows"][0]["status"], "active")
        self.assertEqual(table["profile"]["label"], "Active")
        self.assertEqual(table["profile"]["description"], "An Active user-owned label.")

    def test_validation_errors_translate_recursively_but_keep_machine_codes(self):
        payload = {
            "success": False,
            "detail": "Invalid credentials.",
            "code": "invalid_credentials",
            "errors": {
                "username": ["This field is required."],
            },
            "supported_languages": ["en-us", "fa"],
        }
        with patch("core.api_renderers._", side_effect=self.translate):
            rendered = ProductionJSONRenderer().render(
                payload,
                renderer_context={"response": Response(payload, status=400)},
            )
        result = json.loads(rendered.decode("utf-8"))
        self.assertEqual(result["detail"], "اطلاعات ورود نادرست است.")
        self.assertEqual(result["errors"]["username"], ["تکمیل این فیلد الزامی است."])
        self.assertEqual(result["code"], "invalid_credentials")
        self.assertEqual(result["supported_languages"], ["en-us", "fa"])

    def test_choice_rows_keep_raw_api_value_and_add_a_persian_display_value(self):
        field = SimpleNamespace(
            name="status",
            choices=[("active", "Active")],
            many_to_many=False,
            one_to_many=False,
        )
        instance = SimpleNamespace(
            _meta=SimpleNamespace(get_fields=lambda: [field]),
            status="active",
            get_status_display=lambda: "Active",
        )
        with patch("users.admin_tables_api._", side_effect=self.translate):
            row = _serialize_row(instance, {})

        self.assertEqual(row["status"], "active")
        self.assertEqual(row["_display"]["status"], "فعال")
