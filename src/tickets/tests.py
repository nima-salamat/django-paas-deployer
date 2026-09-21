"""Comprehensive tests for tickets: seen semantics, throttling, CRUD, notifications helpers."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.throttling import check_scope, remaining, ScopedRateThrottle
from tickets.models import Department, Ticket, TicketMessage, TicketReadState

User = get_user_model()


class ThrottlingScopeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_check_scope_allows_under_limit(self):
        self.assertTrue(check_scope("t:a", limit=3, window_seconds=60))
        self.assertTrue(check_scope("t:a", limit=3, window_seconds=60))
        self.assertTrue(check_scope("t:a", limit=3, window_seconds=60))
        self.assertFalse(check_scope("t:a", limit=3, window_seconds=60))

    def test_scopes_are_isolated(self):
        self.assertTrue(check_scope("t:a", limit=1, window_seconds=60))
        self.assertFalse(check_scope("t:a", limit=1, window_seconds=60))
        self.assertTrue(check_scope("t:b", limit=1, window_seconds=60))

    def test_remaining(self):
        check_scope("t:r", limit=5, window_seconds=60)
        check_scope("t:r", limit=5, window_seconds=60)
        self.assertEqual(remaining("t:r", 5), 3)

    def test_parse_rate(self):
        self.assertEqual(ScopedRateThrottle.parse_rate("10/min"), (10, 60))
        self.assertEqual(ScopedRateThrottle.parse_rate("5/hour"), (5, 3600))
        self.assertEqual(ScopedRateThrottle.parse_rate("100/day"), (100, 86400))


class TicketSeenSemanticsTests(TestCase):
    """Seen must only happen via explicit POST /read/, never by mere online presence."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.staff = User.objects.create_user(username="staff", password="pass12345", is_staff=True)
        self.dept = Department.objects.create(name="Support", slug="support")
        self.ticket = Ticket.objects.create(
            user=self.owner,
            department=self.dept,
            subject="Help",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.NORMAL,
        )
        self.msg_staff = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff,
            body="Staff reply",
            is_staff_reply=True,
        )
        self.msg_owner = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.owner,
            body="Owner reply",
            is_staff_reply=False,
        )
        self.client = APIClient()

    def test_messages_start_unseen(self):
        self.msg_staff.refresh_from_db()
        self.assertIsNone(self.msg_staff.seen_at)

    def test_mark_read_only_marks_other_party_messages(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/tickets/{self.ticket.pk}/read/"
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data") or res.json()
        self.assertGreaterEqual(data.get("marked", 0), 1)
        self.msg_staff.refresh_from_db()
        self.msg_owner.refresh_from_db()
        self.assertIsNotNone(self.msg_staff.seen_at)
        # Own message must not be marked as seen by self
        self.assertIsNone(self.msg_owner.seen_at)

    def test_mark_read_idempotent_no_double_count(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/tickets/{self.ticket.pk}/read/"
        r1 = self.client.post(url)
        r2 = self.client.post(url)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json().get("data") or r2.json()
        self.assertEqual(d2.get("marked", 0), 0)

    def test_staff_mark_read_marks_owner_messages(self):
        self.client.force_authenticate(user=self.staff)
        url = f"/api/tickets/{self.ticket.pk}/read/"
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        self.msg_owner.refresh_from_db()
        self.assertIsNotNone(self.msg_owner.seen_at)

    def test_stranger_cannot_mark_read(self):
        stranger = User.objects.create_user(username="stranger", password="pass12345")
        self.client.force_authenticate(user=stranger)
        url = f"/api/tickets/{self.ticket.pk}/read/"
        res = self.client.post(url)
        self.assertIn(res.status_code, (403, 404))

    def test_read_state_updated(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/tickets/{self.ticket.pk}/read/"
        self.client.post(url)
        rs = TicketReadState.objects.get(ticket=self.ticket, user=self.owner)
        self.assertIsNotNone(rs.last_read_at)


class TicketCRUDTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="u1", password="pass12345")
        self.dept = Department.objects.create(name="Billing", slug="billing")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_empty(self):
        res = self.client.get("/api/tickets/")
        self.assertEqual(res.status_code, 200)

    def test_create_ticket(self):
        res = self.client.post(
            "/api/tickets/",
            {"subject": "Need help", "body": "Details here", "department": self.dept.pk, "priority": "normal"},
            format="json",
        )
        # Accept 200/201 depending on ok() helper
        self.assertIn(res.status_code, (200, 201))
        self.assertTrue(Ticket.objects.filter(user=self.user, subject="Need help").exists())

    def test_departments_list(self):
        res = self.client.get("/api/tickets/departments/")
        self.assertEqual(res.status_code, 200)


class TicketMessageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="u2", password="pass12345")
        self.dept = Department.objects.create(name="Tech", slug="tech")
        self.ticket = Ticket.objects.create(
            user=self.user,
            department=self.dept,
            subject="S",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.NORMAL,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_post_message(self):
        res = self.client.post(
            f"/api/tickets/{self.ticket.pk}/messages/",
            {"body": "Hello staff"},
            format="json",
        )
        self.assertIn(res.status_code, (200, 201))
        self.assertTrue(
            TicketMessage.objects.filter(ticket=self.ticket, body__icontains="Hello").exists()
        )
