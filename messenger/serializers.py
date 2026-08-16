"""Messenger serializers — lean MethodFields (no hidden queries).

All DB work must happen in the view / context builders via
select_related / prefetch_related / annotate / bulk maps.
SerializerMethodField only shapes already-loaded data.
"""
from __future__ import annotations

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from rest_framework import serializers

from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, PinnedMessage,
    MessageReadReceipt, UserBio, JoinRequest,
)
from .utils import can_see_profile_photo

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


# ---------------------------------------------------------------------------
# User mini — 100% context-driven (no per-row queries)
# ---------------------------------------------------------------------------

class UserMiniSerializer(serializers.ModelSerializer):
    """Lightweight user card.

    Required bulk context (from build_user_mini_context):
      contact_ids, blocked_ids, avatar_map, bio_map, online_ids
    If maps are missing, returns safe defaults — never hits the DB.
    """
    avatar = serializers.SerializerMethodField()
    is_contact = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "color", "avatar",
            "is_contact", "is_blocked", "is_online", "bio",
        )

    def get_avatar(self, obj):
        avatar_map = self.context.get("avatar_map")
        if avatar_map is not None:
            return avatar_map.get(obj.id)
        return None

    def get_is_contact(self, obj):
        contact_ids = self.context.get("contact_ids")
        if contact_ids is not None:
            return obj.id in contact_ids
        return False

    def get_is_blocked(self, obj):
        blocked_ids = self.context.get("blocked_ids")
        if blocked_ids is not None:
            return obj.id in blocked_ids
        return False

    def get_is_online(self, obj):
        online_ids = self.context.get("online_ids")
        if online_ids is not None:
            return obj.id in online_ids
        return False

    def get_bio(self, obj):
        bio_map = self.context.get("bio_map")
        if bio_map is not None:
            return bio_map.get(obj.id, "") or ""
        return ""


class MessageAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    is_spoiler = serializers.BooleanField(read_only=True)
    is_view_once = serializers.BooleanField(read_only=True)
    view_once_state = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = (
            "id", "original_filename", "content_type", "size", "kind",
            "width", "height", "duration", "url", "created_at",
            "is_spoiler", "is_view_once", "is_purged", "view_once_state",
        )

    def _viewer(self):
        req = self.context.get("request")
        return getattr(req, "user", None) if req else None

    def _view_once_opened(self, obj, viewer):
        if not viewer or not getattr(viewer, "is_authenticated", False):
            return False
        opens = getattr(obj, "_prefetched_view_once_opens", None)
        if opens is not None:
            return any(o.user_id == viewer.id for o in opens)
        try:
            return obj.view_once_opens.filter(user_id=viewer.id).exists()
        except Exception:
            return False

    def get_view_once_state(self, obj):
        """none | pending | opened | own | purged"""
        if not getattr(obj, "is_view_once", False):
            return "none"
        if getattr(obj, "is_purged", False):
            return "purged"
        viewer = self._viewer()
        if not viewer or not getattr(viewer, "is_authenticated", False):
            return "pending"
        if obj.uploaded_by_id and obj.uploaded_by_id == viewer.id:
            return "own"
        if self._view_once_opened(obj, viewer):
            return "opened"
        return "pending"

    def get_url(self, obj):
        if getattr(obj, "is_purged", False):
            return None
        # View-once: never put a durable URL in list/detail payloads.
        # Sender may download without once-token; recipients must call open.
        if getattr(obj, "is_view_once", False):
            viewer = self._viewer()
            if viewer and getattr(viewer, "is_authenticated", False) and obj.uploaded_by_id == viewer.id:
                return f"/api/messenger/attachments/{obj.pk}/download/"
            return None
        return f"/api/messenger/attachments/{obj.pk}/download/"


class ReactionSerializer(serializers.ModelSerializer):
    """Full reaction row — only used for rare detail endpoints."""
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ("id", "emoji", "user", "created_at")


# ---------------------------------------------------------------------------
# Message — reactions / read_state from bulk context only
# ---------------------------------------------------------------------------

