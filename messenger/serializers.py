from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q, Exists, OuterRef
from collections import defaultdict
from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, PinnedMessage,
    MessageReadReceipt, UserBio, JoinRequest,
)
from .utils import can_see_profile_photo, detect_kind

User = get_user_model()



def _format_call_preview(body: str) -> str:
    """Human-readable preview for call system messages in chat list."""
    import json
    try:
        data = json.loads(body[9:])
    except Exception:
        return "Call"
    is_video = bool(data.get("is_video"))
    kind = "Video call" if is_video else "Voice call"
    event = data.get("event")
    status = data.get("status") or ""
    dur = int(data.get("duration") or 0)
    if event == "started":
        return f"{kind} started"
    if status in ("missed", "no_answer"):
        return f"Missed {kind.lower()}"
    if status == "declined":
        return f"Declined {kind.lower()}"
    if status == "busy":
        return f"Busy · {kind.lower()}"
    if dur > 0:
        m, s = divmod(dur, 60)
        return f"{kind} · {m}:{s:02d}"
    return f"{kind} ended"

class UserMiniSerializer(serializers.ModelSerializer):
    """Lightweight user card.

    Avoids N+1 when context provides:
      - contact_ids: set of user ids that are contacts of the viewer
      - blocked_ids: set of user ids blocked by the viewer
      - avatar_map: {user_id: relative_url}
      - bio_map: {user_id: text}
      - online_ids: set of online user ids
    """
    avatar = serializers.SerializerMethodField()
    is_contact = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "color", "avatar", "is_contact", "is_blocked", "is_online", "bio")

    def get_avatar(self, obj):
        avatar_map = self.context.get("avatar_map")
        if avatar_map is not None:
            return avatar_map.get(obj.id)
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
                try:
                    return prof.image.url
                except Exception:
                    return None
        except Exception:
            pass
        return None

    def get_is_contact(self, obj):
        contact_ids = self.context.get("contact_ids")
        if contact_ids is not None:
            return obj.id in contact_ids
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Contact.objects.filter(owner=request.user, contact=obj).exists()

    def get_is_blocked(self, obj):
        blocked_ids = self.context.get("blocked_ids")
        if blocked_ids is not None:
            return obj.id in blocked_ids
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Block.objects.filter(blocker=request.user, blocked=obj).exists()

    def get_is_online(self, obj):
        online_ids = self.context.get("online_ids")
        if online_ids is not None:
            return obj.id in online_ids
        try:
            from .consumers import is_user_online
            return is_user_online(obj.id)
        except Exception:
            return False

    def get_bio(self, obj):
        bio_map = self.context.get("bio_map")
        if bio_map is not None:
            return bio_map.get(obj.id, "")
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
        return f"/api/messenger/attachments/{obj.pk}/download/"


class ReactionSerializer(serializers.ModelSerializer):
    """Full reaction row — only used for rare detail endpoints."""
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ("id", "emoji", "user", "created_at")


