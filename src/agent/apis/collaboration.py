"""Scope-protected Agent facade for ordinary Messenger chats and Tickets.

The facade deliberately delegates to the existing application views after
Agent authentication/scope checks. This keeps tenant permissions, rate limits,
sanitizers, cache invalidation, event fan-out and E2EE transport guards in one
place instead of reimplementing them in the Agent API.
"""
from __future__ import annotations

from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from rest_framework import status
from rest_framework.response import Response

from .base import AgentSecuredAPIView, idempotent


def _call_messenger(view_name: str, method: str, request, *args):
    from messenger import api as messenger_api

    view = getattr(messenger_api, view_name)()
    return getattr(view, method)(request, *args)


def _call_ticket(module_name: str, view_name: str, method: str, request, *args):
    module = __import__(module_name, fromlist=[view_name])
    view = getattr(module, view_name)()
    return getattr(view, method)(request, *args)


def _agent_error(code: str, detail: str, http_status: int):
    return Response(
        {"result": "error", "code": code, "detail": detail},
        status=http_status,
    )


def _standard_conversation(request, conversation_id, *, require_member=True):
    """Resolve only standard chats; encrypted rooms are never read via Django."""
    from messenger.models import Conversation, ConversationParticipant

    conv = Conversation.objects.filter(pk=conversation_id).first()
    if conv is None:
        return None, None, _agent_error(
            "RESOURCE_NOT_FOUND", "Conversation not found.", status.HTTP_404_NOT_FOUND
        )
    if conv.security_mode != Conversation.SecurityMode.STANDARD:
        return None, None, _agent_error(
            "UNSUPPORTED_SECURITY_MODE",
            "Agent Messenger supports standard chats only. End-to-end encrypted conversations are not accessible.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    participant = None
    if require_member:
        participant = ConversationParticipant.objects.filter(
            conversation=conv,
            user=request.user,
            left_at__isnull=True,
        ).first()
        if participant is None:
            return None, None, _agent_error(
                "PERMISSION_DENIED",
                "The account linked to this Agent is not an active participant in this conversation.",
                status.HTTP_403_FORBIDDEN,
            )
    return conv, participant, None


def _owned_ticket(request, ticket_id):
    from tickets.models import Ticket

    ticket = (
        Ticket.objects.select_related("department", "user", "assigned_to", "service", "deploy")
        .filter(pk=ticket_id, user=request.user)
        .first()
    )
    if ticket is None:
        return None, _agent_error(
            "RESOURCE_NOT_FOUND",
            "Ticket not found for the account linked to this Agent.",
            status.HTTP_404_NOT_FOUND,
        )
    return ticket, None


class AgentMessengerView(AgentSecuredAPIView):
    audit_resource_type = "messenger"


class AgentTicketView(AgentSecuredAPIView):
    audit_resource_type = "ticket"


# ---------------------------------------------------------------------------
# Messenger discovery and account-level operations
# ---------------------------------------------------------------------------

class AgentMessengerUserSearchView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/users/search"
    audit_action = "agent.messenger.users.search"

    def get(self, request):
        return _call_messenger("UserSearchAPIView", "get", request)


class AgentMessengerContactsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/contacts"
    audit_action = "agent.messenger.contacts"
    audit_mutating = True

    def get(self, request):
        self.audit_mutating = False
        return _call_messenger("ContactListCreateAPIView", "get", request)

    @idempotent
    def post(self, request):
        self.audit_mutating = True
        return _call_messenger("ContactListCreateAPIView", "post", request)


class AgentMessengerContactDetailView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/contacts/{user_id}"
    audit_action = "agent.messenger.contacts.delete"
    audit_mutating = True

    @idempotent
    def delete(self, request, user_id):
        return _call_messenger("ContactDeleteAPIView", "delete", request, user_id)


class AgentMessengerBlocksView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/blocks"
    audit_action = "agent.messenger.blocks"
    audit_mutating = True

    def get(self, request):
        self.audit_mutating = False
        return _call_messenger("BlockListCreateAPIView", "get", request)

    @idempotent
    def post(self, request):
        self.audit_mutating = True
        return _call_messenger("BlockListCreateAPIView", "post", request)


class AgentMessengerBlockDetailView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/blocks/{user_id}"
    audit_action = "agent.messenger.blocks.unblock"
    audit_mutating = True

    @idempotent
    def delete(self, request, user_id):
        # The application endpoint uses POST for unblock; the Agent surface
        # uses DELETE to express the resource operation.
        return _call_messenger("UnblockAPIView", "post", request, user_id)


# ---------------------------------------------------------------------------
# Conversations, messages, formatting, reactions and scheduled delivery
# ---------------------------------------------------------------------------

class AgentMessengerConversationsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations"
    audit_action = "agent.messenger.conversations"
    audit_mutating = True

    def get(self, request):
        self.audit_mutating = False
        from messenger.models import (
            Conversation,
            ConversationParticipant,
            Message,
        )

        page = max(1, min(100000, int(request.query_params.get("page") or 1)))
        page_size = max(1, min(50, int(request.query_params.get("page_size") or 20)))
        latest_body = (
            Message.objects.filter(
                conversation_id=OuterRef("pk"),
                is_deleted=False,
                is_scheduled=False,
            )
            .order_by("-id")
            .values("body")[:1]
        )
        latest_created = (
            Message.objects.filter(
                conversation_id=OuterRef("pk"),
                is_deleted=False,
                is_scheduled=False,
            )
            .order_by("-id")
            .values("created_at")[:1]
        )
        queryset = (
            Conversation.objects.filter(
                parent_conversation__isnull=True,
                security_mode=Conversation.SecurityMode.STANDARD,
                participants__user=request.user,
                participants__left_at__isnull=True,
            )
            .distinct()
            .annotate(
                active_member_count=Count(
                    "participants",
                    filter=Q(participants__left_at__isnull=True),
                    distinct=True,
                ),
                last_message_preview=Subquery(latest_body),
                last_message_created_at=Subquery(latest_created),
            )
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=ConversationParticipant.objects.filter(
                        left_at__isnull=True
                    ).select_related("user"),
                    to_attr="_agent_active_participants",
                )
            )
            .order_by("-last_message_at", "-created_at")
        )
        total = queryset.count()
        rows = []
        for conv in queryset[(page - 1) * page_size : page * page_size]:
            parts = getattr(conv, "_agent_active_participants", [])
            me = next((p for p in parts if p.user_id == request.user.id), None)
            other = next(
                (p.user for p in parts if p.user_id != request.user.id), None
            ) if conv.type == Conversation.Type.PRIVATE else None
            title = conv.title
            if conv.type == Conversation.Type.PRIVATE:
                title = (
                    getattr(other, "get_full_name", lambda: "")()
                    or getattr(other, "username", "")
                    or "Private conversation"
                )
            rows.append(
                {
                    "id": conv.pk,
                    "public_id": str(conv.public_id),
                    "type": conv.type,
                    "title": title,
                    "description": conv.description if conv.type == Conversation.Type.GROUP else "",
                    "is_public": bool(conv.is_public),
                    "is_closed": bool(conv.is_closed),
                    "requires_approval": bool(conv.requires_approval),
                    "only_admins_send": bool(conv.only_admins_send),
                    "history_visibility": conv.history_visibility,
                    "member_count": conv.active_member_count,
                    "my_role": getattr(me, "role", None),
                    "last_message_at": (
                        conv.last_message_created_at.isoformat()
                        if conv.last_message_created_at
                        else None
                    ),
                    "last_message_preview": (conv.last_message_preview or "")[:160],
                }
            )
        return Response(
            {
                "results": rows,
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": page * page_size < total,
                "security_mode": "standard",
            }
        )

    @idempotent
    def post(self, request):
        self.audit_mutating = True
        from messenger.models import Conversation

        requested_mode = str(request.data.get("security_mode") or "standard").lower()
        if requested_mode != Conversation.SecurityMode.STANDARD:
            return _agent_error(
                "UNSUPPORTED_SECURITY_MODE",
                "Agent can create standard chats only; encrypted chat creation is not supported.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        member_ids = request.data.get("member_ids") or []
        if member_ids and "messenger.members.manage" not in set(request.agent.scopes or []):
            return _agent_error(
                "INSUFFICIENT_SCOPE",
                "Adding members while creating a group requires the messenger.members.manage scope.",
                status.HTTP_403_FORBIDDEN,
            )
        return _call_messenger("ConversationListCreateAPIView", "post", request)


class AgentMessengerConversationDetailView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}"
    audit_action = "agent.messenger.conversation"
    audit_mutating = True

    def get(self, request, conversation_id):
        self.audit_mutating = False
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "ConversationDetailAPIView", "get", request, conversation_id
        )

    @idempotent
    def patch(self, request, conversation_id):
        self.audit_mutating = True
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "ConversationDetailAPIView", "patch", request, conversation_id
        )

    @idempotent
    def delete(self, request, conversation_id):
        self.audit_mutating = True
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "DeleteConversationAPIView", "delete", request, conversation_id
        )


