"""
Messenger REST API — infinite-scroll friendly.
"""
from __future__ import annotations

import logging
from django.contrib.auth import get_user_model
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
    ProfilePhotoPrivacy, ProfilePhotoAllowed,
)
from .serializers import (
    UserMiniSerializer, MessageSerializer, ConversationListSerializer,
    ConversationDetailSerializer, ContactSerializer,
    GroupInviteLinkSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer,
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
            .order_by("-last_message_at", "-created_at")
        )
        page = int(request.query_params.get("page") or 1)
        page_size = min(50, int(request.query_params.get("page_size") or 30))
        start = (page - 1) * page_size
        end = start + page_size
        total = qs.count()
        items = qs[start:end]
        ser = ConversationListSerializer(items, many=True, context={"request": request})
        return ok(data={
            "results": ser.data,
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
                defaults={"role": ConversationParticipant.Role.MEMBER},
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
        conv.save()
        return ok(data=ConversationDetailSerializer(conv, context={"request": request}).data)


class PublicGroupSearchAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        qs = Conversation.objects.filter(type=Conversation.Type.GROUP, is_public=True, is_closed=False)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        qs = qs.order_by("-last_message_at")[:50]
        return ok(data=ConversationListSerializer(qs, many=True, context={"request": request}).data)


class MessageListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_participant(self, conv, user):
        return conv.participants.filter(user=user, left_at__isnull=True).first()

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        if not self.get_participant(conv, request.user):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        qs = (
            Message.objects.filter(conversation=conv, is_deleted=False)
            .select_related("sender", "reply_to", "reply_to__sender", "forwarded_from")
            .prefetch_related("attachments", "reactions__user")
            .order_by("-created_at")
        )
        before_id = request.query_params.get("before_id")
        if before_id:
            try:
                qs = qs.filter(id__lt=int(before_id))
            except ValueError:
                pass
        limit = min(50, int(request.query_params.get("limit") or 40))
        items = list(qs[: limit + 1])
        has_more = len(items) > limit
        items = items[:limit]
        items.reverse()
        ser = MessageSerializer(items, many=True, context={"request": request})
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

        raw_body = request.data.get("body")
        if isinstance(raw_body, (list, tuple)):
            raw_body = raw_body[0] if raw_body else ""
        if not isinstance(raw_body, str):
            raw_body = "" if raw_body is None else str(raw_body)
        body = raw_body.strip()[:10000]

        reply_to_id = request.data.get("reply_to")
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(pk=reply_to_id, conversation=conv).first()

        files = request.FILES.getlist("files") or request.FILES.getlist("file") or []
        if not body and not files:
            return err("Message body or attachment required")

        if files and not part.can_send_media:
            return err("You cannot send media")

        msg = Message.objects.create(
            conversation=conv,
            sender=request.user,
            body=body,
            reply_to=reply_to,
        )

        for f in files[:10]:
            try:
                validate_messenger_file(f)
            except Exception:
                continue
            kind = detect_kind(f.name, getattr(f, "content_type", "") or "")
            MessageAttachment.objects.create(
                conversation=conv,
                message=msg,
                uploaded_by=request.user,
                file=f,
                original_filename=getattr(f, "name", "file")[:255],
                content_type=getattr(f, "content_type", "") or "",
                size=getattr(f, "size", 0) or 0,
                kind=kind,
            )

        try:
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            logger.exception("broadcast failed")

        msg = (
            Message.objects.filter(pk=msg.pk)
            .select_related("sender", "reply_to", "reply_to__sender")
            .prefetch_related("attachments", "reactions")
            .first()
        )
        return ok(
            "Sent",
            data=MessageSerializer(msg, context={"request": request}).data,
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
        try:
            from .consumers import broadcast_message
            # reuse broadcast with type override via fresh payload
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
        msg.body = ""
        msg.save(update_fields=["is_deleted", "body", "updated_at"])
        return ok("Deleted")


class MarkReadAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        part.last_read_at = timezone.now()
        part.save(update_fields=["last_read_at"])
        return ok("Read")



class LeaveConversationAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Not a member", status.HTTP_404_NOT_FOUND)
        if part.role == ConversationParticipant.Role.OWNER:
            # transfer or require delete — for now block leave if sole owner of group
            others = ConversationParticipant.objects.filter(
                conversation_id=pk, left_at__isnull=True
            ).exclude(user=request.user).count()
            conv = part.conversation
            if conv.type == Conversation.Type.GROUP and others == 0:
                return err("Transfer ownership or delete the group first")
        part.left_at = timezone.now()
        part.save(update_fields=["left_at"])
        return ok("Left")



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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        link = get_object_or_404(GroupInviteLink, code=code)
        if not link.is_valid():
            return err("Invite link is invalid or expired")
        conv = link.conversation
        if conv.is_closed:
            return err("Group is closed")
        part, created = ConversationParticipant.objects.get_or_create(
            conversation=conv,
            user=request.user,
            defaults={"role": ConversationParticipant.Role.MEMBER},
        )
        if not created and part.left_at:
            part.left_at = None
            part.save(update_fields=["left_at"])
        link.uses += 1
        link.save(update_fields=["uses"])
        return ok(
            "Joined",
            data=ConversationDetailSerializer(conv, context={"request": request}).data,
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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        att = get_object_or_404(MessageAttachment, pk=pk)
        if not ConversationParticipant.objects.filter(
            conversation=att.conversation, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        from django.http import FileResponse
        return FileResponse(att.file.open("rb"), as_attachment=True, filename=att.original_filename)
