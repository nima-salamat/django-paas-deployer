from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Document, DocumentAsset


@override_settings(MEDIA_ROOT="/tmp/passdeployer-docs-test-media")
class PublicDocsAssetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.published = Document.objects.create(
            title="Published guide",
            slug="published-guide",
            status=Document.Status.PUBLISHED,
        )
        self.draft = Document.objects.create(
            title="Draft guide",
            slug="draft-guide",
            status=Document.Status.DRAFT,
        )

    def make_asset(self, document):
        return DocumentAsset.objects.create(
            document=document,
            file=SimpleUploadedFile("pixel.txt", b"docs asset", content_type="text/plain"),
            name="pixel.txt",
        )

    def test_published_asset_is_public(self):
        asset = self.make_asset(self.published)
        response = self.client.get(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)

    def test_draft_asset_is_not_public(self):
        asset = self.make_asset(self.draft)
        response = self.client.get(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 404)

    def test_published_asset_accepts_head_without_auth(self):
        asset = self.make_asset(self.published)
        response = self.client.head(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)