class AgentMessengerMessagesView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/messages"
    audit_action = "agent.messenger.messages"
    audit_mutating = True

    def get(self, request, conversation_id):
        self.audit_mutating = False
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "MessageListCreateAPIView", "get", request, conversation_id
        )

    @idempotent
    def post(self, request, conversation_id):
        self.audit_mutating = True
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        if (request.data.get("scheduled_for") or request.data.get("schedule_at")) and "messenger.messages.schedule" not in set(request.agent.scopes or []):
            return _agent_error(
                "INSUFFICIENT_SCOPE",
                "Scheduling messages requires the messenger.messages.schedule scope.",
                status.HTTP_403_FORBIDDEN,
            )
        return _call_messenger(
            "MessageListCreateAPIView", "post", request, conversation_id
        )


class AgentMessengerMessageSearchView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/messages/search"
    audit_action = "agent.messenger.messages.search"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "MessageSearchAPIView", "get", request, conversation_id
        )


class AgentMessengerScheduledMessagesView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/scheduled"
    audit_action = "agent.messenger.messages.scheduled"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "ScheduledMessageListAPIView", "get", request, conversation_id
        )


class AgentMessengerMarkReadView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/read"
    audit_action = "agent.messenger.messages.read_state"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger("MarkReadAPIView", "post", request, conversation_id)


