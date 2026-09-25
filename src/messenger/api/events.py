from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_users.authentication import SessionJWTAuthentication

from ..models import Conversation, ConversationParticipant, MessengerEvent


class ConversationEventSyncAPIView(APIView):
    """Durable reconnect cursor for events published after a client checkpoint."""

    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).exists():
            return Response({"detail": "Forbidden"}, status=403)

        try:
            after_id = max(0, int(request.query_params.get("after_id") or 0))
        except (TypeError, ValueError):
            return Response({"detail": "after_id must be an integer"}, status=400)
        try:
            limit = min(100, max(1, int(request.query_params.get("limit") or 50)))
        except (TypeError, ValueError):
            limit = 50

        rows = list(
            MessengerEvent.objects.filter(
                conversation_id=pk, id__gt=after_id
            ).order_by("id")[: limit + 1]
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        results = [
            {
                "event_id": str(row.event_id),
                "cursor": row.id,
                "type": row.event_type,
                "conversation_id": row.conversation_id,
                "actor_id": row.actor_id,
                "message_id": row.message_id,
                "call_id": row.call_id,
                "created_at": row.created_at,
                "payload": row.payload,
            }
            for row in rows
        ]
        return Response({
            "results": results,
            "has_more": has_more,
            "next_after_id": rows[-1].id if rows else after_id,
        })
