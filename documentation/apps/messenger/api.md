# messenger API

Root: /api/messenger/. Authentication uses the global SessionJWTAuthentication/IsAuthenticated policy; resource checks are participant/role/viewer scoped.

## Registered HTTP surface

### Users, contacts and privacy

- GET /users/search/ — viewer-scoped user discovery; UserMiniSerializer derives contact/block/avatar/online/bio state.
- GET,POST /contacts/ — caller's contacts only.
- DELETE /contacts/<user_id>/ — caller-owned contact removal.
- GET,POST /blocks/ — caller-owned blocks.
- POST /blocks/<user_id>/unblock/ — caller-owned unblock.
- GET /users/<id>/profile/ — profile with photo/privacy policy.
- GET /users/by-username/ — username lookup with visibility policy.
- GET /me/photos/ — caller's Profile-backed photos.
- GET,PATCH,DELETE /me/photo-privacy/ — caller's messenger photo policy.
- GET,POST,PATCH /me/bio/ — UserBio owned by messenger.
- POST /me/profile-broadcast/ — post-commit profile update event.

### Conversations

- GET,POST /conversations/ — list accessible conversations or create a private/group conversation.
- GET,PATCH,DELETE /conversations/<pk>/ — detail and permitted group metadata changes.
- GET /conversations/<pk>/messages/ — paginated history for active participants.
- GET /conversations/<pk>/events/ — durable event cursor for reconnect.
- GET /conversations/<pk>/messages/search/ — participant-scoped message search.
- GET /conversations/<pk>/scheduled/ — caller's pending scheduled messages.
- POST /conversations/<pk>/read/ — update caller read state.
- GET /conversations/<pk>/media/ — participant-scoped media list.
- POST /conversations/<pk>/cleanup/ — permitted cleanup of conversation message/media state.

### Messages

- POST /conversations/<pk>/messages/ — validates participant/role, client_message_id idempotency, body/attachments; persists and emits MessengerEvent after commit.
- POST /messages/<pk>/forward/ — reads accessible source, validates accessible destination, creates a new message.
- PATCH /messages/<pk>/edit/ — sender-only edit; marks is_edited.
- DELETE /messages/<pk>/ — sender/role-constrained soft/historical delete.
- POST /messages/<pk>/react/ — caller reaction toggle with participant access.
- POST /messages/<pk>/readers/ — viewer-authorized read-receipt breakdown.
- POST /messages/<pk>/cancel-schedule/ — sender-only cancellation before delivery.

### Pins, invites, groups and membership

- POST/DELETE /conversations/<pk>/pin/ — caller's chat-list pin state.
- GET /conversations/<pk>/pinned/ — pinned messages subject to can_pin_messages/role.
- GET,POST /conversations/<pk>/invite-links/ — list/create owner/admin invite capability.
- DELETE /invite-links/<code>/ — owner/admin revoke.
- GET /groups/search/ — public-group discovery.
- POST /groups/<pk>/join/ — direct join or JoinRequest according to requires_approval.
- POST /join/<code>/ — invite consumption.
- GET /conversations/<pk>/join-requests/ — owner/admin pending requests.
- POST /join-requests/<pk>/approve/ — approve and create membership/system event.
- POST /join-requests/<pk>/reject/ — reject request.
- GET /join-requests/my/ — caller requests.
- DELETE /join-requests/<pk>/cancel/ — caller cancels pending request.
- POST /conversations/<pk>/members/ — add member when role/permission allows.
- DELETE /conversations/<pk>/members/<user_id>/ — remove member.
- PATCH /conversations/<pk>/members/<user_id>/role/ — role change.
- POST /conversations/<pk>/transfer-ownership/ — owner transfer to active member.
- POST /conversations/<pk>/leave/ — leave with owner-transfer/last-member handling.
- DELETE /conversations/<pk>/delete/ — permitted conversation deletion.

### Attachments

- GET /attachments/<pk>/download/ — participant access; view-once restrictions apply.
- POST /attachments/<pk>/view-once/ — opens a view-once attachment, creating a temporary per-recipient capability.
- The application also exposes conversation media lookup and attachment cleanup routes described above.

### Calls

- POST /conversations/<pk>/call/ — creates ringing CallSession and room config.
- GET /conversations/<pk>/call/active/ — current active/ringing call.
- POST /conversations/<pk>/call/join/ — joins current call.
- POST /conversations/<pk>/call/end/ — ends/declines/leaves according to caller/session state.

## Request chain

~~~text
HTTP
 -> authenticated user
 -> conversation/participant/role resolver
 -> serializer or API validation
 -> atomic model mutation
 -> MessengerEvent
 -> transaction.on_commit broadcast
 -> Channels/WebSocket consumers
~~~

Realtime is downstream of database state. Redis/cache is an optimization; /events/ provides durable reconnect state.

## Cross-app effects

Removing/adding Messenger group membership can invoke services share cleanup. User profile images come from users.Profile. Protected attachment serving uses core media security.

## Related source

src/messenger/urls.py, src/messenger/api/*.py, src/messenger/serializers.py, src/messenger/events.py, src/messenger/consumers.py, src/messenger/tasks.py.
