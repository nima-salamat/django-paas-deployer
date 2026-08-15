"""
Messenger REST API — infinite-scroll friendly.
"""
from __future__ import annotations

import secrets

import logging
import mimetypes
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, MessageReadReceipt, UserBio,
    JoinRequest, PinnedMessage, CallSession,
)
from .serializers import (
    UserMiniSerializer, MessageSerializer, ConversationListSerializer,
    ConversationDetailSerializer, ContactSerializer,
    GroupInviteLinkSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer,
    build_message_list_context, build_user_mini_context,
)
from .utils import validate_messenger_file, detect_kind, users_blocked, can_see_profile_photo

User = get_user_model()
logger = logging.getLogger("messenger")


def ok(message="success", data=None, http_status=status.HTTP_200_OK):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=http_status)


def err(message, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"success": False, "message": message}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)


class UserSearchPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class UserSearchAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return ok(data={"results": [], "next": None})
        blocked_ids = set(
            Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)
        ) | set(
            Block.objects.filter(blocked=request.user).values_list("blocker_id", flat=True)
        )
        qs = (
            User.objects.filter(username__icontains=q, is_active=True)
            .exclude(id=request.user.id)
            .exclude(id__in=blocked_ids)
            .order_by("username")
        )
        paginator = UserSearchPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = UserMiniSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(ser.data)


class ContactListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Contact.objects.filter(owner=request.user).select_related("contact").order_by("-created_at")
        return ok(data=ContactSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request):
        uid = request.data.get("user_id")
        if not uid:
            return err("user_id required")
        try:
            target = User.objects.get(pk=uid, is_active=True)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return err("Cannot add yourself")
        if users_blocked(request.user, target):
            return err("User is blocked")
        obj, created = Contact.objects.get_or_create(
            owner=request.user, contact=target,
            defaults={"nickname": (request.data.get("nickname") or "").strip()[:120]},
        )
        return ok(
            "Contact added" if created else "Already in contacts",
            data=ContactSerializer(obj, context={"request": request}).data,
            http_status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ContactDeleteAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        deleted, _ = Contact.objects.filter(owner=request.user, contact_id=user_id).delete()
        return ok("Removed" if deleted else "Not found")


class BlockListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ids = Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)
        users = User.objects.filter(id__in=ids)
        return ok(data=UserMiniSerializer(users, many=True, context={"request": request}).data)

    def post(self, request):
        uid = request.data.get("user_id")
        if not uid:
            return err("user_id required")
        try:
            target = User.objects.get(pk=uid)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return err("Cannot block yourself")
        Block.objects.get_or_create(blocker=request.user, blocked=target)
        Contact.objects.filter(owner=request.user, contact=target).delete()
        return ok("Blocked", http_status=status.HTTP_201_CREATED)


class UnblockAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        Block.objects.filter(blocker=request.user, blocked_id=user_id).delete()
        return ok("Unblocked")


def get_or_create_dm(user_a, user_b) -> Conversation:
    if user_a.id > user_b.id:
        user_a, user_b = user_b, user_a
    existing = (
        Conversation.objects.filter(type=Conversation.Type.PRIVATE)
        .annotate(pc=Count("participants"))
        .filter(pc=2)
        .filter(participants__user=user_a)
        .filter(participants__user=user_b)
        .distinct()
        .first()
    )
    if existing:
        return existing
    conv = Conversation.objects.create(type=Conversation.Type.PRIVATE, created_by=user_a)
    ConversationParticipant.objects.create(conversation=conv, user=user_a, role=ConversationParticipant.Role.OWNER)
    ConversationParticipant.objects.create(conversation=conv, user=user_b, role=ConversationParticipant.Role.MEMBER)
    return conv


class ConversationListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:
            from .tasks import deliver_due_scheduled_messages
            deliver_due_scheduled_messages(limit=30)
        except Exception:
            pass

        page = int(request.query_params.get("page") or 1)
        page_size = min(50, int(request.query_params.get("page_size") or 30))

        # ----- Hot path: per-user conversation list cache -----
        # Stores the full ordered serialized list (max 200). Pagination is
        # applied in-process so any page_size works without extra keys.
        try:
            from .message_cache import ConversationCacheService
            cached_list = ConversationCacheService.get_user_conv_list(request.user.id)
            if cached_list is not None:
                total = len(cached_list)
                start = (page - 1) * page_size
                end = start + page_size
                return ok(data={
                    "results": cached_list[start:end],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_more": end < total,
                })
        except Exception:
            logger.exception("conversation list cache read failed")

        qs = (
            Conversation.objects.filter(
                participants__user=request.user, participants__left_at__isnull=True
            )
            .distinct()
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=ConversationParticipant.objects.filter(left_at__isnull=True).select_related("user"),
                )
            )
        )
        # Sort: pinned (per-user) first, then by last_message_at desc.
        # We sort in Python because is_pinned is per-participant, not per-conversation.
        items = list(qs[:200])
        # Build a quick lookup of pin state for the current user
        pin_map = {}
        for c in items:
            part = next((p for p in c.participants.all() if p.user_id == request.user.id), None)
            pin_map[c.id] = bool(part and part.is_pinned)
        items.sort(
            key=lambda c: (
                not pin_map.get(c.id, False),  # pinned first (False < True)
                -(c.last_message_at.timestamp() if c.last_message_at else c.created_at.timestamp()),
            )
        )
        start = (page - 1) * page_size
        end = start + page_size
        total = len(items)
        page_items = items[start:end]
        ser = ConversationListSerializer(items, many=True, context={"request": request})
        full_data = list(ser.data)
        # Populate cache with the full ordered list (not just this page)
        try:
            from .message_cache import ConversationCacheService
            ConversationCacheService.set_user_conv_list(request.user.id, full_data)
        except Exception:
            logger.exception("conversation list cache write failed")
        return ok(data={
            "results": full_data[start:end],
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": end < total,
        })

    def post(self, request):
        ctype = (request.data.get("type") or "private").lower()
        if ctype == "private":
            uid = request.data.get("user_id")
            if not uid:
                return err("user_id required for private chat")
            try:
                other = User.objects.get(pk=uid, is_active=True)
            except User.DoesNotExist:
                return err("User not found", status.HTTP_404_NOT_FOUND)
            if users_blocked(request.user, other):
                return err("Cannot message blocked user")
            conv = get_or_create_dm(request.user, other)
            return ok(
                "Conversation ready",
                data=ConversationDetailSerializer(conv, context={"request": request}).data,
                http_status=status.HTTP_201_CREATED,
            )
        title = (request.data.get("title") or "").strip()
        if len(title) < 1:
            return err("Group title required")
        member_ids = request.data.get("member_ids") or []
        if not isinstance(member_ids, list):
            member_ids = []
        conv = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title=title[:255],
            description=(request.data.get("description") or "")[:2000],
            is_public=bool(request.data.get("is_public")),
            created_by=request.user,
        )
        ConversationParticipant.objects.create(
            conversation=conv,
            user=request.user,
            role=ConversationParticipant.Role.OWNER,
            can_send_messages=True,
            can_send_media=True,
            can_add_members=True,
            can_pin_messages=True,
            can_change_info=True,
        )
        for mid in member_ids[:100]:
            try:
                u = User.objects.get(pk=mid, is_active=True)
            except User.DoesNotExist:
                continue
            if u.id == request.user.id or users_blocked(request.user, u):
                continue
            ConversationParticipant.objects.get_or_create(
                conversation=conv, user=u,
                defaults={
                    "role": ConversationParticipant.Role.MEMBER,
                    "can_pin_messages": True,
                },
            )
        GroupInviteLink.objects.create(conversation=conv, created_by=request.user)
        return ok(
            "Group created",
            data=ConversationDetailSerializer(conv, context={"request": request}).data,
            http_status=status.HTTP_201_CREATED,
        )


class ConversationDetailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_participant(self, conv, user):
        return conv.participants.filter(user=user, left_at__isnull=True).first()

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        if not self.get_participant(conv, request.user):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        return ok(data=ConversationDetailSerializer(conv, context={"request": request}).data)

    def patch(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = self.get_participant(conv, request.user)
        if not part or (part.role not in ("owner", "admin") and not part.can_change_info):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if "title" in request.data and conv.type == Conversation.Type.GROUP:
            conv.title = str(request.data["title"])[:255]
        if "description" in request.data:
            conv.description = str(request.data["description"])[:2000]
        if "is_public" in request.data:
            conv.is_public = bool(request.data["is_public"])
        if "is_closed" in request.data and part.role == "owner":
            conv.is_closed = bool(request.data["is_closed"])
        # Public-group approval mode — owner only (Telegram-style "requires approval to join")
        if "requires_approval" in request.data and part.role == "owner":
            conv.requires_approval = bool(request.data["requires_approval"])
        if "members_can_add" in request.data and part.role in ("owner", "admin"):
            conv.members_can_add = bool(request.data["members_can_add"])
        # Channel-like mode — only owner/admins can toggle
        if "only_admins_send" in request.data and part.role in ("owner", "admin"):
            conv.only_admins_send = bool(request.data["only_admins_send"])
        # History visibility for new members — owner only
        if "history_visibility" in request.data and part.role == "owner":
            v = str(request.data["history_visibility"]).lower()
            if v in ("all", "from_join", "none"):
                conv.history_visibility = v
        # Group avatar upload
        if "avatar" in request.FILES:
            conv.avatar = request.FILES["avatar"]
        if "clear_avatar" in request.data and request.data["clear_avatar"]:
            conv.avatar = None
        conv.save()
        # Broadcast the change so all participants reload — important for
        # history_visibility changes (clients need to refetch messages with
        # the new filter) and for channel-mode / requires_approval toggles.
        try:
            from .consumers import broadcast_member_change
            broadcast_member_change(conv.id, {
                "type": "group.settings_changed",
                "conversation_id": conv.id,
                "changed_by": request.user.id,
            })
        except Exception:
            pass
        return ok(data=ConversationDetailSerializer(conv, context={"request": request}).data)


class PublicGroupSearchAPIView(APIView):
    """Search public groups.

    Returns an EMPTY list when the query is empty — public groups are NEVER
    listed automatically. Users must actively search by name/description to
    discover them (Telegram-like behaviour for public groups/channels).

    Includes `my_pending_request` flag for each group so the frontend can
    show a "Request sent" / "Cancel request" button on groups that require
    approval.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return ok(data=[])
        qs = (
            Conversation.objects.filter(
                type=Conversation.Type.GROUP, is_public=True, is_closed=False,
            )
            .filter(Q(title__icontains=q) | Q(description__icontains=q))
            .order_by("-last_message_at")[:50]
        )
        items = list(qs)
        # Annotate each group with the viewer's pending join request (if any)
        # and whether they're already a member.
        my_pending_map = {}
        my_member_map = {}
        if items:
            from .models import JoinRequest
            pending = JoinRequest.objects.filter(
                user=request.user,
                conversation__in=items,
                status=JoinRequest.Status.PENDING,
            ).values_list("conversation_id", flat=True)
            my_pending_map = set(pending)
            my_member_map = set(
                ConversationParticipant.objects.filter(
                    user=request.user,
                    conversation__in=items,
                    left_at__isnull=True,
                ).values_list("conversation_id", flat=True)
            )
        out = []
        for c in items:
            d = ConversationListSerializer(c, context={"request": request}).data
            d["my_pending_request"] = c.id in my_pending_map
            d["is_member"] = c.id in my_member_map
            out.append(d)
        return ok(data=out)


class MessageListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_participant(self, conv, user):
        return conv.participants.filter(user=user, left_at__isnull=True).first()

    def get(self, request, pk):
        # Deliver any due scheduled messages before listing (works even without celery beat)
        try:
            from .tasks import deliver_due_scheduled_messages
            deliver_due_scheduled_messages(limit=50)
        except Exception:
            logger.exception("inline deliver_scheduled failed")
        conv = get_object_or_404(Conversation, pk=pk)
        part = self.get_participant(conv, request.user)
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        before_id_raw = request.query_params.get("before_id")
        before_id = None
        if before_id_raw:
            try:
                before_id = int(before_id_raw)
            except ValueError:
                pass
        limit = min(50, int(request.query_params.get("limit") or 40))

        # History-visibility restrictions for ordinary group members prevent a
        # pure cache hit (the cached window is the global latest messages).
        history_restricted = False
        if conv.type == Conversation.Type.GROUP and part.role not in ("owner", "admin"):
            visibility = getattr(conv, "history_visibility", "all") or "all"
            if visibility in ("none", "from_join") and part.joined_at:
                history_restricted = True

        # ------------------------------------------------------------------
        # Hot-cache path (latest N messages in Redis)
        # ------------------------------------------------------------------
        if not history_restricted:
            try:
                from .message_cache import MessageCacheService
                cached = MessageCacheService.get_cached_messages(
                    conv.id, before_id, limit
                )
                if cached is not None:
                    base_msgs, has_more, next_before = cached
                    results = MessageCacheService.enrich_for_viewer(
                        base_msgs, request, conv.id
                    )
                    return ok(data={
                        "results": results,
                        "has_more": has_more,
                        "next_before_id": next_before,
                    })
            except Exception:
                logger.exception("message cache read failed; falling back to DB")

        # ------------------------------------------------------------------
        # Postgres path (source of truth) + opportunistic cache fill
        # ------------------------------------------------------------------
        from django.db.models import Q
        qs = (
            Message.objects.filter(conversation=conv, is_deleted=False)
            .filter(Q(is_scheduled=False) | Q(is_scheduled=True, sender=request.user))
            .select_related("sender", "reply_to", "reply_to__sender", "forwarded_from")
            .prefetch_related("attachments", "reactions")
            .order_by("-created_at")
        )
        if history_restricted:
            qs = qs.filter(created_at__gte=part.joined_at)
        if before_id is not None:
            qs = qs.filter(id__lt=before_id)
        items = list(qs[: limit + 1])
        has_more = len(items) > limit
        items = items[:limit]
        items.reverse()

        # When we served the latest page from DB, populate / refresh the
        # Redis window so subsequent requests become cache hits.
        if not history_restricted and before_id is None and items:
            try:
                from .message_cache import MessageCacheService
                from django.conf import settings as dj_settings
                cache_size = int(getattr(dj_settings, "MESSAGE_CACHE_SIZE", 1000) or 1000)
                # Fetch a full window for the cache (not just the page size)
                window = list(
                    Message.objects.filter(conversation=conv, is_deleted=False, is_scheduled=False)
                    .select_related(
                        "sender", "reply_to", "reply_to__sender", "forwarded_from"
                    )
                    .prefetch_related("attachments", "reactions")
                    .order_by("-id")[:cache_size]
                )
                window.reverse()
                MessageCacheService.cache_messages(conv.id, window)
            except Exception:
                logger.exception("message cache populate failed")

        ctx = build_message_list_context(request, items, conversation_id=conv.id)
        ser = MessageSerializer(items, many=True, context=ctx)
        next_before = items[0].id if has_more and items else None
        return ok(data={
            "results": ser.data,
            "has_more": has_more,
            "next_before_id": next_before,
        })

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = self.get_participant(conv, request.user)
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if conv.is_closed:
            return err("Conversation is closed")
        if not part.can_send_messages:
            return err("You cannot send messages in this chat")
        # Channel-like mode — only owner/admins can send messages
        if getattr(conv, "only_admins_send", False) and part.role not in ("owner", "admin"):
            return err("Only admins can send messages in this group", status.HTTP_403_FORBIDDEN)

        raw_body = request.data.get("body")
        if isinstance(raw_body, (list, tuple)):
            raw_body = raw_body[0] if raw_body else ""
        if not isinstance(raw_body, str):
            raw_body = "" if raw_body is None else str(raw_body)
        full_body = raw_body.strip()

        # Optional schedule (ISO datetime). Message stays private to sender until due.
        scheduled_raw = request.data.get("scheduled_for") or request.data.get("schedule_at")
        scheduled_for = None
        if scheduled_raw:
            from django.utils.dateparse import parse_datetime
            from django.utils import timezone as _tz
            scheduled_for = parse_datetime(str(scheduled_raw))
            if scheduled_for is None:
                return err("Invalid scheduled_for datetime")
            if _tz.is_naive(scheduled_for):
                scheduled_for = _tz.make_aware(scheduled_for, _tz.get_current_timezone())
            if scheduled_for <= _tz.now():
                return err("scheduled_for must be in the future")

        reply_to_id = request.data.get("reply_to")
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(pk=reply_to_id, conversation=conv).first()

        files = request.FILES.getlist("files") or request.FILES.getlist("file") or []
        if not full_body and not files:
            return err("Message body or attachment required")

        if files and not part.can_send_media:
            return err("You cannot send media")

        valid_files = []
        invalid_files = []
        for f in files[:10]:
            try:
                validate_messenger_file(f)
            except ValidationError as exc:
                invalid_files.append(f"{getattr(f, 'name', 'file')}: {'; '.join(exc.messages)}")
                continue
            except Exception as exc:
                invalid_files.append(f"{getattr(f, 'name', 'file')}: {exc}")
                continue
            valid_files.append(f)

        if files and not valid_files:
            return err(
                "No valid attachments were uploaded",
                status.HTTP_400_BAD_REQUEST,
                extra={"errors": invalid_files},
            )

        # Split oversized text into multiple messages (DB TextField is fine, but
        # keep a practical per-message cap for UX / WS payload size).
        MAX_CHUNK = 4000
        if full_body and len(full_body) > MAX_CHUNK and not valid_files:
            chunks = []
            rest = full_body
            while rest:
                if len(rest) <= MAX_CHUNK:
                    chunks.append(rest)
                    break
                cut = rest.rfind("\n", 0, MAX_CHUNK)
                if cut < MAX_CHUNK // 2:
                    cut = MAX_CHUNK
                chunks.append(rest[:cut])
                rest = rest[cut:].lstrip("\n")
        else:
            chunks = [full_body[:10000]] if full_body else [""]

        created_msgs = []
        is_sched = bool(scheduled_for)
        for idx, chunk in enumerate(chunks):
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=chunk,
                reply_to=reply_to if idx == 0 else None,
                scheduled_for=scheduled_for if is_sched else None,
                is_scheduled=is_sched,
            )
            # Attach files only to the first chunk
            if idx == 0:
                for f in valid_files:
                    content_type = getattr(f, "content_type", "") or mimetypes.guess_type(getattr(f, "name", ""))[0] or ""
                    kind = detect_kind(f.name, content_type)
                    MessageAttachment.objects.create(
                        conversation=conv,
                        message=msg,
                        uploaded_by=request.user,
                        file=f,
                        original_filename=getattr(f, "name", "file")[:255],
                        content_type=content_type,
                        size=getattr(f, "size", 0) or 0,
                        kind=kind,
                    )
            created_msgs.append(msg)
            # Cache after DB commit (non-blocking for the HTTP response).
            if not is_sched:
                try:
                    from .message_cache import schedule_add_message
                    schedule_add_message(msg)
                except Exception:
                    logger.exception("message cache schedule add failed")
                try:
                    from .consumers import broadcast_message
                    broadcast_message(msg)
                except Exception:
                    logger.exception("broadcast failed")

        # Return last created (or single) for UI
        last = created_msgs[-1]
        last = (
            Message.objects.filter(pk=last.pk)
            .select_related("sender", "reply_to", "reply_to__sender")
            .prefetch_related("attachments")
            .first()
        )
        ctx = build_message_list_context(request, created_msgs, conversation_id=conv.id)
        payload = MessageSerializer(last, context=ctx).data
        if len(created_msgs) > 1:
            payload = {
                **payload,
                "split_count": len(created_msgs),
                "messages": MessageSerializer(created_msgs, many=True, context=ctx).data,
            }
        return ok(
            "Scheduled" if is_sched else "Sent",
            data=payload,
            http_status=status.HTTP_201_CREATED,
        )


class MessageForwardAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        src = get_object_or_404(Message, pk=pk, is_deleted=False)
        if not ConversationParticipant.objects.filter(
            conversation=src.conversation, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        target_id = request.data.get("conversation_id")
        if not target_id:
            return err("conversation_id required")
        target = get_object_or_404(Conversation, pk=target_id)
        part = ConversationParticipant.objects.filter(
            conversation=target, user=request.user, left_at__isnull=True
        ).first()
        if not part or not part.can_send_messages:
            return err("Cannot send to target", status.HTTP_403_FORBIDDEN)
        new_msg = Message.objects.create(
            conversation=target,
            sender=request.user,
            body=src.body,
            forwarded_from=src.sender,
            forwarded_from_message=src,
        )
        for att in src.attachments.all():
            MessageAttachment.objects.create(
                conversation=target,
                message=new_msg,
                uploaded_by=request.user,
                file=att.file,
                original_filename=att.original_filename,
                content_type=att.content_type,
                size=att.size,
                kind=att.kind,
                width=att.width,
                height=att.height,
                duration=att.duration,
            )
        try:
            from .message_cache import schedule_add_message
            schedule_add_message(new_msg)
        except Exception:
            logger.exception("message cache schedule add (forward) failed")
        try:
            from .consumers import broadcast_message
            broadcast_message(new_msg)
        except Exception:
            pass
        return ok(
            "Forwarded",
            data=MessageSerializer(new_msg, context={"request": request}).data,
            http_status=status.HTTP_201_CREATED,
        )


class MessageReactAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        if not ConversationParticipant.objects.filter(
            conversation=msg.conversation, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        emoji = (request.data.get("emoji") or "").strip()[:32]
        if not emoji:
            return err("emoji required")
        obj, created = MessageReaction.objects.get_or_create(
            message=msg, user=request.user, emoji=emoji
        )
        if not created:
            obj.delete()
            action = "removed"
        else:
            action = "added"
        # Keep reaction aggregates inside the hot-cache in sync (after commit)
        try:
            from .message_cache import schedule_update_message
            schedule_update_message(msg)
        except Exception:
            logger.exception("message cache schedule update (reaction) failed")
        try:
            from .consumers import broadcast_reaction
            broadcast_reaction(msg, request.user, emoji, action)
        except Exception:
            pass
        return ok(action, data={"emoji": emoji, "action": action})



class MessageEditAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        if msg.sender_id != request.user.id:
            return err("Only the sender can edit this message", status.HTTP_403_FORBIDDEN)
        raw = request.data.get("body")
        if not isinstance(raw, str):
            raw = "" if raw is None else str(raw)
        body = raw.strip()[:10000]
        if not body and not msg.attachments.exists():
            return err("Body cannot be empty")
        msg.body = body
        msg.is_edited = True
        msg.save(update_fields=["body", "is_edited", "updated_at"])
        # Sync Redis after DB commit (non-blocking); only touches hot window if present.
        try:
            from .message_cache import schedule_update_message
            schedule_update_message(msg)
        except Exception:
            logger.exception("message cache schedule update (edit) failed")
        try:
            from .consumers import _send
            _send(f"messenger_conv_{msg.conversation_id}", {
                "type": "message.edited",
                "conversation_id": msg.conversation_id,
                "message_id": msg.id,
                "body": body[:200],
            })
        except Exception:
            pass
        msg = (
            Message.objects.filter(pk=msg.pk)
            .select_related("sender", "reply_to", "reply_to__sender", "forwarded_from")
            .prefetch_related("attachments", "reactions__user")
            .first()
        )
        return ok("Edited", data=MessageSerializer(msg, context={"request": request}).data)


class MessageDeleteAPIView(APIView):

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        msg = get_object_or_404(Message, pk=pk)
        if msg.sender_id != request.user.id:
            part = ConversationParticipant.objects.filter(
                conversation=msg.conversation, user=request.user, left_at__isnull=True
            ).first()
            if not part or part.role not in ("owner", "admin"):
                return err("Forbidden", status.HTTP_403_FORBIDDEN)
        msg.is_deleted = True
        msg.is_scheduled = False
        msg.body = ""
        msg.save(update_fields=["is_deleted", "is_scheduled", "body", "updated_at"])
        # Pins + attachment files (important for cancelled schedules / soft delete)
        try:
            from .signals import soft_delete_message_side_effects
            soft_delete_message_side_effects(msg)
        except Exception:
            PinnedMessage.objects.filter(message=msg).delete()
        # Remove from hot-cache after successful soft-delete (non-blocking)
        try:
            from .message_cache import schedule_delete_message
            schedule_delete_message(msg.conversation_id, msg.id)
        except Exception:
            logger.exception("message cache schedule delete failed")
        try:
            from .consumers import _send
            _send(f"messenger_conv_{msg.conversation_id}", {
                "type": "message.deleted",
                "conversation_id": msg.conversation_id,
                "message_id": msg.id,
            })
            # personal channels for participants so list previews update
            for uid in ConversationParticipant.objects.filter(
                conversation_id=msg.conversation_id, left_at__isnull=True
            ).values_list("user_id", flat=True):
                _send(f"messenger_user_{uid}", {
                    "type": "message.deleted",
                    "conversation_id": msg.conversation_id,
                    "message_id": msg.id,
                })
        except Exception:
            logger.exception("broadcast delete failed")
        return ok("Deleted")


class MarkReadAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """Mark messages as read.

        Preferred (viewport-accurate):
          { "message_ids": [1, 2, 3] }
        Explicit mark-all from chat list:
          { "force_all": true }
        Without either, do not bulk-mark downloaded history.
        """
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        raw_ids = request.data.get("message_ids")
        up_to = request.data.get("up_to_message_id")
        force_all = bool(request.data.get("force_all"))
        message_ids = []
        if isinstance(raw_ids, (list, tuple)):
            for x in raw_ids:
                try:
                    message_ids.append(int(x))
                except (TypeError, ValueError):
                    pass

        msg_qs = Message.objects.filter(
            conversation_id=pk, is_deleted=False, is_system=False, is_scheduled=False
        ).exclude(sender=request.user)

        if message_ids:
            msg_qs = msg_qs.filter(id__in=message_ids)
        elif up_to is not None:
            try:
                up_to_i = int(up_to)
            except (TypeError, ValueError):
                return err("Invalid up_to_message_id", status.HTTP_400_BAD_REQUEST)
            up_msg = (
                Message.objects.filter(pk=up_to_i, conversation_id=pk)
                .values("created_at")
                .first()
            )
            if not up_msg:
                return ok("Read", data={"receipts": 0})
            msg_qs = msg_qs.filter(created_at__lte=up_msg["created_at"])
        elif force_all:
            prev = part.last_read_at
            if prev:
                msg_qs = msg_qs.filter(created_at__gt=prev)
        else:
            return ok("Read", data={"receipts": 0, "skipped": True})

        new_receipts = []
        latest_created = None
        for m in msg_qs.values("id", "sender_id", "created_at").iterator():
            _, created = MessageReadReceipt.objects.get_or_create(
                message_id=m["id"], user=request.user,
            )
            if created:
                new_receipts.append({
                    "message_id": m["id"],
                    "sender_id": m["sender_id"],
                    "reader_id": request.user.id,
                })
            if latest_created is None or m["created_at"] > latest_created:
                latest_created = m["created_at"]

        if latest_created and (not part.last_read_at or latest_created > part.last_read_at):
            part.last_read_at = latest_created
            part.save(update_fields=["last_read_at"])
        elif force_all:
            from django.utils import timezone as tz
            part.last_read_at = tz.now()
            part.save(update_fields=["last_read_at"])

        if new_receipts:
            try:
                from .consumers import broadcast_read
                broadcast_read(pk, request.user.id, new_receipts)
            except Exception:
                logger.exception("broadcast_read failed")
        return ok("Read", data={"receipts": len(new_receipts)})



def _auto_transfer_or_cleanup(conv, leaving_part):
    """When the owner/creator leaves a group:
    - If other members exist, transfer ownership to the oldest admin,
      or if no admins, the oldest remaining member.
    - If no members remain, hard-delete the group and all its contents.

    For private DMs, the caller handles deletion separately.

    Returns (transferred_to_user_id or None, deleted: bool).
    """
    remaining = list(
        ConversationParticipant.objects.filter(
            conversation=conv, left_at__isnull=True
        ).exclude(user_id=leaving_part.user_id).order_by("joined_at")
    )
    if not remaining:
        # No one left — delete the group entirely (messages, attachments, etc.)
        conv_id = conv.pk
        conv.delete()
        return None, True
    # Pick the oldest admin; if none, the oldest member
    new_owner = next(
        (p for p in remaining if p.role == ConversationParticipant.Role.ADMIN),
        remaining[0],
    )
    new_owner.role = ConversationParticipant.Role.OWNER
    new_owner.can_add_members = True
    new_owner.can_pin_messages = True
    new_owner.can_change_info = True
    new_owner.save(update_fields=[
        "role", "can_add_members", "can_pin_messages", "can_change_info",
    ])
    return new_owner.user_id, False


class LeaveConversationAPIView(APIView):
    """Leave a conversation.

    Groups:
    - If the leaver is the owner/creator, ownership auto-transfers to the oldest
      admin (or oldest member if no admins). The group stays alive.
    - If the leaver is the LAST member, the group + all messages are deleted.
    - The leaver's previously-sent messages STAY in the group (Telegram behaviour).

    Private DMs:
    - Both sides leave; the conversation is hard-deleted.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Not a member", status.HTTP_404_NOT_FOUND)
        conv = part.conversation
        part.left_at = timezone.now()
        part.save(update_fields=["left_at"])

        transferred_to = None
        deleted = False
        if conv.type == Conversation.Type.GROUP:
            if part.role == ConversationParticipant.Role.OWNER:
                transferred_to, deleted = _auto_transfer_or_cleanup(conv, part)
                if deleted:
                    try:
                        from .consumers import broadcast_member_change
                        broadcast_member_change(pk, {
                            "type": "conversation.deleted",
                            "conversation_id": pk,
                        })
                    except Exception:
                        pass
                    return ok("Left — group deleted (no members remained)")
            # Post a system message about the leave
            try:
                msg = Message.objects.create(
                    conversation=conv,
                    sender=request.user,
                    body=f"{request.user.username} left the group",
                    is_system=True,
                )
                from .consumers import broadcast_message
                broadcast_message(msg)
            except Exception:
                pass
            if transferred_to:
                try:
                    new_owner = User.objects.only("id", "username").get(pk=transferred_to)
                    msg = Message.objects.create(
                        conversation=conv,
                        sender=request.user,
                        body=f"Ownership transferred to {new_owner.username}",
                        is_system=True,
                    )
                    from .consumers import broadcast_message
                    broadcast_message(msg)
                except Exception:
                    pass
            # Broadcast member change so other clients reload
            try:
                from .consumers import broadcast_member_change
                broadcast_member_change(pk, {
                    "type": "member.left",
                    "conversation_id": pk,
                    "user_id": request.user.id,
                    "transferred_to": transferred_to,
                })
            except Exception:
                pass
        else:
            # Private DM: hide for both and hard-delete
            ConversationParticipant.objects.filter(conversation=conv).update(left_at=timezone.now())
            conv.delete()
            return ok("Left")
        return ok("Left", data={"transferred_to": transferred_to})


class RemoveMemberAPIView(APIView):
    """Remove a member from a group (owner/admin only).

    The removed member's messages STAY in the group (Telegram behaviour).
    Their `left_at` is set to now so they can no longer access the group.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, user_id):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if my_part.role not in ("owner", "admin"):
            return err("Only admins can remove members", status.HTTP_403_FORBIDDEN)
        target = ConversationParticipant.objects.filter(
            conversation=conv, user_id=user_id, left_at__isnull=True
        ).first()
        if not target:
            return err("Member not found", status.HTTP_404_NOT_FOUND)
        # Cannot remove another owner/admin unless you're the owner
        if target.role in ("owner", "admin") and my_part.role != "owner":
            return err("Only the group owner can remove other admins", status.HTTP_403_FORBIDDEN)
        if target.role == "owner":
            return err("Cannot remove the group owner", status.HTTP_403_FORBIDDEN)
        target.left_at = timezone.now()
        target.save(update_fields=["left_at"])
        # System message
        try:
            removed_user = User.objects.only("id", "username").get(pk=user_id)
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{request.user.username} removed {removed_user.username}",
                is_system=True,
            )
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        # Broadcast so other clients reload the member list
        try:
            from .consumers import broadcast_member_change
            broadcast_member_change(pk, {
                "type": "member.removed",
                "conversation_id": pk,
                "user_id": user_id,
            })
        except Exception:
            pass
        detail = ConversationDetailSerializer(conv, context={"request": request}).data
        return ok("Member removed", data={"conversation": detail})


class MemberRoleAPIView(APIView):
    """Promote/demote a group member.

    POST body: { "role": "admin" | "member" }
    Only the group owner can promote/demote.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, user_id):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if my_part.role != "owner":
            return err("Only the group owner can change roles", status.HTTP_403_FORBIDDEN)
        new_role = (request.data.get("role") or "").strip().lower()
        if new_role not in ("admin", "member"):
            return err("role must be 'admin' or 'member'")
        target = ConversationParticipant.objects.filter(
            conversation=conv, user_id=user_id, left_at__isnull=True
        ).first()
        if not target:
            return err("Member not found", status.HTTP_404_NOT_FOUND)
        if target.role == "owner":
            return err("Cannot change the owner's role", status.HTTP_403_FORBIDDEN)
        target.role = new_role
        if new_role == "admin":
            target.can_add_members = True
            target.can_pin_messages = True
            target.can_change_info = True
        else:
            target.can_add_members = False
            target.can_pin_messages = False
            target.can_change_info = False
        target.save(update_fields=[
            "role", "can_add_members", "can_pin_messages", "can_change_info",
        ])
        try:
            target_user = User.objects.only("id", "username").get(pk=user_id)
            action = "promoted to admin" if new_role == "admin" else "demoted to member"
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{target_user.username} {action}",
                is_system=True,
            )
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        try:
            from .consumers import broadcast_member_change
            broadcast_member_change(pk, {
                "type": "member.role_changed",
                "conversation_id": pk,
                "user_id": user_id,
                "role": new_role,
            })
        except Exception:
            pass
        detail = ConversationDetailSerializer(conv, context={"request": request}).data
        return ok(f"Role changed to {new_role}", data={"conversation": detail})


