from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import Department, Ticket, TicketMessage, DepartmentMembership

User = get_user_model()

class TicketAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="u1", email="u1@test.com", password="pass12345")
        self.staff = User.objects.create_user(username="staff1", email="s@test.com", password="pass12345", is_staff=True)
        self.dept = Department.objects.create(name="Technical Support", slug="tech")
        DepartmentMembership.objects.create(user=self.staff, department=self.dept)

    def test_create_ticket(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/tickets/", {"department_id": self.dept.id, "subject": "Help needed", "body": "Details here"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Ticket.objects.filter(user=self.user).exists())

    def test_user_cannot_see_others_tickets(self):
        t = Ticket.objects.create(user=self.user, department=self.dept, subject="Mine")
        other = User.objects.create_user(username="u2", email="u2@test.com", password="pass12345")
        self.client.force_authenticate(other)
        resp = self.client.get(f"/api/tickets/{t.id}/")
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_staff_department_access(self):
        t = Ticket.objects.create(user=self.user, department=self.dept, subject="Staff visible")
        self.client.force_authenticate(self.staff)
        resp = self.client.get(f"/api/tickets/{t.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_message_creation(self):
        t = Ticket.objects.create(user=self.user, department=self.dept, subject="Msg test")
        self.client.force_authenticate(self.user)
        resp = self.client.post(f"/api/tickets/{t.id}/messages/", {"body": "Follow up"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TicketMessage.objects.filter(ticket=t).count(), 1)