class MessageSerializer(serializers.ModelSerializer):
    """Message payload. Viewer-specific fields come from context maps only."""

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
            "scheduled_for", "is_scheduled",
        )
        read_only_fields = fields

    def get_reactions(self, obj):
        agg_map = self.context.get("reaction_agg")
        if agg_map is not None:
            by_emoji = agg_map.get(obj.id) or {}
            return [
                {"emoji": em, "count": data["count"], "mine": data["mine"]}
                for em, data in sorted(by_emoji.items())
            ]
        # Prefetched reactions without viewer aggregation
        cache = getattr(obj, "_prefetched_objects_cache", {}) or {}
        reactions = cache.get("reactions")
        if reactions is None:
            return []
        viewer_id = None
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            viewer_id = request.user.id
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
        # Prefer select_related reply_to already on the instance
        r = getattr(obj, "reply_to", None)
        if r is None:
            return {"id": obj.reply_to_id, "body": "", "sender": None}
        if getattr(r, "is_deleted", False):
            return {"id": obj.reply_to_id, "body": "Deleted message", "sender": None}
        return {
            "id": r.id,
            "body": (r.body or "")[:120],
            "sender": UserMiniSerializer(r.sender, context=self.context).data if r.sender_id else None,
        }

    def get_read_state(self, obj):
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        if not viewer or not viewer.is_authenticated:
            return "sent"
        if obj.is_system or obj.is_deleted:
            return "read"
        if obj.sender_id != viewer.id:
            return "read"

        read_ids = self.context.get("read_message_ids")
        if read_ids is not None:
            return "read" if obj.id in read_ids else "sent"

        # Prefetched receipts only — no extra query
        cache = getattr(obj, "_prefetched_objects_cache", {}) or {}
        receipts = cache.get("read_receipts")
        if receipts is not None:
            for r in receipts:
                if r.user_id != obj.sender_id:
                    return "read"
            return "sent"

        last_reads = self.context.get("participant_last_reads")
        if last_reads is not None:
            for uid, lr in last_reads:
                if uid != obj.sender_id and lr and lr >= obj.created_at:
                    return "read"
            return "sent"
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


# ---------------------------------------------------------------------------
# Conversation list — pure; all data from attrs set by the view
# ---------------------------------------------------------------------------

class ConversationListSerializer(serializers.ModelSerializer):
    """Chat-list row.

    The view MUST attach:
      - _prefetched_active_participants  (list of ConversationParticipant)
      - _prefetched_last_message         (Message | None)
      - annotated_unread                 (int)
    and pass build_user_mini_context for participant users.
    MethodFields never issue queries.
    """
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
        parts = getattr(obj, "_prefetched_active_participants", None)
        if parts is None:
            return []
        # Chat list only needs a tiny subset (peer / self). Full member lists
        # for big groups made every list request multi-megabyte and slow.
        if self.context.get("lean_list"):
            request = self.context.get("request")
            viewer_id = getattr(getattr(request, "user", None), "id", None) if request else None
            if obj.type == Conversation.Type.PRIVATE:
                slim = [p for p in parts if viewer_id is None or p.user_id != viewer_id][:1]
                if viewer_id:
                    self_p = next((p for p in parts if p.user_id == viewer_id), None)
                    if self_p:
                        slim = [self_p] + slim
                parts = slim
            else:
                # group: only current user's participant row (permissions / pin)
                if viewer_id is not None:
                    parts = [p for p in parts if p.user_id == viewer_id][:1]
                else:
                    parts = parts[:1]
        return ParticipantSerializer(parts, many=True, context=self.context).data

    def get_last_message(self, obj):
        msg = getattr(obj, "_prefetched_last_message", None)
        if msg is not None and getattr(msg, "is_scheduled", False):
            msg = None
        if not msg:
            return None
        has_att = bool(getattr(msg, "_has_attachments", False))
        body = msg.body or ""
        if body.startswith("__call__:"):
            body = _format_call_preview(body)
        return {
            "id": msg.id,
            "body": body[:100],
            "sender_id": msg.sender_id,
            "created_at": msg.created_at,
            "has_attachments": has_att,
            "is_system": bool(getattr(msg, "is_system", False)),
        }

    def get_unread_count(self, obj):
        annotated = getattr(obj, "annotated_unread", None)
        return int(annotated) if annotated is not None else 0

    def get_peer(self, obj):
        if obj.type != Conversation.Type.PRIVATE:
            return None
        request = self.context.get("request")
        viewer_id = getattr(getattr(request, "user", None), "id", None) if request else None
        parts = getattr(obj, "_prefetched_active_participants", None) or []
        for p in parts:
            if viewer_id is None or p.user_id != viewer_id:
                user = getattr(p, "user", None)
                if user is not None:
                    return UserMiniSerializer(user, context=self.context).data
        return None

    def get_is_pinned(self, obj):
        request = self.context.get("request")
        viewer_id = getattr(getattr(request, "user", None), "id", None) if request else None
        if not viewer_id:
            return False
        parts = getattr(obj, "_prefetched_active_participants", None) or []
        for p in parts:
            if p.user_id == viewer_id:
                return bool(p.is_pinned)
        return False

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        # Prefer select_related created_by
        user = getattr(obj, "created_by", None)
        if user is None:
            return {"id": obj.created_by_id, "username": "", "color": None,
                    "avatar": None, "is_contact": False, "is_blocked": False,
                    "is_online": False, "bio": ""}
        return UserMiniSerializer(user, context=self.context).data


