from __future__ import annotations

import os

import pytest

if os.environ.get("DJANGO_FULL_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("requires the full Django/PostgreSQL test profile", allow_module_level=True)
pytestmark = pytest.mark.deployment_integration

import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from unittest.mock import patch

from deploy.apis import DeployViewSet
from deploy.apis import _shallow_request_data
from deploy.models import Deploy
from deploy.serializers import DeploySerializer
from plans.models import Plan
from services.models import Service
from users.models import User


class DeploymentRequestDataRegressionTests(TestCase):
    def test_shallow_request_data_preserves_uploaded_file_identity(self):
        uploaded = self._zip_for_regression("app.zip", b"body")
        from django.http import QueryDict

        data = QueryDict("", mutable=True)
        data["name"] = "file"
        data.setlist("zip_file", [uploaded])

        mapped = _shallow_request_data(data)

        self.assertIs(mapped["zip_file"], uploaded)
        self.assertEqual(mapped["name"], "file")

    @staticmethod
    def _zip_for_regression(name, body):
        return SimpleUploadedFile(name, body, content_type="application/zip")


class DeploymentFileUploadRegressionTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_dir.name, MEDIA_URL="/media/")
        self.override.enable()

        self.user = User.objects.create_user(
            username="deploy-file-test",
            email="deploy-file-test@example.com",
            password="test-password",
        )
        self.plan = Plan.objects.create(
            name="Bronze",
            platform="django",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
        )
        self.service = Service.objects.create(
            name="deploy-file-service",
            user=self.user,
            plan=self.plan,
        )

    def tearDown(self):
        self.override.disable()
        self.media_dir.cleanup()

    def _zip(self, name: str, body: bytes):
        return SimpleUploadedFile(name, body, content_type="application/zip")

    def test_create_multipart_persists_zip(self):
        request = APIRequestFactory().post(
            "/deploy/",
            {
                "name": "file-create",
                "service": str(self.service.pk),
                "version": "1.0",
                "config": "{}",
                "zip_file": self._zip("app.zip", b"create-body"),
            },
            format="multipart",
        )
        force_authenticate(request, user=self.user)
        with patch(
            "deploy.daily_limits.assert_daily_deploy_allowed",
            return_value=(True, "", 0, 100),
        ):
            response = DeployViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 201)
        deploy = Deploy.objects.get(name="file-create")
        self.assertTrue(deploy.zip_file.name)
        self.assertTrue(deploy.zip_file.storage.exists(deploy.zip_file.name))
        with deploy.zip_file.open("rb") as fh:
            self.assertEqual(fh.read(), b"create-body")

    def test_update_multipart_replaces_zip_and_removes_old_object(self):
        deploy = Deploy.objects.create(
            name="file-update",
            service=self.service,
            version="1.0",
            zip_file=self._zip("old.zip", b"old-body"),
            config={},
        )
        old_name = deploy.zip_file.name

        request = APIRequestFactory().put(
            f"/deploy/{deploy.pk}/",
            {
                "name": "file-update",
                "version": "1.0",
                "config": "{}",
                "zip_file": self._zip("new.zip", b"new-body"),
            },
            format="multipart",
        )
        force_authenticate(request, user=self.user)
        response = DeployViewSet.as_view({"put": "update"})(request)

        self.assertEqual(response.status_code, 200)
        deploy.refresh_from_db()
        self.assertNotEqual(deploy.zip_file.name, old_name)
        self.assertFalse(deploy.zip_file.storage.exists(old_name))
        self.assertTrue(deploy.zip_file.storage.exists(deploy.zip_file.name))
        with deploy.zip_file.open("rb") as fh:
            self.assertEqual(fh.read(), b"new-body")

    def test_same_deploy_name_is_allowed_on_different_services(self):
        service_two = Service.objects.create(
            name="deploy-file-service-two",
            user=self.user,
            plan=self.plan,
        )
        Deploy.objects.create(
            name="shared-deploy-name",
            service=self.service,
            version="1.0",
            config={},
        )
        other = Deploy.objects.create(
            name="shared-deploy-name",
            service=service_two,
            version="1.0",
            config={},
        )

        self.assertEqual(other.service_id, service_two.pk)
        self.assertEqual(
            Deploy.objects.filter(name="shared-deploy-name").count(),
            2,
        )

    def test_duplicate_api_deploy_name_gets_unique_suffix(self):
        existing = Deploy.objects.create(
            name="same-service-name",
            service=self.service,
            version="1.0",
            config={},
        )

        request = APIRequestFactory().post(
            "/deploy/",
            {
                "name": "same-service-name",
                "service": str(self.service.pk),
                "version": "1.0",
                "config": "{}",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        with patch(
            "deploy.daily_limits.assert_daily_deploy_allowed",
            return_value=(True, "", 0, 100),
        ):
            response = DeployViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 201)
        created = Deploy.objects.exclude(pk=existing.pk).get(service=self.service)
        self.assertEqual(created.name, "same-service-name-2")

    def test_api_deploy_name_scope_allows_same_name_on_another_service(self):
        service_two = Service.objects.create(
            name="deploy-file-service-api-two",
            user=self.user,
            plan=self.plan,
        )
        Deploy.objects.create(
            name="production",
            service=self.service,
            version="1.0",
            config={},
        )

        def create(service):
            request = APIRequestFactory().post(
                "/deploy/",
                {
                    "name": "production",
                    "service": str(service.pk),
                    "version": "1.0",
                    "config": "{}",
                },
                format="json",
            )
            force_authenticate(request, user=self.user)
            with patch(
                "deploy.daily_limits.assert_daily_deploy_allowed",
                return_value=(True, "", 0, 100),
            ):
                return DeployViewSet.as_view({"post": "create"})(request)

        same_service = create(self.service)
        other_service = create(service_two)

        self.assertEqual(same_service.status_code, 201)
        self.assertEqual(other_service.status_code, 201)
        self.assertEqual(
            Deploy.objects.get(service=self.service, name="production-2").service_id,
            self.service.pk,
        )
        self.assertEqual(
            Deploy.objects.get(service=service_two, name="production").service_id,
            service_two.pk,
        )

    def test_duplicate_model_deploy_name_is_still_rejected(self):
        Deploy.objects.create(
            name="same-service-name",
            service=self.service,
            version="1.0",
            config={},
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Deploy.objects.create(
                name="same-service-name",
                service=self.service,
                version="1.0",
                config={},
            )

    def test_zip_file_representation_points_to_authenticated_download(self):
        deploy = Deploy.objects.create(
            name="file-url",
            service=self.service,
            version="1.0",
            zip_file=self._zip("app.zip", b"url-body"),
            config={},
        )
        request = APIRequestFactory().get(f"/deploy/{deploy.pk}/")
        force_authenticate(request, user=self.user)
        data = DeploySerializer(deploy, context={"request": request}).data

        self.assertEqual(
            data["zip_file"],
            f"http://testserver/deploy/{deploy.pk}/download/",
        )
        self.assertNotIn("/media/deployments/", data["zip_file"])
