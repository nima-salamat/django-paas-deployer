# messenger API

Canonical mount: /api/messenger/. Routes and methods below are derived from src/messenger/urls.py and the registered APIView classes. Authentication is SessionJWTAuthentication + IsAuthenticated; authorization is participant/role/viewer scoped. The Matrix device logout route is the exception: it uses the supplied Matrix device token as proof of ownership so explicit logout remains possible after a Django session expires.

Topic handlers live in `src/messenger/api/topics.py`. For standard groups, GET/POST operates on child topic conversations while preserving the existing root timeline as General. The endpoint rejects legacy topic operations for `matrix_e2ee` records until they are backed by actual Matrix rooms.

## Exact HTTP surface

### Users, contacts and profile

| Method | Route | What it does |
|---|---|---|
| GET | /api/messenger/users/search/ | Searches active users by username; blocked users and the caller are excluded. |
| GET | /api/messenger/contacts/ | Lists the caller's contacts with pagination and optional username/nickname/name search. |
| POST | /api/messenger/contacts/ | Adds an active user as a contact, optionally recording a nickname; self-add and blocked relationships are rejected. |
| DELETE | /api/messenger/contacts/<int:user_id>/ | Removes the caller's contact relationship with that user. |
| GET | /api/messenger/blocks/ | Lists users blocked by the caller. |
| POST | /api/messenger/blocks/ | Blocks a user, removes the caller's contact entry for that user and invalidates the caller's Messenger list cache. |
| POST | /api/messenger/blocks/<int:user_id>/unblock/ | Removes the caller's block for that user. |
| GET | /api/messenger/users/<int:user_id>/profile/ | Returns an active user's Messenger profile; profile photos are included only when the caller passes the photo-privacy policy. |
| GET | /api/messenger/users/by-username/ | Resolves an exact username (ignoring an optional leading @) to the same privacy-filtered profile payload without creating a contact. |
| GET | /api/messenger/me/photos/ | Lists the caller's existing users.Profile images and current Messenger photo-privacy settings; Messenger does not own upload/reorder/delete. |
| PATCH | /api/messenger/me/photo-privacy/ | Changes the caller's photo-visibility scope and optional allow-list of up to 200 users. |
| GET | /api/messenger/me/bio/ | Reads the caller's Messenger bio/about text. |
| PATCH | /api/messenger/me/bio/ | Updates the caller's bio, truncated to 255 characters. |
| POST | /api/messenger/me/profile-broadcast/ | Broadcasts a profile-update event to the caller's conversations after an external profile/photo/username change. |

### Conversations and messages

| Method | Route | Important contract |
|---|---|---|
| GET, POST | /api/messenger/conversations/ | List accessible conversations or create private/group conversation. |
| GET, PATCH | /api/messenger/conversations/<int:pk>/ | Conversation detail/settings; no DELETE handler is registered. |
| GET, POST | /api/messenger/conversations/<int:pk>/topics/ | List the caller's visible topics or create a topic (owner/admin or member with info-management permission); creation preserves the root's existing history as General. |
| GET, POST | /api/messenger/conversations/<int:pk>/messages/ | History/create; create validates membership, capability, attachments and client_message_id idempotency. |
| GET | /api/messenger/conversations/<int:pk>/events/ | Durable reconnect cursor; after_id and bounded limit are query inputs. |
| GET | /api/messenger/conversations/<int:pk>/messages/search/ | Participant-scoped message search. |
| GET | /api/messenger/conversations/<int:pk>/scheduled/ | Caller-visible scheduled messages. |
| POST | /api/messenger/messages/<int:pk>/cancel-schedule/ | Cancel pending sender-owned scheduled message. |
| POST | /api/messenger/conversations/<int:pk>/read/ | Update caller read state; returns the authoritative `last_read_at` cursor and invalidates the caller's conversation-list projection when it advances. |
| POST | /api/messenger/messages/<int:pk>/react/ | Reaction toggle. |
| DELETE | /api/messenger/messages/<int:pk>/react/ | Remove the authenticated user's reaction for the supplied emoji in the request body; idempotent and never removes another user's reaction. |
| PATCH | /api/messenger/messages/<int:pk>/edit/ | Sender-authorized edit. |
| DELETE | /api/messenger/messages/<int:pk>/ | Sender/role-constrained delete. |
| POST | /api/messenger/messages/<int:pk>/forward/ | Forward accessible message to authorized destination. |
| GET | /api/messenger/messages/<int:pk>/readers/ | Read-receipt breakdown. |

### Pins, invites and membership