class ConversationDetailSerializer(ConversationListSerializer):
    invite_links = serializers.SerializerMethodField()
    pins = serializers.SerializerMethodField()

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ("invite_links", "pins")

    def get_invite_links(self, obj):
        # Prefetched on the view as _prefetched_invite_links; empty if not admin
        links = getattr(obj, "_prefetched_invite_links", None)
        if links is None:
            return []
        return GroupInviteLinkSerializer(links, many=True, context=self.context).data

    def get_pins(self, obj):
        pins = getattr(obj, "_prefetched_pins", None)
        if pins is None:
            return []
        out = []
        for p in pins:
            msg = p.message
            out.append({
                "id": p.id,
                "message": MessageSerializer(msg, context=self.context).data if msg else None,
                "pinned_at": p.pinned_at,
            })
        return out


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
        # Prefer prefetched allowed_users
        cache = getattr(obj, "_prefetched_objects_cache", {}) or {}
        allowed = cache.get("allowed_users")
        if allowed is not None:
            return [a.user_id for a in allowed]
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
        conv = getattr(obj, "conversation", None)
        if conv is not None:
            return conv.title or "Group"
        return "Group"


# ---------------------------------------------------------------------------
# Bulk context builders (the only place that hits the DB for serialization)
# ---------------------------------------------------------------------------

def build_user_mini_context(request, user_ids):
    """Preload contact/block/avatar/bio/online maps for a set of user ids.

    Always returns the map keys so UserMiniSerializer never falls back to DB.
    """
    ctx = {"request": request}
    empty = {
        "contact_ids": set(),
        "blocked_ids": set(),
        "avatar_map": {},
        "bio_map": {},
        "online_ids": set(),
    }
    if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
        ctx.update(empty)
        return ctx
    viewer = request.user
    user_ids = list({int(uid) for uid in user_ids if uid})
    if not user_ids:
        ctx.update(empty)
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
        profiles = (
            Profile.objects.filter(user_id__in=user_ids)
            .exclude(image__isnull=True)
            .exclude(image="")
            .order_by("user_id", "order", "id")
            .only("user_id", "image", "order")
        )
        for p in profiles:
            if p.user_id in avatar_map:
                continue
            try:
                avatar_map[p.user_id] = p.image.url
            except Exception:
                pass
        # Privacy: null out avatars the viewer cannot see
        for uid in list(avatar_map.keys()):
            if uid == viewer.id:
                continue
            try:
                if not can_see_profile_photo(viewer, User(id=uid)):
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
    """Bulk context for message list/detail — reactions + read_state + user mini."""
    msg_ids = [m.id for m in messages]
    user_ids = set()
    for m in messages:
        if m.sender_id:
            user_ids.add(m.sender_id)
        if m.forwarded_from_id:
            user_ids.add(m.forwarded_from_id)
        reply = getattr(m, "reply_to", None)
        if reply is not None and reply.sender_id:
            user_ids.add(reply.sender_id)

    ctx = build_user_mini_context(request, user_ids)

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

    own_msg_ids = [m.id for m in messages if m.sender_id == viewer_id]
    read_message_ids = set()
    if own_msg_ids and viewer_id:
        read_message_ids = set(
            MessageReadReceipt.objects.filter(message_id__in=own_msg_ids)
            .exclude(user_id=viewer_id)
            .values_list("message_id", flat=True)
            .distinct()
        )
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
                for _uid, lr in others:
                    if lr and lr >= m.created_at:
                        read_message_ids.add(m.id)
                        break
    ctx["read_message_ids"] = read_message_ids
    return ctx


def build_conversation_list_context(request, conversations):
    """Bulk user-mini context for every participant + created_by on the list."""
    user_ids = set()
    for c in conversations:
        if c.created_by_id:
            user_ids.add(c.created_by_id)
        parts = getattr(c, "_prefetched_active_participants", None) or []
        for p in parts:
            if p.user_id:
                user_ids.add(p.user_id)
    return build_user_mini_context(request, user_ids)


def prepare_conversation_detail(conv, user):
    """Attach invite links + pins for detail serializer (no N+1 inside serializer)."""
    part = None
    parts = getattr(conv, "_prefetched_active_participants", None)
    if parts is not None:
        part = next((p for p in parts if p.user_id == user.id), None)
    else:
        part = conv.participants.filter(user=user, left_at__isnull=True).first()

    if part and part.role in ("owner", "admin"):
        conv._prefetched_invite_links = list(conv.invite_links.filter(is_active=True)[:10])
    else:
        conv._prefetched_invite_links = []

    conv._prefetched_pins = list(
        conv.pins.select_related(
            "message", "message__sender", "message__reply_to", "message__reply_to__sender",
            "message__forwarded_from",
        ).prefetch_related("message__attachments", "message__reactions")[:5]
    )
    return conv
