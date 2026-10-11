# Messenger secure-chat architecture decision

## Decision status

**Matrix-backed E2EE is now implemented as an opt-in code path, but it is not production-certified and must remain disabled until a real Synapse deployment is configured and the end-to-end acceptance suite passes.** Normal chats continue to use the existing server-readable Messenger path. No existing conversation is automatically upgraded.

The new code path adds the official `matrix-js-sdk@41.6.0` with Rust/WASM crypto, server-managed Matrix identities, device-bound Matrix sessions, verified encrypted room registration, secure DM/group/topic creation, an encrypted-text-only room UI, first-device recovery-key setup, existing-device SAS verification, and device listing/revocation. The administrator token and identity-encryption key remain backend-only. The standard conversation-create endpoint still rejects a requested `matrix_e2ee` mode; only the Matrix flow can register a room after checking its encryption algorithm, Matrix device identity, intended members, and (for groups) the Matrix Space relationship.

The secure UI deliberately supports only encrypted text in this first implementation. Search, attachments, forwarding, reactions, scheduled messages, read receipts, public discovery/invites and Jitsi calls are not advertised as E2EE capabilities and are blocked on secure rooms. A successful Django login alone does not unlock old history; the user must restore the prior Matrix key backup or verify an existing trusted device. The configured homeserver, real two-account/two-device recovery and revocation flows, and production operational hardening still need deployment-level verification before calling the feature ready.

The security feature is feasible, but it must be implemented as a protocol integration—not as a home-grown encryption wrapper around `Message.body`.

## Requirements

- The server must not receive readable message bodies, replies, attachment contents, or media encryption keys for secure conversations.
- Every browser installation is a separate cryptographic device. A login from another browser must not silently clone private device keys.
- Users can verify devices and detect unexpected identity-key changes.
- Losing a browser/device must not silently destroy history if the user previously configured recovery.
- Recovery material must never be sent to the server in plaintext.
- Revoking a device prevents it from receiving future secure-room traffic; it cannot erase plaintext or keys that the device already copied.
- Existing non-encrypted chats remain compatible and are never silently migrated to secure chat.
- Topics/subgroups must be represented as separate encrypted rooms under the same logical group, so encryption membership and key rotation happen per room.

## Selected cryptographic foundation

Use the maintained Matrix client protocol and its established E2EE implementation rather than defining a new protocol:

- `matrix-js-sdk` for client-server messaging, room membership, device management, encrypted event handling, and encrypted media.
- `@matrix-org/matrix-sdk-crypto-wasm` for the Rust/WASM-backed Matrix crypto state machine.
- An existing self-hosted Matrix homeserver (for example, Synapse). It may run in a separate Compose project; the Paas Deploy(er) Compose stack does not need to start another Synapse service. The `matrix-synapse-with-postgresql` Ready App is optional for operators who intentionally want to deploy a new homeserver, not a prerequisite for Messenger integration.

The WASM package implements a crypto state machine without doing network I/O itself; the Matrix client-server protocol still has to carry device keys, one-time keys, to-device messages, membership changes and encrypted room events. Therefore the package cannot simply be dropped into the current Django message endpoint and provide encryption automatically.

References:
- Matrix E2EE implementation guide: https://matrix.org/docs/matrix-concepts/end-to-end-encryption/
- Matrix crypto WASM API: https://matrix-org.github.io/matrix-sdk-crypto-wasm/
- Matrix client-server E2EE API and key backups: https://spec.matrix.org/latest/client-server-api/
- Telegram's device-bound Secret Chats behavior for comparison: https://telegram.org/faq
- IETF MLS standard for future evaluation: https://www.rfc-editor.org/rfc/rfc9420.html

## Proposed account and room mapping

1. Each Django user maps to one server-managed Matrix identity. The browser receives only a user-scoped Matrix session/token; the homeserver administrator credential remains backend-only.
2. Each browser installation gets a distinct Matrix device ID and local cryptographic store.
3. A root group maps to a Matrix Space. The root's existing history remains the non-encrypted General conversation until the user explicitly starts a new secure group; secure General and every secure topic are separate encrypted rooms under that Space.
4. Topic membership, role changes, removals and new devices are synchronized through a durable outbox. Do not rely on a best-effort Django signal as the only cross-system consistency mechanism.
5. A secure-room membership change must update the encrypted room's membership and key state. Former members must not receive keys for subsequent messages.
6. The current Django model can retain display metadata and access mapping, but secure message payloads must go through the Matrix encrypted-room flow.

## Recovery and lost-device behavior

