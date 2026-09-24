from __future__ import annotations

import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from deploy.apis import DeployViewSet
from deploy.models import Deploy
from deploy.serializers import DeploySerializer
from plans.models import Plan
from services.models import Service
from users.models import User


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
