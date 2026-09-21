from pathlib import Path
import unittest


class DocsAssetSecurityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[2]
        cls.apis = (root / "docs" / "apis.py").read_text()
        cls.urls = (root / "docs" / "urls.py").read_text()
        cls.serializers = (root / "docs" / "serializers.py").read_text()

    def test_public_asset_get_uses_method_aware_jwt_and_allow_any(self):
        self.assertIn("class DocsAssetJWTAuthentication(JWTAuthentication):", self.apis)
        self.assertIn('if request.method == "GET":', self.apis)
        self.assertIn("authentication_classes = [DocsAssetJWTAuthentication, SessionAuthentication]", self.apis)
        self.assertIn('if self.request.method == "GET":', self.apis)
        self.assertIn("return [AllowAny()]", self.apis)

    def test_public_asset_route_never_reads_draft_or_unattached_files(self):
        block = self.apis.split("class DocumentAssetAPIView", 1)[1].split("class DocumentAssetAdminPreviewAPIView", 1)[0]
        self.assertIn('if not asset.document_id or asset.document.status != Document.Status.PUBLISHED:', block)
        self.assertIn("raise Http404", block)
        self.assertNotIn('query_params.get("token")', block)
        self.assertNotIn("get_validated_token", block)

    def test_admin_preview_is_a_separate_protected_read(self):
        self.assertIn("class DocumentAssetAdminPreviewAPIView(APIView):", self.apis)
        preview = self.apis.split("class DocumentAssetAdminPreviewAPIView", 1)[1]
        self.assertIn("authentication_classes = [JWTAuthentication, SessionAuthentication]", preview)
        self.assertIn("permission_classes = [IsAuthenticated, DocsManagePermission]", preview)
        self.assertIn('path("admin/assets/<uuid:asset_id>/"', self.urls)

    def test_serializer_keeps_public_url_jwt_free(self):
        self.assertIn('path = f"/api/docs/assets/{obj.id}/"', self.serializers)
        self.assertNotIn("token=", self.serializers)


if __name__ == "__main__":
    unittest.main()