The UI must distinguish three operations:

- **Remove/revoke device:** stop future access from that device; does not erase data already copied to it.
- **Export recovery material:** explicitly export a recovery key or encrypted backup file, require confirmation that the user saved it, and never post the raw secret to the server.
- **Restore on a new device:** create fresh device keys, verify the user's recovery material, retrieve the server-side encrypted key backup (or import an encrypted export), then show which historical messages were successfully recovered.

A server-side key backup is acceptable only when its contents remain cryptographically unusable without the user's recovery secret. If a user loses every device and every recovery copy, the service must clearly explain that old encrypted history may be unrecoverable. It must never claim the account password alone can decrypt history unless the chosen protocol explicitly provides that guarantee.

## Why the current Messenger API is not enough

The current path is designed around readable server-side message data:
- `Message.body` is queried and serialized as text.
- Redis message caching stores serialized message payloads.
- message search expects server-readable message bodies.
- realtime events and conversation previews are derived from message bodies.
- current attachment endpoints manage files and view-once access, but do not implement an E2EE encrypted-attachment format and key distribution.

Consequently, encrypting only the composer text would leak or break data through search, replies, cache payloads, list previews, WebSocket events, notifications, exports and attachments. Secure conversations must use a separate encrypted transport path, with no plaintext preview fallback.


## Second-pass audit: implementation blockers

The following are concrete integration risks found by reviewing the current Messenger code and the existing Matrix Ready App definition. They are blockers, not optional polish.

### Existing functionality that must be reused, not rebuilt

- Normal direct/group messaging, message search, forwarding, reactions, read state, file uploads/downloads, scheduled messages, WebSocket delivery and Jitsi calls already have Django-owned implementations.
- Group topics already exist as child `Conversation` records; the existing conversation remains General. The frontend already has topic navigation and a create-topic flow.
- A Matrix Synapse Ready App template exists for optional independent deployment. Messenger can instead use the operator's already-running Synapse; the app template is not automatically launched or required by the backend Compose stack.
- The product already has a Django device/session management UI. Matrix cryptographic devices are distinct from Django browser sessions, so the UI needs a linked view rather than pretending they are the same object.

### Data-model and routing blockers

1. `get_or_create_dm(user_a, user_b)` explicitly filters to `security_mode=standard`. Secure DM/group creation is a separate React Matrix-SDK flow followed by `POST /api/messenger/secure/conversations/`, which verifies the live encrypted room before storing an immutable room binding. It never converts an existing normal conversation.
2. `Conversation.security_mode` distinguishes `standard` from `matrix_e2ee`; the mode and `matrix_room_id`/`matrix_space_id` mapping are immutable in model saves and guarded by PostgreSQL constraints/triggers. `POST /secure/conversations/` registers only a client-created room whose algorithm, signed-in device, member list and Space relationship were verified against the live homeserver. The normal conversation-create API cannot create or downgrade an E2EE room.
3. Existing message handlers are prevented from handling E2EE messages: ORM/PostgreSQL guards reject plaintext `Message`, `MessageAttachment` and server-side drafts; legacy message/search/event/media/member/invite/pin/call endpoints fail closed; the Matrix WebSocket subscription and message broadcast path excludes encrypted conversations; chat-list preview/unread queries skip E2EE conversations; and the React UI uses the Matrix client rather than Django history. These controls are required so an implementation bug cannot silently downgrade an E2EE room.
4. Conversation list data is built using the latest Django message body as a preview and database-backed unread counts. E2EE entries must not leak body text through previews, search, Redis cache inspection, error reporting, telemetry, notifications, logs or exports. Secure-room unread/activity state must be derived from Matrix event metadata or client sync without introducing plaintext message rows.
5. Existing attachment endpoints serve Django-managed files. They are not encrypted-media endpoints. Secure media must be encrypted client-side and sent as Matrix encrypted file content; the old download/view-once flow must reject E2EE records unless a compatible secure implementation exists.
6. Current call flows use the Messenger/Jitsi integration. Encrypted messages do not make a Jitsi call end-to-end encrypted. Secure chats must either use a separately verified secure-call design or explicitly show that calls are not covered by the message encryption guarantee.

### Correct room and migration semantics

