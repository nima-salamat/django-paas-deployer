from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, PinnedMessage,
    MessageReadReceipt, UserBio,
)
from .utils import can_see_profile_photo, detect_kind

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    is_contact = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "color", "avatar", "is_contact", "is_blocked", "is_online", "bio")

    def get_avatar(self, obj):
        """Use existing users.Profile images only."""
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        if not can_see_profile_photo(viewer, obj):
            return None
        try:
            from users.models import Profile
            prof = (
                Profile.objects.filter(user=obj)
                .exclude(image__isnull=True)
                .exclude(image="")
                .order_by("order", "id")
                .first()
            )
            if prof and getattr(prof, "image", None):
                url = prof.image.url
                if request:
                    try:
                        return request.build_absolute_uri(url)
                    except Exception:
                        pass
                return url
        except Exception:
            pass
        return None

    def get_is_contact(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Contact.objects.filter(owner=request.user, contact=obj).exists()

    def get_is_blocked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Block.objects.filter(blocker=request.user, blocked=obj).exists()

    def get_is_online(self, obj):
        """Check cache-based presence for this user."""
        try:
            from .consumers import is_user_online
            return is_user_online(obj.id)
        except Exception:
            return False

    def get_bio(self, obj):
        """Return the user's bio text (Telegram-style 'about')."""
        try:
            bio = getattr(obj, "messenger_bio", None)
            if bio:
                return bio.text or ""
        except Exception:
            pass
        return ""


class MessageAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = (
            "id", "original_filename", "content_type", "size", "kind",
            "width", "height", "duration", "url", "created_at",
        )

    def get_url(self, obj):
        request = self.context.get("request")
        url = f"/api/messenger/attachments/{obj.pk}/download/"
        abs_url = request.build_absolute_uri(url) if request else url
        # Pass JWT through query string so <img src=...> works without auth headers.
        if request and "token" in request.query_params:
            sep = "&" if "?" in abs_url else "?"
            abs_url = f"{abs_url}{sep}token={request.query_params['token']}"
        return abs_url


class ReactionSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ("id", "emoji", "user", "created_at")


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMiniSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    reply_to_preview = serializers.SerializerMethodField()
    forwarded_from_user = UserMiniSerializer(source="forwarded_from", read_only=True)
    read_state = serializers.SerializerMethodField()
    readers = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id", "conversation", "sender", "body", "reply_to", "reply_to_preview",
            "forwarded_from", "forwarded_from_user", "forwarded_from_message",
            "is_edited", "is_system", "is_deleted", "created_at", "updated_at",
            "attachments", "reactions", "read_state", "readers",
        )
        read_only_fields = fields

    def get_reactions(self, obj):
        # Aggregate: {emoji: count, users: [...]} simplified to list
        qs = obj.reactions.select_related("user")[:50]
        return ReactionSerializer(qs, many=True, context=self.context).data

    def get_reply_to_preview(self, obj):
        if not obj.reply_to_id:
            return None
        r = obj.reply_to
        if not r or r.is_deleted:
            return {"id": obj.reply_to_id, "body": "Deleted message", "sender": None}
        return {
            "id": r.id,
            "body": (r.body or "")[:120],
            "sender": UserMiniSerializer(r.sender, context=self.context).data if r.sender else None,
        }

    def get_read_state(self, obj):
        """One of: 'sent' | 'read'.
        - For sender's own message: 'read' if at least one non-sender participant has
          last_read_at >= message.created_at (or a MessageReadReceipt from a non-sender exists).
        - For other viewers: always 'read' (they're reading it now).
        - System / others' messages: 'read'.
        """
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        if not viewer or not viewer.is_authenticated:
            return "sent"
        if obj.is_system or obj.is_deleted:
            return "read"
        # Only the sender cares about read state of their own message.
        if obj.sender_id != viewer.id:
            return "read"
        # Sender's own message -> check if any other participant has read it.
        # Cheap path: MessageReadReceipt from any non-sender.
        qs = MessageReadReceipt.objects.filter(message=obj).exclude(user_id=obj.sender_id)
        if qs.exists():
            return "read"
        # Fallback: participant.last_read_at >= message.created_at (covers receipts
        # created before this feature shipped).
        participants = ConversationParticipant.objects.filter(
            conversation_id=obj.conversation_id, left_at__isnull=True
        ).exclude(user_id=obj.sender_id)
        for p in participants:
            if p.last_read_at and p.last_read_at >= obj.created_at:
                return "read"
        return "sent"

    def get_readers(self, obj):
        """List of {user, seen_at} for users who have read this message.
        Includes the sender's own receipts from `last_read_at` (computed on the fly).
        """
        request = self.context.get("request")
        out = []
        seen_ids = set()
        for r in obj.read_receipts.select_related("user")[:200]:
            out.append({
                "user": UserMiniSerializer(r.user, context=self.context).data,
                "seen_at": r.seen_at,
                "source": "receipt",
            })
            seen_ids.add(r.user_id)
        # Supplement with participants whose last_read_at >= message.created_at.
        participants = ConversationParticipant.objects.filter(
            conversation_id=obj.conversation_id, left_at__isnull=True
        ).select_related("user")
        for p in participants:
            if p.user_id in seen_ids:
                continue
            if p.last_read_at and p.last_read_at >= obj.created_at:
                out.append({
                    "user": UserMiniSerializer(p.user, context=self.context).data,
                    "seen_at": p.last_read_at,
                    "source": "last_read_at",
                })
                seen_ids.add(p.user_id)
        return out


class ParticipantSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = ConversationParticipant
        fields = (
            "id", "user", "role", "can_send_messages", "can_send_media",
            "can_add_members", "can_pin_messages", "can_change_info",
            "is_muted", "joined_at", "last_read_at", "left_at",
            "is_pinned", "pinned_at",
        )


class ConversationListSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    peer = serializers.SerializerMethodField()  # for private chats
    is_pinned = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id", "public_id", "type", "title", "description", "avatar", "avatar_url",
            "is_public", "is_closed", "members_can_add", "only_admins_send",
            "history_visibility", "created_by",
            "created_at", "updated_at", "last_message_at",
            "participants", "last_message", "unread_count", "peer", "is_pinned",
        )

    def get_avatar_url(self, obj):
        """Absolute URL for the group avatar (if set)."""
        request = self.context.get("request")
        if not obj.avatar:
            return None
        try:
            url = obj.avatar.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None

    def get_participants(self, obj):
        qs = obj.participants.filter(left_at__isnull=True).select_related("user")[:200]
        return ParticipantSerializer(qs, many=True, context=self.context).data

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).order_by("-created_at").first()
        if not msg:
            return None
        return {
            "id": msg.id,
            "body": (msg.body or "")[:100],
            "sender_id": msg.sender_id,
            "created_at": msg.created_at,
            "has_attachments": msg.attachments.exists(),
        }

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        part = obj.participants.filter(user=request.user, left_at__isnull=True).first()
        if not part or not part.last_read_at:
            return obj.messages.filter(is_deleted=False).exclude(sender=request.user).count()
        return obj.messages.filter(
            is_deleted=False, created_at__gt=part.last_read_at
        ).exclude(sender=request.user).count()

    def get_peer(self, obj):
        if obj.type != Conversation.Type.PRIVATE:
            return None
        request = self.context.get("request")
        if not request:
            return None
        other = (
            obj.participants.filter(left_at__isnull=True)
            .exclude(user=request.user)
            .select_related("user")
            .first()
        )
        if other:
            return UserMiniSerializer(other.user, context=self.context).data
        return None

    def get_is_pinned(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        part = obj.participants.filter(user=request.user, left_at__isnull=True).first()
        return bool(part and part.is_pinned)

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return UserMiniSerializer(obj.created_by, context=self.context).data


class ConversationDetailSerializer(ConversationListSerializer):
    invite_links = serializers.SerializerMethodField()
    pins = serializers.SerializerMethodField()

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ("invite_links", "pins")

    def get_invite_links(self, obj):
        request = self.context.get("request")
        if not request:
            return []
        # Only owners/admins see links
        part = obj.participants.filter(user=request.user, left_at__isnull=True).first()
        if not part or part.role not in ("owner", "admin"):
            return []
        links = obj.invite_links.filter(is_active=True)[:10]
        return GroupInviteLinkSerializer(links, many=True, context=self.context).data

    def get_pins(self, obj):
        pins = obj.pins.select_related("message", "message__sender")[:5]
        return [
            {
                "id": p.id,
                "message": MessageSerializer(p.message, context=self.context).data,
                "pinned_at": p.pinned_at,
            }
            for p in pins
        ]


class GroupInviteLinkSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = GroupInviteLink
        fields = ("id", "code", "url", "is_active", "max_uses", "uses", "expires_at", "created_at")

    def get_url(self, obj):
        request = self.context.get("request")
        path = f"/messenger/join/{obj.code}"
        return request.build_absolute_uri(path) if request else path


class ContactSerializer(serializers.ModelSerializer):
    contact = UserMiniSerializer(read_only=True)

    class Meta:
        model = Contact
        fields = ("id", "contact", "nickname", "created_at")


class ProfilePhotoSerializer(serializers.Serializer):
    """Serializes existing users.Profile rows (not a messenger-owned model)."""
    id = serializers.IntegerField()
    url = serializers.SerializerMethodField()
    order = serializers.IntegerField()
    created_at = serializers.DateTimeField()

    def get_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class ProfilePhotoPrivacySerializer(serializers.ModelSerializer):
    allowed_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhotoPrivacy
        fields = ("scope", "allowed_user_ids", "updated_at")

    def get_allowed_user_ids(self, obj):
        return list(obj.allowed_users.values_list("user_id", flat=True))