class AgentMessengerMessageReactView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/messages/{message_id}/react"
    audit_action = "agent.messenger.messages.react"
    audit_mutating = True

    @idempotent
    def post(self, request, message_id):
        from messenger.models import Message

        msg = (
            Message.objects.select_related("conversation")
            .filter(pk=message_id, is_deleted=False)
            .first()
        )
        if msg is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Message not found.", 404)
        _, _, error = _standard_conversation(
            request, msg.conversation_id
        )
        if error:
            return error
        return _call_messenger("MessageReactAPIView", "post", request, message_id)


class AgentMessengerMessageEditView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/messages/{message_id}/edit"
    audit_action = "agent.messenger.messages.edit"
    audit_mutating = True

    @idempotent
    def patch(self, request, message_id):
        from messenger.models import Message

        msg = Message.objects.filter(pk=message_id, is_deleted=False).first()
        if msg is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Message not found.", 404)
        _, _, error = _standard_conversation(request, msg.conversation_id)
        if error:
            return error
        return _call_messenger("MessageEditAPIView", "patch", request, message_id)


class AgentMessengerMessageDeleteView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/messages/{message_id}"
    audit_action = "agent.messenger.messages.delete"
    audit_mutating = True

    @idempotent
    def delete(self, request, message_id):
        from messenger.models import Message

        msg = Message.objects.filter(pk=message_id, is_deleted=False).first()
        if msg is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Message not found.", 404)
        _, _, error = _standard_conversation(request, msg.conversation_id)
        if error:
            return error
        return _call_messenger("MessageDeleteAPIView", "delete", request, message_id)


class AgentMessengerScheduledMessageCancelView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/messages/{message_id}/cancel-schedule"
    audit_action = "agent.messenger.messages.schedule.cancel"
    audit_mutating = True

    @idempotent
    def post(self, request, message_id):
        from messenger.models import Message

        msg = Message.objects.filter(pk=message_id, is_deleted=False).first()
        if msg is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Scheduled message not found.", 404)
        _, _, error = _standard_conversation(request, msg.conversation_id)
        if error:
            return error
        if msg.sender_id != request.user.id:
            return _agent_error(
                "PERMISSION_DENIED",
                "Only the message sender may cancel a scheduled message.",
                status.HTTP_403_FORBIDDEN,
            )
        return _call_messenger(
            "ScheduledMessageCancelAPIView", "post", request, message_id
        )


# ---------------------------------------------------------------------------
# Public groups, join requests, membership and per-member permissions
# ---------------------------------------------------------------------------

class AgentMessengerGroupSearchView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/groups/search"
    audit_action = "agent.messenger.groups.search"

    def get(self, request):
        return _call_messenger("PublicGroupSearchAPIView", "get", request)


