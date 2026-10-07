# messenger

## Purpose

messenger owns the messaging subsystem: contacts, blocks, conversations, participants, messages, reactions, read state, media, groups, invites, join requests and calls.

## Why this boundary exists

Messaging has its own participant graph, per-user visibility and realtime consistency requirements. It should not become part of users identity state or services deployment state.

## Responsibilities

Conversation/member lifecycle; contacts/blocks; message CRUD/forward/edit/delete; reactions/read receipts; attachments/view-once; group roles/invites/join requests; pins/drafts; calls; MessengerEvent; Channels consumers; caches/scheduled tasks.

## Non-responsibilities

User identity is users. Service-share authorization is services. Deployment lifecycle is deployments. Generic media serving is core.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)
- [tests.md](tests.md)

## Core state path

~~~text
HTTP mutation
 -> participant/role authorization
 -> DB transaction
 -> MessengerEvent
 -> post-commit Channels broadcast
~~~

## Security

Active ConversationParticipant membership is the primary resource boundary. Group role/action flags add constraints. Attachment URLs depend on viewer/view-once state. Profile-photo visibility is evaluated independently.

## Invariants

1. Durable DB state precedes realtime broadcast.
2. Reconnect uses durable event cursor/sync.
3. Message client idempotency is preserved.
4. View-once recipients do not get a durable URL before open.
5. Group ownership is represented by current participant role; created_by is historical context.

## Reading order

models.md -> api.md -> serializers.md -> background.md -> tests.md.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)

## Detailed contracts

- [Detailed API reference](api-reference.md)