- Security mode is immutable after a conversation is created. Do not add an "Enable encryption" action that flips an existing normal conversation in place.
- A newly created secure group must have an encrypted General timeline as well as encrypted topic rooms. Do not place an unencrypted General conversation beneath a group that the UI calls secure.
- Creating a secure variant from an existing normal DM/group creates a separate secure conversation with no copied plaintext history. The original remains normal and unchanged.
- A Matrix Space is an organizational container, not an encryption boundary for its names, room hierarchy, membership, timestamps or other metadata. Do not promise that E2EE hides metadata from the homeserver operator.
- Standard topic membership inherits root-group membership/permissions by application logic. Encrypted topic creation is now routed through Matrix and creates a separate encrypted room linked under the mapped Matrix Space; member keys are not copied from Django. Full post-creation member/role-change reconciliation is not yet backed by a durable Matrix outbox, so do not enable encrypted group membership mutations beyond the supported creation flow until that reconciler exists and is tested.
- Secure/public discovery, invite links, cross-server federation and room aliases need explicit policy. Do not make E2EE rooms searchable as public groups by default or allow arbitrary federation without a clear threat model.

### Element-like first-login and history-recovery state machine

A successful Django account login is not proof that a Matrix cryptographic device is trusted and does not itself give the new browser the keys to decrypt old messages. Match Element's explicit trust/recovery flow:

1. **Existing device already trusted:** create independent keys for the new browser and show an interactive verification request (for example, cross-signing / QR or emoji verification supported by the selected SDK). After the user verifies it, allow key requests to be handled by the trusted existing device. Do not copy private device keys from the previous browser.
2. **No old device available, recovery already set up:** ask the user for the recovery key/passphrase, validate it using Matrix Secret Storage, then restore the server-side encrypted key backup. A successful account password login alone must not unlock it.
3. **First secure-device setup:** initialize Rust crypto once for the browser profile; set up Secret Storage and cross-signing, establish key backup if absent, show the recovery key only to the user, and require an explicit saved-it confirmation before treating recovery as ready. Never reset an existing backup merely because local IndexedDB is empty.
4. **History status:** distinguish `device unverified`, `waiting for verification`, `recovery required`, `restoring`, `partially restored`, and `ready`. For an unavailable message key, show a per-message undecryptable state with actions to verify another device or restore backup. Never display an empty timeline as if the history has been successfully restored.
5. **No usable device or recovery secret:** preserve the account and future use where supported, but make unavailable old history explicit. Do not weaken trust or fallback to the normal Django transport.
6. **Device revocation:** revoke the Matrix device/session so it stops receiving future events/keys. Clearly explain that revocation cannot erase messages or keys already copied from that device.

Recovery keys are not the Django password. The frontend includes recovery-key setup/restore and existing-device SAS verification flows, but these flows still require end-to-end acceptance against the actual configured homeserver. Recovery keys must not be logged, sent to analytics, placed in URLs, stored in Django/Redis, or included in error telemetry. The UI must distinguish a valid backup restore from partial history recovery.

### Matrix identity and device safety

- Never send a Synapse admin token or application-service token to the browser. An application-service token can act as users in its configured namespace; it is not a per-user client credential.
- Do not use Synapse's admin "login as user" endpoint as the normal browser-login mechanism: official Synapse documentation states that this endpoint does not create a device entry. Device-aware authentication, token expiry/revocation and a one-device-per-browser crypto store are required.
- Use one Matrix client/crypto-store owner per browser profile and coordinate multiple tabs. The Matrix JS SDK warns that multiple clients sharing the same IndexedDB crypto store can corrupt state and cause decryption failures.
- Device verification, changed/unverified-device warnings, revoke behavior, recovery-key setup/export/import, and encrypted key backup are part of the feature—not later add-ons. Do not silently trust new devices or imply that account-password reset recovers E2EE history.
- Before production use of any Synapse deployment, qualify and pin its image version, harden configuration/secrets and backups, decide whether federation is permitted, and test the actual reverse-proxy/public URL and CORS behavior. These deployment choices apply to the existing homeserver too.

### Required integration gate

Before treating the currently implemented "Start encrypted chat" path as production-ready, run acceptance tests for the configured homeserver, device-bound sessions, encrypted text, room/Space membership validation, recovery, verification, revocation, browser-storage loss, CORS, backups and two independent users/devices. Durable post-creation membership/role reconciliation and encrypted media remain limitations. Keep unsupported features unavailable, and preserve fail-closed behavior: never fall back to Django plaintext.

## Current implementation boundary

