# messenger state and choice contracts

## Conversation

type: private or group.

history_visibility: all, from_join or none. It controls what new group members can see; it is not an authorization bypass.

## Participant role

owner, admin or member. Current owner/admin state is represented by ConversationParticipant.role. Group ownership transfer changes participant roles; Conversation.created_by remains creator history.

Action flags can_send_messages, can_send_media, can_add_members, can_pin_messages and can_change_info narrow what that participant can do.

## JoinRequest

pending -> approved/rejected. A user may cancel a pending request; approval also creates membership and a system event/message.

## Message

Messages can be scheduled, edited/deleted, forwarded/replied and marked system. client_message_id provides request idempotency for sender/conversation.

## CallSession

A call moves through the implemented ringing/active/end/missed/declined/busy lifecycle. There is a uniqueness rule preventing multiple active call sessions for the same conversation.

## View-once

Attachment state combines is_view_once/is_purged with per-user AttachmentViewOnceOpen rows. Opening creates a recipient-specific capability window; later access follows expiry/purge rules.
