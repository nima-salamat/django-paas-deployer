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
from ..permissions import IsTicketOwnerOrStaff, IsStaffOrSuperuser, CanManageTicket
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

class StaffTicketListAPIView(APIView):
    """
    Advanced filters:
      status, priority (comma-separated multi)
      department, assigned_to (me|unassigned|<id>)
      search (public_id, subject, username, email)
      created_from, created_to, updated_from (ISO date)
      service_id, has_attachments (1/0)
      ordering: -last_message_at (default), created_at, priority, status
    """
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        from django.utils.dateparse import parse_date, parse_datetime

        qs = Ticket.objects.select_related(
            "department", "user", "service", "deploy", "assigned_to"
        ).annotate(message_count=Count("messages"))

        if not request.user.is_superuser:
            dept_ids = list(
                DepartmentMembership.objects.filter(user=request.user).values_list(
                    "department_id", flat=True
                )
            )
            qs = qs.filter(department_id__in=dept_ids)

        status_raw = request.query_params.get("status", "").strip()
        if status_raw:
            statuses = [s.strip() for s in status_raw.split(",") if s.strip()]
            qs = qs.filter(status__in=statuses) if len(statuses) > 1 else qs.filter(status=statuses[0])

        priority_raw = request.query_params.get("priority", "").strip()
        if priority_raw:
            priorities = [p.strip() for p in priority_raw.split(",") if p.strip()]
            qs = qs.filter(priority__in=priorities) if len(priorities) > 1 else qs.filter(priority=priorities[0])

        if request.query_params.get("department"):
            qs = qs.filter(department_id=request.query_params["department"])

        if request.query_params.get("service_id"):
            qs = qs.filter(service_id=request.query_params["service_id"])

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(subject__icontains=search)
                | Q(public_id__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
            )

        assigned = request.query_params.get("assigned_to")
        if assigned == "me":
            qs = qs.filter(assigned_to=request.user)
        elif assigned == "unassigned":
            qs = qs.filter(assigned_to__isnull=True)
        elif assigned:
            qs = qs.filter(assigned_to_id=assigned)

        def _parse_dt(val):
            if not val:
                return None
            dt = parse_datetime(val)
            if dt:
                return dt
            d = parse_date(val)
            if d:
                from datetime import datetime, time
                from django.utils import timezone as tz
                return tz.make_aware(datetime.combine(d, time.min))
            return None

        created_from = _parse_dt(request.query_params.get("created_from"))
        created_to = _parse_dt(request.query_params.get("created_to"))
        updated_from = _parse_dt(request.query_params.get("updated_from"))
        if created_from:
            qs = qs.filter(created_at__gte=created_from)
        if created_to:
            qs = qs.filter(created_at__lte=created_to)
        if updated_from:
            qs = qs.filter(updated_at__gte=updated_from)

        has_att = request.query_params.get("has_attachments")
        if has_att in ("1", "true", "True"):
            qs = qs.filter(attachments__isnull=False).distinct()
        elif has_att in ("0", "false", "False"):
            qs = qs.filter(attachments__isnull=True)

        ordering = request.query_params.get("ordering", "-last_message_at").strip()
        allowed_order = {
            "created_at", "-created_at",
            "last_message_at", "-last_message_at",
            "priority", "-priority",
            "status", "-status",
            "updated_at", "-updated_at",
        }
        if ordering in allowed_order:
            qs = qs.order_by(ordering, "-id")
        else:
            qs = qs.order_by("-last_message_at", "-id")

        paginator = TicketPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            TicketListSerializer(page, many=True, context={"request": request}).data
        )


class StaffTicketStatusAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser, CanManageTicket]
    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        ser = TicketStatusSerializer(data=request.data)
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        ticket.status = ser.validated_data["status"]
        ticket.closed_at = timezone.now() if ticket.status in (Ticket.Status.CLOSED, Ticket.Status.RESOLVED) else None
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        return ok("Status updated", data=TicketDetailSerializer(ticket, context={"request": request}).data)

class StaffTicketPriorityAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser, CanManageTicket]
    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        ser = TicketPrioritySerializer(data=request.data)
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        ticket.priority = ser.validated_data["priority"]
        ticket.save(update_fields=["priority", "updated_at"])
        return ok("Priority updated", data={"priority": ticket.priority})

class StaffTicketAssignDepartmentAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]
    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        if not request.user.is_superuser:
            if not DepartmentMembership.objects.filter(user=request.user, department_id=ticket.department_id, is_manager=True).exists():
                return err("Permission denied.", status.HTTP_403_FORBIDDEN)
        ser = TicketAssignDepartmentSerializer(data=request.data)
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        ticket.department_id = ser.validated_data["department_id"]
        ticket.save(update_fields=["department_id", "updated_at"])
        return ok("Department updated", data=TicketDetailSerializer(ticket, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------
class StaffTicketStatsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        user = request.user
        qs = Ticket.objects.all()
        if not user.is_superuser:
            dept_ids = DepartmentMembership.objects.filter(user=user).values_list("department_id", flat=True)
            qs = qs.filter(department_id__in=dept_ids)

        def c(status=None, **extra):
            q = qs
            if status:
                q = q.filter(status=status)
            return q.filter(**extra).count() if extra else q.count()

        by_dept = list(
            qs.values("department_id", "department__name")
            .annotate(total=Count("id"), open=Count("id", filter=Q(status=Ticket.Status.OPEN)))
            .order_by("department__name")
        )
        data = {
            "total": qs.count(),
            "open": c(Ticket.Status.OPEN),
            "in_progress": c(Ticket.Status.IN_PROGRESS),
            "waiting_user": c(Ticket.Status.WAITING_USER),
            "resolved": c(Ticket.Status.RESOLVED),
            "closed": c(Ticket.Status.CLOSED),
            "urgent": qs.filter(priority=Ticket.Priority.URGENT).exclude(
                status__in=[Ticket.Status.CLOSED, Ticket.Status.RESOLVED]
            ).count(),
            "unassigned": qs.filter(assigned_to__isnull=True).exclude(
                status__in=[Ticket.Status.CLOSED, Ticket.Status.RESOLVED]
            ).count(),
            "by_department": [
                {
                    "department_id": r["department_id"],
                    "name": r["department__name"],
                    "total": r["total"],
                    "open": r["open"],
                }
                for r in by_dept
            ],
        }
        return ok(data=data)


# ---------------------------------------------------------------------------
# Assign ticket to staff
# ---------------------------------------------------------------------------
class StaffTicketAssignAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser, CanManageTicket]

    def post(self, request, pk):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        assignee_id = request.data.get("assigned_to_id")
        if assignee_id in (None, "", "null"):
            ticket.assigned_to = None
            ticket.save(update_fields=["assigned_to", "updated_at"])
            return ok("Unassigned", data=TicketDetailSerializer(ticket, context={"request": request}).data)
        try:
            assignee = User.objects.get(pk=assignee_id, is_staff=True, is_active=True)
        except User.DoesNotExist:
            return err("Staff user not found.")
        # Assignee should belong to ticket department (unless superuser assigning)
        if not request.user.is_superuser:
            if not DepartmentMembership.objects.filter(user=assignee, department_id=ticket.department_id).exists():
                return err("Assignee is not a member of this department.")
        ticket.assigned_to = assignee
        ticket.save(update_fields=["assigned_to", "updated_at"])
        return ok("Assigned", data=TicketDetailSerializer(ticket, context={"request": request}).data)