class TransferOwnershipAPIView(APIView):
    """Transfer group ownership to another member.

    The current owner becomes an admin; the target member becomes the owner.
    Only the current owner can call this.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part or my_part.role != "owner":
            return err("Only the owner can transfer ownership", status.HTTP_403_FORBIDDEN)
        target_id = request.data.get("user_id")
        if not target_id:
            return err("user_id required")
        target = ConversationParticipant.objects.filter(
            conversation=conv, user_id=target_id, left_at__isnull=True
        ).first()
        if not target:
            return err("Member not found", status.HTTP_404_NOT_FOUND)
        if target.user_id == request.user.id:
            return err("You already own this group")
        # Swap roles
        my_part.role = ConversationParticipant.Role.ADMIN
        my_part.save(update_fields=["role"])
        target.role = ConversationParticipant.Role.OWNER
        target.can_add_members = True
        target.can_pin_messages = True
        target.can_change_info = True
        target.save(update_fields=[
            "role", "can_add_members", "can_pin_messages", "can_change_info",
        ])
        # Update created_by on the conversation so the new owner is shown as creator
        conv.created_by = target.user
        conv.save(update_fields=["created_by"])
        try:
            target_user = User.objects.only("id", "username").get(pk=target_id)
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"Ownership transferred to {target_user.username}",
                is_system=True,
            )
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        try:
            from .consumers import broadcast_member_change
            broadcast_member_change(pk, {
                "type": "ownership.transferred",
                "conversation_id": pk,
                "new_owner_id": target_id,
            })
        except Exception:
            pass
        detail = ConversationDetailSerializer(conv, context={"request": request}).data
        return ok("Ownership transferred", data={"conversation": detail})




class AddMembersAPIView(APIView):
    """Add users to a group; posts a system message like Telegram."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if part.role not in ("owner", "admin"):
            if not getattr(conv, "members_can_add", True) or not part.can_add_members:
                return err("You cannot add members to this group", status.HTTP_403_FORBIDDEN)
        ids = request.data.get("user_ids") or request.data.get("member_ids") or []
        if not isinstance(ids, list) or not ids:
            return err("user_ids required")
        added = []
        for uid in ids[:50]:
            try:
                u = User.objects.get(pk=uid, is_active=True)
            except User.DoesNotExist:
                continue
            if u.id == request.user.id:
                continue
            if users_blocked(request.user, u):
                continue
            obj, created = ConversationParticipant.objects.get_or_create(
                conversation=conv,
                user=u,
                defaults={
                    "role": ConversationParticipant.Role.MEMBER,
                    "can_pin_messages": True,
                },
            )
            if not created and obj.left_at:
                from django.utils import timezone as _tz
                obj.left_at = None
                obj.joined_at = _tz.now()
                obj.save(update_fields=["left_at", "joined_at"])
                created = True
            if created:
                added.append(u)
        for u in added:
            body = f"{request.user.username} added {u.username}"
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=body,
                is_system=True,
            )
            try:
                from .consumers import broadcast_message
                broadcast_message(msg)
            except Exception:
                pass
        detail = ConversationDetailSerializer(conv, context={"request": request}).data
        return ok(
            "Members added" if added else "No new members",
            data={
                "added": [{"id": u.id, "username": u.username} for u in added],
                "conversation": detail,
            },
        )


