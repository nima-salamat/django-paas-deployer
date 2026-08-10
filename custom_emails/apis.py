from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from .models import EmailTemplate, EmailLog
from .serializers import EmailTemplateSerializer, EmailTemplatePreviewSerializer, EmailSendSerializer, EmailLogSerializer
from .services import build_context, render_template_string, sanitize_email_html, prevent_header_injection
from .tasks import send_email_log_task, send_bulk_email_task
from tickets.utils import check_rate_limit

User = get_user_model()

def ok(message="success", data=None, http_status=200):
    body = {"success": True, "message": message}
    if data is not None: body["data"] = data
    return Response(body, status=http_status)

def err(message, http_status=400, extra=None):
    body = {"success": False, "message": message}
    if extra: body.update(extra)
    return Response(body, status=http_status)

class IsStaffUser(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and (request.user.is_staff or request.user.is_superuser))

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class EmailTemplateListCreateAPIView(APIView):
    permission_classes = [IsStaffUser]
    def get(self, request):
        qs = EmailTemplate.objects.all()
        search = request.query_params.get("search","").strip()
        if search: qs = qs.filter(Q(name__icontains=search)|Q(subject__icontains=search))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EmailTemplateSerializer(page, many=True).data)
    def post(self, request):
        ser = EmailTemplateSerializer(data=request.data)
        if not ser.is_valid(): return err("Validation failed", extra={"errors": ser.errors})
        obj = ser.save(created_by=request.user)
        return ok("Created", data=EmailTemplateSerializer(obj).data, http_status=201)

class EmailTemplateDetailAPIView(APIView):
    permission_classes = [IsStaffUser]
    def get_object(self, pk):
        try: return EmailTemplate.objects.get(pk=pk)
        except EmailTemplate.DoesNotExist: return None
    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj: return err("Not found", 404)
        return ok(data=EmailTemplateSerializer(obj).data)
    def put(self, request, pk):
        obj = self.get_object(pk)
        if not obj: return err("Not found", 404)
        ser = EmailTemplateSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid(): return err("Validation failed", extra={"errors": ser.errors})
        ser.save()
        return ok("Updated", data=ser.data)
    def delete(self, request, pk):
        obj = self.get_object(pk)
        if not obj: return err("Not found", 404)
        obj.is_active = False
        obj.save(update_fields=["is_active","updated_at"])
        return ok("Deactivated")

class EmailTemplatePreviewAPIView(APIView):
    permission_classes = [IsStaffUser]
    def post(self, request):
        ser = EmailTemplatePreviewSerializer(data=request.data)
        if not ser.is_valid(): return err("Validation failed", extra={"errors": ser.errors})
        data = ser.validated_data
        user = User.objects.filter(pk=data["user_id"]).first() if data.get("user_id") else None
        ctx = build_context(user)
        try:
            subject = render_template_string(data["subject"], ctx)
            body = sanitize_email_html(render_template_string(data["body"], ctx))
        except ValueError as e:
            return err(str(e))
        return ok(data={"subject": subject, "body": body, "context": ctx})

class EmailSendAPIView(APIView):
    permission_classes = [IsStaffUser]
    def post(self, request):
        if not check_rate_limit(f"email_send:{request.user.id}", 30, 3600):
            return err("Rate limit exceeded", 429)
        ser = EmailSendSerializer(data=request.data)
        if not ser.is_valid(): return err("Validation failed", extra={"errors": ser.errors})
        data = ser.validated_data
        template = data.get("_template")
        if data.get("is_test"):
            test_email = prevent_header_injection(data["test_email"])
            ctx = build_context(request.user)
            subject = data.get("subject") or (template.subject if template else "")
            body = data.get("body") or (template.body if template else "")
            try:
                subject = prevent_header_injection(render_template_string(subject, ctx))
                body = sanitize_email_html(render_template_string(body, ctx))
            except ValueError as e:
                return err(str(e))
            log = EmailLog.objects.create(recipient=request.user, recipient_email=test_email, template=template, subject=subject, body_preview=body[:5000], status=EmailLog.Status.PENDING, sent_by=request.user, is_test=True)
            send_email_log_task.delay(log.id)
            return ok("Test queued", data={"log_id": log.id})
        recipients = []
        for u in User.objects.filter(pk__in=data.get("user_ids") or [], is_active=True).exclude(email__isnull=True).exclude(email=""):
            recipients.append((u, u.email))
        for email in data.get("emails") or []:
            recipients.append((None, prevent_header_injection(email)))
        if not recipients: return err("No valid recipients")
        if len(recipients) > 500: return err("Max 500 recipients")
        log_ids = []
        base_subject = data.get("subject") or (template.subject if template else "")
        base_body = data.get("body") or (template.body if template else "")
        for user, email in recipients:
            ctx = build_context(user)
            try:
                subject = prevent_header_injection(render_template_string(base_subject, ctx))
                body = sanitize_email_html(render_template_string(base_body, ctx))
            except ValueError as e:
                return err(str(e))
            log = EmailLog.objects.create(recipient=user, recipient_email=email, template=template, subject=subject, body_preview=body[:5000], status=EmailLog.Status.PENDING, sent_by=request.user, is_test=False)
            log_ids.append(log.id)
        send_bulk_email_task.delay(log_ids)
        return ok(f"Queued {len(log_ids)} emails", data={"queued": len(log_ids)}, http_status=202)

class EmailLogListAPIView(APIView):
    permission_classes = [IsStaffUser]
    def get(self, request):
        qs = EmailLog.objects.select_related("recipient","template").all()
        if request.query_params.get("status"): qs = qs.filter(status=request.query_params["status"])
        search = request.query_params.get("search","").strip()
        if search: qs = qs.filter(Q(recipient_email__icontains=search)|Q(subject__icontains=search))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EmailLogSerializer(page, many=True).data)

class EmailLogDetailAPIView(APIView):
    permission_classes = [IsStaffUser]
    def get(self, request, pk):
        try: log = EmailLog.objects.select_related("recipient","template").get(pk=pk)
        except EmailLog.DoesNotExist: return err("Not found", 404)
        return ok(data=EmailLogSerializer(log).data)
