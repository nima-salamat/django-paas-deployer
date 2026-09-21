"""Ticket REST API."""
from __future__ import annotations
import logging
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from ..models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment
from ..permissions import IsTicketOwnerOrStaff, IsStaffOrSuperuser, CanManageTicket, IsSuperuserOnly
from ..serializers import (
    DepartmentSerializer, TicketListSerializer, TicketDetailSerializer,
    TicketCreateSerializer, TicketMessageCreateSerializer, TicketMessageSerializer,
    TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer,
)
from ..utils import check_rate_limit, get_ticket_setting, validate_upload_file, safe_filename, validate_ticket_quota

logger = logging.getLogger("tickets.apis")

def ok(message="success", data=None, http_status=status.HTTP_200_OK):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=http_status)

def err(message, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"success": False, "message": message}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)


from .common import ok, err, TicketPagination

class AdminDepartmentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        # Superuser: all; staff: only their departments with stats
        if request.user.is_superuser:
            qs = Department.objects.all().order_by("order", "name")
        else:
            ids = DepartmentMembership.objects.filter(user=request.user).values_list("department_id", flat=True)
            qs = Department.objects.filter(id__in=ids).order_by("order", "name")
        qs = qs.annotate(
            staff_count=Count("memberships", distinct=True),
            open_tickets=Count(
                "tickets",
                filter=Q(tickets__status__in=[Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING_USER]),
                distinct=True,
            ),
            total_tickets=Count("tickets", distinct=True),
        )
        data = []
        for d in qs:
            data.append({
                "id": d.id,
                "name": d.name,
                "slug": d.slug,
                "description": d.description,
                "is_active": d.is_active,
                "order": d.order,
                "staff_count": d.staff_count,
                "open_tickets": d.open_tickets,
                "total_tickets": d.total_tickets,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
            })
        return ok(data=data)

    def post(self, request):
        if not request.user.is_superuser:
            return err("Only admin can create departments.", status.HTTP_403_FORBIDDEN)
        ser = DepartmentSerializer(data=request.data)
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        obj = ser.save()
        return ok("Created", data=DepartmentSerializer(obj).data, http_status=status.HTTP_201_CREATED)


class AdminDepartmentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get_object(self, pk):
        try:
            return Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        if not request.user.is_superuser:
            if not DepartmentMembership.objects.filter(user=request.user, department=obj).exists():
                return err("Forbidden", status.HTTP_403_FORBIDDEN)
        members = list(
            DepartmentMembership.objects.filter(department=obj)
            .select_related("user")
            .values("id", "user_id", "user__username", "user__email", "is_manager", "created_at")
        )
        data = DepartmentSerializer(obj).data
        data["memberships"] = [
            {
                "id": m["id"],
                "user_id": m["user_id"],
                "username": m["user__username"],
                "email": m["user__email"],
                "is_manager": m["is_manager"],
                "created_at": m["created_at"],
            }
            for m in members
        ]
        return ok(data=data)

    def put(self, request, pk):
        if not request.user.is_superuser:
            return err("Only admin can edit departments.", status.HTTP_403_FORBIDDEN)
        obj = self.get_object(pk)
        if not obj:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        ser = DepartmentSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        ser.save()
        return ok("Updated", data=ser.data)

    def delete(self, request, pk):
        if not request.user.is_superuser:
            return err("Only admin can deactivate departments.", status.HTTP_403_FORBIDDEN)
        obj = self.get_object(pk)
        if not obj:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return ok("Deactivated")


class AdminDepartmentMembershipAPIView(APIView):
    """Add/remove staff from department. Admin only."""
    permission_classes = [IsSuperuserOnly]

    def post(self, request, pk):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return err("Department not found", status.HTTP_404_NOT_FOUND)
        user_id = request.data.get("user_id")
        is_manager = bool(request.data.get("is_manager", False))
        try:
            staff = User.objects.get(pk=user_id, is_staff=True)
        except User.DoesNotExist:
            return err("Staff user not found.")
        mem, created = DepartmentMembership.objects.get_or_create(
            user=staff, department=dept, defaults={"is_manager": is_manager}
        )
        if not created:
            mem.is_manager = is_manager
            mem.save(update_fields=["is_manager"])
        return ok(
            "Membership saved",
            data={"id": mem.id, "user_id": staff.id, "username": staff.username, "is_manager": mem.is_manager},
            http_status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        user_id = request.data.get("user_id") or request.query_params.get("user_id")
        deleted, _ = DepartmentMembership.objects.filter(department_id=pk, user_id=user_id).delete()
        if not deleted:
            return err("Membership not found", status.HTTP_404_NOT_FOUND)
        return ok("Removed")


class AdminStaffListAPIView(APIView):
    """List staff users with their department memberships. Admin only."""
    permission_classes = [IsSuperuserOnly]

    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        qs = User.objects.filter(is_staff=True).order_by("username")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
        data = []
        for u in qs[:100]:
            memberships = list(
                DepartmentMembership.objects.filter(user=u).select_related("department")
            )
            data.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "departments": [
                    {
                        "id": m.department_id,
                        "name": m.department.name,
                        "is_manager": m.is_manager,
                    }
                    for m in memberships
                ],
                "assigned_open": Ticket.objects.filter(
                    assigned_to=u
                ).exclude(status__in=[Ticket.Status.CLOSED, Ticket.Status.RESOLVED]).count(),
            })
        return ok(data=data)