class DeleteConversationAPIView(APIView):
    """
    Private DM: both users leave (conversation hidden for both; deleted if empty).
    Group: only owner (or admin) can hard-delete the whole group + messages + media.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        if conv.type == Conversation.Type.PRIVATE:
            # Hide for everyone in the DM and remove conversation
            ConversationParticipant.objects.filter(conversation=conv).update(left_at=timezone.now())
            # Hard delete conversation (cascades messages)
            conv_id = conv.pk
            conv.delete()
            return ok("Chat deleted", data={"id": conv_id})

        # Group: owner or admin may delete entire group
        if part.role not in (
            ConversationParticipant.Role.OWNER,
            ConversationParticipant.Role.ADMIN,
        ):
            return err("Only group owner/admin can delete the group", status.HTTP_403_FORBIDDEN)
        conv_id = conv.pk
        conv.delete()
        return ok("Group deleted", data={"id": conv_id})


class InviteLinkCreateAPIView(APIView):

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        link = GroupInviteLink.objects.create(
            conversation=conv,
            created_by=request.user,
            max_uses=request.data.get("max_uses"),
        )
        return ok(data=GroupInviteLinkSerializer(link, context={"request": request}).data, http_status=status.HTTP_201_CREATED)


class InviteLinkRevokeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, link_id):
        link = get_object_or_404(GroupInviteLink, pk=link_id, conversation_id=pk)
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        link.is_active = False
        link.save(update_fields=["is_active"])
        return ok("Revoked")


class JoinByInviteAPIView(APIView):
    """Join a group via invite link OR (if the group requires approval) create
    a pending join request that admins can approve/reject.

    If the group has `requires_approval=True`, this endpoint creates a
    JoinRequest (PENDING) and returns 200 with a special payload
    `{joined: False, pending: True}` so the frontend can show
    "Request sent" instead of opening the chat.

    If the group does not require approval, the user is added as a member
    immediately.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        link = get_object_or_404(GroupInviteLink, code=code)
        if not link.is_valid():
            return err("Invite link is invalid or expired")
        conv = link.conversation
        if conv.is_closed:
            return err("Group is closed")
        # If user is already an active member, just return the conversation
        existing = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if existing:
            return ok(
                "Already a member",
                data={
                    "joined": True,
                    "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
                },
            )
        # If the group requires approval, create a pending join request
        if getattr(conv, "requires_approval", False):
            from .models import JoinRequest
            # Delete any prior rejected request so a new pending one can be created
            JoinRequest.objects.filter(
                user=request.user, conversation=conv, status=JoinRequest.Status.REJECTED
            ).delete()
            req, created = JoinRequest.objects.get_or_create(
                user=request.user, conversation=conv,
                defaults={"status": JoinRequest.Status.PENDING},
            )
            if not created and req.status == JoinRequest.Status.PENDING:
                return ok(
                    "Request already pending",
                    data={"joined": False, "pending": True, "request_id": req.id},
                )
            # Notify admins about the new request
            try:
                from .consumers import broadcast_join_request
                broadcast_join_request(conv.id, {
                    "type": "join_request.new",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": request.user.id,
                })
            except Exception:
                pass
            link.uses += 1
            link.save(update_fields=["uses"])
            return ok(
                "Join request sent",
                data={"joined": False, "pending": True, "request_id": req.id},
            )
        # No approval required — direct join
        part, created = ConversationParticipant.objects.get_or_create(
            conversation=conv,
            user=request.user,
            defaults={
                "role": ConversationParticipant.Role.MEMBER,
                "can_pin_messages": True,
            },
        )
        if not created and part.left_at:
            from django.utils import timezone as _tz
            part.left_at = None
            part.joined_at = _tz.now()
            part.save(update_fields=["left_at", "joined_at"])
        link.uses += 1
        link.save(update_fields=["uses"])
        # Post a system message about the new member
        try:
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{request.user.username} joined the group",
                is_system=True,
            )
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        return ok(
            "Joined",
            data={
                "joined": True,
                "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
            },
        )


