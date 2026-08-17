"""Wagtail admin (snippet) registration for the messenger app."""
from __future__ import annotations

from cms.wagtail_admin.utils import panels_for
from messenger.models import (
    AttachmentViewOnceOpen,
    Block,
    CallSession,
    Contact,
    Conversation,
    ConversationParticipant,
    GroupInviteLink,
    JoinRequest,
    Message,
    MessageAttachment,
    MessageReaction,
    MessageReadReceipt,
    PinnedMessage,
    ProfilePhotoAllowed,
    ProfilePhotoPrivacy,
    UserBio,
)
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class UserBioViewSet(SnippetViewSet):
    model = UserBio
    icon = "user"
    menu_label = "User bios"
    menu_order = 230
    list_display = ["id", "user", "updated_at"]
    search_fields = ["user__username", "text"]
    panels = panels_for(
        editable=["user", "text"],
        read_only=["updated_at"],
    )


class ContactViewSet(SnippetViewSet):
    model = Contact
    icon = "user"
    menu_label = "Contacts"
    menu_order = 231
    list_display = ["id", "owner", "contact", "nickname", "created_at"]
    search_fields = ["owner__username", "contact__username", "nickname"]
    panels = panels_for(
        editable=["owner", "contact", "nickname"],
        read_only=["created_at"],
    )


class BlockViewSet(SnippetViewSet):
    model = Block
    icon = "block"
    menu_label = "Blocks"
    menu_order = 232
    list_display = ["id", "blocker", "blocked", "created_at"]
    search_fields = ["blocker__username", "blocked__username"]
    panels = panels_for(
        editable=["blocker", "blocked"],
        read_only=["created_at"],
    )


class ProfilePhotoPrivacyViewSet(SnippetViewSet):
    model = ProfilePhotoPrivacy
    icon = "image"
    menu_label = "Photo privacy"
    menu_order = 233
    list_display = ["id", "user", "scope", "updated_at"]
    search_fields = ["user__username"]
    list_filter = ["scope"]
    panels = panels_for(
        editable=["user", "scope"],
        read_only=["updated_at"],
    )


class ProfilePhotoAllowedViewSet(SnippetViewSet):
    model = ProfilePhotoAllowed
    icon = "image"
    menu_label = "Photo allowed users"
    menu_order = 234
    list_display = ["id", "privacy", "user", "created_at"]
    search_fields = ["user__username"]
    panels = panels_for(
        editable=["privacy", "user"],
        read_only=["created_at"],
    )


class ConversationViewSet(SnippetViewSet):
    model = Conversation
    icon = "group"
    menu_label = "Conversations"
    menu_order = 200
    list_display = ["id", "public_id", "type", "title", "updated_at"]
    search_fields = ["public_id", "title"]
    list_filter = ["type", "is_public", "is_closed"]
    panels = panels_for(
        editable=[
            "type",
            "title",
            "description",
            "avatar",
            "is_public",
            "is_closed",
            "requires_approval",
            "members_can_add",
            "only_admins_send",
            "history_visibility",
            "created_by",
        ],
        read_only=["public_id", "created_at", "updated_at", "last_message_at"],
    )


class ConversationParticipantViewSet(SnippetViewSet):
    model = ConversationParticipant
    icon = "group"
    menu_label = "Participants"
    menu_order = 201
    list_display = ["id", "conversation", "user", "role", "is_muted", "joined_at", "left_at"]
    search_fields = ["user__username", "conversation__title"]
    list_filter = ["role", "is_muted"]
    panels = panels_for(
        editable=[
            "conversation",
            "user",
            "role",
            "can_send_messages",
            "can_send_media",
            "can_add_members",
            "can_pin_messages",
            "can_change_info",
            "is_muted",
            "last_read_at",
            "left_at",
            "is_pinned",
            "pinned_at",
        ],
        read_only=["joined_at"],
    )


class GroupInviteLinkViewSet(SnippetViewSet):
    model = GroupInviteLink
    icon = "link"
    menu_label = "Group invite links"
    menu_order = 202
    list_display = ["id", "conversation", "code", "is_active", "uses", "max_uses", "expires_at", "created_at"]
    search_fields = ["code"]
    list_filter = ["is_active"]
    panels = panels_for(
        editable=["conversation", "created_by", "is_active", "max_uses", "expires_at"],
        read_only=["code", "uses", "created_at"],
    )


