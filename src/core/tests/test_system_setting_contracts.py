from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from core.models import SettingCategory, SettingValueType, SystemSetting


class SystemSettingContractTests(TestCase):
    def test_cast_value_supports_all_persistent_types(self):
        cases = [
            (SettingValueType.STRING, "hello", "hello"),
            (SettingValueType.INTEGER, "12", 12),
            (SettingValueType.FLOAT, "1.5", 1.5),
            (SettingValueType.BOOLEAN, "true", True),
            (SettingValueType.JSON, '{"a": 1}', {"a": 1}),
        ]
        for value_type, raw, expected in cases:
            setting = SystemSetting(
                key=f"test.{value_type}",
                value=raw,
                value_type=value_type,
                category=SettingCategory.GENERAL,
            )
            self.assertEqual(setting.cast_value(), expected)

    def test_invalid_casts_degrade_to_safe_defaults(self):
        self.assertEqual(
            SystemSetting(key="i", value="bad", value_type=SettingValueType.INTEGER).cast_value(),
            0,
        )
        self.assertEqual(
            SystemSetting(key="f", value="bad", value_type=SettingValueType.FLOAT).cast_value(),
            0.0,
        )
        self.assertIsNone(
            SystemSetting(key="j", value="{bad", value_type=SettingValueType.JSON).cast_value()
        )

    def test_set_cast_value_serializes_boolean_and_json(self):
        boolean = SystemSetting(key="bool", value_type=SettingValueType.BOOLEAN)
        boolean.set_cast_value(True)
        self.assertEqual(boolean.value, "true")

        json_setting = SystemSetting(key="json", value_type=SettingValueType.JSON)
        json_setting.set_cast_value({"enabled": True})
        self.assertEqual(json_setting.cast_value(), {"enabled": True})

    def test_save_and_delete_bust_system_setting_cache(self):
        setting = SystemSetting(
            key="cache.test",
            value="one",
            value_type=SettingValueType.STRING,
            category=SettingCategory.GENERAL,
        )
        with patch("core.models.cache.delete") as delete:
            setting.save()
            delete.assert_any_call("syssetting:cache.test")
            delete.assert_any_call("syssetting:__all__")

            delete.reset_mock()
            setting.delete()
            delete.assert_any_call("syssetting:cache.test")
            delete.assert_any_call("syssetting:__all__")