class AgentMessengerGroupJoinView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/groups/{conversation_id}/join"
    audit_action = "agent.messenger.groups.join"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(
            request, conversation_id, require_member=False
        )
        if error:
            return error
        from messenger.models import Conversation

        conv = Conversation.objects.filter(
            pk=conversation_id,
            type=Conversation.Type.GROUP,
            is_public=True,
            is_closed=False,
        ).first()
        if conv is None:
            return _agent_error(
                "RESOURCE_NOT_FOUND", "Open public group not found.", 404
            )
        return _call_messenger("PublicGroupJoinAPIView", "post", request, conversation_id)


class AgentMessengerParticipantsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/participants"
    audit_action = "agent.messenger.groups.participants.read"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "GroupParticipantsListAPIView", "get", request, conversation_id
        )


class AgentMessengerMembersView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/members"
    audit_action = "agent.messenger.groups.members"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger("AddMembersAPIView", "post", request, conversation_id)


class AgentMessengerMemberDetailView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/members/{user_id}"
    audit_action = "agent.messenger.groups.members.remove"
    audit_mutating = True

    @idempotent
    def delete(self, request, conversation_id, user_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "RemoveMemberAPIView", "delete", request, conversation_id, user_id
        )


class AgentMessengerMemberRoleView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/members/{user_id}/role"
    audit_action = "agent.messenger.groups.members.role"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id, user_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "MemberRoleAPIView", "post", request, conversation_id, user_id
        )


class AgentMessengerMemberPermissionsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/members/{user_id}/permissions"
    audit_action = "agent.messenger.groups.members.permissions"
    audit_mutating = True

    @idempotent
    def patch(self, request, conversation_id, user_id):
        from messenger.models import Conversation, ConversationParticipant

        conv, actor, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        if conv.type != Conversation.Type.GROUP:
            return _agent_error(
                "INVALID_RESOURCE_TYPE", "Member permissions apply to group chats only.", 400
            )
        if actor.role not in (
            ConversationParticipant.Role.OWNER,
            ConversationParticipant.Role.ADMIN,
        ):
            return _agent_error(
                "PERMISSION_DENIED", "Only a group owner or admin can update member permissions.", 403
            )
        target = ConversationParticipant.objects.filter(
            conversation=conv,
            user_id=user_id,
            left_at__isnull=True,
        ).select_related("user").first()
        if target is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Active group member not found.", 404)
        if target.role in (
            ConversationParticipant.Role.OWNER,
            ConversationParticipant.Role.ADMIN,
        ):
            if actor.role != ConversationParticipant.Role.OWNER:
                return _agent_error(
                    "PERMISSION_DENIED", "An admin cannot change another owner's or admin's permissions.", 403
                )
            if target.role == ConversationParticipant.Role.OWNER:
                return _agent_error(
                    "PERMISSION_DENIED", "The group owner's permissions are immutable here.", 403
                )

        fields = {
            "can_send_messages",
            "can_send_media",
            "can_add_members",
            "can_pin_messages",
            "can_change_info",
            "is_muted",
        }
        supplied = set(request.data.keys())
        if not supplied or not supplied.issubset(fields):
            return _agent_error(
                "INVALID_REQUEST",
                "Supply one or more of: " + ", ".join(sorted(fields)) + ".",
                400,
            )
        if actor.role == ConversationParticipant.Role.ADMIN:
            elevated = supplied & {"can_add_members", "can_change_info"}
            if elevated:
                return _agent_error(
                    "PERMISSION_DENIED",
                    "Only the group owner can change member-management permissions.",
                    403,
                )
        for key in supplied:
            if not isinstance(request.data[key], bool):
                return _agent_error(
                    "INVALID_REQUEST", f"{key} must be a JSON boolean.", 400
                )
            setattr(target, key, request.data[key])
        target.save(update_fields=sorted(supplied))
        return Response(
            {
                "result": "success",
                "conversation_id": conv.pk,
                "user_id": target.user_id,
                "role": target.role,
                "permissions": {key: getattr(target, key) for key in sorted(fields)},
            }
        )


class AgentMessengerJoinRequestsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/join-requests"
    audit_action = "agent.messenger.groups.join_requests.read"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "JoinRequestListAPIView", "get", request, conversation_id
        )


class AgentMessengerJoinRequestActionView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/join-requests/{request_id}/action"
    audit_action = "agent.messenger.groups.join_requests.action"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id, request_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "JoinRequestActionAPIView", "post", request, conversation_id, request_id
        )


# ---------------------------------------------------------------------------
# Invite links, caller-owned join requests, forwarding and destructive chat
# operations. Every route remains restricted to STANDARD conversations.
# ---------------------------------------------------------------------------

