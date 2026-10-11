from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from tickets.models import Department, DepartmentMembership
from users.models import Rule

User = get_user_model()


class DepartmentAdminPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_user(
            username="department-manager",
            email="department-manager@example.test",
            password="password123",
            is_staff=True,
        )
        Rule.objects.create(user=self.manager, rules=["departments.manage"])
        self.staff = User.objects.create_user(
            username="department-staff",
            email="department-staff@example.test",
            password="password123",
            is_staff=True,
        )
        self.member = User.objects.create_user(
            username="department-member",
            email="department-member@example.test",
            password="password123",
            is_staff=True,
        )
        self.department = Department.objects.create(name="Support")
        self.other_department = Department.objects.create(name="Operations")

    def test_departments_manage_can_crud_metadata_but_not_memberships(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get("/api/tickets/admin/departments/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data["data"]), 2)

        created = self.client.post(
            "/api/tickets/admin/departments/",
            {"name": "Platform", "description": "Platform support", "order": 3},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        department_id = created.data["data"]["id"]

        updated = self.client.put(
            f"/api/tickets/admin/departments/{department_id}/",
            {"name": "Platform Engineering", "description": "Updated", "order": 4},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["data"]["name"], "Platform Engineering")

        deactivated = self.client.delete(f"/api/tickets/admin/departments/{department_id}/")
        self.assertEqual(deactivated.status_code, 200, deactivated.content)
        self.assertFalse(Department.objects.get(pk=department_id).is_active)

        # Managing department metadata must not silently grant staff membership
        # or manager-role administration, which remains superuser-only.
        membership = self.client.post(
            f"/api/tickets/admin/departments/{self.department.pk}/members/",
            {"user_id": self.member.pk, "is_manager": True},
            format="json",
        )
        self.assertEqual(membership.status_code, 403)

    def test_staff_without_departments_manage_is_limited_to_assigned_departments(self):
        DepartmentMembership.objects.create(user=self.staff, department=self.department)
        self.client.force_authenticate(user=self.staff)

        response = self.client.get("/api/tickets/admin/departments/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["id"] for row in response.data["data"]], [self.department.pk])

        create = self.client.post(
            "/api/tickets/admin/departments/",
            {"name": "Not allowed"},
            format="json",
        )
        self.assertEqual(create.status_code, 403)

        update = self.client.put(
            f"/api/tickets/admin/departments/{self.department.pk}/",
            {"description": "Not allowed"},
            format="json",
        )
        self.assertEqual(update.status_code, 403)

        deactivate = self.client.delete(f"/api/tickets/admin/departments/{self.department.pk}/")
        self.assertEqual(deactivate.status_code, 403)
        self.assertTrue(Department.objects.get(pk=self.department.pk).is_active)