class DepartmentStaffListAPIView(APIView):
    """Staff members of a department (for assignment dropdown)."""
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request, pk):
        if not request.user.is_superuser:
            if not DepartmentMembership.objects.filter(user=request.user, department_id=pk).exists():
                return err("Forbidden", status.HTTP_403_FORBIDDEN)
        members = DepartmentMembership.objects.filter(department_id=pk).select_related("user")
        data = [
            {
                "id": m.user_id,
                "username": m.user.username,
                "email": m.user.email,
                "is_manager": m.is_manager,
            }
            for m in members
            if m.user.is_active
        ]
        return ok(data=data)


class StaffTicketDeleteAPIView(APIView):
    """Hard-delete a ticket (superuser or staff with department manager / tickets.delete rule)."""
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def delete(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        user = request.user
        if not user.is_superuser:
            from users.admin_apis import user_has_rule
            if not user_has_rule(user, "tickets.delete"):
                from ..models import DepartmentMembership
                if not DepartmentMembership.objects.filter(
                    user=user, department_id=ticket.department_id, is_manager=True
                ).exists():
                    return err("Forbidden", status.HTTP_403_FORBIDDEN)
        ticket.delete()
        return ok("Ticket deleted")


class TicketMarkReadAPIView(APIView):
    """
    POST /api/tickets/<pk>/read/
    Marks messages from the other party as seen and updates TicketReadState.
    Call only when the user is viewing the ticket (not merely online).
    """
    permission_classes = [IsAuthenticated, IsTicketOwnerOrStaff]

    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        user = request.user
        now = timezone.now()
        qs = ticket.messages.filter(seen_at__isnull=True).exclude(author_id=user.id)
        marked_ids = list(qs.values_list("id", flat=True)[:200])
        updated = qs.update(seen_at=now) if marked_ids else 0
        from ..models import TicketReadState
        TicketReadState.objects.update_or_create(
            ticket=ticket, user=user, defaults={"last_read_at": now}
        )
        # Broadcast only when something newly became seen
        if updated > 0:
            try:
                from .consumers import broadcast_ticket_event
                broadcast_ticket_event(
                    "ticket.seen",
                    ticket,
                    extra={
                        "reader_id": user.id,
                        "marked": updated,
                        "message_ids": marked_ids,
                        "is_staff": bool(user.is_staff or user.is_superuser),
                    },
                )
            except Exception:
                import logging
                logging.getLogger("tickets.apis").exception("ticket.seen broadcast failed")
        return ok(
            "Marked as read",
            data={
                "marked": updated,
                "message_ids": marked_ids,
                "last_read_at": now.isoformat(),
            },
        )


class AdminUserMembershipAPIView(APIView):
    """
    Manage department memberships for a single user (multi-department).
    GET  /api/tickets/admin/users/<user_id>/memberships/
    PUT  /api/tickets/admin/users/<user_id>/memberships/
         body: { "memberships": [ {"department_id": 1, "is_manager": false}, ... ] }
    """
    permission_classes = [IsSuperuserOnly]

    def get(self, request, user_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        memberships = list(
            DepartmentMembership.objects.filter(user=user).select_related("department")
        )
        all_depts = list(Department.objects.filter(is_active=True).order_by("order", "name"))
        return ok(data={
            "user_id": user.id,
            "username": user.username,
            "is_staff": user.is_staff,
            "memberships": [
                {
                    "id": m.id,
                    "department_id": m.department_id,
                    "department_name": m.department.name,
                    "is_manager": m.is_manager,
                }
                for m in memberships
            ],
            "departments": [
                {"id": d.id, "name": d.name, "slug": d.slug}
                for d in all_depts
            ],
        })

    def put(self, request, user_id):
        from django.contrib.auth import get_user_model
        from django.db import transaction
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        raw = request.data.get("memberships")
        if raw is None:
            return err("memberships list required")
        if not isinstance(raw, list):
            return err("memberships must be a list")
        # Normalize
        wanted = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                did = int(item.get("department_id"))
            except (TypeError, ValueError):
                continue
            wanted[did] = bool(item.get("is_manager", False))
        valid_ids = set(
            Department.objects.filter(id__in=wanted.keys(), is_active=True).values_list("id", flat=True)
        )
        wanted = {k: v for k, v in wanted.items() if k in valid_ids}
        with transaction.atomic():
            existing = {
                m.department_id: m
                for m in DepartmentMembership.objects.filter(user=user)
            }
            # delete removed
            for did, mem in list(existing.items()):
                if did not in wanted:
                    mem.delete()
            # create/update
            for did, is_mgr in wanted.items():
                if did in existing:
                    mem = existing[did]
                    if mem.is_manager != is_mgr:
                        mem.is_manager = is_mgr
                        mem.save(update_fields=["is_manager"])
                else:
                    DepartmentMembership.objects.create(
                        user=user, department_id=did, is_manager=is_mgr
                    )
        memberships = list(
            DepartmentMembership.objects.filter(user=user).select_related("department")
        )
        return ok(
            "Memberships updated",
            data={
                "user_id": user.id,
                "memberships": [
                    {
                        "id": m.id,
                        "department_id": m.department_id,
                        "department_name": m.department.name,
                        "is_manager": m.is_manager,
                    }
                    for m in memberships
                ],
            },
        )
