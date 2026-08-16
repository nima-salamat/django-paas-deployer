"""Messenger API — members."""
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


def _schedule_member_cache(conv_id, extra_user_ids=None, system_msg=None):
    """Fire-and-forget membership cache sync (Celery after commit)."""
    try:
        from ..message_cache import schedule_membership_cache_sync
        mid = getattr(system_msg, "id", None) if system_msg is not None else None
        schedule_membership_cache_sync(conv_id, extra_user_ids=extra_user_ids, system_msg_id=mid)
    except Exception:
        pass


User = get_user_model()
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
                        from ..consumers import broadcast_member_change
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
                from ..consumers import broadcast_message
                broadcast_message(msg)
                try:
                    from ..message_cache import schedule_add_message
                    schedule_add_message(msg)
                except Exception:
                    pass
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
                    from ..consumers import broadcast_message
                    broadcast_message(msg)
                except Exception:
                    pass
            # Broadcast member change so other clients reload
            try:
                from ..consumers import broadcast_member_change
                broadcast_member_change(pk, {
                    "type": "member.left",
                    "conversation_id": pk,
                    "user_id": request.user.id,
                    "transferred_to": transferred_to,
                })
            except Exception:
                pass
            _schedule_member_cache(pk, extra_user_ids=[request.user.id])
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
            from ..consumers import broadcast_message
            broadcast_message(msg)
            try:
                from ..message_cache import schedule_add_message
                schedule_add_message(msg)
            except Exception:
                pass
        except Exception:
            pass
        # Broadcast so other clients reload the member list
        try:
            from ..consumers import broadcast_member_change
            broadcast_member_change(pk, {
                "type": "member.removed",
                "conversation_id": pk,
                "user_id": user_id,
            })
        except Exception:
            pass
        _schedule_member_cache(pk, extra_user_ids=[user_id])
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
            from ..consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        try:
            from ..consumers import broadcast_member_change
            broadcast_member_change(pk, {
                "type": "member.role_changed",
                "conversation_id": pk,
                "user_id": user_id,
                "role": new_role,
            })
        except Exception:
            pass
            _schedule_member_cache(pk)
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
            from ..consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            pass
        try:
            from ..consumers import broadcast_member_change
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
                from ..consumers import broadcast_message, broadcast_member_change
                broadcast_message(msg)
                broadcast_member_change(pk, {
                    "type": "member.joined",
                    "conversation_id": pk,
                    "user_id": u.id,
                })
            except Exception:
                pass
            try:
                from ..message_cache import schedule_add_message
                schedule_add_message(msg)
            except Exception:
                pass
        if added:
            _schedule_member_cache(pk, extra_user_ids=[u.id for u in added])
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



