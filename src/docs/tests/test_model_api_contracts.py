from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from docs.models import Document, DocumentCategory
from docs.serializers import DocumentSerializer

User = get_user_model()


class DocsModelAndAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_category_and_document_auto_slug_and_append_order(self):
        category = DocumentCategory.objects.create(name="Getting Started")
        first = Document.objects.create(title="Install", category=category, status=Document.Status.PUBLISHED)
        second = Document.objects.create(title="Configure", category=category, status=Document.Status.PUBLISHED)

        self.assertEqual(category.slug, "getting-started")
        self.assertEqual(first.slug, "install")
        self.assertEqual(second.slug, "configure")
        self.assertEqual(second.order, first.order + 10)

    def test_public_documents_are_accessible_without_authentication(self):
        Document.objects.create(
            title="Published",
            status=Document.Status.PUBLISHED,
            content="# Hello",
        )
        Document.objects.create(
            title="Draft",
            status=Document.Status.DRAFT,
            content="# Secret draft",
        )

        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, 200)
        titles = {row["title"] for row in response.json()}
        self.assertEqual(titles, {"Published"})

    def test_public_document_detail_only_returns_published_documents(self):
        doc = Document.objects.create(
            title="Published detail",
            status=Document.Status.PUBLISHED,
        )
        response = self.client.get(f"/api/docs/public/{doc.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], doc.title)

        doc.status = Document.Status.DRAFT
        doc.save()
        self.assertEqual(
            self.client.get(f"/api/docs/public/{doc.slug}/").status_code,
            404,
        )

    def test_document_serializer_accepts_blank_slug_because_model_generates_it(self):
        serializer = DocumentSerializer(
            data={"title": "Auto Slug", "content": "", "slug": ""}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
