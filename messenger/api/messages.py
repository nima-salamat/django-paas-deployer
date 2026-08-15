"""Messenger API — messages."""
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

from ..models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, MessageReadReceipt, UserBio,
    JoinRequest, PinnedMessage, CallSession,
)
from ..serializers import (
    UserMiniSerializer, MessageSerializer, ConversationListSerializer,
    ConversationDetailSerializer, ContactSerializer,
    GroupInviteLinkSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer,
    build_message_list_context, build_user_mini_context,
)
from ..utils import validate_messenger_file, detect_kind, users_blocked, can_see_profile_photo
from .common import ok, err, _attach_list_side_data, get_or_create_dm, logger

User = get_user_model()
class MessageListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_participant(self, conv, user):
        return conv.participants.filter(user=user, left_at__isnull=True).first()

    def get(self, request, pk):
        # Scheduled delivery is Celery-only on the hot path (see beat schedule).
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

        history_restricted = False
        if conv.type == Conversation.Type.GROUP and part.role not in ("owner", "admin"):
            visibility = getattr(conv, "history_visibility", "all") or "all"
            if visibility in ("none", "from_join") and part.joined_at:
                history_restricted = True

        # ------------------------------------------------------------------
        # Hot-cache path (latest N messages in Redis, per conversation)
        # ------------------------------------------------------------------
        if not history_restricted:
            try:
                from ..message_cache import MessageCacheService
                cached = MessageCacheService.get_cached_messages(
                    conv.id, before_id, limit
                )
                if cached is not None:
                    base_msgs, has_more, next_before = cached
                    results = MessageCacheService.enrich_for_viewer(
                        base_msgs, request, conv.id
                    )
                    resp = ok(data={
                        "results": results,
                        "has_more": has_more,
                        "next_before_id": next_before,
                        "cache": "HIT",
                    })
                    try:
                        resp.headers["X-Messenger-Cache"] = "HIT"
                    except Exception:
                        pass
                    return resp
            except Exception:
                logger.exception("message cache read failed; falling back to DB")

        # ------------------------------------------------------------------
        # Postgres path (source of truth)
        # ------------------------------------------------------------------
        from django.db.models import Q
        qs = (
            Message.objects.filter(conversation=conv, is_deleted=False)
            .filter(Q(is_scheduled=False) | Q(is_scheduled=True, sender=request.user))
            .select_related("sender", "reply_to", "reply_to__sender", "forwarded_from")
            .prefetch_related("attachments", "reactions")
            .order_by("-id")  # id is monotonic with created_at and matches cache scores
        )
        if history_restricted:
            qs = qs.filter(created_at__gte=part.joined_at)
        if before_id is not None:
            qs = qs.filter(id__lt=before_id)
        items = list(qs[: limit + 1])
        has_more = len(items) > limit
        items = items[:limit]
        items.reverse()

        # Populate Redis in background so this response is not delayed.
        if not history_restricted and before_id is None and items:
            try:
                from ..message_cache import MessageCacheService, run_after_commit
                conv_id = conv.id
                # Seed with the page we already loaded (instant), then full rebuild.
                try:
                    MessageCacheService.cache_messages(conv_id, items)
                except Exception:
                    logger.exception("seed message cache failed")
                run_after_commit(lambda: MessageCacheService.rebuild_chat_cache(conv_id))
            except Exception:
                logger.exception("message cache populate schedule failed")

        ctx = build_message_list_context(request, items, conversation_id=conv.id)
        ser = MessageSerializer(items, many=True, context=ctx)
        next_before = items[0].id if has_more and items else None
        resp = ok(data={
            "results": ser.data,
            "has_more": has_more,
            "next_before_id": next_before,
            "cache": "MISS",
        })
        try:
            resp.headers["X-Messenger-Cache"] = "MISS"
        except Exception:
            pass
        return resp

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
                    from ..message_cache import schedule_add_message
                    schedule_add_message(msg)
                except Exception:
                    logger.exception("message cache schedule add failed")
                try:
                    from ..consumers import broadcast_message
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
            from ..message_cache import schedule_add_message
            schedule_add_message(new_msg)
        except Exception:
            logger.exception("message cache schedule add (forward) failed")
        try:
            from ..consumers import broadcast_message
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
            from ..message_cache import schedule_update_message
            schedule_update_message(msg)
        except Exception:
            logger.exception("message cache schedule update (reaction) failed")
        try:
            from ..consumers import broadcast_reaction
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
            from ..message_cache import schedule_update_message
            schedule_update_message(msg)
        except Exception:
            logger.exception("message cache schedule update (edit) failed")
        try:
            from ..consumers import _send
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
            from ..signals import soft_delete_message_side_effects
            soft_delete_message_side_effects(msg)
        except Exception:
            PinnedMessage.objects.filter(message=msg).delete()
        # Remove from hot-cache after successful soft-delete (non-blocking)
        try:
            from ..message_cache import schedule_delete_message
            schedule_delete_message(msg.conversation_id, msg.id)
        except Exception:
            logger.exception("message cache schedule delete failed")
        try:
            from ..consumers import _send
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
                from ..consumers import broadcast_read
                broadcast_read(pk, request.user.id, new_receipts)
            except Exception:
                logger.exception("broadcast_read failed")
        return ok("Read", data={"receipts": len(new_receipts)})




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
            from ..signals import soft_delete_message_side_effects
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

