"""Wagtail admin (snippet) registration for the tickets app."""
from __future__ import annotations

from cms.wagtail_admin.utils import panels_for
from tickets.models import (
    Department,
    DepartmentMembership,
    Ticket,
    TicketAttachment,
    TicketMessage,
    TicketReadState,
)
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class DepartmentViewSet(SnippetViewSet):
    model = Department
    icon = "folder-open-1"
    menu_label = "Departments"
    menu_order = 300
    list_display = ["name", "slug", "is_active", "order", "created_at"]
    search_fields = ["name", "slug"]
    list_filter = ["is_active"]
    panels = panels_for(
        editable=["name", "slug", "description", "is_active", "order"],
        read_only=["created_at", "updated_at"],
    )


class DepartmentMembershipViewSet(SnippetViewSet):
    model = DepartmentMembership
    icon = "group"
    menu_label = "Department members"
    menu_order = 301
    list_display = ["user", "department", "is_manager", "created_at"]
    search_fields = ["user__username", "department__name"]
    list_filter = ["is_manager", "department"]
    panels = panels_for(
        editable=["user", "department", "is_manager"],
        read_only=["created_at"],
    )


class TicketViewSet(SnippetViewSet):
    model = Ticket
    icon = "doc-full"
    menu_label = "Tickets"
    menu_order = 302
    list_display = ["id", "public_id", "subject", "status", "priority", "created_at"]
    search_fields = ["subject", "public_id"]
    list_filter = ["status", "priority"]
    panels = panels_for(
        editable=[
            "user",
            "department",
            "service",
            "deploy",
            "subject",
            "status",
            "priority",
            "assigned_to",
        ],
        read_only=[
            "public_id",
            "created_at",
            "updated_at",
            "closed_at",
            "last_message_at",
        ],
    )


class TicketMessageViewSet(SnippetViewSet):
    model = TicketMessage
    icon = "comment"
    menu_label = "Ticket messages"
    menu_order = 303
    list_display = ["id", "ticket", "author", "is_staff_reply", "created_at"]
    search_fields = ["ticket__public_id", "body"]
    list_filter = ["is_staff_reply"]
    panels = panels_for(
        editable=["ticket", "author", "body", "is_staff_reply"],
        read_only=["seen_at", "created_at", "updated_at"],
    )


class TicketReadStateViewSet(SnippetViewSet):
    model = TicketReadState
    icon = "tick"
    menu_label = "Ticket read states"
    menu_order = 304
    list_display = ["ticket", "user", "last_read_at", "updated_at"]
    search_fields = ["user__username", "ticket__public_id"]
    panels = panels_for(
        editable=["ticket", "user", "last_read_at"],
        read_only=["updated_at"],
    )


class TicketAttachmentViewSet(SnippetViewSet):
    model = TicketAttachment
    icon = "doc-full"
    menu_label = "Ticket attachments"
    menu_order = 305
    list_display = ["id", "ticket", "message", "original_filename", "size", "uploaded_by", "created_at"]
    search_fields = ["original_filename", "ticket__public_id"]
    panels = panels_for(
        editable=["ticket", "message", "uploaded_by", "file", "original_filename", "content_type", "size"],
        read_only=["created_at"],
    )


class TicketsGroup(SnippetViewSetGroup):
    items = (
        TicketViewSet,
        TicketMessageViewSet,
        TicketAttachmentViewSet,
        TicketReadStateViewSet,
        DepartmentViewSet,
        DepartmentMembershipViewSet,
    )
    menu_label = "Tickets"
    menu_icon = "doc-full"
    menu_order = 300