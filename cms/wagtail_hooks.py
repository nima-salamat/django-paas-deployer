"""
Register the project's existing Django models in Wagtail admin (snippets).

This exposes the existing (non-Wagtail) domain models in the Wagtail control
panel without converting them to Wagtail Page/Snippet models and without
altering the database schema.  Only Wagtail snippet registration (view sets)
is used here; the underlying models and tables are untouched.

User management is handled by wagtail.users (with our custom forms), so the
custom User model is intentionally NOT registered here.

DeployLog is stored in a separate database (DEPLOYMENT_LOG_DB_ALIAS) and is
therefore intentionally NOT registered here (a Wagtail snippet view set would
query the default database).
"""
from __future__ import annotations

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Small helpers to keep the many view-set definitions concise.
# ---------------------------------------------------------------------------

def _panels(editable, read_only=()):
    """Build a list of FieldPanels; `editable` are writable, `read_only` are not."""
    panels = [FieldPanel(f) for f in editable]
    panels += [FieldPanel(f, read_only=True) for f in read_only]
    return panels


def _timestamps_ro():
    """Read-only created/updated timestamps common to BaseModel-based models."""
    return ["created_at", "updated_at"]


# ===========================================================================
# Plans
# ===========================================================================

class PlanViewSet(SnippetViewSet):
    model = None  # set below once the model is importable
    icon = "doc-full-inverse"
    menu_label = _("Plans")
    menu_order = 100
    list_display = ["name", "platform", "plan_type", "max_cpu", "max_ram", "max_storage", "price_per_hour", "created_at"]
    list_filter = ["platform", "plan_type", "storage_type", "name"]
    search_fields = ["name", "platform"]
    ordering = ["name", "platform"]
    list_per_page = 50
    panels = _panels(
        editable=["name", "platform", "plan_type", "max_cpu", "max_ram", "max_storage", "price_per_hour", "storage_type"],
        read_only=["id", "created_at", "updated_at"],
    )


# ===========================================================================
# Services & networks
# ===========================================================================

class PrivateNetworkViewSet(SnippetViewSet):
    model = None
    icon = "globe"
    menu_label = _("Private networks")
    menu_order = 101
    list_display = ["name", "user", "description", "created_at"]
    search_fields = ["name", "user__username", "description"]
    list_filter = ["user"]
    panels = _panels(
        editable=["name", "user", "description"],
        read_only=["id", "created_at", "updated_at"],
    )


class ServiceViewSet(SnippetViewSet):
    model = None
    icon = "cog"
    menu_label = _("Services")
    menu_order = 102
    list_display = ["name", "user", "plan", "network", "status", "deployed_at", "created_at"]
    list_filter = ["status", "plan", "user", "read_only"]
    search_fields = ["name", "user__username", "plan__name"]
    panels = _panels(
        editable=["name", "user", "plan", "network", "selected_deploy", "read_only"],
        read_only=[
            "id",
            "selected_deploy_at",
            "deploy_started",
            "deployed_at",
            "status",
            "task_id",
            "created_at",
            "updated_at",
        ],
    )


class VolumeViewSet(SnippetViewSet):
    model = None
    icon = "cog"
    menu_label = _("Volumes")
    menu_order = 103
    list_display = ["name", "user", "service", "size_mb", "default_mode", "created_at"]
    search_fields = ["name", "user__username", "service__name"]
    list_filter = ["default_mode", "user"]
    panels = _panels(
        editable=["name", "user", "service", "size_mb", "default_bind", "default_mode"],
        read_only=["id", "service_attachments", "created_at", "updated_at"],
    )


# ===========================================================================
# Deploy
# ===========================================================================

class DeployViewSet(SnippetViewSet):
    model = None
    icon = "upload"
    menu_label = _("Deployments")
    menu_order = 104
    list_display = ["name", "service", "version", "status", "stage", "progress", "started_at", "created_at"]
    list_filter = ["status", "rollback_status", "service"]
    search_fields = ["name", "service__name", "status_message", "error_message"]
    ordering = ["-created_at"]
    list_per_page = 50
    panels = _panels(
        editable=["name", "service", "version", "zip_file"],
        read_only=[
            "id",
            "config",
            "started_at",
            "completed_at",
            "updated_file_at",
            "status",
            "stage",
            "progress",
            "status_message",
            "error_message",
            "rollback_status",
            "health_status",
            "container_status",
            "image_status",
            "volume_status",
            "network_status",
            "cancel_requested",
            "created_at",
            "updated_at",
        ],
    )


# ===========================================================================
# System settings
# ===========================================================================

