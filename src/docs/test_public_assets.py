from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Document, DocumentAsset


@override_settings(MEDIA_ROOT="/tmp/passdeployer-docs-test-media")
class PublicDocsAssetTests(TestCase):
    """Documentation files must be downloadable by everyone, no login.

    The public asset endpoint treats the asset UUID as an unguessable
    capability token: anyone holding the link can GET/HEAD the file,
    regardless of the asset's document attachment or draft status.
    Mutations (PATCH/DELETE) stay admin-only.
    """

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
        # Published attachments are safe for shared caches.
        self.assertIn("public", response["Cache-Control"])

    def test_draft_asset_is_downloadable_without_login(self):
        asset = self.make_asset(self.draft)
        response = self.client.get(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)
        # Draft bytes stay out of shared caches but are still fetchable.
        self.assertIn("private", response["Cache-Control"])

    def test_unattached_library_asset_is_downloadable_without_login(self):
        asset = self.make_asset(None)
        response = self.client.get(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])

    def test_published_asset_accepts_head_without_auth(self):
        asset = self.make_asset(self.published)
        response = self.client.head(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)

    def test_asset_with_garbage_bearer_is_still_public(self):
        asset = self.make_asset(self.published)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer garbage-token")
        try:
            response = self.client.get(f"/api/docs/assets/{asset.id}/")
        finally:
            self.client.credentials()
        self.assertEqual(response.status_code, 200)

    def test_unknown_uuid_returns_404(self):
        response = self.client.get("/api/docs/assets/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(response.status_code, 404)

    def test_anonymous_patch_is_rejected(self):
        asset = self.make_asset(self.published)
        response = self.client.patch(
            f"/api/docs/assets/{asset.id}/", {"alt": "hijack"}, format="json"
        )
        self.assertIn(response.status_code, (401, 403))

    def test_anonymous_delete_is_rejected(self):
        asset = self.make_asset(self.published)
        response = self.client.delete(f"/api/docs/assets/{asset.id}/")
        self.assertIn(response.status_code, (401, 403))

    def test_file_content_disposition_has_safe_filename(self):
        asset = self.make_asset(self.published)
        response = self.client.get(f"/api/docs/assets/{asset.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="pixel.txt"', response["Content-Disposition"])
