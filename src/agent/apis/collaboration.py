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


# ---------------------------------------------------------------------------
# Messenger discovery and account-level operations
# ---------------------------------------------------------------------------

class AgentMessengerUserSearchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/users/search"
    audit_action = "agent.messenger.users.search"

    def get(self, request):
        return _call_messenger("UserSearchAPIView", "get", request)


class AgentMessengerContactsView(AgentSecuredAPIView):
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


class AgentMessengerContactDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/contacts/{user_id}"
    audit_action = "agent.messenger.contacts.delete"
    audit_mutating = True

    @idempotent
    def delete(self, request, user_id):
        return _call_messenger("ContactDeleteAPIView", "delete", request, user_id)


class AgentMessengerBlocksView(AgentSecuredAPIView):
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


class AgentMessengerBlockDetailView(AgentSecuredAPIView):
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

class AgentMessengerConversationsView(AgentSecuredAPIView):
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


class AgentMessengerConversationDetailView(AgentSecuredAPIView):
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


class AgentMessengerMessagesView(AgentSecuredAPIView):
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


class AgentMessengerMessageSearchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/messages/search"
    audit_action = "agent.messenger.messages.search"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "MessageSearchAPIView", "get", request, conversation_id
        )


class AgentMessengerScheduledMessagesView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/scheduled"
    audit_action = "agent.messenger.messages.scheduled"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "ScheduledMessageListAPIView", "get", request, conversation_id
        )


class AgentMessengerMarkReadView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/read"
    audit_action = "agent.messenger.messages.read_state"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger("MarkReadAPIView", "post", request, conversation_id)


class AgentMessengerMessageReactView(AgentSecuredAPIView):
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


class AgentMessengerMessageEditView(AgentSecuredAPIView):
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


class AgentMessengerMessageDeleteView(AgentSecuredAPIView):
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


class AgentMessengerScheduledMessageCancelView(AgentSecuredAPIView):
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

class AgentMessengerGroupSearchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/groups/search"
    audit_action = "agent.messenger.groups.search"

    def get(self, request):
        return _call_messenger("PublicGroupSearchAPIView", "get", request)


class AgentMessengerGroupJoinView(AgentSecuredAPIView):
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


class AgentMessengerParticipantsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/participants"
    audit_action = "agent.messenger.groups.participants.read"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "GroupParticipantsListAPIView", "get", request, conversation_id
        )


class AgentMessengerMembersView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/members"
    audit_action = "agent.messenger.groups.members"
    audit_mutating = True

    @idempotent
    def post(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger("AddMembersAPIView", "post", request, conversation_id)


class AgentMessengerMemberDetailView(AgentSecuredAPIView):
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


class AgentMessengerMemberRoleView(AgentSecuredAPIView):
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


class AgentMessengerMemberPermissionsView(AgentSecuredAPIView):
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


class AgentMessengerJoinRequestsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/messenger/conversations/{conversation_id}/join-requests"
    audit_action = "agent.messenger.groups.join_requests.read"

    def get(self, request, conversation_id):
        _, _, error = _standard_conversation(request, conversation_id)
        if error:
            return error
        return _call_messenger(
            "JoinRequestListAPIView", "get", request, conversation_id
        )


class AgentMessengerJoinRequestActionView(AgentSecuredAPIView):
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
# Tickets — deliberately limited to tickets owned by the linked user.
# Staff-facing ticket administration is not granted through Agent scopes.
# ---------------------------------------------------------------------------

class AgentTicketDepartmentsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/tickets/departments"
    audit_action = "agent.tickets.departments.read"

    def get(self, request):
        return _call_ticket(
            "tickets.api.user_tickets", "DepartmentListAPIView", "get", request
        )


class AgentTicketContextView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/tickets/context"
    audit_action = "agent.tickets.context.read"

    def get(self, request):
        return _call_ticket(
            "tickets.api.user_tickets", "MyTicketContextAPIView", "get", request
        )


class AgentTicketsView(AgentSecuredAPIView):
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


class AgentTicketDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/tickets/{ticket_id}"
    audit_action = "agent.tickets.detail"

    def get(self, request, ticket_id):
        _, error = _owned_ticket(request, ticket_id)
        if error:
            return error
        return _call_ticket(
            "tickets.api.user_tickets", "TicketDetailAPIView", "get", request, ticket_id
        )


class AgentTicketMessagesView(AgentSecuredAPIView):
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


class AgentTicketReadView(AgentSecuredAPIView):
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


class AgentTicketCloseView(AgentSecuredAPIView):
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
