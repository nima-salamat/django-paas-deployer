from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from app_catalog.models import ApplicationInstance, ApplicationStatus
from app_catalog.serializers import ApplicationInstanceSerializer

User = get_user_model()


class ApplicationInstanceModelAndSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="catalog-model-user",
            email="catalog-model@example.com",
            password="password123",
        )

    def make_instance(self):
        return ApplicationInstance.objects.create(
            user=self.user,
            name="Catalog App",
            slug="catalog-app",
            catalog_id="wordpress",
            definition_version="1.0",
            software_version="1.2.3",
            variant_id="default",
            definition_snapshot={"catalog_id": "wordpress", "version": "1.0"},
            config={"domain": "catalog.example.test"},
            secret_config={"db_password": "never-return-plain"},
            status=ApplicationStatus.PENDING,
        )

    def test_installation_intent_is_immutable_after_creation(self):
        instance = self.make_instance()
        instance.software_version = "9.9.9"
        with self.assertRaises(ValueError):
            instance.save()

    def test_non_intent_runtime_state_remains_mutable(self):
        instance = self.make_instance()
        instance.status = ApplicationStatus.FAILED
        instance.error_code = "TEST"
        instance.save()
        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.FAILED)
        self.assertEqual(instance.error_code, "TEST")

    def test_application_serializer_does_not_expose_secret_config_payload(self):
        instance = self.make_instance()
        data = ApplicationInstanceSerializer(instance).data
        self.assertNotIn("secret_config", data)
        self.assertIn("config", data)
