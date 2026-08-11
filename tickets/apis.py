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
from .models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment
from .permissions import IsTicketOwnerOrStaff, IsStaffOrSuperuser, CanManageTicket
from .serializers import (
    DepartmentSerializer, TicketListSerializer, TicketDetailSerializer,
    TicketCreateSerializer, TicketMessageCreateSerializer, TicketMessageSerializer,
    TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer,
)
from .utils import check_rate_limit, get_ticket_setting, validate_upload_file, safe_filename, validate_ticket_quota

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

class TicketPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 50

class DepartmentListAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = Department.objects.filter(is_active=True).order_by("order", "name")
        if (request.user.is_staff or request.user.is_superuser) and request.query_params.get("all") == "1":
            qs = Department.objects.all().order_by("order", "name")
        return ok(data=DepartmentSerializer(qs, many=True).data)


class MyTicketContextAPIView(APIView):
    """User's services and deploys for optional ticket linking."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from services.models import Service
        from deploy.models import Deploy

        services = Service.objects.filter(user=request.user).order_by("name").only("id", "name")
        service_id = request.query_params.get("service_id")
        deploys_qs = Deploy.objects.filter(service__user=request.user).select_related("service")
        if service_id:
            deploys_qs = deploys_qs.filter(service_id=service_id)
        deploys_qs = deploys_qs.order_by("-created_at")[:50]

        def deploy_label(d):
            name = getattr(d, "name", None)
            if name:
                return name
            ver = getattr(d, "version", None)
            if ver is not None and str(ver) != "":
                return f"v{ver}"
            return str(d.id)[:8]

        return ok(data={
            "services": [{"id": str(s.id), "name": s.name} for s in services],
            "deploys": [{
                "id": str(d.id),
                "name": deploy_label(d),
                "version": str(getattr(d, "version", "") or ""),
                "status": getattr(d, "status", "") or "",
                "service_id": str(d.service_id),
            } for d in deploys_qs],
        })

class MyTicketListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    def get(self, request):
        qs = Ticket.objects.filter(user=request.user).select_related("department", "user", "service", "deploy").annotate(message_count=Count("messages"))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("priority"):
            qs = qs.filter(priority=request.query_params["priority"])
        if request.query_params.get("department"):
            qs = qs.filter(department_id=request.query_params["department"])
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(subject__icontains=search) | Q(public_id__icontains=search))
        paginator = TicketPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(TicketListSerializer(page, many=True, context={"request": request}).data)

    def post(self, request):
        user = request.user
        max_open = int(get_ticket_setting("tickets.max_open_per_user", 10))
        open_count = Ticket.objects.filter(user=user, status__in=[Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING_USER]).count()
        if open_count >= max_open:
            return err(f"Open ticket limit reached ({max_open}).", status.HTTP_429_TOO_MANY_REQUESTS)
        if not check_rate_limit(f"ticket_create:{user.id}", int(get_ticket_setting("tickets.create_rate_limit", 5)), int(get_ticket_setting("tickets.create_rate_window", 3600))):
            return err("Rate limit exceeded.", status.HTTP_429_TOO_MANY_REQUESTS)
        ser = TicketCreateSerializer(data=request.data, context={"request": request})
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        data = ser.validated_data
        ticket = Ticket.objects.create(
            user=user,
            department_id=data["department_id"],
            subject=data["subject"],
            priority=data.get("priority", Ticket.Priority.NORMAL),
            service_id=data.get("service_id"),
            deploy_id=data.get("deploy_id"),
            last_message_at=timezone.now(),
        )
        msg = TicketMessage.objects.create(ticket=ticket, author=user, body=data["body"], is_staff_reply=False)
        files = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        max_files = int(get_ticket_setting("tickets.max_attachments_per_message", 5))
        if len(files) > max_files:
            return err(f"Max {max_files} attachments.")
        for f in files:
            try:
                validate_upload_file(f)
            except Exception as e:
                return err(str(e))
        try:
            validate_ticket_quota(ticket.id, [getattr(f, "size", 0) for f in files])
        except Exception as e:
            return err(str(e))
        for f in files:
            TicketAttachment.objects.create(
                ticket=ticket,
                message=msg,
                uploaded_by=user,
                file=f,
                original_filename=safe_filename(f.name),
                content_type=getattr(f, "content_type", "") or "",
                size=f.size,
            )
        return ok("Ticket created", data=TicketDetailSerializer(ticket, context={"request": request}).data, http_status=status.HTTP_201_CREATED)

class TicketDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTicketOwnerOrStaff]
    def get_object(self, pk):
        try:
            return Ticket.objects.select_related("department", "user", "assigned_to", "service", "deploy").prefetch_related(
                Prefetch("messages", queryset=TicketMessage.objects.select_related("author").prefetch_related("attachments")), "attachments"
            ).get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
    def get(self, request, pk):
        ticket = self.get_object(pk)
        self.check_object_permissions(request, ticket)
        return ok(data=TicketDetailSerializer(ticket, context={"request": request}).data)

class TicketCloseAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTicketOwnerOrStaff]
    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        if ticket.status == Ticket.Status.CLOSED:
            return err("Already closed.")
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        return ok("Ticket closed", data=TicketDetailSerializer(ticket, context={"request": request}).data)

class TicketMessageCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTicketOwnerOrStaff]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    def post(self, request, pk):
        try:
            ticket = Ticket.objects.select_related("department").get(pk=pk)
        except Ticket.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, ticket)
        if ticket.status == Ticket.Status.CLOSED:
            return err("Cannot reply to closed ticket.")
        if not check_rate_limit(f"ticket_msg:{request.user.id}", int(get_ticket_setting("tickets.message_rate_limit", 20)), int(get_ticket_setting("tickets.message_rate_window", 3600))):
            return err("Message rate limit exceeded.", status.HTTP_429_TOO_MANY_REQUESTS)
        files = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        body_raw = (request.data.get("body") or "").strip()
        if not body_raw and not files:
            return err("Body or attachments required.")
        ser = TicketMessageCreateSerializer(data={"body": body_raw or "<p></p>"})
        if not ser.is_valid():
            return err("Validation failed", extra={"errors": ser.errors})
        is_staff_reply = bool(request.user.is_staff or request.user.is_superuser) and ticket.user_id != request.user.id
        msg = TicketMessage.objects.create(ticket=ticket, author=request.user, body=ser.validated_data["body"], is_staff_reply=is_staff_reply)
        if is_staff_reply and ticket.status in (Ticket.Status.OPEN, Ticket.Status.WAITING_USER):
            ticket.status = Ticket.Status.IN_PROGRESS
            ticket.save(update_fields=["status", "updated_at"])
        elif not is_staff_reply and ticket.status == Ticket.Status.WAITING_USER:
            ticket.status = Ticket.Status.IN_PROGRESS
            ticket.save(update_fields=["status", "updated_at"])
        files = files[: int(get_ticket_setting("tickets.max_attachments_per_message", 5))]
        for f in files:
            try:
                validate_upload_file(f)
            except Exception as e:
                return err(str(e))
        try:
            validate_ticket_quota(ticket.id, [getattr(f, "size", 0) for f in files])
        except Exception as e:
            return err(str(e))
        for f in files:
            TicketAttachment.objects.create(
                ticket=ticket,
                message=msg,
                uploaded_by=request.user,
                file=f,
                original_filename=safe_filename(f.name),
                content_type=getattr(f, "content_type", "") or "",
                size=f.size,
            )
        return ok("Message sent", data=TicketMessageSerializer(msg, context={"request": request}).data, http_status=status.HTTP_201_CREATED)


def user_can_access_ticket(user, ticket) -> bool:
    """
    Strict access for ticket content (messages/attachments):
    - authenticated + active
    - superuser
    - ticket owner
    - staff assigned to this ticket
    - staff with DepartmentMembership on ticket.department
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", True):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if ticket is None:
        return False
    if ticket.user_id == user.id:
        return True
    # staff-only paths below
    if not getattr(user, "is_staff", False):
        return False
    if getattr(ticket, "assigned_to_id", None) and ticket.assigned_to_id == user.id:
        return True
    dept_id = getattr(ticket, "department_id", None)
    if dept_id and DepartmentMembership.objects.filter(user=user, department_id=dept_id).exists():
        return True
    return False