class MyProfilePhotosAPIView(APIView):
    """
    Reads existing users.Profile images only.
    Upload / reorder / delete stays in the users Profile UI — messenger does not own photos.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from users.models import Profile
        photos = (
            Profile.objects.filter(user=request.user)
            .exclude(image="")
            .filter(image__isnull=False)
            .order_by("order", "id")
        )
        privacy, _ = ProfilePhotoPrivacy.objects.get_or_create(user=request.user)
        return ok(data={
            "photos": ProfilePhotoSerializer(photos, many=True, context={"request": request}).data,
            "privacy": ProfilePhotoPrivacySerializer(privacy).data,
        })


class ProfilePhotoPrivacyAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        privacy, _ = ProfilePhotoPrivacy.objects.get_or_create(user=request.user)
        scope = request.data.get("scope")
        if scope in dict(ProfilePhotoPrivacy.Scope.choices):
            privacy.scope = scope
            privacy.save(update_fields=["scope", "updated_at"])
        if "allowed_user_ids" in request.data and isinstance(request.data["allowed_user_ids"], list):
            privacy.allowed_users.all().delete()
            for uid in request.data["allowed_user_ids"][:200]:
                try:
                    u = User.objects.get(pk=uid)
                    ProfilePhotoAllowed.objects.create(privacy=privacy, user=u)
                except User.DoesNotExist:
                    pass
        return ok(data=ProfilePhotoPrivacySerializer(privacy).data)


class UserProfileAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        data = UserMiniSerializer(user, context={"request": request}).data
        if can_see_profile_photo(request.user, user):
            from users.models import Profile
            photos = (
                Profile.objects.filter(user=user)
                .exclude(image="")
                .filter(image__isnull=False)
                .order_by("order", "id")
            )
            data["photos"] = ProfilePhotoSerializer(photos, many=True, context={"request": request}).data
        else:
            data["photos"] = []
        return ok(data=data)


class AttachmentDownloadAPIView(APIView):
    """Attachment download — supports JWT via Authorization header OR ?token= query param.
    The query-param fallback lets the browser load <img src="...?token=..."> and
    <audio>/<video> without custom headers (which those tags cannot send).

    IMPORTANT: authentication_classes is empty so an expired Authorization header
    cannot short-circuit the request before we try ?token= (common when a page
    still has an old header from a previous SPA session / service worker).
    """
    authentication_classes = []  # fully manual — see _authenticate()
    permission_classes = []

    def _authenticate(self, request):
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # 1) Authorization: Bearer <access>
        auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
        if auth.startswith("Bearer "):
            tok = auth[7:].strip()
            try:
                access = AccessToken(tok)
                user_id = access.get("user_id") or access.get("user")
                if user_id:
                    user = User.objects.filter(pk=user_id, is_active=True).first()
                    if user:
                        return user
            except Exception:
                pass

        # 2) ?token=<access>  (img / audio / video tags)
        tok = request.GET.get("token") or request.query_params.get("token")
        if tok:
            try:
                access = AccessToken(tok)
                user_id = access.get("user_id") or access.get("user")
                if user_id:
                    user = User.objects.filter(pk=user_id, is_active=True).first()
                    if user:
                        return user
            except Exception:
                pass

        # 3) Session auth
        if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False):
            return request.user
        return None

    def get(self, request, pk):
        user = self._authenticate(request)
        if not user:
            return err("Unauthorized", status.HTTP_401_UNAUTHORIZED)
        request.user = user

        att = get_object_or_404(MessageAttachment, pk=pk)
        if not ConversationParticipant.objects.filter(
            conversation=att.conversation, user=user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        from django.http import FileResponse
        content_type = (
            att.content_type
            or mimetypes.guess_type(att.original_filename or att.file.name)[0]
            or "application/octet-stream"
        )
        inline_kinds = {"image", "gif", "video", "audio", "voice"}
        try:
            fh = att.file.open("rb")
        except Exception:
            return err("File not found", status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            fh,
            as_attachment=att.kind not in inline_kinds,
            filename=att.original_filename or (getattr(att.file, "name", None) or "file").rsplit("/", 1)[-1],
            content_type=content_type,
        )
        disposition = "inline" if att.kind in inline_kinds else "attachment"
        safe_name = (att.original_filename or "file").replace('"', "")
        response["Content-Disposition"] = f'{disposition}; filename="{safe_name}"'
        response["Accept-Ranges"] = "bytes"
        response["X-Content-Type-Options"] = "nosniff"
        # Help cross-origin <video>/<audio>/wavesurfer range requests
        response["Access-Control-Expose-Headers"] = "Content-Range, Accept-Ranges, Content-Length, Content-Type"
        response["Cache-Control"] = "private, max-age=3600"
        return response


class ConversationPinAPIView(APIView):
    """Toggle pin/unpin of a conversation for the current user (per-user pin)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        part.is_pinned = not part.is_pinned
        part.pinned_at = timezone.now() if part.is_pinned else None
        part.save(update_fields=["is_pinned", "pinned_at"])
        return ok(
            "Pinned" if part.is_pinned else "Unpinned",
            data={"is_pinned": part.is_pinned},
        )


class MessagePinAPIView(APIView):
    """Pin or unpin a specific message in its conversation.

    POST /messages/<pk>/pin/  — toggle pin on/off.

    Only participants with `can_pin_messages` (or owner/admin) may pin.
    Returns the current pin state and the list of pinned message ids for
    the conversation so the frontend can update its bar in one round-trip.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        conv = msg.conversation
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        # Permission check: owner/admin always allowed.
        # In private (direct) chats, every participant can pin.
        # In group chats, non-owner/admin needs explicit can_pin_messages.
        if conv.type != Conversation.Type.PRIVATE:
            if part.role not in ("owner", "admin") and not part.can_pin_messages:
                return err("You don't have permission to pin messages", status.HTTP_403_FORBIDDEN)

        existing = PinnedMessage.objects.filter(conversation=conv, message=msg).first()
        if existing:
            existing.delete()
            pinned = False
        else:
            PinnedMessage.objects.create(conversation=conv, message=msg, pinned_by=request.user)
            pinned = True

        # Return all pinned message ids for this conversation (newest-first)
        pin_ids = list(
            PinnedMessage.objects.filter(conversation=conv)
            .select_related("message")
            .order_by("-pinned_at")
            .values_list("message_id", flat=True)
        )

        # Broadcast to other participants so their pinned bar updates
        try:
            from .consumers import broadcast_pin
            broadcast_pin(conv.id, {
                "type": "message.pinned" if pinned else "message.unpinned",
                "conversation_id": conv.id,
                "message_id": msg.id,
                "pinned_by": request.user.id,
                "pinned_message_ids": pin_ids,
            })
        except Exception:
            pass

        return ok(
            "Pinned" if pinned else "Unpinned",
            data={"pinned": pinned, "message_id": msg.id, "pinned_message_ids": pin_ids},
        )


class ConversationPinnedMessagesAPIView(APIView):
    """List all pinned messages for a conversation (newest-pinned-first).

    GET /conversations/<pk>/pinned-messages/

    Returns a list of { id, message, pinned_at } objects.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        if not ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        pins = (
            PinnedMessage.objects.filter(conversation=conv, message__is_deleted=False)
            .select_related("message", "message__sender", "pinned_by")
            .order_by("-pinned_at")
        )
        data = [
            {
                "id": p.id,
                "message": MessageSerializer(p.message, context={"request": request}).data,
                "pinned_by": UserMiniSerializer(p.pinned_by, context={"request": request}).data if p.pinned_by else None,
                "pinned_at": p.pinned_at,
            }
            for p in pins
        ]
        return ok(data=data)