- Migration `0019_conversation_security_mode` adds immutable `security_mode` state (existing conversations remain `standard`); migration `0020_matrix_identity_and_room_binding` adds Matrix identity/device tracking and room-binding protections.
- `src/messenger/matrix_service.py` provisions a Paas Deployer-specific Matrix identity per Django user through the Synapse Admin API, encrypts the generated account password with the Fernet key, logs in a real device ID, validates device ownership, verifies encrypted room bindings, and revokes devices. The Synapse administrator access token never leaves Django.
- The API exposes device-session, identity-resolution, device-list/revocation and secure-room-registration routes. The React app uses `matrix-js-sdk` with Rust/WASM crypto, separate browser-device state, SAS verification and recovery UI.
- A secure room is created by the Matrix client; Django validates its algorithm, device, participant list and (for a group) Space relationship before storing metadata. Standard conversations are not automatically migrated, and the ordinary conversation-create route refuses an E2EE request rather than silently making a plaintext conversation.
- ORM/PostgreSQL protections reject plaintext `Message`, `MessageAttachment` and server-side drafts for E2EE conversations. Legacy message/search/event/media/member/invite/pin/call routes and the standard Channels path fail closed for encrypted rooms; chat previews avoid plaintext leakage.
- The secure UI is intentionally text-only. Encrypted media and secure equivalents for search, forwarding, reactions, scheduled messages, read receipts and calls are not shipped. Durable reconciliation for later group membership/role changes is also incomplete; do not treat secure-group administration as production-ready.
- These repository checks protect boundaries but do not replace integration tests against the operator's actual Synapse. The feature remains opt-in and must not be described as production-certified until the acceptance gates below pass.

## Existing Synapse deployment and environment

- The default `compose.yaml` does not contain a Synapse service. The Django `web` service joins the existing external Synapse network through `MATRIX_DOCKER_NETWORK` (default `matrix_matrix`, if the Synapse Compose project directory is `/opt/matrix`). Confirm the actual name with `docker network ls --filter name=matrix --format '{{.Name}}'`; set the exact result in Paas Deploy(er)'s root `.env`. The network is external: if it does not exist, Compose fails rather than starting a new Synapse or creating an unrelated network.
- `MATRIX_HOMESERVER_URL` is the public HTTPS Matrix Client-Server API base URL. React connects to it directly, so a Docker-only hostname must never be used for this value. Verify that the reverse proxy passes the Matrix CORS pre-flight and response headers required by browser clients.
- `MATRIX_HOMESERVER_DOMAIN` must equal Synapse's configured `server_name`; it can differ from the public API hostname (for example, URL `https://matrix.example.com` with server name `example.com`).
- `MATRIX_HOMESERVER_INTERNAL_URL` is optional. It lets Django call Synapse over a private Docker network while the browser continues using the public URL. Only set it after the Django service is attached to the same private network and the configured service alias resolves there. An HTTP URL is accepted only for a single-label service hostname; it must stay on a private host-local Docker network.
- `MATRIX_ADMIN_ACCESS_TOKEN` and `MATRIX_IDENTITY_ENCRYPTION_KEY` are backend secrets; do not add them to the React environment or expose them in API responses. The integration provisions new Paas Deployer-specific Matrix users; it does not automatically reuse or modify the homeserver's existing user accounts.

## Rollout and acceptance gates

1. Configure the existing homeserver's public HTTPS endpoint, reverse proxy/CORS, admin access, TLS, account/device policy and backups. A second Synapse instance is not required.
2. Set `MATRIX_DOCKER_NETWORK` to the exact existing Synapse network name and `MATRIX_HOMESERVER_INTERNAL_URL=http://synapse:8008`. Recreate the Django `web` service so it joins that network. No Synapse service is added to this Compose project.
3. With two independent Django users and two browser devices, verify account provisioning, encrypted DM/group creation, delivery, SAS verification, first-device recovery setup, recovery on another device, invalid recovery material and device revocation.
4. Verify that a new device cannot read prior history without verification or a valid recovery backup, that server-side logs/cache/API responses never contain plaintext secure messages or recovery secrets, and that losing IndexedDB fails closed rather than reusing the old device ID.
5. Confirm unsupported features remain blocked in secure rooms and exercise user removal/role-change behavior. Until durable Matrix membership reconciliation is implemented and tested, do not enable unrestricted membership mutations for encrypted groups.
6. Run the backend Django test suite and frontend build/secure-mode tests against the candidate commit, then run live acceptance tests against the real Synapse. Only after all critical checks pass should the feature be considered production-ready.

## Explicit non-goals

- Do not invent a custom Double Ratchet/MLS implementation.
- Do not store a shared plaintext group key in Django.
- Do not treat HTTPS or database-at-rest encryption as end-to-end encryption.
- Do not advertise server-side plaintext search for encrypted rooms.
- Do not promise that key export can recover history if the exported file or recovery secret was not saved.
