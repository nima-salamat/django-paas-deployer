"""Wagtail admin (snippet) registration for the custom_emails app."""
from __future__ import annotations

from cms.wagtail_admin.utils import panels_for
from custom_emails.models import EmailLog, EmailTemplate
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class EmailTemplateViewSet(SnippetViewSet):
    model = EmailTemplate
    icon = "mail"
    menu_label = "Email templates"
    menu_order = 130
    list_display = ["name", "subject", "is_active", "created_at"]
    search_fields = ["name", "subject"]
    list_filter = ["is_active"]
    ordering = ["name"]
    panels = panels_for(
        editable=["name", "subject", "body", "description", "is_active", "created_by"],
        read_only=["created_at", "updated_at"],
    )


class EmailLogViewSet(SnippetViewSet):
    model = EmailLog
    icon = "mail"
    menu_label = "Email log"
    menu_order = 131
    list_display = ["recipient_email", "subject", "status", "is_test", "created_at", "sent_at"]
    list_filter = ["status", "is_test"]
    search_fields = ["recipient_email", "subject"]
    ordering = ["-created_at"]
    panels = panels_for(
        editable=[],
        read_only=[
            "recipient",
            "recipient_email",
            "template",
            "subject",
            "body_preview",
            "status",
            "error_message",
            "sent_by",
            "is_test",
            "created_at",
            "sent_at",
            "failed_at",
            "celery_task_id",
        ],
    )


class EmailsGroup(SnippetViewSetGroup):
    items = (
        EmailTemplateViewSet,
        EmailLogViewSet,
    )
    menu_label = "Emails"
    menu_icon = "mail"
    menu_order = 130