class SystemSettingViewSet(SnippetViewSet):
    model = None
    icon = "cog"
    menu_label = _("System settings")
    menu_order = 110
    list_display = ["key", "category", "label", "value_type", "is_secret", "is_editable", "updated_at"]
    list_filter = ["category", "value_type", "is_secret", "is_editable"]
    search_fields = ["key", "label", "description", "value"]
    ordering = ["category", "key"]
    list_per_page = 50
    panels = _panels(
        editable=["label", "category", "description", "value_type", "value", "is_secret", "is_editable"],
        read_only=["key", "created_at", "updated_at"],
    )


# ===========================================================================
# Auth / users
# ===========================================================================

class LoginSettingsViewSet(SnippetViewSet):
    model = None
    icon = "lock"
    menu_label = _("Login settings")
    menu_order = 120
    list_display = ["is_active", "allow_login", "allow_username", "allow_email", "allow_phone", "updated_at"]
    list_filter = ["is_active", "allow_login"]
    panels = [
        MultiFieldPanel(
            [
                FieldPanel("is_active"),
                FieldPanel("allow_login"),
                FieldPanel("custom_login_closed_title"),
                FieldPanel("custom_login_closed_message"),
            ],
            heading=_("Master switch"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_username"),
                FieldPanel("allow_email"),
                FieldPanel("allow_phone"),
            ],
            heading=_("Allowed identifiers"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("require_password"),
                FieldPanel("require_otp"),
                FieldPanel("password_as_second_factor"),
            ],
            heading=_("Authentication factors"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_auto_signup"),
                FieldPanel("require_invite_for_signup"),
                FieldPanel("auto_activate_on_signup"),
                FieldPanel("require_password_on_signup"),
                FieldPanel("activate_after_successful_otp"),
            ],
            heading=_("Signup / activation"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_username_recovery"),
                FieldPanel("recovery_via_email"),
                FieldPanel("recovery_via_phone"),
            ],
            heading=_("Username recovery"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_password_recovery"),
                FieldPanel("password_recovery_via_email"),
                FieldPanel("password_recovery_via_phone"),
                FieldPanel("require_confirm_password"),
                FieldPanel("min_password_length"),
            ],
            heading=_("Password recovery"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("otp_length"),
                FieldPanel("otp_expire_minutes"),
                FieldPanel("otp_max_attempts"),
            ],
            heading=_("OTP settings"),
        ),
        FieldPanel("updated_at", read_only=True),
    ]


class InviteLinkViewSet(SnippetViewSet):
    model = None
    icon = "link"
    menu_label = _("Invite links")
    menu_order = 121
    list_display = ["token", "label", "uses_count", "max_uses", "is_active", "expires_at", "created_at"]
    search_fields = ["token", "label", "created_by__username"]
    list_filter = ["is_active", "created_at"]
    ordering = ["-created_at"]
    panels = _panels(
        editable=["label", "created_by", "max_uses", "is_active", "expires_at"],
        read_only=["token", "uses_count", "created_at", "updated_at"],
    )


class InviteUsageViewSet(SnippetViewSet):
    model = None
    icon = "link"
    menu_label = _("Invite usage")
    menu_order = 122
    list_display = ["user", "invite", "used_at", "ip_address"]
    search_fields = ["user__username", "invite__token", "ip_address"]
    ordering = ["-used_at"]
    panels = _panels(
        editable=[],
        read_only=["invite", "user", "used_at", "ip_address", "user_agent"],
    )


class AuthCodeViewSet(SnippetViewSet):
    model = None
    icon = "key"
    menu_label = _("Auth codes")
    menu_order = 123
    list_display = ["user", "contact", "purpose", "attempts", "created_at", "updated_at"]
    list_filter = ["purpose"]
    search_fields = ["user__username", "contact"]
    ordering = ["-updated_at"]
    panels = _panels(
        editable=["user", "contact", "purpose"],
        read_only=["code", "attempts", "created_at", "updated_at"],
    )


# ===========================================================================
# Emails
# ===========================================================================

class EmailTemplateViewSet(SnippetViewSet):
    model = None
    icon = "mail"
    menu_label = _("Email templates")
    menu_order = 130
    list_display = ["name", "subject", "is_active", "created_at"]
    search_fields = ["name", "subject"]
    list_filter = ["is_active"]
    ordering = ["name"]
    panels = _panels(
        editable=["name", "subject", "body", "description", "is_active", "created_by"],
        read_only=["created_at", "updated_at"],
    )


