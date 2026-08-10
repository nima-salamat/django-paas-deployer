from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import Department, Ticket, TicketMessage, DepartmentMembership

User = get_user_model()

class DepartmentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="u1", email="u1@test.com", password="pass12345")
        self.admin = User.objects.create_user(username="admin1", email="a@test.com", password="pass12345", is_staff=True, is_superuser=True)
        self.staff = User.objects.create_user(username="staff1", email="s@test.com", password="pass12345", is_staff=True)
        self.dept = Department.objects.create(name="Technical Support", slug="tech")
        self.dept2 = Department.objects.create(name="Financial", slug="fin")
        DepartmentMembership.objects.create(user=self.staff, department=self.dept)

    def test_department_list_authenticated(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/tickets/departments/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json().get("data") or resp.json()
        self.assertTrue(isinstance(data, list))
        self.assertGreaterEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Technical Support")

    def test_department_response_shape(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/tickets/departments/")
        body = resp.json()
        self.assertIn("success", body)
        self.assertIn("data", body)
        self.assertTrue(body["success"])

    def test_staff_sees_only_own_department_tickets(self):
        t1 = Ticket.objects.create(user=self.user, department=self.dept, subject="Tech issue")
        t2 = Ticket.objects.create(user=self.user, department=self.dept2, subject="Money issue")
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/api/tickets/staff/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.json().get("results") or resp.json().get("data") or []
        ids = [r["id"] for r in results]
        self.assertIn(t1.id, ids)
        self.assertNotIn(t2.id, ids)

    def test_admin_sees_all_tickets(self):
        Ticket.objects.create(user=self.user, department=self.dept, subject="A")
        Ticket.objects.create(user=self.user, department=self.dept2, subject="B")
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/tickets/staff/")
        results = resp.json().get("results") or resp.json().get("data") or []
        self.assertGreaterEqual(len(results), 2)

    def test_staff_cannot_access_other_dept_detail(self):
        t = Ticket.objects.create(user=self.user, department=self.dept2, subject="Secret")
        self.client.force_authenticate(self.staff)
        resp = self.client.get(f"/api/tickets/{t.id}/")
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_assign_ticket(self):
        t = Ticket.objects.create(user=self.user, department=self.dept, subject="Assign me")
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/tickets/staff/{t.id}/assign/", {"assigned_to_id": self.staff.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        t.refresh_from_db()
        self.assertEqual(t.assigned_to_id, self.staff.id)

    def test_stats(self):
        Ticket.objects.create(user=self.user, department=self.dept, subject="S", priority="urgent")
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/api/tickets/staff/stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json().get("data") or resp.json()
        self.assertIn("total", data)
        self.assertIn("open", data)

    def test_admin_create_department(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/tickets/admin/departments/", {"name": "Sales", "description": "Sales team"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Department.objects.filter(name="Sales").exists())

    def test_staff_cannot_create_department(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post("/api/tickets/admin/departments/", {"name": "Nope"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TicketUserTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="u1", email="u1@test.com", password="pass12345")
        self.dept = Department.objects.create(name="General", slug="general")

    def test_create_ticket(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/tickets/", {"department_id": self.dept.id, "subject": "Help", "body": "Details"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
