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
        from core.app_cache import (
            cache_get, cache_set, ticket_user_list_key, TICKET_USER_TTL, TICKET_USER_LIMIT,
        )
        params = {k: request.query_params.get(k) or "" for k in ("status", "priority", "department", "search", "page", "page_size")}
        key = ticket_user_list_key(request.user.id, params)
        cached = cache_get(key)
        if cached is not None:
            # Must match the uncached response shape (paginated body, not ok() wrapper)
            return Response(cached)
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
        # Newest activity first (model Meta already orders by -last_message_at; keep explicit)
        # Do NOT slice before paginate — sliced QS breaks Paginator.count()
        qs = qs.order_by("-last_message_at", "-created_at", "-id")
        paginator = TicketPagination()
        page = paginator.paginate_queryset(qs, request)
        data = TicketListSerializer(page, many=True, context={"request": request}).data
        resp = paginator.get_paginated_response(data)
        try:
            cache_set(key, resp.data, TICKET_USER_TTL)
        except Exception:
            pass
        return resp

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
        raw_body = request.data.get("body")
        # Ensure we always work with a plain string (avoids [object Object] downstream)
        if isinstance(raw_body, (list, tuple)):
            raw_body = raw_body[0] if raw_body else ""
        if not isinstance(raw_body, str):
            raw_body = "" if raw_body is None else str(raw_body)
        body_raw = raw_body.strip()
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
        # Re-fetch so attachments (with download_url) are included in the response
        msg = (
            TicketMessage.objects
            .select_related("author")
            .prefetch_related("attachments")
            .get(pk=msg.pk)
        )
        return ok(
            "Message sent",
            data=TicketMessageSerializer(msg, context={"request": request}).data,
            http_status=status.HTTP_201_CREATED,
        )


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