class EmailLogViewSet(SnippetViewSet):
    model = None
    icon = "mail"
    menu_label = _("Email log")
    menu_order = 131
    list_display = ["recipient_email", "subject", "status", "is_test", "created_at", "sent_at"]
    list_filter = ["status", "is_test"]
    search_fields = ["recipient_email", "subject"]
    ordering = ["-created_at"]
    panels = _panels(
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


# ===========================================================================
# Users
# ===========================================================================

class ReceiptViewSet(SnippetViewSet):
    model = None
    icon = "doc-full"
    menu_label = _("Receipts")
    menu_order = 140
    list_display = ["user", "amount", "status", "created_at", "updated_at"]
    list_filter = ["status", "user"]
    search_fields = ["user__username", "user__email"]
    ordering = ["-created_at"]
    panels = _panels(
        editable=["user", "amount", "status"],
        read_only=["created_at", "updated_at"],
    )


class ProfileViewSet(SnippetViewSet):
    model = None
    icon = "user"
    menu_label = _("Profiles")
    menu_order = 141
    list_display = ["user", "order", "created_at"]
    search_fields = ["user__username", "user__email"]
    panels = _panels(
        editable=["user", "order", "image"],
        read_only=["created_at"],
    )


class RuleViewSet(SnippetViewSet):
    model = None
    icon = "list-ul"
    menu_label = _("User rules")
    menu_order = 142
    list_display = ["user", "created_at", "updated_at"]
    search_fields = ["user__username"]
    panels = _panels(
        editable=["user"],
        read_only=["rules", "created_at", "updated_at"],
    )


# ===========================================================================
# Registration (imports wrapped so a single model failure cannot take down
# the whole admin hook).
# ===========================================================================

def _build_and_register():
    # ---- plans ----
    try:
        from plans.models import Plan

        PlanViewSet.model = Plan
        register_snippet(PlanViewSet)
    except Exception:
        pass

    # ---- services ----
    try:
        from services.models import PrivateNetwork, Service, Volume

        PrivateNetworkViewSet.model = PrivateNetwork
        register_snippet(PrivateNetworkViewSet)
        ServiceViewSet.model = Service
        register_snippet(ServiceViewSet)
        VolumeViewSet.model = Volume
        register_snippet(VolumeViewSet)
    except Exception:
        pass

    # ---- deploy ----
    try:
        from deploy.models import Deploy

        DeployViewSet.model = Deploy
        register_snippet(DeployViewSet)
    except Exception:
        pass

    # ---- core ----
    try:
        from core.models import SystemSetting

        SystemSettingViewSet.model = SystemSetting
        register_snippet(SystemSettingViewSet)
    except Exception:
        pass

    # ---- auth ----
    try:
        from auth_users.models import AuthCode, InviteLink, InviteUsage, LoginSettings

        LoginSettingsViewSet.model = LoginSettings
        register_snippet(LoginSettingsViewSet)
        InviteLinkViewSet.model = InviteLink
        register_snippet(InviteLinkViewSet)
        InviteUsageViewSet.model = InviteUsage
        register_snippet(InviteUsageViewSet)
        AuthCodeViewSet.model = AuthCode
        register_snippet(AuthCodeViewSet)
    except Exception:
        pass

    # ---- emails ----
    try:
        from custom_emails.models import EmailLog, EmailTemplate

        EmailTemplateViewSet.model = EmailTemplate
        register_snippet(EmailTemplateViewSet)
        EmailLogViewSet.model = EmailLog
        register_snippet(EmailLogViewSet)
    except Exception:
        pass

    # ---- users ----
    try:
        from users.models import Profile, Receipt, Rule

        ReceiptViewSet.model = Receipt
        register_snippet(ReceiptViewSet)
        ProfileViewSet.model = Profile
        register_snippet(ProfileViewSet)
        RuleViewSet.model = Rule
        register_snippet(RuleViewSet)
    except Exception:
        pass


_build_and_register()


# ===========================================================================
# Messenger (registered through a snippet group).
# ===========================================================================

def _register_messenger():
    try:
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
    except Exception:
        return

    class UserBioViewSet(SnippetViewSet):
        model = UserBio
        icon = "user"
        menu_label = "User bios"
        menu_order = 230
        list_display = ["id", "user", "updated_at"]
        search_fields = ["user__username", "text"]
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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

    register_snippet(MessengerGroup)


# ===========================================================================
# Tickets (registered through a snippet group).
# ===========================================================================

def _register_tickets():
    try:
        from tickets.models import (
            Department,
            DepartmentMembership,
            Ticket,
            TicketAttachment,
            TicketMessage,
            TicketReadState,
        )
    except Exception:
        return

    class DepartmentViewSet(SnippetViewSet):
        model = Department
        icon = "folder-open-1"
        menu_label = "Departments"
        menu_order = 300
        list_display = ["name", "slug", "is_active", "order", "created_at"]
        search_fields = ["name", "slug"]
        list_filter = ["is_active"]
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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
        panels = _panels(
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

    register_snippet(TicketsGroup)


_register_messenger()
_register_tickets()