class MessageSerializer(serializers.ModelSerializer):
    """Optimized message payload.

    - reactions: aggregated list of {emoji, count, mine}  (no per-user payloads)
    - read_state: 'sent' | 'read'  (cheap; uses prefetched data when available)
    - readers: REMOVED from list responses — fetch via GET /messages/<id>/readers/
    """
    sender = UserMiniSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    reply_to_preview = serializers.SerializerMethodField()
    forwarded_from_user = UserMiniSerializer(source="forwarded_from", read_only=True)
    read_state = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id", "conversation", "sender", "body", "reply_to", "reply_to_preview",
            "forwarded_from", "forwarded_from_user", "forwarded_from_message",
            "is_edited", "is_system", "is_deleted", "created_at", "updated_at",
            "attachments", "reactions", "read_state",
        )
        read_only_fields = fields

    def get_reactions(self, obj):
        """Aggregate reactions to {emoji, count, mine} — no user payloads."""
        request = self.context.get("request")
        viewer_id = getattr(getattr(request, "user", None), "id", None) if request else None

        # Prefer prefetched cache built in to_representation / list view
        agg_map = self.context.get("reaction_agg")  # {message_id: {emoji: {count, mine}}}
        if agg_map is not None:
            by_emoji = agg_map.get(obj.id) or {}
            return [
                {"emoji": em, "count": data["count"], "mine": data["mine"]}
                for em, data in sorted(by_emoji.items())
            ]

        # Prefetched reactions (from Prefetch)
        reactions = getattr(obj, "_prefetched_objects_cache", {}).get("reactions")
        if reactions is None:
            try:
                reactions = list(obj.reactions.all())
            except Exception:
                reactions = []

        counts = defaultdict(lambda: {"count": 0, "mine": False})
        for r in reactions:
            counts[r.emoji]["count"] += 1
            if viewer_id and r.user_id == viewer_id:
                counts[r.emoji]["mine"] = True
        return [
            {"emoji": em, "count": data["count"], "mine": data["mine"]}
            for em, data in sorted(counts.items())
        ]

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

        Only meaningful for the sender's own messages.
        Uses context caches when available to avoid N+1:
          - read_message_ids: set of message ids that have ≥1 non-sender receipt
          - participant_last_reads: list of (user_id, last_read_at) for non-senders
        """
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        if not viewer or not viewer.is_authenticated:
            return "sent"
        if obj.is_system or obj.is_deleted:
            return "read"
        if obj.sender_id != viewer.id:
            return "read"

        # Fast path: precomputed set of message ids that are read by someone else
        read_ids = self.context.get("read_message_ids")
        if read_ids is not None:
            return "read" if obj.id in read_ids else "sent"

        # Prefetched receipts
        receipts = getattr(obj, "_prefetched_objects_cache", {}).get("read_receipts")
        if receipts is not None:
            for r in receipts:
                if r.user_id != obj.sender_id:
                    return "read"
        else:
            if MessageReadReceipt.objects.filter(message=obj).exclude(user_id=obj.sender_id).exists():
                return "read"

        # Fallback: participant last_read_at
        last_reads = self.context.get("participant_last_reads")
        if last_reads is not None:
            for uid, lr in last_reads:
                if uid != obj.sender_id and lr and lr >= obj.created_at:
                    return "read"
            return "sent"

        participants = ConversationParticipant.objects.filter(
            conversation_id=obj.conversation_id, left_at__isnull=True
        ).exclude(user_id=obj.sender_id).only("last_read_at", "user_id")
        for p in participants:
            if p.last_read_at and p.last_read_at >= obj.created_at:
                return "read"
        return "sent"


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
    peer = serializers.SerializerMethodField()
    is_pinned = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id", "public_id", "type", "title", "description", "avatar", "avatar_url",
            "is_public", "is_closed", "requires_approval", "members_can_add", "only_admins_send",
            "history_visibility", "created_by",
            "created_at", "updated_at", "last_message_at",
            "participants", "last_message", "unread_count", "peer", "is_pinned",
        )

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        try:
            return obj.avatar.url
        except Exception:
            return None

    def get_participants(self, obj):
        # Prefer prefetched active participants
        parts = getattr(obj, "_prefetched_active_participants", None)
        if parts is None:
            qs = obj.participants.filter(left_at__isnull=True).select_related("user")[:200]
            parts = list(qs)
        return ParticipantSerializer(parts, many=True, context=self.context).data

    def get_last_message(self, obj):
        # Prefer annotation / prefetched last message
        msg = getattr(obj, "_prefetched_last_message", None)
        if msg is None:
            msg = obj.messages.filter(is_deleted=False).order_by("-created_at").first()
        if not msg:
            return None
        has_att = getattr(msg, "_has_attachments", None)
        if has_att is None:
            has_att = msg.attachments.exists()
        body = msg.body or ""
        if body.startswith("__call__:"):
            body = _format_call_preview(body)
        return {
            "id": msg.id,
            "body": body[:100],
            "sender_id": msg.sender_id,
            "created_at": msg.created_at,
            "has_attachments": bool(has_att),
            "is_system": bool(getattr(msg, "is_system", False)),
        }

    def get_unread_count(self, obj):
        # Prefer annotation from list view
        annotated = getattr(obj, "annotated_unread", None)
        if annotated is not None:
            return annotated
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
        parts = getattr(obj, "_prefetched_active_participants", None)
        if parts is not None:
            for p in parts:
                if p.user_id != request.user.id:
                    return UserMiniSerializer(p.user, context=self.context).data
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
        parts = getattr(obj, "_prefetched_active_participants", None)
        if parts is not None:
            for p in parts:
                if p.user_id == request.user.id:
                    return bool(p.is_pinned)
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
        return f"/messenger/join/{obj.code}"


class ContactSerializer(serializers.ModelSerializer):
    contact = UserMiniSerializer(read_only=True)

    class Meta:
        model = Contact
        fields = ("id", "contact", "nickname", "created_at")


class ProfilePhotoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    url = serializers.SerializerMethodField()
    order = serializers.IntegerField()
    created_at = serializers.DateTimeField()

    def get_url(self, obj):
        if not obj.image:
            return None
        try:
            return obj.image.url
        except Exception:
            return None


class ProfilePhotoPrivacySerializer(serializers.ModelSerializer):
    allowed_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhotoPrivacy
        fields = ("scope", "allowed_user_ids", "updated_at")

    def get_allowed_user_ids(self, obj):
        return list(obj.allowed_users.values_list("user_id", flat=True))


class JoinRequestSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    conversation_title = serializers.SerializerMethodField()
    decided_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = JoinRequest
        fields = (
            "id", "conversation", "user", "status",
            "decided_by", "decided_at", "created_at",
            "conversation_title",
        )
        read_only_fields = ("id", "status", "decided_by", "decided_at", "created_at")

    def get_conversation_title(self, obj):
        try:
            return obj.conversation.title or "Group"
        except Exception:
            return "Group"


# ---------------------------------------------------------------------------
# Helpers used by API views to build bulk context and avoid N+1
# ---------------------------------------------------------------------------

def build_user_mini_context(request, user_ids):
    """Preload contact/block/avatar/bio/online maps for a set of user ids."""
    ctx = {"request": request}
    if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
        return ctx
    viewer = request.user
    user_ids = list({int(uid) for uid in user_ids if uid})
    if not user_ids:
        ctx.update({
            "contact_ids": set(),
            "blocked_ids": set(),
            "avatar_map": {},
            "bio_map": {},
            "online_ids": set(),
        })
        return ctx

    contact_ids = set(
        Contact.objects.filter(owner=viewer, contact_id__in=user_ids)
        .values_list("contact_id", flat=True)
    )
    blocked_ids = set(
        Block.objects.filter(blocker=viewer, blocked_id__in=user_ids)
        .values_list("blocked_id", flat=True)
    )
    bio_map = dict(
        UserBio.objects.filter(user_id__in=user_ids).values_list("user_id", "text")
    )

    avatar_map = {}
    try:
        from users.models import Profile
        # First profile image per user (ordered)
        profiles = (
            Profile.objects.filter(user_id__in=user_ids)
            .exclude(image__isnull=True)
            .exclude(image="")
            .order_by("user_id", "order", "id")
        )
        for p in profiles:
            if p.user_id not in avatar_map:
                try:
                    avatar_map[p.user_id] = p.image.url
                except Exception:
                    pass
        # Apply photo privacy: if viewer cannot see, null out
        for uid in list(avatar_map.keys()):
            # cheap privacy check — only for non-self
            if uid == viewer.id:
                continue
            try:
                target = User(id=uid)  # minimal stub for can_see
                target.id = uid
                if not can_see_profile_photo(viewer, target):
                    avatar_map[uid] = None
            except Exception:
                pass
    except Exception:
        pass

    online_ids = set()
    try:
        from .consumers import is_user_online
        for uid in user_ids:
            if is_user_online(uid):
                online_ids.add(uid)
    except Exception:
        pass

    ctx.update({
        "contact_ids": contact_ids,
        "blocked_ids": blocked_ids,
        "avatar_map": avatar_map,
        "bio_map": bio_map,
        "online_ids": online_ids,
    })
    return ctx


def build_message_list_context(request, messages, conversation_id=None):
    """Build context for serializing a list of messages without N+1."""
    msg_ids = [m.id for m in messages]
    user_ids = set()
    for m in messages:
        if m.sender_id:
            user_ids.add(m.sender_id)
        if m.forwarded_from_id:
            user_ids.add(m.forwarded_from_id)
        if m.reply_to_id and getattr(m, "reply_to", None) and m.reply_to.sender_id:
            user_ids.add(m.reply_to.sender_id)

    ctx = build_user_mini_context(request, user_ids)

    # Aggregate reactions in one query
    reaction_agg = defaultdict(lambda: defaultdict(lambda: {"count": 0, "mine": False}))
    viewer_id = request.user.id if request and request.user.is_authenticated else None
    if msg_ids:
        for row in (
            MessageReaction.objects.filter(message_id__in=msg_ids)
            .values("message_id", "emoji", "user_id")
        ):
            bucket = reaction_agg[row["message_id"]][row["emoji"]]
            bucket["count"] += 1
            if viewer_id and row["user_id"] == viewer_id:
                bucket["mine"] = True
    ctx["reaction_agg"] = reaction_agg

    # Read state for viewer's own messages
    own_msg_ids = [m.id for m in messages if m.sender_id == viewer_id]
    read_message_ids = set()
    if own_msg_ids:
        read_message_ids = set(
            MessageReadReceipt.objects.filter(message_id__in=own_msg_ids)
            .exclude(user_id=viewer_id)
            .values_list("message_id", flat=True)
            .distinct()
        )
        # Also check participant last_read_at for messages that may lack receipts
        if conversation_id:
            others = list(
                ConversationParticipant.objects.filter(
                    conversation_id=conversation_id, left_at__isnull=True
                )
                .exclude(user_id=viewer_id)
                .values_list("user_id", "last_read_at")
            )
            ctx["participant_last_reads"] = others
            for m in messages:
                if m.id in read_message_ids or m.sender_id != viewer_id:
                    continue
                for uid, lr in others:
                    if lr and lr >= m.created_at:
                        read_message_ids.add(m.id)
                        break
    ctx["read_message_ids"] = read_message_ids
    return ctx
