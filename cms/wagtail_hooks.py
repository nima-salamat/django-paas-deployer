"""
Register domain models in Wagtail admin (snippets).

User management is handled by wagtail.users (with our custom forms).
"""
from __future__ import annotations

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


def _register():
    try:
        from messenger.models import Conversation, Message, CallSession
    except Exception:
        Conversation = Message = CallSession = None  # type: ignore

    try:
        from tickets.models import Ticket
    except Exception:
        Ticket = None  # type: ignore

    if Conversation is not None:

        class ConversationViewSet(SnippetViewSet):
            model = Conversation
            icon = "group"
            menu_label = "Conversations"
            menu_order = 200
            list_display = ["id", "public_id", "type", "title", "updated_at"]
            search_fields = ["public_id", "title"]
            list_filter = ["type", "is_public", "is_closed"]

        class MessageViewSet(SnippetViewSet):
            model = Message
            icon = "comment"
            menu_label = "Messages"
            menu_order = 210
            list_display = ["id", "conversation_id", "sender_id", "is_system", "created_at"]
            search_fields = ["body"]

        class CallSessionViewSet(SnippetViewSet):
            model = CallSession
            icon = "media"
            menu_label = "Call sessions"
            menu_order = 220
            list_display = [
                "public_id",
                "conversation_id",
                "status",
                "is_video",
                "started_at",
                "duration_seconds",
            ]
            list_filter = ["status", "is_video"]

        class MessengerGroup(SnippetViewSetGroup):
            items = (ConversationViewSet, MessageViewSet, CallSessionViewSet)
            menu_label = "Messenger"
            menu_icon = "comment"
            menu_order = 200

        register_snippet(MessengerGroup)

    if Ticket is not None:

        class TicketViewSet(SnippetViewSet):
            model = Ticket
            icon = "doc-full"
            menu_label = "Tickets"
            menu_order = 300
            list_display = ["id", "public_id", "subject", "status", "priority", "created_at"]
            search_fields = ["subject", "public_id"]
            list_filter = ["status", "priority"]

        register_snippet(TicketViewSet)


_register()
