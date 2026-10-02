# messenger background and realtime behavior

## Scheduled tasks

finalize_unanswered_call marks a ringing call as missed when its deadline expires and publishes the call event.

deliver_due_scheduled_messages runs on a short Beat interval. It selects due scheduled messages, locks/claims them, and creates the normal delivery event rather than delivering from the conversation-list API.

purge_view_once_if_complete removes expired/fully-consumed view-once media according to the model policy.

## WebSocket authentication

MessengerConsumer accepts only a session-bound access JWT with `sid`, validates the corresponding UserSession during the handshake, and revalidates the server-side session on heartbeat. Revoking the session therefore closes the connection without requiring the browser to reuse sessionless credentials.

## Event flow


A successful HTTP mutation records MessengerEvent as part of the database lifecycle and broadcasts only after commit. Consumer helpers broadcast message/reaction/call/read/member/profile/join-request/pin events to Channels groups.

## Presence

MessengerConsumer updates online state and broadcasts presence. Presence is ephemeral/cache-like; conversation/message/membership data remains durable.

## Service-share side effect

Member leave/removal/group deletion invokes services.share_cleanup so a Messenger membership change can revoke or update Service sharing. This is a deliberate cross-app side effect; it must not be replaced with a client-only permission change.

## User deletion

The Messenger User pre-delete signal applies the same durable leave semantics used by the conversation API. A deleted user leaves active group memberships; group ownership transfers to the oldest active admin/member or the group is removed when no active members remain. Private DMs are hard-deleted with their conversation media. User-specific conversation-list/presence caches are invalidated after deletion, while other users' message history survives where Message.sender uses `SET_NULL`.

## Tests as contracts

tests_calls.py and tests_call_state.py protect call lifecycle; tests_message_cache.py protects cache invalidation and membership state. HTTP/event regressions should preserve durable state before broadcast ordering.
