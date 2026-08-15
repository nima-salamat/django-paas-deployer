from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Contact,
    Block,
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MessageAttachment,
    GroupInviteLink,
    ProfilePhotoPrivacy,
    PinnedMessage,
)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "contact", "nickname", "created_at")
    search_fields = ("owner__username", "contact__username", "nickname")
    raw_id_fields = ("owner", "contact")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("id", "blocker", "blocked", "created_at")
    search_fields = ("blocker__username", "blocked__username")
    raw_id_fields = ("blocker", "blocked")


class ConversationParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0
    raw_id_fields = ("user",)
    fields = (
        "user", "role", "joined_at", "left_at",
        "can_send_messages", "can_send_media", "is_muted", "is_pinned",
    )
    readonly_fields = ("joined_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "type", "title", "is_public", "history_visibility",
        "last_message_at", "created_at",
    )
    list_filter = ("type", "is_public", "history_visibility", "requires_approval", "only_admins_send")
    search_fields = ("title", "public_id", "description")
    raw_id_fields = ("created_by",)
    inlines = [ConversationParticipantInline]
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "user", "role", "joined_at", "left_at", "is_muted")
    list_filter = ("role",)
    search_fields = ("user__username", "conversation__title")
    raw_id_fields = ("conversation", "user")


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    raw_id_fields = ("uploaded_by",)
    fields = ("original_filename", "kind", "content_type", "size", "file", "uploaded_by")
    readonly_fields = ("size",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "sender",
        "body_preview",
        "is_system",
        "is_deleted",
        "is_scheduled",
        "scheduled_for",
        "schedule_status",
        "created_at",
    )
    list_filter = (
        "is_system",
        "is_deleted",
        "is_scheduled",
        "is_edited",
        "created_at",
    )
    search_fields = ("body", "sender__username", "id")
    raw_id_fields = (
        "conversation", "sender", "reply_to",
        "forwarded_from", "forwarded_from_message",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = [MessageAttachmentInline]
    date_hierarchy = "created_at"
    actions = ("cancel_scheduled", "force_deliver_scheduled")

    @admin.display(description="Body")
    def body_preview(self, obj):
        text = (obj.body or "")[:80]
        return text + ("…" if obj.body and len(obj.body) > 80 else "")

    @admin.display(description="Schedule")
    def schedule_status(self, obj):
        if not obj.is_scheduled and not (obj.scheduled_for and not obj.is_deleted):
            if obj.scheduled_for and obj.is_deleted:
                return format_html('<span style="color:#999">cancelled</span>')
            return "—"
        if obj.is_deleted:
            return format_html('<span style="color:#999">cancelled</span>')
        if obj.scheduled_for and obj.scheduled_for <= timezone.now():
            return format_html('<span style="color:#c62828">due</span>')
        if obj.is_scheduled:
            return format_html('<span style="color:#ef6c00">pending</span>')
        return "—"

    @admin.action(description="Cancel selected scheduled messages")
    def cancel_scheduled(self, request, queryset):
        qs = queryset.filter(is_scheduled=True, is_deleted=False)
        n = 0
        from .signals import soft_delete_message_side_effects
        for msg in qs.iterator():
            msg.is_deleted = True
            msg.is_scheduled = False
            msg.body = ""
            msg.save(update_fields=["is_deleted", "is_scheduled", "body", "updated_at"])
            soft_delete_message_side_effects(msg)
            n += 1
        self.message_user(request, f"Cancelled {n} scheduled message(s).")

    @admin.action(description="Force-deliver selected scheduled messages now")
    def force_deliver_scheduled(self, request, queryset):
        from .tasks import deliver_scheduled_messages

        qs = queryset.filter(is_scheduled=True, is_deleted=False)
        ids = list(qs.values_list("id", flat=True))
        now = timezone.now()
        updated = qs.update(scheduled_for=now)
        try:
            deliver_scheduled_messages.delay()
        except Exception:
            deliver_scheduled_messages()
        self.message_user(
            request,
            f"Triggered delivery for {updated} message(s) (ids={ids[:20]}).",
        )


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "user", "emoji", "created_at")
    search_fields = ("emoji", "user__username")
    raw_id_fields = ("message", "user")


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "conversation", "message", "original_filename",
        "kind", "size", "uploaded_by",
    )
    list_filter = ("kind",)
    search_fields = ("original_filename",)
    raw_id_fields = ("conversation", "message", "uploaded_by")


@admin.register(GroupInviteLink)
class GroupInviteLinkAdmin(admin.ModelAdmin):
    list_display = (
        "id", "conversation", "code", "is_active",
        "uses", "max_uses", "expires_at", "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code",)
    raw_id_fields = ("conversation", "created_by")


@admin.register(ProfilePhotoPrivacy)
class ProfilePhotoPrivacyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "scope", "updated_at")
    list_filter = ("scope",)
    raw_id_fields = ("user",)


@admin.register(PinnedMessage)
class PinnedMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "message", "pinned_by", "pinned_at")
    raw_id_fields = ("conversation", "message", "pinned_by")


# Optional models — register only if present in this codebase revision
try:
    from .models import JoinRequest

    @admin.register(JoinRequest)
    class JoinRequestAdmin(admin.ModelAdmin):
        list_display = ("id", "conversation", "user", "status", "created_at", "decided_at")
        list_filter = ("status",)
        raw_id_fields = ("conversation", "user", "decided_by")
except Exception:
    pass

try:
    from .models import CallSession

    @admin.register(CallSession)
    class CallSessionAdmin(admin.ModelAdmin):
        list_display = (
            "id", "public_id", "conversation", "initiator",
            "status", "is_video", "started_at", "ended_at",
        )
        list_filter = ("status", "is_video")
        search_fields = ("public_id", "room_name")
        raw_id_fields = ("conversation", "initiator")
except Exception:
    pass

try:
    from .models import UserBio

    @admin.register(UserBio)
    class UserBioAdmin(admin.ModelAdmin):
        list_display = ("id", "user", "updated_at")
        search_fields = ("user__username", "text")
        raw_id_fields = ("user",)
except Exception:
    pass
