# messenger contracts and tests

| Test | Protected behavior | Invariant |
|---|---|---|
| src/messenger/tests/test_topics_api.py | topic creation, General history preservation, group membership sync, top-level list isolation and authorization | topics are separate conversations; root membership remains the default source |
| tests_calls.py | call start/join/end/finalization | one active call lifecycle and correct post-commit realtime effects |
| tests_call_state.py | ringing/active/missed/declined state | call state transitions remain consistent |
| tests_message_cache.py | membership/conversation cache behavior | cache invalidation follows durable membership/messages without becoming authority |

There are also behavior tests embedded in API/model modules and Django's normal test discovery. When changing membership, events, message idempotency or view-once media, inspect both model behavior and consumer/event code.

The strongest realtime invariant is durable state before broadcast; reconnect must be recoverable through event sync.
