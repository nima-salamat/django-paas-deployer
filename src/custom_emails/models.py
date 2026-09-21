
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
User = settings.AUTH_USER_MODEL

class EmailTemplate(models.Model):
    name = models.CharField(max_length=120, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField(help_text="HTML. Variables: {{ user.username }}, {{ user.email }}, {{ site_name }}")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_email_templates")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["name"]
    def __str__(self):
        return self.name

class EmailLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs")
    recipient_email = models.EmailField()
    template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs")
    subject = models.CharField(max_length=255)
    body_preview = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.TextField(blank=True, default="")
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_email_logs")
    is_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True, default="")
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]
    def __str__(self):
        return f"{self.recipient_email} ({self.status})"
