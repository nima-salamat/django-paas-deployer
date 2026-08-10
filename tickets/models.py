"""
Ticketing system models.
"""
from __future__ import annotations
import os, uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

User = settings.AUTH_USER_MODEL

def ticket_attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    safe = "".join(c for c in os.path.splitext(filename)[0] if c.isalnum() or c in "-_")[:40]
    name = f"{uuid.uuid4().hex}_{safe}{ext}"
    ticket_id = instance.ticket_id or "tmp"
    return f"tickets/{ticket_id}/{name}"

class Department(models.Model):
    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(_("slug"), max_length=120, unique=True, blank=True)
    description = models.TextField(_("description"), blank=True, default="")
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("department")
        verbose_name_plural = _("departments")

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "department"
            slug, n = base, 1
            while Department.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"; n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class DepartmentMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="department_memberships")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="memberships")
    is_manager = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "department")

    def __str__(self):
        return f"{self.user} @ {self.department}"

class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        IN_PROGRESS = "in_progress", _("In Progress")
        WAITING_USER = "waiting_user", _("Waiting for User")
        RESOLVED = "resolved", _("Resolved")
        CLOSED = "closed", _("Closed")

    class Priority(models.TextChoices):
        LOW = "low", _("Low")
        NORMAL = "normal", _("Normal")
        HIGH = "high", _("High")
        URGENT = "urgent", _("Urgent")

    public_id = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="tickets")
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        verbose_name="related service",
    )
    deploy = models.ForeignKey(
        "deploy.Deploy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        verbose_name="related deploy",
    )
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["department", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = self._generate_public_id()
        if self.status in (self.Status.CLOSED, self.Status.RESOLVED) and not self.closed_at:
            self.closed_at = timezone.now()
        if self.status not in (self.Status.CLOSED, self.Status.RESOLVED):
            self.closed_at = None
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_public_id():
        date_part = timezone.now().strftime("%Y%m%d")
        for _ in range(20):
            candidate = f"TKT-{date_part}-{uuid.uuid4().hex[:4].upper()}"
            if not Ticket.objects.filter(public_id=candidate).exists():
                return candidate
        return f"TKT-{date_part}-{uuid.uuid4().hex[:8].upper()}"

    def __str__(self):
        return f"{self.public_id} — {self.subject[:40]}"

class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="ticket_messages")
    body = models.TextField()
    is_staff_reply = models.BooleanField(default=False)
    # When the other party (owner vs staff) has read this message
    seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        Ticket.objects.filter(pk=self.ticket_id).update(last_message_at=self.created_at, updated_at=timezone.now())


class TicketReadState(models.Model):
    """Per-user last-read cursor on a ticket (messenger-style)."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="read_states")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticket_read_states")
    last_read_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("ticket", "user")]
        indexes = [models.Index(fields=["user", "last_read_at"])]


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="ticket_attachments")
    file = models.FileField(upload_to=ticket_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