class AgentMessengerMyJoinRequestsView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/me/join-requests"
    audit_action = "agent.messenger.join_requests.own.read"

    def get(self, request):
        return _call_messenger("MyJoinRequestsAPIView", "get", request)


class AgentMessengerJoinRequestCancelView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/join-requests/{request_id}"
    audit_action = "agent.messenger.join_requests.own.cancel"
    audit_mutating = True

    @idempotent
    def delete(self, request, request_id):
        from messenger.models import JoinRequest

        join_request = (
            JoinRequest.objects.select_related("conversation")
            .filter(pk=request_id, user=request.user)
            .first()
        )
        if join_request is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Join request not found.", 404)
        _, _, error = _standard_conversation(
            request, join_request.conversation_id, require_member=False
        )
        if error:
            return error
        return _call_messenger(
            "JoinRequestCancelAPIView", "delete", request, request_id
        )


class AgentMessengerJoinByInviteView(AgentMessengerView):
    # Invite codes are accepted in the JSON body, never in the URL, to keep
    # them out of browser history, reverse-proxy access logs and audit paths.
    agent_contract_path = "/agent/v1/messenger/join"
    audit_action = "agent.messenger.invites.join"
    audit_mutating = True

    @idempotent
    def post(self, request):
        from messenger.models import GroupInviteLink

        code = str(request.data.get("code") or "").strip()
        if not code:
            return _agent_error("INVALID_REQUEST", "code is required.", 400)
        invite = (
            GroupInviteLink.objects.select_related("conversation")
            .filter(code=code)
            .first()
        )
        if invite is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Invite link not found.", 404)
        _, _, error = _standard_conversation(
            request, invite.conversation_id, require_member=False
        )
        if error:
            return error
        return _call_messenger("JoinByInviteAPIView", "post", request, code)


class AgentMessengerInviteLinksView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/invite-links"
    audit_action = "agent.messenger.invites.create"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "InviteLinkCreateAPIView", "post", request, conversation_id
        )


class AgentMessengerInviteLinkRevokeView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/invite-links/{link_id}"
    audit_action = "agent.messenger.invites.revoke"
    audit_mutating = True

    @idempotent
    def delete(self, request, conversation_id, link_id):
        from messenger.models import GroupInviteLink

        link = (
            GroupInviteLink.objects.select_related("conversation")
            .filter(pk=link_id, conversation_id=conversation_id)
            .first()
        )
        if link is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Invite link not found.", 404)
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        # The application API uses POST for revoke; the Agent API uses DELETE.
        return _call_messenger(
            "InviteLinkRevokeAPIView", "post", request, conversation_id, link_id
        )


class AgentMessengerMessageForwardView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/messages/{message_id}/forward"
    audit_action = "agent.messenger.messages.forward"
    audit_mutating = True

    @idempotent
    def post(self, request, message_id):
        from messenger.models import Message

        message = (
            Message.objects.select_related("conversation")
            .filter(pk=message_id, is_deleted=False)
            .first()
        )
        if message is None:
            return _agent_error("RESOURCE_NOT_FOUND", "Message not found.", 404)
        from messenger.models import Conversation, ConversationParticipant

        source, source_participant, error = _standard_conversation(
            request, message.conversation_id
        )
        if error:
            return error
        # Match the visibility rules used by message history. A caller must not
        # forward messages from before joining a restricted group.
        if (
            source.type == Conversation.Type.GROUP
            and source_participant.role not in (
                ConversationParticipant.Role.OWNER,
                ConversationParticipant.Role.ADMIN,
            )
        ):
            visibility = getattr(source, "history_visibility", "all") or "all"
            if (
                visibility in ("none", "from_join")
                and source_participant.joined_at
                and message.created_at < source_participant.joined_at
            ):
                return _agent_error(
                    "PERMISSION_DENIED",
                    "This message is outside the caller's visible group history.",
                    403,
                )
        if message.is_scheduled and message.sender_id != request.user.id:
            return _agent_error(
                "PERMISSION_DENIED",
                "Only the sender may access a scheduled message before delivery.",
                403,
            )
        raw_target_id = request.data.get("conversation_id")
        try:
            target_id = int(raw_target_id)
        except (TypeError, ValueError):
            return _agent_error(
                "INVALID_REQUEST", "conversation_id must be a positive integer.", 400
            )
        if target_id < 1:
            return _agent_error(
                "INVALID_REQUEST", "conversation_id must be a positive integer.", 400
            )
        target, target_participant, error = _standard_conversation(
            request, target_id
        )
        if error:
            return error
        if target.is_closed:
            return _agent_error(
                "CONVERSATION_CLOSED", "The target conversation is closed.", 409
            )
        if not target_participant.can_send_messages:
            return _agent_error(
                "PERMISSION_DENIED",
                "The caller cannot send messages in the target conversation.",
                403,
            )
        if (
            target.only_admins_send
            and target_participant.role not in (
                ConversationParticipant.Role.OWNER,
                ConversationParticipant.Role.ADMIN,
            )
        ):
            return _agent_error(
                "PERMISSION_DENIED",
                "Only group owners/admins can send to this target group.",
                403,
            )
        if message.attachments.exists() and not target_participant.can_send_media:
            return _agent_error(
                "PERMISSION_DENIED",
                "The caller cannot send media in the target conversation.",
                403,
            )
        return _call_messenger(
            "MessageForwardAPIView", "post", request, message_id
        )


