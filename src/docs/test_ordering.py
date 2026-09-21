"""Ordering contract for the documentation tree.

Documents and categories expose an explicit ``order`` that drives:
  * the public docs sidebar / index / prev-next navigation,
  * the admin content tree in the React panel,
  * the Django admin changelists.

These tests pin down the ordering APIs added on top of the models:
  * ``POST /api/docs/admin/documents/reorder/`` and
    ``POST /api/docs/admin/categories/reorder/`` persist an explicit id
    sequence as spaced order values (10, 20, 30 …),
  * newly created items append to the end of their section,
  * moving an item to another section repositions it there,
  * the Django admin exposes ▲/▼ move URLs and a renumber action.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Document, DocumentCategory

User = get_user_model()
API = "/api/docs"


def make_section(name, **kwargs):
    return DocumentCategory.objects.create(name=name, slug=kwargs.pop("slug", name.lower().replace(" ", "-")), **kwargs)


def make_doc(title, section=None, order=0, status=Document.Status.PUBLISHED):
    return Document.objects.create(
        title=title,
        slug=title.lower().replace(" ", "-"),
        category=section,
        order=order,
        status=status,
    )


class DocumentReorderAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="docs-order-admin", email="docs-admin@example.com", password="irrelevant-123"
        )
        self.client.force_authenticate(self.admin)
        self.section = make_section("Getting started")
        self.a = make_doc("Intro", self.section, order=10)
        self.b = make_doc("Install", self.section, order=20)
        self.c = make_doc("Quickstart", self.section, order=30)

    def refresh(self):
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()

    def test_reorder_rewrites_sequence(self):
        response = self.client.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.c.id), str(self.a.id), str(self.b.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.refresh()
        self.assertEqual((self.c.order, self.a.order, self.b.order), (10, 20, 30))

    def test_reorder_normalizes_legacy_zero_ties(self):
        # Rows created before ordering existed all share order=0.
        self.a.order = 0
        self.b.order = 0
        self.c.order = 0
        for doc in (self.a, self.b, self.c):
            doc.save(update_fields=["order"])
        response = self.client.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.a.id), str(self.b.id), str(self.c.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.refresh()
        self.assertEqual((self.a.order, self.b.order, self.c.order), (10, 20, 30))

    def test_reorder_ignores_duplicate_ids(self):
        response = self.client.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.a.id), str(self.a.id), str(self.b.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.refresh()
        self.assertEqual((self.a.order, self.b.order), (10, 20))

    def test_reorder_rejects_unknown_id_without_writing(self):
        ghost = str(uuid.uuid4())
        response = self.client.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.a.id), ghost]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("missing", response.json())
        # Validate-before-write: the known id must NOT be half-applied.
        self.refresh()
        self.assertEqual((self.a.order, self.b.order, self.c.order), (10, 20, 30))

    def test_reorder_rejects_bad_body(self):
        for body in ({"ids": "nope"}, {"ids": []}, {}, {"ids": [123, None]}):
            response = self.client.post(f"{API}/admin/documents/reorder/", body, format="json")
            self.assertEqual(response.status_code, 400, msg=body)

    def test_anonymous_reorder_is_rejected(self):
        anonymous = APIClient()
        response = anonymous.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.a.id)]},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_new_document_appends_to_section_end(self):
        response = self.client.post(
            f"{API}/admin/documents/",
            {
                "title": "Configuration",
                "slug": "configuration",
                "category": str(self.section.id),
                "status": Document.Status.DRAFT,
                "content": "# Configuration\n",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Document.objects.get(slug="configuration").order, 40)

    def test_new_document_with_explicit_order_keeps_it(self):
        response = self.client.post(
            f"{API}/admin/documents/",
            {
                "title": "First contact",
                "slug": "first-contact",
                "category": str(self.section.id),
                "order": 5,
                "status": Document.Status.DRAFT,
                "content": "# First\n",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Document.objects.get(slug="first-contact").order, 5)

    def test_moving_to_another_section_repositions_to_end(self):
        other = make_section("CLI")
        first = make_doc("CLI login", other, order=10)
        make_doc("CLI deploy", other, order=40)
        response = self.client.patch(
            f"{API}/admin/documents/{self.b.id}/",
            {"category": str(other.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.b.refresh_from_db()
        self.assertEqual(self.b.category_id, other.id)
        self.assertEqual(self.b.order, 50)
        first.refresh_from_db()
        self.assertEqual(first.order, 10)

    def test_patch_with_explicit_order_wins_over_reposition(self):
        other = make_section("CLI")
        make_doc("CLI login", other, order=10)
        response = self.client.patch(
            f"{API}/admin/documents/{self.b.id}/",
            {"category": str(other.id), "order": 25},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.b.refresh_from_db()
        self.assertEqual(self.b.order, 25)

    def test_public_tree_reflects_reorder(self):
        self.client.post(
            f"{API}/admin/documents/reorder/",
            {"ids": [str(self.c.id), str(self.b.id), str(self.a.id)]},
            format="json",
        )
        response = APIClient().get(f"{API}/tree/")
        self.assertEqual(response.status_code, 200)
        titles = [doc["title"] for doc in response.json()["categories"][0]["documents"]]
        self.assertEqual(titles, ["Quickstart", "Install", "Intro"])


class CategoryReorderAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="docs-cat-admin", email="docs-cat-admin@example.com", password="irrelevant-123"
        )
        self.client.force_authenticate(self.admin)
        self.alpha = make_section("Alpha", order=10)
        self.beta = make_section("Beta", order=20)

    def test_reorder_categories(self):
        response = self.client.post(
            f"{API}/admin/categories/reorder/",
            {"ids": [str(self.beta.id), str(self.alpha.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.alpha.refresh_from_db()
        self.beta.refresh_from_db()
        self.assertEqual((self.beta.order, self.alpha.order), (10, 20))

    def test_new_category_appends_to_root_end(self):
        response = self.client.post(
            f"{API}/admin/categories/",
            {"name": "Gamma", "parent": None},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(DocumentCategory.objects.get(slug="gamma").order, 30)

    def test_new_subcategory_appends_within_parent(self):
        child_one = DocumentCategory.objects.create(
            name="Alpha child one", slug="alpha-child-one", parent=self.alpha
        )
        self.assertEqual(child_one.order, 10)
        response = self.client.post(
            f"{API}/admin/categories/",
            {"name": "Alpha child two", "parent": str(self.alpha.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(DocumentCategory.objects.get(slug="alpha-child-two").order, 20)


class DjangoAdminOrderingTests(TestCase):
    """The legacy Django admin gets the same ordering powers as the panel."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="docs-dj-admin", email="docs-dj-admin@example.com", password="irrelevant-123"
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.section = make_section("Getting started")
        self.a = make_doc("Intro", self.section, order=10)
        self.b = make_doc("Install", self.section, order=20)
        self.c = make_doc("Quickstart", self.section, order=30)

    def move(self, doc, direction):
        return self.client.get(
            reverse("admin:docs_document_move", args=[doc.pk, direction]), follow=True
        )

    def test_move_up_swaps_and_renumbers(self):
        response = self.move(self.c, "up")
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual((self.a.order, self.c.order, self.b.order), (10, 20, 30))

    def test_move_up_at_top_is_noop(self):
        response = self.move(self.a, "up")
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(self.a.order, 10)
        self.b.refresh_from_db()
        self.assertEqual(self.b.order, 20)

    def test_move_down_at_bottom_is_noop(self):
        for doc, order in ((self.a, 0), (self.b, 0), (self.c, 45)):
            Document.objects.filter(pk=doc.pk).update(order=order)
        self.move(self.c, "down")  # already last → boundary no-op
        self.c.refresh_from_db()
        self.assertEqual(self.c.order, 45)  # boundary no-op leaves values untouched

    def test_renumber_action_respaces_sections(self):
        Document.objects.filter(pk=self.a.pk).update(order=3)
        Document.objects.filter(pk=self.b.pk).update(order=7)
        Document.objects.filter(pk=self.c.pk).update(order=77)
        response = self.client.post(
            reverse("admin:docs_document_changelist"),
            {
                "action": "renumber_orders",
                "_selected_action": [str(self.a.pk), str(self.c.pk)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        # The whole affected section is renumbered, not only the selection.
        self.assertEqual((self.a.order, self.b.order, self.c.order), (10, 20, 30))

    def test_anonymous_cannot_move(self):
        anonymous = Client()
        response = anonymous.get(
            reverse("admin:docs_document_move", args=[self.b.pk, "up"])
        )
        # admin_view redirects anonymous users to the login page.
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        self.b.refresh_from_db()
        self.assertEqual(self.b.order, 20)

    def test_changelist_groups_by_section_order(self):
        other = make_section("Zeta", order=1)  # sorts before "Getting started"
        make_doc("Zeta intro", other, order=10)
        response = self.client.get(reverse("admin:docs_document_changelist"))
        self.assertEqual(response.status_code, 200)
        rows = list(
            Document.objects.order_by("category__order", "category__name", "order", "title")
            .values_list("title", flat=True)
        )
        self.assertLess(rows.index("Zeta intro"), rows.index("Intro"))