| Method | Route | Important contract |
|---|---|---|
| POST | /api/messenger/conversations/<int:pk>/pin/ | Caller conversation-list pin state. |
| POST | /api/messenger/messages/<int:pk>/pin/ | Legacy toggle pin/unpin action. |
| PUT | /api/messenger/messages/<int:pk>/pin/ | Ensure the message is pinned; idempotent. |
| DELETE | /api/messenger/messages/<int:pk>/pin/ | Ensure the message is unpinned; idempotent. |
| GET | /api/messenger/conversations/<int:pk>/pinned-messages/ | Canonical pinned-message route; /pinned/ is not registered. |
| POST | /api/messenger/conversations/<int:pk>/invite-links/ | Create group invite; owner/admin only. |
| POST | /api/messenger/conversations/<int:pk>/invite-links/<int:link_id>/revoke/ | Revoke invite; one POST action endpoint, not DELETE. |
| GET | /api/messenger/groups/search/ | Public-group search. |
| POST | /api/messenger/groups/<int:pk>/join/ | Direct join or pending JoinRequest. |
| POST | /api/messenger/join/<str:code>/ | Consume invite. |
| GET | /api/messenger/conversations/<int:pk>/join-requests/ | List pending requests for group managers. |
| POST | /api/messenger/conversations/<int:pk>/join-requests/<int:req_id>/action/ | Single approve/reject action endpoint; action is request data. |
| GET | /api/messenger/me/join-requests/ | Caller-owned join-request list. |
| DELETE | /api/messenger/join-requests/<int:req_id>/ | Cancel caller-owned pending request. |
| POST | /api/messenger/conversations/<int:pk>/members/ | Add members. |
| DELETE | /api/messenger/conversations/<int:pk>/members/<int:user_id>/ | Remove member. |
| POST | /api/messenger/conversations/<int:pk>/members/<int:user_id>/role/ | Change role. |
| POST | /api/messenger/conversations/<int:pk>/transfer-ownership/ | Transfer ownership. |
| POST | /api/messenger/conversations/<int:pk>/leave/ | Leave conversation. |
| DELETE | /api/messenger/conversations/<int:pk>/delete/ | Delete conversation. |
| POST, DELETE | /api/messenger/conversations/<int:pk>/avatar/ | Set/clear group avatar. |

### Optional Matrix secure chat

These endpoints are reserved for the opt-in E2EE path; they do not change standard conversations.

| Method | Route | Important contract |
|---|---|---|
| POST | /api/messenger/secure/device-session/ | Create a normal Matrix login for a newly generated device ID; the Synapse admin credential stays on the backend. |
| POST | /api/messenger/secure/device-session/logout/ | Validate the Matrix token with `whoami`, log out that device on Synapse and mark `logged_out_at`; Matrix-token-authenticated self-service, intentionally works after Django JWT expiry and does not permanently revoke the app device ID. |
| GET | /api/messenger/secure/device-session/ | Validate that the supplied Matrix access token and device belong to the currently authenticated Django account. |
| POST | /api/messenger/secure/identities/ | Resolve active Messenger contacts/authorized conversation participants to server-managed Matrix user IDs. |
| GET | /api/messenger/secure/devices/ | List Matrix device records associated with the current Django user. |
| POST | /api/messenger/secure/devices/<str:device_id>/revoke/ | Revoke a device/session through Synapse and mark the local device record revoked. |
| POST | /api/messenger/secure/conversations/ | Register an existing Matrix room only after verifying the E2EE algorithm, requesting device, intended participants and (for a group) the reciprocal Matrix Space relationship. Does not create a plaintext fallback. |

