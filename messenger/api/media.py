"""Messenger API — media."""
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
        from ..models import MessageAttachment
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
        from ..models import PinnedMessage
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
            from ..consumers import broadcast_member_change
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
        from ..serializers import MessageAttachmentSerializer
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



