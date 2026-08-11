from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink, ProfilePhoto,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, PinnedMessage,
)
from .utils import can_see_profile_photo, detect_kind

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    is_contact = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "color", "avatar", "is_contact", "is_blocked")

    def get_avatar(self, obj):
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        if not can_see_profile_photo(viewer, obj):
            return None
        # Prefer messenger multi-photos first
        photo = obj.messenger_photos.order_by("order", "id").first()
        if photo and photo.image:
            url = photo.image.url
            return request.build_absolute_uri(url) if request else url
        # Fallback to existing profile image if any
        try:
            prof = (
                obj.profile_set.filter(image__isnull=False)
                .exclude(image="")
                .order_by("id")
                .first()
            )
            if prof and getattr(prof, "image", None):
                url = prof.image.url
                return request.build_absolute_uri(url) if request else url
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
        return request.build_absolute_uri(url) if request else url


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

    class Meta:
        model = Message
        fields = (
            "id", "conversation", "sender", "body", "reply_to", "reply_to_preview",
            "forwarded_from", "forwarded_from_user", "forwarded_from_message",
            "is_edited", "is_deleted", "created_at", "updated_at",
            "attachments", "reactions",
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


class ParticipantSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = ConversationParticipant
        fields = (
            "id", "user", "role", "can_send_messages", "can_send_media",
            "can_add_members", "can_pin_messages", "can_change_info",
            "is_muted", "joined_at", "last_read_at", "left_at",
        )


class ConversationListSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    peer = serializers.SerializerMethodField()  # for private chats

    class Meta:
        model = Conversation
        fields = (
            "id", "public_id", "type", "title", "description", "avatar",
            "is_public", "is_closed", "created_at", "updated_at", "last_message_at",
            "participants", "last_message", "unread_count", "peer",
        )

    def get_participants(self, obj):
        qs = obj.participants.filter(left_at__isnull=True).select_related("user")[:20]
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


class ProfilePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhoto
        fields = ("id", "url", "order", "created_at")

    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class ProfilePhotoPrivacySerializer(serializers.ModelSerializer):
    allowed_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhotoPrivacy
        fields = ("scope", "allowed_user_ids", "updated_at")

    def get_allowed_user_ids(self, obj):
        return list(obj.allowed_users.values_list("user_id", flat=True))
