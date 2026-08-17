"""Messenger API — calls."""
from __future__ import annotations

import json as _json
import secrets
import logging
import mimetypes
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone as _tz
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
    from ..models import CallSession, Message
    from ..consumers import broadcast_message, broadcast_call_event

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
    # Keep Redis/message cache in sync so hang-up / missed / declined
    # system messages appear immediately on next fetch.
    try:
        from ..message_cache import schedule_add_message
        schedule_add_message(msg)
    except Exception:
        logger.exception("schedule_add_message for call end failed")
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
        from ..models import CallSession, Message
        from ..consumers import broadcast_message, broadcast_call_event

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        video = bool(request.data.get("video", True))
        audio = bool(request.data.get("audio", True))

        # Serialize call creation per conversation. A stale ringing session is
        # terminal after the ring window, while an active call remains active
        # until an explicit hang-up/end arrives.
        with transaction.atomic():
            locked = list(
                CallSession.objects.select_for_update()
                .filter(
                    conversation=conv,
                    status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE],
                )
                .order_by("started_at")
            )
            now = _tz.now()
            for old in locked:
                if old.status == CallSession.Status.RINGING and old.started_at:
                    age = (now - old.started_at).total_seconds()
                    if age >= 30:
                        _finish_call(old, CallSession.Status.NO_ANSWER, ended_by_user=request.user)
                        continue
                return err("Call already in progress", status.HTTP_409_CONFLICT)

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
            from ..message_cache import schedule_add_message
            schedule_add_message(start_msg)
        except Exception:
            logger.exception("schedule_add_message for call start failed")
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
            from ..tasks import finalize_unanswered_call
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
        from ..models import CallSession
        from ..consumers import broadcast_call_event

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        call_id = request.query_params.get("call_id") or request.query_params.get("call")
        with transaction.atomic():
            qs = CallSession.objects.select_for_update().filter(conversation=conv).order_by("-started_at")
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
        from ..models import CallSession

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        call_id = request.data.get("call_id")
        reason = (request.data.get("reason") or "ended").strip().lower()
        status_map = {
            "declined": CallSession.Status.DECLINED,
            "no_answer": CallSession.Status.NO_ANSWER,
            "missed": CallSession.Status.MISSED,
            "ended": CallSession.Status.ENDED,
            "busy": CallSession.Status.DECLINED,
        }

        with transaction.atomic():
            qs = CallSession.objects.select_for_update().filter(conversation=conv).order_by("-started_at")
            if call_id:
                session = qs.filter(public_id=call_id).first()
            else:
                session = qs.filter(
                    status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE]
                ).first()

            if not session:
                # Still notify peers to stop ringing UI. This is idempotent: the
                # caller may have already finalized the session on another device.
                try:
                    from ..consumers import broadcast_call_event
                    broadcast_call_event(conv.id, {
                        "type": "call.ended",
                        "conversation_id": conv.id,
                        "user_id": request.user.id,
                        "username": getattr(request.user, "username", "") or "",
                        "status": reason,
                    })
                except Exception:
                    logger.exception("broadcast idempotent call.ended failed")
                return ok("Call already ended", data={"active": False})

            if session.status not in (CallSession.Status.RINGING, CallSession.Status.ACTIVE):
                return ok("Call already ended", data={
                    "active": False,
                    "call_id": str(session.public_id),
                    "status": session.status,
                })

            # Caller cancels while ringing → missed for callee.
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
        from ..models import CallSession
        from datetime import timedelta

        conv = get_object_or_404(Conversation, pk=pk)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        cutoff = _tz.now() - timedelta(seconds=30)
        # Self-heal abandoned ringing sessions when Celery/websocket delivery
        # was interrupted. This makes the server authoritative for call state.
        stale_ringing = (
            CallSession.objects.filter(
                conversation=conv,
                status=CallSession.Status.RINGING,
                started_at__lt=cutoff,
            )
            .order_by("started_at")
        )
        for stale in stale_ringing[:20]:
            try:
                with transaction.atomic():
                    locked = CallSession.objects.select_for_update().get(pk=stale.pk)
                    if locked.status == CallSession.Status.RINGING and locked.started_at < cutoff:
                        _finish_call(locked, CallSession.Status.NO_ANSWER, ended_by_user=locked.initiator)
            except Exception:
                logger.exception("stale ringing call cleanup failed for %s", stale.public_id)

        session = (
            CallSession.objects.filter(
                conversation=conv,
                status__in=[CallSession.Status.RINGING, CallSession.Status.ACTIVE],
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
        elapsed = int((_tz.now() - session.started_at).total_seconds())
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




