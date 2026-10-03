from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from tickets.models import Department, Ticket, TicketMessage
from tickets.permissions import CanManageTicket, IsStaffOrSuperuser, IsTicketOwnerOrStaff
from tickets.serializers import TicketCreateSerializer, TicketMessageCreateSerializer

User = get_user_model()


class TicketModelSerializerInvariantTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ticket-serializer", password="password123")
        self.department = Department.objects.create(name="Support", slug="support-test")

    def test_department_generates_unique_slug_when_missing(self):
        first = Department.objects.create(name="Billing")
        second = Department.objects.create(name="Billing")
        self.assertNotEqual(first.slug, second.slug)

    def test_ticket_closing_state_sets_closed_at(self):
        ticket = Ticket.objects.create(
            user=self.user,
            department=self.department,
            subject="Close me",
            status=Ticket.Status.CLOSED,
        )
        self.assertIsNotNone(ticket.closed_at)

        ticket.status = Ticket.Status.OPEN
        ticket.save()
        self.assertIsNone(ticket.closed_at)

    def test_ticket_message_updates_parent_last_message_at(self):
        ticket = Ticket.objects.create(
            user=self.user,
            department=self.department,
            subject="Message",
        )
        message = TicketMessage.objects.create(
            ticket=ticket,
            author=self.user,
            body="Hello",
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.last_message_at, message.created_at)

    def test_ticket_create_serializer_sanitizes_html(self):
        serializer = TicketCreateSerializer(
            data={
                "department_id": self.department.pk,
                "subject": "Valid subject",
                "body": "<script>alert(1)</script><b>safe</b>",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("<script>", serializer.validated_data["body"])

    def test_ticket_message_serializer_rejects_blank_body(self):
        serializer = TicketMessageCreateSerializer(data={"body": "   "})
        self.assertFalse(serializer.is_valid())
        self.assertIn("body", serializer.errors)


class TicketPermissionMatrixTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(username="ticket-owner", password="password123")
        self.staff = User.objects.create_user(username="ticket-staff", password="password123", is_staff=True)
        self.stranger = User.objects.create_user(username="ticket-stranger", password="password123")
        self.superuser = User.objects.create_superuser(username="ticket-super", email="super@example.com", password="password123")
        self.department = Department.objects.create(name="Tech")
        self.ticket = Ticket.objects.create(
            user=self.owner,
            department=self.department,
            subject="Scoped",
        )

    def request(self, user):
        request = self.factory.get("/api/tickets/")
        request.user = user
        return request

    def test_owner_can_access_ticket_but_stranger_cannot(self):
        permission = IsTicketOwnerOrStaff()
        self.assertTrue(permission.has_permission(self.request(self.owner), None))
        self.assertTrue(permission.has_object_permission(self.request(self.owner), None, self.ticket))
        self.assertFalse(permission.has_object_permission(self.request(self.stranger), None, self.ticket))

    def test_assigned_staff_can_manage_but_unscoped_staff_cannot(self):
        self.ticket.assigned_to = self.staff
        self.ticket.save()

        permission = CanManageTicket()
        self.assertTrue(permission.has_object_permission(self.request(self.staff), None, self.ticket))

        other_staff = User.objects.create_user(username="ticket-other-staff", password="password123", is_staff=True)
        self.assertFalse(
            permission.has_object_permission(self.request(other_staff), None, self.ticket)
        )

    def test_superuser_bypasses_ticket_object_scope(self):
        permission = IsTicketOwnerOrStaff()
        self.assertTrue(permission.has_object_permission(self.request(self.superuser), None, self.ticket))

    def test_staff_permission_requires_active_staff_or_superuser(self):
        permission = IsStaffOrSuperuser()
        self.assertTrue(permission.has_permission(self.request(self.staff), None))
        self.assertTrue(permission.has_permission(self.request(self.superuser), None))
        self.assertFalse(permission.has_permission(self.request(self.owner), None))