The ordinary `POST /conversations/` endpoint still returns `503` when a caller requests `security_mode=matrix_e2ee`; it never downgrades the request to a normal conversation. The React secure client creates the encrypted Matrix room and then calls the secure mapping endpoint. The secure client supports E2EE text and client-side encrypted Matrix media (images, voice/audio, video and arbitrary files). It encrypts each file locally, uploads ciphertext to Synapse, and sends the file key, IV and integrity hash only inside the Matrix-encrypted room event; it does not use the ordinary Django attachment endpoints. The React client also supports device-local search over messages already loaded and decrypted on that device, Matrix `m.reaction` annotations (including removal of the current user's own reaction), Matrix `m.read` receipts when an incoming event becomes visible, Matrix `m.replace` message edits, and Matrix redactions for deleting the current user's own messages. Message replacement content is sent in the encrypted event payload; read receipts, reaction relations and redaction metadata are Matrix room activity rather than ordinary Django messages. Small media (up to 12 MiB when a plaintext size is available) is decrypted automatically after ciphertext integrity verification; larger or unknown-size attachments require an explicit user action. Read receipts and reaction/redaction metadata can reveal activity to room participants and the homeserver according to Matrix semantics. Secure replies, forwarding, scheduled messages and Jitsi calls remain unavailable and must stay blocked for E2EE rooms. These client-side paths still require live acceptance tests against the configured Synapse deployment; they are not production-certified by repository tests alone.

#### Connecting an existing Synapse homeserver

No Synapse service is required in this repository's `compose.yaml`. The `web` service attaches to an existing external Docker network named by `MATRIX_DOCKER_NETWORK` (default `matrix_matrix`, the usual Compose-generated name when the Synapse project directory is `/opt/matrix`). The network is declared external, so Compose fails rather than creating a substitute network if that name is wrong. Keep your existing Synapse deployment separate; do not deploy the Ready App template unless you intentionally want a second, independent homeserver.

Confirm the real network name on the host with `docker network ls --filter name=matrix --format '{{.Name}}'`. Set `MATRIX_DOCKER_NETWORK` in the Paas Deploy(er) root `.env` to the exact result if it is not `matrix_matrix`. Only the Django `web` service needs this network for the current synchronous Matrix API integration; no new Synapse or PostgreSQL service is added here. The existing `synapse` container name is used as the backend DNS alias on that network.

Configure these values in the backend `.env` (the Django service already loads it with `env_file`):

- `MATRIX_HOMESERVER_URL`: the public HTTPS Matrix Client-Server API base URL. The React browser uses this URL directly, and Django uses it unless an internal URL is configured. It must be reachable from user browsers and provide the CORS responses required by the Matrix Client-Server API through your reverse proxy.
- `MATRIX_HOMESERVER_DOMAIN`: the exact Synapse `server_name` (the domain part of Matrix user IDs), not necessarily the hostname in the public URL.
- `MATRIX_HOMESERVER_INTERNAL_URL`: for this deployment, `http://synapse:8008` uses the existing container alias on the shared private network. The browser never receives this internal URL. A plain-HTTP value is accepted only for a single-label Docker service hostname; do not route it over a public network.
- `MATRIX_DOCKER_NETWORK`: the exact existing Docker network name from the Synapse Compose project. It is external and will not be created by Paas Deploy(er).
- `MATRIX_ADMIN_ACCESS_TOKEN`: an administrator access token used only by Django for Synapse Admin API operations.
- `MATRIX_IDENTITY_ENCRYPTION_KEY`: a dedicated Fernet key for encrypting the generated Matrix account passwords stored in Django. Keep a secure backup; rotating it without re-encrypting stored credentials disables future provisioning/login.

The integration creates Paas Deployer-specific Matrix accounts (localparts derived from Django UUIDs) on the configured homeserver. It does not automatically link or take over existing Synapse usernames/passwords; existing Matrix accounts remain untouched. To authenticate the same Matrix users already present on Synapse, a separate explicit account-mapping/SSO design would be needed.

### Media and calls

| Method | Route | What it does |
|---|---|---|
| GET | /api/messenger/conversations/<int:pk>/media/ | Lists image/video/audio/voice/file attachments for an active conversation member; supports `kind`, `before_id` and bounded `limit` pagination. |
| POST | /api/messenger/conversations/<int:pk>/cleanup/ | Destructively clears the entire conversation history for every participant, deletes stored attachment files, resets the caller's read cursor, invalidates caches and broadcasts `messages.cleared`. |
| GET | /api/messenger/attachments/<int:pk>/download/ | Streams an attachment after checking authentication, active conversation membership and transport mode. View-once media additionally requires an unexpired per-user one-time token/window; purged media returns 410. |
| POST | /api/messenger/attachments/<int:pk>/view-once/ | Opens a view-once attachment once for the caller, issues a download URL/token valid for 15 seconds and schedules a purge check when all recipients have opened. |
| POST | /api/messenger/conversations/<int:pk>/call/ | Starts a conversation call with optional `video`/`audio` flags; creates a durable CallSession and call-start system message, and rings peers for 30 seconds. Only one active/ringing call may exist per conversation. |
| GET | /api/messenger/conversations/<int:pk>/call/join/ | Joins the selected/current ringing or active call (optional `call_id` query parameter), transitions a ringing call to active, registers the participant and returns Jitsi room configuration. |
| GET | /api/messenger/conversations/<int:pk>/call/active/ | Reads the current ringing/active call and caller participant state; self-heals ringing sessions older than the 30-second window. |
| POST | /api/messenger/conversations/<int:pk>/call/end/ | Ends/declines/leaves a call using optional `call_id` and `reason`; group participants can leave without ending the call for everyone else. |

## Durable/realtime contract

HTTP -> authentication -> participant/role/object authorization -> API validation -> durable mutation -> MessengerEvent where required -> transaction.on_commit -> cache/Channels broadcast.

The database is authoritative. Redis is a hot cache. /conversations/<pk>/events/ is the durable reconnect path. Message creation can update the message cache after commit; profile/member/join/call mutations broadcast events; view-once opening creates AttachmentViewOnceOpen and later purge may delete the file; Messenger membership changes can revoke ServiceShare access; scheduled delivery is Celery/Beat driven.

Source: src/messenger/urls.py, src/messenger/api/*.py, src/messenger/serializers.py, src/messenger/events.py, src/messenger/consumers.py, src/messenger/tasks.py.