
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment
from .utils import sanitize_html

User = get_user_model()

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ("id","name","slug","description","is_active","order","created_at","updated_at")
        read_only_fields = ("id","slug","created_at","updated_at")

class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id","username","email","color")

class ServiceBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()

class DeployBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    version = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)

class TicketAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    class Meta:
        model = TicketAttachment
        fields = ("id","original_filename","content_type","size","created_at","download_url","message")
        read_only_fields = fields
    def get_download_url(self, obj):
        request = self.context.get("request")
        url = f"/api/tickets/attachments/{obj.pk}/download/"
        return request.build_absolute_uri(url) if request else url

class TicketMessageSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    class Meta:
        model = TicketMessage
        fields = ("id","author","body","is_staff_reply","created_at","updated_at","attachments")
        read_only_fields = fields

class TicketListSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    user = UserBriefSerializer(read_only=True)
    service = ServiceBriefSerializer(read_only=True)
    deploy = DeployBriefSerializer(read_only=True)
    message_count = serializers.IntegerField(read_only=True, required=False)
    class Meta:
        model = Ticket
        fields = ("id","public_id","subject","status","priority","department","user","service","deploy","created_at","updated_at","last_message_at","closed_at","message_count")

class TicketDetailSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    user = UserBriefSerializer(read_only=True)
    assigned_to = UserBriefSerializer(read_only=True)
    service = ServiceBriefSerializer(read_only=True)
    deploy = DeployBriefSerializer(read_only=True)
    messages = TicketMessageSerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    class Meta:
        model = Ticket
        fields = ("id","public_id","subject","status","priority","department","user","assigned_to","service","deploy","created_at","updated_at","last_message_at","closed_at","messages","attachments")

class TicketCreateSerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField()
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, default=Ticket.Priority.NORMAL, required=False)
    service_id = serializers.UUIDField(required=False, allow_null=True)
    deploy_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_department_id(self, value):
        if not Department.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Department not found or inactive.")
        return value

    def validate_subject(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Subject too short.")
        return value

    def validate_body(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Body required.")
        return sanitize_html(value)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        service_id = attrs.get("service_id")
        deploy_id = attrs.get("deploy_id")
        if service_id and user:
            from services.models import Service
            if not Service.objects.filter(pk=service_id, user=user).exists():
                raise serializers.ValidationError({"service_id": "Service not found or not owned by you."})
        if deploy_id and user:
            from deploy.models import Deploy
            qs = Deploy.objects.filter(pk=deploy_id, service__user=user)
            if service_id:
                qs = qs.filter(service_id=service_id)
            if not qs.exists():
                raise serializers.ValidationError({"deploy_id": "Deploy not found or not owned by you."})
            if not service_id:
                attrs["service_id"] = qs.first().service_id
        return attrs

class TicketMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField()
    def validate_body(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Body required.")
        return sanitize_html(value)

class TicketStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Ticket.Status.choices)

class TicketPrioritySerializer(serializers.Serializer):
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices)

class TicketAssignDepartmentSerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    def validate_department_id(self, value):
        if not Department.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Department not found.")
        return value