class AgentMessengerConversationHistoryClearView(AgentMessengerView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/clear-history"
    audit_action = "agent.messenger.conversations.history.clear"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        from messenger.models import Conversation, ConversationParticipant

        conv, participant, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        # Clearing group history affects every member; limit it to group admins.
        if (
            conv.type == Conversation.Type.GROUP
            and participant.role not in (
                ConversationParticipant.Role.OWNER,
                ConversationParticipant.Role.ADMIN,
            )
        ):
            return _agent_error(
                "PERMISSION_DENIED",
                "Only a group owner or admin can clear group history.",
                403,
            )
        return _call_messenger(
            "ConversationCleanupAPIView", "post", request, conversation_id
        )


# ---------------------------------------------------------------------------
# Tickets — deliberately limited to tickets owned by the linked user.
# Staff-facing ticket administration is not granted through Agent scopes.
# ---------------------------------------------------------------------------

class AgentTicketDepartmentsView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/departments"
    audit_action = "agent.tickets.departments.read"

    def get(self, request):
        return _call_ticket(
            "tickets.api.user_tickets", "DepartmentListAPIView", "get", request
        )


class AgentTicketContextView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/context"
    audit_action = "agent.tickets.context.read"

    def get(self, request):
        return _call_ticket(
            "tickets.api.user_tickets", "MyTicketContextAPIView", "get", request
        )


class AgentTicketsView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets"
    audit_action = "agent.tickets"
    audit_mutating = True

    def get(self, request):
        self.audit_mutating = False
        return _call_ticket(
            "tickets.api.user_tickets", "MyTicketListCreateAPIView", "get", request
        )

    @idempotent
    def post(self, request):
        self.audit_mutating = True
        return _call_ticket(
            "tickets.api.user_tickets", "MyTicketListCreateAPIView", "post", request
        )


class AgentTicketDetailView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/{ticket_id}"
    audit_action = "agent.tickets.detail"

    def get(self, request, ticket_id):
        _, error = _owned_ticket(request, ticket_id)
        if error:
            return error
        return _call_ticket(
            "tickets.api.user_tickets", "TicketDetailAPIView", "get", request, ticket_id
        )


class AgentTicketMessagesView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/{ticket_id}/messages"
    audit_action = "agent.tickets.messages"
    audit_mutating = True

    @idempotent
    def post(self, request, ticket_id):
        _, error = _owned_ticket(request, ticket_id)
        if error:
            return error
        return _call_ticket(
            "tickets.api.user_tickets",
            "TicketMessageCreateAPIView",
            "post",
            request,
            ticket_id,
        )


class AgentTicketReadView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/{ticket_id}/read"
    audit_action = "agent.tickets.read_state"
    audit_mutating = True

    @idempotent
    def post(self, request, ticket_id):
        _, error = _owned_ticket(request, ticket_id)
        if error:
            return error
        return _call_ticket(
            "tickets.api.admin_tickets", "TicketMarkReadAPIView", "post", request, ticket_id
        )


class AgentTicketCloseView(AgentTicketView):
    agent_contract_path = "/agent/v1/tickets/{ticket_id}/close"
    audit_action = "agent.tickets.close"
    audit_mutating = True

    @idempotent
    def post(self, request, ticket_id):
        _, error = _owned_ticket(request, ticket_id)
        if error:
            return error
        return _call_ticket(
            "tickets.api.user_tickets", "TicketCloseAPIView", "post", request, ticket_id
        )
