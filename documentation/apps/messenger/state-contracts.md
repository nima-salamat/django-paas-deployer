# messenger state and choice contracts

## Conversation
type is private or group. history_visibility is all, from_join or none and controls what new members can see; it is not an authorization bypass.

## Participant
role is owner/admin/member. left_at null means active membership. Ownership transfer changes participant roles while Conversation.created_by remains creator history. Action flags constrain operations.

## JoinRequest
pending -> approved/rejected. Caller cancellation is DELETE on the request resource. Approval also creates membership/system-event side effects.

## Message
Messages may be scheduled, edited, deleted, forwarded or replied. client_message_id is the sender/conversation idempotency key.

## Durable event cursor
MessengerEvent.id is the reconnect cursor. WebSocket delivery is downstream of this durable row.

## CallSession
Call state is managed by transition_call: ringing -> active or terminal states such as ended, missed, declined and no_answer. Conversation-level locking prevents competing active calls.

## View-once
AttachmentViewOnceOpen records recipient-specific open/expiry state. MessageAttachment.is_purged means the stored file has been invalidated/removed.

## Boundary invariant
Durable state is committed before realtime consumers are expected to act on it. Redis is a cache; the database and durable event rows are authoritative.