class MessageReadersAPIView(APIView):
    """Returns full read receipt breakdown for a single message:
    { read: [...], unread: [...], conversation_id, sender_id, created_at }
    Used by the "Seen by" right-click submenu.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        if not ConversationParticipant.objects.filter(
            conversation=msg.conversation, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        participants = list(
            ConversationParticipant.objects.filter(
                conversation=msg.conversation, left_at__isnull=True
            ).select_related("user")
        )
        # Build read set from MessageReadReceipt
        receipt_users = {}  # user_id -> seen_at
        for r in msg.read_receipts.all():
            receipt_users[r.user_id] = r.seen_at
        # Supplement with last_read_at
        read_list = []
        unread_list = []
        for p in participants:
            seen_at = receipt_users.get(p.user_id)
            if not seen_at and p.last_read_at and p.last_read_at >= msg.created_at:
                seen_at = p.last_read_at
            entry = {
                "user": UserMiniSerializer(p.user, context={"request": request}).data,
                "seen_at": seen_at,
                "role": p.role,
            }
            if seen_at:
                read_list.append(entry)
            elif p.user_id != msg.sender_id:
                # Sender always implicitly "saw" their own message
                unread_list.append(entry)
            else:
                read_list.append(entry)  # sender counts as read
        return ok(data={
            "message_id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "created_at": msg.created_at,
            "read": read_list,
            "unread": unread_list,
        })


class ConversationCleanupAPIView(APIView):
    """Delete ALL messages in a conversation for the current user.

    Behaviour:
    - Private DM: HARD-deletes all messages + their attachment files from disk
      for BOTH participants (the conversation is shared, so deleting files is
      the only way to actually reclaim disk space). This is what Telegram does
      when you "Clear history" — the files are gone for everyone.
    - Group: HARD-deletes all messages + their attachment files for EVERYONE.
      Group participants who didn't request the cleanup will also lose their
      copy. This matches Telegram's group "Clear history" behaviour.
    - The user must be an active participant.
    - Attachment files (images, videos, voice messages, documents) are deleted
      from MEDIA_ROOT via the FileField API so disk space is reclaimed.

    Body: { } (no params needed)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        # Collect all attachments for this conversation and delete their
        # underlying files from disk BEFORE deleting the message rows.
        # (Once the Message rows are gone, the ORM cascade will also delete
        # the MessageAttachment rows, but it does NOT delete the files.)
        from .models import MessageAttachment
        attachments = MessageAttachment.objects.filter(conversation=conv)
        files_deleted = 0
        for att in attachments.iterator():
            try:
                if att.file:
                    att.file.delete(save=False)
                    files_deleted += 1
            except Exception:
                logger.warning(
                    "Could not delete attachment file id=%s", att.id, exc_info=True
                )
        # Now hard-delete all messages (cascade will remove attachments rows,
        # reactions, read receipts, etc.)
        msgs = Message.objects.filter(conversation=conv)
        count = msgs.count()
        # Delete pinned-message rows referencing these messages first to
        # avoid cascade integrity errors.
        from .models import PinnedMessage
        PinnedMessage.objects.filter(conversation=conv).delete()
        msgs.delete()
        # Reset read state for this participant so unread badge clears
        part.last_read_at = timezone.now()
        part.save(update_fields=["last_read_at"])
        # Update conversation's last_message_at to null since there are no
        # messages left.
        Conversation.objects.filter(pk=conv.pk).update(
            last_message_at=None, updated_at=timezone.now()
        )
        # Broadcast to all participants so their clients reload the chat
        # (otherwise they'd be looking at stale messages that are now gone).
        try:
            from .consumers import broadcast_member_change
            broadcast_member_change(conv.id, {
                "type": "messages.cleared",
                "conversation_id": conv.id,
                "user_id": request.user.id,
            })
        except Exception:
            pass
        return ok(
            f"Cleared {count} messages ({files_deleted} files deleted)",
            data={"cleared": count, "files_deleted": files_deleted},
        )


class ConversationMediaAPIView(APIView):
    """List all media attachments (images, videos, voice, audio, files) in a conversation.

    Used by the in-chat image gallery (< > navigation). Paginated by message cursor
    (newest first) so the client can fetch older media on demand.

    Query params:
      - kind: comma-separated filter (image,video,audio,voice,file). Default: image
      - before_id: message id cursor (load older media)
      - limit: default 30, max 100
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        if not ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        kinds_param = (request.query_params.get("kind") or "image").lower()
        kinds = [k.strip() for k in kinds_param.split(",") if k.strip()]
        if not kinds:
            kinds = ["image"]
        limit = min(100, int(request.query_params.get("limit") or 30))
        qs = (
            MessageAttachment.objects.filter(
                conversation=conv, kind__in=kinds, message__is_deleted=False, message__is_scheduled=False
            )
            .select_related("message", "message__sender")
            .order_by("-message__created_at", "-id")
        )
        before_id = request.query_params.get("before_id")
        if before_id:
            try:
                qs = qs.filter(message_id__lt=int(before_id))
            except ValueError:
                pass
        items = list(qs[: limit + 1])
        has_more = len(items) > limit
        items = items[:limit]
        from .serializers import MessageAttachmentSerializer
        result = []
        for att in items:
            ser = MessageAttachmentSerializer(att, context={"request": request}).data
            ser["message_id"] = att.message_id
            ser["message_created_at"] = att.message.created_at if att.message else att.created_at
            ser["sender"] = (
                UserMiniSerializer(att.message.sender, context={"request": request}).data
                if att.message and att.message.sender else None
            )
            result.append(ser)
        next_before = items[-1].message_id if has_more and items else None
        return ok(data={
            "results": result,
            "has_more": has_more,
            "next_before_id": next_before,
        })


class UserByUsernameAPIView(APIView):
    """Look up a user by exact username — used for @mention click navigation.

    Returns the same payload as UserProfileAPIView so the client can show the
    profile panel without adding the user to contacts.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        username = (request.query_params.get("username") or "").strip().lstrip("@")
        if not username:
            return err("username required")
        try:
            user = User.objects.get(username__iexact=username, is_active=True)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        data = UserMiniSerializer(user, context={"request": request}).data
        if can_see_profile_photo(request.user, user):
            from users.models import Profile
            photos = (
                Profile.objects.filter(user=user)
                .exclude(image="")
                .filter(image__isnull=False)
                .order_by("order", "id")
            )
            data["photos"] = ProfilePhotoSerializer(photos, many=True, context={"request": request}).data
        else:
            data["photos"] = []
        return ok(data=data)