class JoinRequestViewSet(SnippetViewSet):
    model = JoinRequest
    icon = "user"
    menu_label = "Join requests"
    menu_order = 203
    list_display = ["id", "conversation", "user", "status", "decided_by", "created_at"]
    search_fields = ["user__username"]
    list_filter = ["status"]
    panels = panels_for(
        editable=["conversation", "user", "status", "decided_by", "decided_at"],
        read_only=["created_at"],
    )


class MessageViewSet(SnippetViewSet):
    model = Message
    icon = "comment"
    menu_label = "Messages"
    menu_order = 210
    list_display = ["id", "conversation_id", "sender_id", "is_system", "created_at"]
    search_fields = ["body"]
    list_filter = ["is_system", "is_deleted", "is_scheduled", "is_edited"]
    panels = panels_for(
        editable=[
            "conversation",
            "sender",
            "body",
            "reply_to",
            "forwarded_from",
            "forwarded_from_message",
            "is_edited",
            "is_system",
            "is_deleted",
            "scheduled_for",
            "is_scheduled",
        ],
        read_only=["created_at", "updated_at"],
    )


class MessageReactionViewSet(SnippetViewSet):
    model = MessageReaction
    icon = "comment"
    menu_label = "Message reactions"
    menu_order = 211
    list_display = ["id", "message", "user", "emoji", "created_at"]
    search_fields = ["emoji", "user__username"]
    panels = panels_for(
        editable=["message", "user", "emoji"],
        read_only=["created_at"],
    )


class MessageReadReceiptViewSet(SnippetViewSet):
    model = MessageReadReceipt
    icon = "tick"
    menu_label = "Read receipts"
    menu_order = 212
    list_display = ["id", "message", "user", "seen_at"]
    search_fields = ["user__username"]
    panels = panels_for(
        editable=["message", "user"],
        read_only=["seen_at"],
    )


class MessageAttachmentViewSet(SnippetViewSet):
    model = MessageAttachment
    icon = "doc-full"
    menu_label = "Attachments"
    menu_order = 213
    list_display = ["id", "conversation", "message", "original_filename", "kind", "size", "created_at"]
    search_fields = ["original_filename"]
    list_filter = ["kind", "is_spoiler", "is_view_once", "is_purged"]
    panels = panels_for(
        editable=[
            "conversation",
            "message",
            "uploaded_by",
            "file",
            "original_filename",
            "content_type",
            "size",
            "kind",
            "width",
            "height",
            "duration",
            "is_spoiler",
            "is_view_once",
            "is_purged",
        ],
        read_only=["created_at"],
    )


class AttachmentViewOnceOpenViewSet(SnippetViewSet):
    model = AttachmentViewOnceOpen
    icon = "view"
    menu_label = "View-once opens"
    menu_order = 214
    list_display = ["id", "attachment", "user", "opened_at", "expires_at"]
    search_fields = ["user__username"]
    panels = panels_for(
        editable=["attachment", "user"],
        read_only=["opened_at", "expires_at"],
    )


class PinnedMessageViewSet(SnippetViewSet):
    model = PinnedMessage
    icon = "pin"
    menu_label = "Pinned messages"
    menu_order = 215
    list_display = ["id", "conversation", "message", "pinned_by", "pinned_at"]
    search_fields = ["conversation__title"]
    panels = panels_for(
        editable=["conversation", "message", "pinned_by"],
        read_only=["pinned_at"],
    )


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
    panels = panels_for(
        editable=["conversation", "initiator", "is_video", "status", "room_name"],
        read_only=[
            "public_id",
            "started_at",
            "answered_at",
            "ended_at",
            "duration_seconds",
            "start_message",
            "end_message",
        ],
    )


class MessengerGroup(SnippetViewSetGroup):
    items = (
        ConversationViewSet,
        ConversationParticipantViewSet,
        MessageViewSet,
        MessageReactionViewSet,
        MessageReadReceiptViewSet,
        MessageAttachmentViewSet,
        AttachmentViewOnceOpenViewSet,
        PinnedMessageViewSet,
        GroupInviteLinkViewSet,
        JoinRequestViewSet,
        CallSessionViewSet,
        ContactViewSet,
        BlockViewSet,
        UserBioViewSet,
        ProfilePhotoPrivacyViewSet,
        ProfilePhotoAllowedViewSet,
    )
    menu_label = "Messenger"
    menu_icon = "comment"
    menu_order = 200
