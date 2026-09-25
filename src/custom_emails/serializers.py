from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import EmailTemplate, EmailLog

User = get_user_model()

class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ("id","name","subject","body","description","is_active","created_at","updated_at")
        read_only_fields = ("id","created_at","updated_at")

class EmailTemplatePreviewSerializer(serializers.Serializer):
    template_id = serializers.IntegerField(required=False)
    subject = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)
    user_id = serializers.IntegerField(required=False, allow_null=True)
    def validate(self, attrs):
        tid = attrs.get("template_id")
        if tid:
            try:
                tpl = EmailTemplate.objects.get(pk=tid)
            except EmailTemplate.DoesNotExist:
                raise serializers.ValidationError({"template_id": "Not found"})
            attrs["_template"] = tpl
            attrs.setdefault("subject", tpl.subject)
            attrs.setdefault("body", tpl.body)
        if not attrs.get("subject") or not attrs.get("body"):
            raise serializers.ValidationError("subject and body required")
        return attrs

class EmailSendSerializer(serializers.Serializer):
    template_id = serializers.IntegerField(required=False, allow_null=True)
    user_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    emails = serializers.ListField(child=serializers.EmailField(), required=False, allow_empty=True)
    subject = serializers.CharField(required=False, allow_blank=True, max_length=255)
    body = serializers.CharField(required=False, allow_blank=True)
    is_test = serializers.BooleanField(default=False)
    test_email = serializers.EmailField(required=False, allow_null=True)
    def validate(self, attrs):
        if attrs.get("is_test"):
            if not attrs.get("test_email"):
                raise serializers.ValidationError({"test_email": "Required for test"})
        elif not attrs.get("user_ids") and not attrs.get("emails"):
            raise serializers.ValidationError("Provide user_ids or emails")
        tid = attrs.get("template_id")
        if tid:
            try:
                attrs["_template"] = EmailTemplate.objects.get(pk=tid, is_active=True)
            except EmailTemplate.DoesNotExist:
                raise serializers.ValidationError({"template_id": "Active template not found"})
        elif not attrs.get("subject") or not attrs.get("body"):
            raise serializers.ValidationError("subject and body required without template")
        return attrs

class EmailLogSerializer(serializers.ModelSerializer):
    recipient_username = serializers.CharField(source="recipient.username", read_only=True, default="")
    template_name = serializers.CharField(source="template.name", read_only=True, default="")
    class Meta:
        model = EmailLog
        fields = ("id","recipient","recipient_username","recipient_email","template","template_name","subject","status","error_message","is_test","created_at","sent_at","failed_at")
        read_only_fields = fields
