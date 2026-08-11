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

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.PRIVATE, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")  # groups only
    description = models.TextField(blank=True, default="")
    avatar = models.ImageField(upload_to="messenger/groups/", null=True, blank=True)
    is_public = models.BooleanField(default=False, db_index=True)  # appears in search
    is_closed = models.BooleanField(default=False)  # no new joins / messages
    members_can_add = models.BooleanField(default=True)  # members may add contacts
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
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "id"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PinnedMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="pins")
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    pinned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conversation", "message")
