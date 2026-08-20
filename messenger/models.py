"""
Telegram-like messenger models.
"""
from __future__ import annotations

import os
import secrets
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

User = settings.AUTH_USER_MODEL


def messenger_attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    safe = "".join(c for c in os.path.splitext(filename)[0] if c.isalnum() or c in "-_")[:40]
    name = f"{uuid.uuid4().hex}_{safe}{ext}"
    conv_id = getattr(instance, "conversation_id", None) or "tmp"
    return f"messenger/{conv_id}/{name}"


# ---------------------------------------------------------------------------
# User Bio (Messenger-owned — does not modify the core User model)
# ---------------------------------------------------------------------------

class UserBio(models.Model):
    """Per-user bio shown on their profile (Telegram-style 'about' field)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="messenger_bio")
    text = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Bio({self.user_id}): {self.text[:40]}"


# ---------------------------------------------------------------------------
# Contacts & Blocks
# ---------------------------------------------------------------------------

class Contact(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_contacts")
    contact = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_contacted_by")
    nickname = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "contact")
        indexes = [models.Index(fields=["owner", "contact"])]

    def __str__(self):
        return f"{self.owner_id} → {self.contact_id}"


class Block(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_blocks")
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        indexes = [models.Index(fields=["blocker", "blocked"])]


# ---------------------------------------------------------------------------
# Profile photo privacy (who can see which photos)
# ---------------------------------------------------------------------------

class ProfilePhotoPrivacy(models.Model):
    """
    Controls visibility of profile photos.
    Scope choices:
      - everyone
      - contacts
      - nobody
      - specific (use ProfilePhotoAllowed)
    Applies to existing users.Profile images (not a separate photo store).
    """
    class Scope(models.TextChoices):
        EVERYONE = "everyone", _("Everyone")
        CONTACTS = "contacts", _("Contacts only")
        NOBODY = "nobody", _("Nobody")
        SPECIFIC = "specific", _("Specific users")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="messenger_photo_privacy")
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.EVERYONE)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PhotoPrivacy({self.user_id}={self.scope})"


class ProfilePhotoAllowed(models.Model):
    privacy = models.ForeignKey(ProfilePhotoPrivacy, on_delete=models.CASCADE, related_name="allowed_users")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("privacy", "user")



# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class Conversation(models.Model):
    class Type(models.TextChoices):
        PRIVATE = "private", _("Private")
        GROUP = "group", _("Group")

    class HistoryVisibility(models.TextChoices):
        """Who can see messages sent BEFORE they joined the group."""
        ALL = "all", _("All new members see history")
        FROM_JOIN = "from_join", _("Only messages from join-time onward")
        NONE = "none", _("No history for new members")

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.PRIVATE, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")  # groups only
    description = models.TextField(blank=True, default="")
    avatar = models.ImageField(upload_to="messenger/groups/", null=True, blank=True)
    is_public = models.BooleanField(default=False, db_index=True)  # appears in search
    is_closed = models.BooleanField(default=False)  # no new joins / messages
    # If True, users must send a join request that admins approve/reject
    # (Telegram-style "private public groups"). If False, anyone can join directly.
    requires_approval = models.BooleanField(default=False)
    members_can_add = models.BooleanField(default=True)  # members may add contacts
    # Channel-like mode — only owner/admins can send messages
    only_admins_send = models.BooleanField(default=False)
    # History visibility for new members (group only)
    history_visibility = models.CharField(
        max_length=12, choices=HistoryVisibility.choices,
        default=HistoryVisibility.ALL,
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_conversations")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["type", "is_public"]),
            models.Index(fields=["last_message_at"]),
        ]

    def __str__(self):
        if self.type == self.Type.PRIVATE:
            return f"DM {self.public_id}"
        return self.title or f"Group {self.public_id}"


class ConversationParticipant(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        ADMIN = "admin", _("Admin")
        MEMBER = "member", _("Member")

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_participations")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    # Permissions (group)
    can_send_messages = models.BooleanField(default=True)
    can_send_media = models.BooleanField(default=True)
    can_add_members = models.BooleanField(default=False)
    can_pin_messages = models.BooleanField(default=False)
    can_change_info = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    # Soft leave
    left_at = models.DateTimeField(null=True, blank=True)
    # Per-user pin (chat appears at top of that user's list)
    is_pinned = models.BooleanField(default=False)
    pinned_at = models.DateTimeField(null=True, blank=True)
    # Unsent composer draft (synced across devices via WS)
    draft_text = models.TextField(blank=True, default="")
    draft_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("conversation", "user")
        indexes = [
            models.Index(fields=["user", "left_at"]),
            models.Index(fields=["conversation", "user"]),
            models.Index(fields=["user", "is_pinned"]),
        ]

    def __str__(self):
        return f"{self.user_id} in {self.conversation_id} ({self.role})"


class GroupInviteLink(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="invite_links")
    code = models.CharField(max_length=32, unique=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)  # None = unlimited
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_urlsafe(16)[:24]
        super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_uses is not None and self.uses >= self.max_uses:
            return False
        return True

    def __str__(self):
        return f"Invite {self.code} → {self.conversation_id}"


# ---------------------------------------------------------------------------
# Join Requests (Telegram-style — for public groups that require admin approval)
# ---------------------------------------------------------------------------

class JoinRequest(models.Model):
    """A user's request to join a public group that requires approval.

    Lifecycle:
      - User creates a PENDING request via /conversations/<pk>/join-request/
      - Admin sees pending requests via /conversations/<pk>/join-requests/
      - Admin APPROVES -> user is added as a member + request marked APPROVED
      - Admin REJECTS  -> request marked REJECTED (user can re-request later)
      - User can CANCEL their own pending request via /join-requests/<pk>/
        (deletes the request entirely so admins no longer see it)
    """
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="join_requests"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_join_requests")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Who acted on this request (set when approved/rejected)
    decided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="messenger_join_requests_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # One active request per (conversation, user) — but allow re-requesting
        # after rejection, so unique_together is on (conversation, user, status).
        unique_together = [("conversation", "user", "status")]
        indexes = [
            models.Index(fields=["conversation", "status"], name="messenger_jr_conv_status_idx"),
            models.Index(fields=["user", "status"], name="messenger_jr_user_status_idx"),
        ]

    def __str__(self):
        return f"JoinRequest({self.user_id} → {self.conversation_id}={self.status})"


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="messenger_messages")
    body = models.TextField(blank=True, default="")  # plain text / markdown-ish
    # Reply
    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"
    )
    # Forward
    forwarded_from = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="forwarded_messages"
    )
    forwarded_from_message = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="forwards"
    )
    is_edited = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)  # soft delete for others
    # When set in the future, message is held (visible only to sender) until due.
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    is_scheduled = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "id"]),
            models.Index(fields=["is_scheduled", "scheduled_for"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Do not bump conversation activity for still-pending scheduled messages
        if self.is_scheduled and self.scheduled_for:
            return
        Conversation.objects.filter(pk=self.conversation_id).update(
            last_message_at=self.created_at, updated_at=timezone.now()
        )

    def __str__(self):
        return f"Msg {self.pk} in {self.conversation_id}"


class MessageReaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_reactions")
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user", "emoji")
        indexes = [models.Index(fields=["message", "emoji"])]


class MessageReadReceipt(models.Model):
    """
    Per-message read receipt — records when each user read a specific message.
    Used for "Seen by" lists and Telegram-style single/double ticks.
    """
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="read_receipts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messenger_read_receipts")
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [models.Index(fields=["message", "user"])]


class MessageAttachment(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", _("Image")
        VIDEO = "video", _("Video")
        GIF = "gif", _("GIF")
        AUDIO = "audio", _("Audio")
        FILE = "file", _("File")
        VOICE = "voice", _("Voice")

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(Message, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to=messenger_attachment_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.FILE)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)  # seconds for video/audio
    # Media privacy flags (Telegram-style)
    is_spoiler = models.BooleanField(default=False)  # blurred until recipient taps
    is_view_once = models.BooleanField(default=False)  # one open per recipient, then locked
    is_purged = models.BooleanField(default=False)  # file deleted after all recipients viewed
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class AttachmentViewOnceOpen(models.Model):
    """Tracks which users have opened a view-once attachment.

    Access is valid only until expires_at (opened_at + VIEW_ONCE_SECONDS).
    """
    attachment = models.ForeignKey(
        MessageAttachment, on_delete=models.CASCADE, related_name="view_once_opens"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="view_once_opens")
    opened_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        unique_together = ("attachment", "user")
        indexes = [models.Index(fields=["attachment", "user"])]


class PinnedMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="pins")
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    pinned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conversation", "message")


# ---------------------------------------------------------------------------
# Voice / video call sessions (stored history + ring state)
# ---------------------------------------------------------------------------

class CallSession(models.Model):
    """One outbound call attempt in a conversation (Telegram-style)."""

    class Status(models.TextChoices):
        RINGING = "ringing", _("Ringing")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")
        MISSED = "missed", _("Missed")
        DECLINED = "declined", _("Declined")
        NO_ANSWER = "no_answer", _("No answer")

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="call_sessions"
    )
    initiator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="messenger_calls_started"
    )
    is_video = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RINGING, db_index=True)
    room_name = models.CharField(max_length=120, blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    # System message rows linked for chat history
    start_message = models.ForeignKey(
        Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    end_message = models.ForeignKey(
        Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["conversation", "status"]),
            models.Index(fields=["conversation", "-started_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation"],
                condition=models.Q(status__in=["ringing", "active"]),
                name="uniq_active_call_per_conversation",
            ),
        ]

    def __str__(self):
        return f"Call {self.public_id} ({self.status})"

