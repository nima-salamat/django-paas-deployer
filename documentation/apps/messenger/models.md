# messenger models

The messenger model graph is the durable source for conversations; WebSocket state is a delivery layer.

## UserBio

One-to-one messenger-owned profile text. user is the canonical users.User relation. text is optional and limited to 255 characters; messenger owns the bio value even though users owns the identity.

## Contact / Block

Contact(owner, contact) is a directed relationship and is unique per pair. Block(blocker, blocked) is also directed and unique. These are viewer policy inputs; neither grants access to conversations.

## ProfilePhotoPrivacy / ProfilePhotoAllowed

ProfilePhotoPrivacy is one-to-one per user. scope is everyone, contacts, nobody or specific. For specific scope, ProfilePhotoAllowed rows enumerate permitted viewers. Messenger reuses users.Profile image files; it does not duplicate the image store.

## Conversation

public_id is the stable external identifier. type is private/group. title/description/avatar/public/closed/approval/member/send/history flags define group behavior. `is_forum` marks a root group whose sidebar can expand into topic conversations. `parent_conversation` links each topic conversation to its root and is null for ordinary conversations and forum roots. Existing history stays in the root conversation, which serves as General; each child topic has an independent message timeline and cache. created_by is historical creator context; active ownership comes from ConversationParticipant.role. last_message_at drives chat-list ordering and is updated by Message.save() for non-scheduled messages.

## ConversationParticipant

One row per conversation/user. role is owner/admin/member. Permission booleans gate group actions; left_at is a soft membership boundary. last_read_at tracks read position; is_pinned/pinned_at and draft_text/draft_updated_at are per-user UI state. The uniqueness constraint on (conversation,user) means a departed user keeps the same membership identity rather than receiving a second row.

## GroupInviteLink

Cryptographically generated code; active/expiry/max_uses/uses define validity. codes are capability tokens and must not be treated as permanent identity.

## JoinRequest

conversation + user + status is unique. status is pending/approved/rejected. Approval creates membership; rejection leaves the user unjoined and permits a later request.

## Message

conversation is the resource scope; sender may become null after account deletion. reply_to and forwarded_from_message preserve provenance. is_edited/is_deleted/is_system describe message lifecycle. client_message_id is the caller idempotency key and is unique for non-null sender/conversation combinations. scheduled_for/is_scheduled hold future messages until the Celery delivery task.

## MessengerEvent

Durable event envelope with event_id/event_type/conversation plus optional actor/message/call and structured payload. It is the reconnect/fanout record: DB commit happens before broadcast.

## MessageReaction / MessageReadReceipt

Reactions are unique per message/user/emoji. Read receipts are unique per message/user and timestamp when the user saw the message.

## MessageAttachment

Conversation-scoped file with uploader, file metadata and Kind (image/video/gif/audio/file/voice). is_spoiler, is_view_once and is_purged encode media privacy/lifecycle. message may be null during upload/staging.

## AttachmentViewOnceOpen

Unique per attachment/user. opened_at/expires_at define the temporary recipient capability. This row is not a general download grant.

## PinnedMessage

Unique conversation/message relation. pinned_by is audit/actor context; pin authorization is checked before creation.

## CallSession / CallSessionParticipant

CallSession has ringing/active/ended/missed/declined/no_answer states and a conditional uniqueness constraint allowing only one ringing/active call per conversation. CallSessionParticipant is unique per call/user and left_at represents current presence in that call.

## Deletion and authority

Conversation deletion cascades participant/message/event/media state according to ORM relations. User deletion SET_NULLs historical sender/actor fields where configured rather than rewriting history.

Do not treat cached presence, online flags or WebSocket membership as durable authority. ConversationParticipant, Message, MessengerEvent and CallSession are the durable state owners.

## Structured fields

MessengerEvent.payload is the main JSON contract: producers write event-specific bounded keys and consumers render/broadcast them. Do not expose arbitrary payload keys as public API without a corresponding event contract.

Source: src/messenger/models.py.

> **Complete field reference:** [field-reference.md](field-reference.md) lists every field explicitly declared in `src/messenger/models.py`, including type, null/blank behavior, defaults, constraints and purpose.
