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
from rest_framework.pagination import PageNumberPagination
from .models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment
from .permissions import IsTicketOwnerOrStaff, IsStaffOrSuperuser, CanManageTicket
from .serializers import (
    DepartmentSerializer, TicketListSerializer, TicketDetailSerializer,
    TicketCreateSerializer, TicketMessageCreateSerializer, TicketMessageSerializer,
    TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer,
)
from .utils import check_rate_limit, get_ticket_setting, validate_upload_file, safe_filename

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
            TicketAttachment.objects.create(ticket=ticket, message=msg, uploaded_by=user, file=f, original_filename=safe_filename(f.name), content_type=getattr(f, "content_type", "") or "", size=f.size)
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
        ser = TicketMessageCreateSerializer(data=request.data)
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
        files = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        for f in files[:int(get_ticket_setting("tickets.max_attachments_per_message", 5))]:
            try:
                validate_upload_file(f)
            except Exception as e:
                return err(str(e))
            TicketAttachment.objects.create(ticket=ticket, message=msg, uploaded_by=request.user, file=f, original_filename=safe_filename(f.name), content_type=getattr(f, "content_type", "") or "", size=f.size)
        return ok("Message sent", data=TicketMessageSerializer(msg, context={"request": request}).data, http_status=status.HTTP_201_CREATED)

class AttachmentDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTicketOwnerOrStaff]
    def get(self, request, pk):
        try:
            att = TicketAttachment.objects.select_related("ticket").get(pk=pk)
        except TicketAttachment.DoesNotExist:
            raise Http404
        self.check_object_permissions(request, att)
        if not att.file or not att.file.storage.exists(att.file.name):
            raise Http404("File not found.")
        handle = att.file.open("rb")
        response = FileResponse(handle, as_attachment=True, filename=att.original_filename or "attachment")
        if att.content_type:
            response["Content-Type"] = att.content_type
        return response

class StaffTicketListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]
    def get(self, request):
        qs = Ticket.objects.select_related("department", "user", "service", "deploy").annotate(message_count=Count("messages"))
        if not request.user.is_superuser:
            dept_ids = DepartmentMembership.objects.filter(user=request.user).values_list("department_id", flat=True)
            qs = qs.filter(department_id__in=dept_ids)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("priority"):
            qs = qs.filter(priority=request.query_params["priority"])
        if request.query_params.get("department"):
            qs = qs.filter(department_id=request.query_params["department"])
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(subject__icontains=search) | Q(public_id__icontains=search) | Q(user__username__icontains=search))
        paginator = TicketPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(TicketListSerializer(page, many=True, context={"request": request}).data)

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