class JWTQueryOrHeaderAuthentication(JWTAuthentication):
    """Accept Bearer header OR ?token= / ?access= query (for <img>/<audio> tags)."""

    def authenticate(self, request):
        raw = request.GET.get("token") or request.GET.get("access")
        if raw:
            validated = self.get_validated_token(raw)
            return self.get_user(validated), validated
        return super().authenticate(request)


class AttachmentDownloadAPIView(APIView):
    """
    Download / preview a ticket attachment.
    Auth: JWT or session. Access (strict):
      - active user
      - ticket owner, OR
      - superuser, OR
      - staff assigned to the ticket, OR
      - staff member of the ticket's department
    Random staff outside the department → 404.
    Media (image/audio/video) served inline for chat preview.
    """
    authentication_classes = [JWTQueryOrHeaderAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from pathlib import Path as _Path
        import mimetypes

        att = (
            TicketAttachment.objects
            .select_related("ticket", "ticket__user", "ticket__department")
            .filter(pk=pk)
            .first()
        )
        if not att:
            raise Http404("Attachment not found.")

        ticket = att.ticket
        if not user_can_access_ticket(request.user, ticket):
            raise Http404("Attachment not found.")

        if not att.file:
            raise Http404("No file available for this attachment.")

        try:
            exists = att.file.storage.exists(att.file.name)
        except Exception:
            exists = False
        if not exists:
            raise Http404("File not found on storage.")

        try:
            file_handle = att.file.open("rb")
        except Exception:
            raise Http404("File not accessible.")

        filename = att.original_filename or _Path(att.file.name).name or "attachment"
        # Prefer stored content_type; fall back to guess from filename
        content_type = (att.content_type or "").strip()
        if not content_type:
            guessed, _ = mimetypes.guess_type(filename)
            content_type = guessed or "application/octet-stream"

        ct_lower = content_type.lower()
        name_lower = filename.lower()
        inline = (
            ct_lower.startswith("image/")
            or ct_lower.startswith("audio/")
            or ct_lower.startswith("video/")
            or name_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
                                    ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac",
                                    ".mp4", ".webm", ".mov", ".mkv"))
        )

        response = FileResponse(
            file_handle,
            as_attachment=not inline,
            filename=filename,
            content_type=content_type,
        )
        # Explicit disposition helps browsers preview media in <img>/<audio>
        if inline:
            response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response

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


# ---------------------------------------------------------------------------
# Admin: Department CRUD
# ---------------------------------------------------------------------------
class IsSuperuserOnly(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and request.user.is_superuser)


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
                from .models import DepartmentMembership
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
        from .models import TicketReadState
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