class UserBioAPIView(APIView):
    """Get or set the current user's bio (Telegram-style 'about' field).

    GET  /me/bio/         -> {text: "..."}
    PATCH /me/bio/        -> {text: "new bio"}  (max 255 chars)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bio, _ = UserBio.objects.get_or_create(user=request.user)
        return ok(data={"text": bio.text or ""})

    def patch(self, request):
        text = str(request.data.get("text") or "")[:255]
        bio, _ = UserBio.objects.get_or_create(user=request.user)
        bio.text = text
        bio.save(update_fields=["text", "updated_at"])
        return ok("Bio updated", data={"text": bio.text})


class GroupAvatarAPIView(APIView):
    """Upload or clear a group's avatar (owner/admin only).

    POST   /conversations/<pk>/avatar/   (multipart: avatar=<file>)   -> upload
    DELETE /conversations/<pk>/avatar/                                -> clear
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Only admins can change the group avatar", status.HTTP_403_FORBIDDEN)
        f = request.FILES.get("avatar")
        if not f:
            return err("avatar file required")
        # Basic size check (10MB)
        if getattr(f, "size", 0) > 10 * 1024 * 1024:
            return err("Image too large (max 10MB)")
        # Validate it is actually an image (Django ImageField requires Pillow;
        # we use a FileField, so do a manual content-type sanity check).
        ctype = (getattr(f, "content_type", "") or "").lower()
        if ctype and not ctype.startswith("image/"):
            return err("File must be an image")
        # Delete the previous avatar file from storage (if any) BEFORE
        # assigning the new one — otherwise the old file lingers and may
        # conflict with the new name on case-insensitive filesystems.
        old_avatar = conv.avatar
        if old_avatar:
            try:
                old_avatar.delete(save=False)
            except Exception:
                logger.warning("Could not delete previous group avatar", exc_info=True)
        # Assign new file. Django's FileField.save() will write the file
        # to MEDIA_ROOT/messenger/groups/<unique-name> using the storage backend.
        # We use a deterministic, unique filename to avoid collisions and
        # make the URL predictable for the client.
        import os
        import uuid
        ext = os.path.splitext(f.name)[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            ext = ".jpg"
        safe_name = f"group_{conv.pk}_{uuid.uuid4().hex[:12]}{ext}"
        f.name = safe_name
        try:
            conv.avatar = f
            conv.save(update_fields=["avatar", "updated_at"])
        except Exception as save_exc:
            logger.error("Group avatar save failed: %s", save_exc, exc_info=True)
            return err(
                f"Could not save image: {save_exc}",
                status.HTTP_400_BAD_REQUEST,
            )
        # Force a refresh from DB so the serializer returns the committed path
        conv.refresh_from_db()
        # Verify the file actually exists on disk (debug aid — surfaces
        # misconfigured MEDIA_ROOT / volume mounts early).
        try:
            from django.conf import settings
            path = conv.avatar.path if hasattr(conv.avatar, "path") else None
            if path and not os.path.exists(path):
                logger.error(
                    "Group avatar file missing after save: %s (MEDIA_ROOT=%s)",
                    path, getattr(settings, "MEDIA_ROOT", "<unset>"),
                )
        except Exception:
            pass
        return ok("Avatar updated", data=ConversationDetailSerializer(conv, context={"request": request}).data)

    def delete(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Only admins can change the group avatar", status.HTTP_403_FORBIDDEN)
        if conv.avatar:
            # Delete the file from storage
            try:
                conv.avatar.delete(save=False)
            except Exception:
                pass
            conv.avatar = None
            conv.save(update_fields=["avatar", "updated_at"])
        return ok("Avatar removed", data=ConversationDetailSerializer(conv, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Join Requests (Telegram-style — for public groups that require approval)
# ---------------------------------------------------------------------------

class PublicGroupJoinAPIView(APIView):
    """Join a public group directly (no invite code required).

    If the group has `requires_approval=True`, this creates a pending
    JoinRequest and returns `{joined: False, pending: True}`.

    If the group does NOT require approval, the user is added as a member
    immediately and the conversation payload is returned.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(
            Conversation, pk=pk,
            type=Conversation.Type.GROUP, is_public=True, is_closed=False,
        )
        # Already an active member?
        existing = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if existing:
            return ok(
                "Already a member",
                data={
                    "joined": True,
                    "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
                },
            )
        # Approval required -> create a pending request
        if getattr(conv, "requires_approval", False):
            from .models import JoinRequest
            # Clear any prior rejected request so a fresh pending one can be created
            JoinRequest.objects.filter(
                user=request.user, conversation=conv, status=JoinRequest.Status.REJECTED
            ).delete()
            req, created = JoinRequest.objects.get_or_create(
                user=request.user, conversation=conv,
                defaults={"status": JoinRequest.Status.PENDING},
            )
            if not created and req.status == JoinRequest.Status.PENDING:
                return ok(
                    "Request already pending",
                    data={"joined": False, "pending": True, "request_id": req.id},
                )
            try:
                from .consumers import broadcast_join_request
                broadcast_join_request(conv.id, {
                    "type": "join_request.new",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": request.user.id,
                })
            except Exception:
                pass
            return ok(
                "Join request sent",
                data={"joined": False, "pending": True, "request_id": req.id},
            )
        # Direct join
        part, created = ConversationParticipant.objects.get_or_create(
            conversation=conv,
            user=request.user,
            defaults={
                "role": ConversationParticipant.Role.MEMBER,
                "can_pin_messages": True,
            },
        )
        if not created and part.left_at:
            from django.utils import timezone as _tz
            part.left_at = None
            part.joined_at = _tz.now()
            part.save(update_fields=["left_at", "joined_at"])
        # System message about the new member
        try:
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{request.user.username} joined the group",
                is_system=True,
            )
            from .consumers import broadcast_message, broadcast_member_change
            broadcast_message(msg)
            broadcast_member_change(conv.id, {
                "type": "member.joined",
                "conversation_id": conv.id,
                "user_id": request.user.id,
            })
        except Exception:
            pass
        return ok(
            "Joined",
            data={
                "joined": True,
                "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
            },
        )


class JoinRequestListAPIView(APIView):
    """List pending join requests for a group (admins only).

    GET /conversations/<pk>/join-requests/   -> [{ id, user, status, created_at }, ...]
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part or my_part.role not in ("owner", "admin"):
            return err("Only admins can view join requests", status.HTTP_403_FORBIDDEN)
        qs = (
            conv.join_requests.filter(status=JoinRequest.Status.PENDING)
            .select_related("user", "decided_by")
            .order_by("-created_at")
        )
        from .serializers import JoinRequestSerializer
        return ok(data=JoinRequestSerializer(qs, many=True, context={"request": request}).data)


class JoinRequestActionAPIView(APIView):
    """Approve or reject a pending join request (admins only).

    POST /conversations/<pk>/join-requests/<req_id>/action/
      body: { "action": "approve" | "reject" }

    On approve: the requesting user is added as a member + the request is
    marked APPROVED + a system message is posted + the user is notified
    via their personal WS channel so their client opens the chat.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, req_id):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part or my_part.role not in ("owner", "admin"):
            return err("Only admins can act on join requests", status.HTTP_403_FORBIDDEN)
        try:
            req = conv.join_requests.get(pk=req_id)
        except JoinRequest.DoesNotExist:
            return err("Join request not found", status.HTTP_404_NOT_FOUND)
        if req.status != JoinRequest.Status.PENDING:
            return err(f"Request already {req.status}")
        action = (request.data.get("action") or "").strip().lower()
        if action not in ("approve", "reject"):
            return err("action must be 'approve' or 'reject'")
        req.decided_by = request.user
        req.decided_at = timezone.now()
        if action == "approve":
            req.status = JoinRequest.Status.APPROVED
            # Add the user as a member
            part, created = ConversationParticipant.objects.get_or_create(
                conversation=conv,
                user=req.user,
                defaults={
                    "role": ConversationParticipant.Role.MEMBER,
                    "can_pin_messages": True,
                },
            )
            if not created and part.left_at:
                from django.utils import timezone as _tz
                part.left_at = None
                part.joined_at = _tz.now()
                part.save(update_fields=["left_at", "joined_at"])
            # System message
            try:
                msg = Message.objects.create(
                    conversation=conv,
                    sender=request.user,
                    body=f"{req.user.username} joined the group",
                    is_system=True,
                )
                from .consumers import broadcast_message, broadcast_member_change, broadcast_join_request
                broadcast_message(msg)
                broadcast_member_change(conv.id, {
                    "type": "member.joined",
                    "conversation_id": conv.id,
                    "user_id": req.user_id,
                })
                # Notify the requester that they were approved
                broadcast_join_request(conv.id, {
                    "type": "join_request.approved",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": req.user_id,
                })
            except Exception:
                pass
        else:
            req.status = JoinRequest.Status.REJECTED
            try:
                from .consumers import broadcast_join_request
                broadcast_join_request(conv.id, {
                    "type": "join_request.rejected",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": req.user_id,
                })
            except Exception:
                pass
        # The user asked that requests be DELETED after the admin acts on them
        # (the operation is complete — there's no reason to keep a decided
        # request around cluttering the admin's list or the user's "My
        # requests" list). We broadcast the decision BEFORE deleting so the
        # frontend can show the "approved/rejected" toast.
        req.save(update_fields=["status", "decided_by", "decided_at"])
        req_id = req.id
        req_status = req.status
        req_user_id = req.user_id
        req.delete()
        return ok(f"Request {req_status}", data={"status": req_status, "request_id": req_id, "user_id": req_user_id})


class MyJoinRequestsAPIView(APIView):
    """List all of the current user's join requests (any status).

    GET /me/join-requests/  -> [{ id, conversation, conversation_title, status, created_at, ... }]
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            JoinRequest.objects.filter(user=request.user)
            .select_related("conversation", "decided_by")
            .order_by("-created_at")
        )
        from .serializers import JoinRequestSerializer
        return ok(data=JoinRequestSerializer(qs, many=True, context={"request": request}).data)


class JoinRequestCancelAPIView(APIView):
    """Cancel (delete) the current user's own pending join request.

    DELETE /join-requests/<req_id>/  -> 200 OK

    The user can only cancel their OWN pending requests. Once approved or
    rejected, the request can no longer be cancelled (the user can leave
    the group separately if approved).
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, req_id):
        try:
            req = JoinRequest.objects.get(pk=req_id, user=request.user)
        except JoinRequest.DoesNotExist:
            return err("Join request not found", status.HTTP_404_NOT_FOUND)
        if req.status != JoinRequest.Status.PENDING:
            return err(f"Cannot cancel a {req.status} request")
        conv_id = req.conversation_id
        req.delete()
        # Notify admins that the request was cancelled (so their UI updates)
        try:
            from .consumers import broadcast_join_request
            broadcast_join_request(conv_id, {
                "type": "join_request.cancelled",
                "conversation_id": conv_id,
                "user_id": request.user.id,
            })
        except Exception:
            pass
        return ok("Request cancelled")


class ProfileUpdateBroadcastAPIView(APIView):
    """Notify all conversations the current user is part of that their profile
    has changed (avatar, bio, etc).

    POST /me/profile-broadcast/  -> 200 OK

    Called by the frontend after the user updates their profile photo, bio,
    or username. The backend fans out a `profile.update` WebSocket event to
    every conversation + the user's own personal channel.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            from .consumers import broadcast_profile_update
            broadcast_profile_update(request.user.id)
        except Exception:
            pass
        return ok("Broadcast sent")


# ------------------------------------------------------------# Voice / video calls (custom UI + Jitsi media transport)
# ---------------------------------------------------------------------------

import json as _json
from django.utils import timezone as _tz


def _call_body(payload: dict) -> str:
    """Machine-readable system message body for call events."""
    return "__call__:" + _json.dumps(payload, separators=(",", ":"))


def _jitsi_config(request, conv: Conversation, room_name: str | None = None):
    """Build room config for a conversation (media via self-hosted or public meet)."""
    from django.conf import settings as dj_settings
    from urllib.parse import urlparse

    base = (getattr(dj_settings, "JITSI_BASE_URL", None) or "https://meet.jit.si").rstrip("/")
    parsed = urlparse(base)
    domain = parsed.netloc or "meet.jit.si"
    room = room_name or f"messenger-{conv.public_id.hex}"
    display_name = (
        getattr(request.user, "username", None)
        or getattr(request.user, "email", None)
        or f"User-{request.user.id}"
    )
    join_url = f"{base}/{room}"
    return {
        "domain": domain,
        "base_url": base,
        "room": room,
        "join_url": join_url,
        "display_name": display_name,
        "conversation_id": conv.id,
        "conversation_public_id": str(conv.public_id),
        "user_id": request.user.id,
        "config": {
            "startWithAudioMuted": False,
            "startWithVideoMuted": False,
            "disableModeratorIndicator": True,
            "enableClosePage": False,
            "prejoinPageEnabled": False,
            "prejoinConfig": {"enabled": False},
            "requireDisplayName": False,
            "enableWelcomePage": False,
            "disableDeepLinking": True,
            "hideConferenceSubject": True,
            "hideConferenceTimer": True,
            "toolbarButtons": [],
            "notifications": [],
        },
        "interface_config": {
            "DISABLE_JOIN_LEAVE_NOTIFICATIONS": True,
            "SHOW_JITSI_WATERMARK": False,
            "SHOW_WATERMARK_FOR_GUESTS": False,
            "SHOW_BRAND_WATERMARK": False,
            "SHOW_POWERED_BY": False,
            "TOOLBAR_ALWAYS_VISIBLE": False,
            "TOOLBAR_BUTTONS": [],
            "FILM_STRIP_MAX_HEIGHT": 0,
            "HIDE_INVITE_MORE_HEADER": True,
            "MOBILE_APP_PROMO": False,
            "APP_NAME": "Call",
            "PROVIDER_NAME": "Call",
        },
    }


def _finish_call(session, status: str, ended_by_user=None, display_status: str | None = None):
    """Mark session finished, post system message, broadcast."""
    from .models import CallSession, Message
    from .consumers import broadcast_message, broadcast_call_event

    if session.status in (
        CallSession.Status.ENDED,
        CallSession.Status.MISSED,
        CallSession.Status.DECLINED,
        CallSession.Status.NO_ANSWER,
    ):
        return session

    now = _tz.now()
    session.status = status
    session.ended_at = now
    if session.answered_at:
        session.duration_seconds = max(0, int((now - session.answered_at).total_seconds()))
    else:
        session.duration_seconds = 0
    session.save(update_fields=["status", "ended_at", "duration_seconds"])

    initiator_name = ""
    if session.initiator_id:
        initiator_name = getattr(session.initiator, "username", None) or f"User-{session.initiator_id}"

    shown = display_status or status
    payload = {
        "v": 1,
        "event": "ended",
        "call_id": str(session.public_id),
        "status": shown,
        "is_video": bool(session.is_video),
        "duration": session.duration_seconds,
        "initiator_id": session.initiator_id,
        "initiator_username": initiator_name,
    }
    msg = Message.objects.create(
        conversation_id=session.conversation_id,
        sender=session.initiator,
        body=_call_body(payload),
        is_system=True,
    )
    session.end_message = msg
    session.save(update_fields=["end_message"])
    try:
        broadcast_message(msg)
    except Exception:
        logger.exception("broadcast call end message failed")
    try:
        broadcast_call_event(session.conversation_id, {
            "type": "call.ended",
            "conversation_id": session.conversation_id,
            "call_id": str(session.public_id),
            "status": shown,
            "duration": session.duration_seconds,
            "is_video": bool(session.is_video),
            "user_id": getattr(ended_by_user, "id", None),
            "username": getattr(ended_by_user, "username", "") or "",
        })
    except Exception:
        logger.exception("broadcast call.ended failed")
    return session


class ConversationCallStartAPIView(APIView):
    """Start a call — creates DB session, system message, rings peers 30s.

    POST /conversations/<pk>/call/
    Body (optional): { "video": true|false, "audio": true|false }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import CallSession, Message
        from .consumers import broadcast_message, broadcast_call_event

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        video = bool(request.data.get("video", True))
        audio = bool(request.data.get("audio", True))

        # End any still-ringing/active session in this conversation first
        for old in CallSession.objects.filter(
            conversation=conv,
            status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE],
        ):
            _finish_call(old, CallSession.Status.ENDED, ended_by_user=request.user)

        room = f"messenger-{conv.public_id.hex}-{secrets.token_hex(4)}"
        session = CallSession.objects.create(
            conversation=conv,
            initiator=request.user,
            is_video=video,
            status=CallSession.Status.RINGING,
            room_name=room,
        )

        initiator_name = getattr(request.user, "username", "") or f"User-{request.user.id}"
        start_payload = {
            "v": 1,
            "event": "started",
            "call_id": str(session.public_id),
            "status": "ringing",
            "is_video": video,
            "initiator_id": request.user.id,
            "initiator_username": initiator_name,
        }
        start_msg = Message.objects.create(
            conversation=conv,
            sender=request.user,
            body=_call_body(start_payload),
            is_system=True,
        )
        session.start_message = start_msg
        session.save(update_fields=["start_message"])
        try:
            broadcast_message(start_msg)
        except Exception:
            logger.exception("broadcast call start message failed")

        cfg = _jitsi_config(request, conv, room_name=room)
        cfg["config"]["startWithVideoMuted"] = not video
        cfg["config"]["startWithAudioMuted"] = not audio
        cfg["media"] = {"video": video, "audio": audio}
        cfg["call_id"] = str(session.public_id)
        cfg["call_status"] = session.status
        cfg["ring_timeout"] = 30
        cfg["initiator"] = {
            "id": request.user.id,
            "username": initiator_name,
        }

        try:
            broadcast_call_event(conv.id, {
                "type": "call.started",
                "conversation_id": conv.id,
                "call_id": str(session.public_id),
                "room": cfg["room"],
                "domain": cfg["domain"],
                "join_url": cfg["join_url"],
                "media": cfg["media"],
                "is_video": video,
                "ring_timeout": 30,
                "initiator": cfg["initiator"],
            }, exclude_user_id=request.user.id)
        except Exception:
            logger.exception("broadcast_call_event failed")

        # Auto no-answer after 30s (Celery if available, else peers also timeout client-side)
        try:
            from .tasks import finalize_unanswered_call
            finalize_unanswered_call.apply_async(args=[str(session.public_id)], countdown=30)
        except Exception:
            logger.debug("celery schedule for call timeout skipped", exc_info=True)

        return ok("Call started", data=cfg)


class ConversationCallJoinAPIView(APIView):
    """Join an active/ringing call.

    GET /conversations/<pk>/call/join/?call_id=<uuid>
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .models import CallSession
        from .consumers import broadcast_call_event

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        call_id = request.query_params.get("call_id") or request.query_params.get("call")
        qs = CallSession.objects.filter(conversation=conv).order_by("-started_at")
        if call_id:
            session = qs.filter(public_id=call_id).first()
        else:
            session = qs.filter(
                status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE]
            ).first()

        if not session:
            return err("No active call", status.HTTP_404_NOT_FOUND)
        if session.status not in (CallSession.Status.RINGING, CallSession.Status.ACTIVE):
            return err("Call already ended", status.HTTP_409_CONFLICT)

        if session.status == CallSession.Status.RINGING:
            session.status = CallSession.Status.ACTIVE
            session.answered_at = _tz.now()
            session.save(update_fields=["status", "answered_at"])
            try:
                broadcast_call_event(conv.id, {
                    "type": "call.answered",
                    "conversation_id": conv.id,
                    "call_id": str(session.public_id),
                    "user_id": request.user.id,
                    "username": getattr(request.user, "username", "") or "",
                })
            except Exception:
                logger.exception("broadcast call.answered failed")

        cfg = _jitsi_config(request, conv, room_name=session.room_name or None)
        cfg["call_id"] = str(session.public_id)
        cfg["call_status"] = session.status
        cfg["media"] = {"video": bool(session.is_video), "audio": True}
        cfg["config"]["startWithVideoMuted"] = not bool(session.is_video)
        return ok(data=cfg)


class ConversationCallEndAPIView(APIView):
    """End / decline / leave a call.

    POST /conversations/<pk>/call/end/
    Body optional: { "call_id": "...", "reason": "ended"|"declined"|"no_answer" }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import CallSession

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        call_id = request.data.get("call_id")
        reason = (request.data.get("reason") or "ended").strip().lower()
        qs = CallSession.objects.filter(conversation=conv).order_by("-started_at")
        if call_id:
            session = qs.filter(public_id=call_id).first()
        else:
            session = qs.filter(
                status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE]
            ).first()

        if not session:
            # Still notify peers to stop ringing UI
            try:
                from .consumers import broadcast_call_event
                broadcast_call_event(conv.id, {
                    "type": "call.ended",
                    "conversation_id": conv.id,
                    "user_id": request.user.id,
                    "username": getattr(request.user, "username", "") or "",
                    "status": reason,
                })
            except Exception:
                pass
            return o
        status_map = {
            "declined": CallSession.Status.DECLINED,
            "no_answer": CallSession.Status.NO_ANSWER,
            "missed": CallSession.Status.MISSED,
            "ended": CallSession.Status.ENDED,
            "busy": CallSession.Status.DECLINED,
        }
        # Caller cancels while ringing → missed for callee
        if session.status == CallSession.Status.RINGING:
            if session.initiator_id == request.user.id:
                final = CallSession.Status.MISSED
            else:
                final = status_map.get(reason, CallSession.Status.DECLINED)
        else:
            final = status_map.get(reason, CallSession.Status.ENDED)

        _finish_call(
            session,
            final,
            ended_by_user=request.user,
            display_status="busy" if reason == "busy" else None,
        )
        return ok("Call ended", data={
            "call_id": str(session.public_id),
            "status": session.status,
            "duration": session.duration_seconds,
        })



class ConversationCallActiveAPIView(APIView):
    """Return the current ringing/active call for this conversation (if any).

    GET /conversations/<pk>/call/active/
    Used so a user who opens the chat (or comes online mid-ring) can join.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .models import CallSession
        from django.utils import timezone
        from datetime import timedelta

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        cutoff = timezone.now() - timedelta(seconds=40)
        session = (
            CallSession.objects.filter(
                conversation=conv,
                status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE],
                started_at__gte=cutoff,
            )
            .select_related("initiator")
            .order_by("-started_at")
            .first()
        )
        if not session:
            return ok(data={"active": False})

        initiator_name = ""
        if session.initiator_id:
            initiator_name = getattr(session.initiator, "username", None) or f"User-{session.initiator_id}"
        elapsed = int((timezone.now() - session.started_at).total_seconds())
        remaining = max(0, 30 - elapsed) if session.status == CallSession.Status.RINGING else None
        cfg = _jitsi_config(request, conv, room_name=session.room_name or None)
        return ok(data={
            "active": True,
            "call_id": str(session.public_id),
            "status": session.status,
            "is_video": bool(session.is_video),
            "media": {"video": bool(session.is_video), "audio": True},
            "room": session.room_name or cfg.get("room"),
            "domain": cfg.get("domain"),
            "join_url": cfg.get("join_url"),
            "ring_remaining": remaining,
            "initiator": {"id": session.initiator_id, "username": initiator_name},
            "started_at": session.started_at.isoformat(),
            "config": cfg.get("config"),
            "interface_config": cfg.get("interface_config"),
            "display_name": cfg.get("display_name"),
            "conversation_id": conv.id,
            "base_url": cfg.get("base_url"),
        })



class MessageSearchAPIView(APIView):
    """Search messages in a conversation (body contains query)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from django.db.models import Q
        conv = get_object_or_404(Conversation, pk=pk)
        part = conv.participants.filter(user=request.user, left_at__isnull=True).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return ok(data={"results": [], "count": 0})
        qs = Message.objects.filter(
            conversation=conv, is_deleted=False, is_scheduled=False, is_system=False
        ).filter(body__icontains=q).select_related("sender").order_by("-created_at")
        if conv.type == Conversation.Type.GROUP and part.role not in ("owner", "admin"):
            visibility = getattr(conv, "history_visibility", "all") or "all"
            if visibility in ("none", "from_join") and part.joined_at:
                qs = qs.filter(created_at__gte=part.joined_at)
        limit = min(50, int(request.query_params.get("limit") or 30))
        items = list(qs[:limit])
        ctx = build_message_list_context(request, items, conversation_id=conv.id)
        return ok(data={
            "results": MessageSerializer(items, many=True, context=ctx).data,
            "count": len(items),
        })


class ScheduledMessageCancelAPIView(APIView):
    """Cancel a pending scheduled message (sender only). Soft-deletes so it never delivers."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk)
        if msg.sender_id != request.user.id:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if not msg.is_scheduled:
            return err("Message is not scheduled")
        msg.is_deleted = True
        msg.is_scheduled = False
        msg.body = ""
        msg.save(update_fields=["is_deleted", "is_scheduled", "body", "updated_at"])
        try:
            from .signals import soft_delete_message_side_effects
            soft_delete_message_side_effects(msg)
        except Exception:
            logger.exception("cancel-schedule cleanup failed for %s", msg.pk)
        return ok("Scheduled message cancelled", data={"id": msg.id})


class ScheduledMessageListAPIView(APIView):
    """List pending scheduled messages for a conversation (sender only)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = conv.participants.filter(user=request.user, left_at__isnull=True).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        qs = (
            Message.objects.filter(
                conversation=conv, sender=request.user, is_scheduled=True, is_deleted=False
            )
            .select_related("sender")
            .prefetch_related("attachments")
            .order_by("scheduled_for")
        )
        ctx = build_message_list_context(request, list(qs), conversation_id=conv.id)
        return ok(data=MessageSerializer(qs, many=True, context=ctx).data)
