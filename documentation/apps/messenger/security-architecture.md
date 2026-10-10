# Messenger secure-chat architecture decision

## Decision status

**End-to-end encryption is not implemented yet.** Existing Messenger conversations continue to use the current server-readable message path. They must not be labelled or presented as end-to-end encrypted.

A preparation layer is now committed: each conversation has an immutable `security_mode`; normal conversations default to `standard`; requests for `matrix_e2ee` fail with HTTP 503 rather than silently creating a plaintext chat; Django message/media creation is blocked for conversations marked encrypted; and the React Messenger hides its ordinary timeline, composer, upload, search and call controls for such records. This is a fail-closed boundary, not yet an active Matrix implementation. The device login, verification, key-share, backup/recovery and encrypted event transport remain unimplemented.

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
- A self-hosted Matrix homeserver (for example, Synapse) operated alongside the existing Django platform. This avoids depending on a public third-party homeserver for private room data. The backend repository already includes a Ready App definition named `matrix-synapse-with-postgresql`; that makes deployment available, but it does not by itself provision user identities or integrate Matrix encryption into Messenger.

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
- A Matrix Synapse Ready App template already exists in the app catalog. It deploys a homeserver and PostgreSQL, but it does not integrate that homeserver with Messenger identities, devices, rooms, or encryption.
- The product already has a Django device/session management UI. Matrix cryptographic devices are distinct from Django browser sessions, so the UI needs a linked view rather than pretending they are the same object.

### Data-model and routing blockers

1. `get_or_create_dm(user_a, user_b)` now explicitly filters to `security_mode=standard`, preventing the ordinary DM path from selecting a Matrix conversation. The future Matrix DM provisioner must be separate and bind an immutable security mode to the actual Matrix room ID; no such provisioner is shipped yet.
2. `Conversation.security_mode` now distinguishes `standard` from `matrix_e2ee`, and is immutable through the model save path and a PostgreSQL trigger. There is still no Matrix room binding or working secure-chat creation endpoint, so no existing endpoint can provision a usable E2EE room.
3. Existing message handlers assume the conversation has Django `Message` rows. Model and PostgreSQL database guards reject plaintext `Message`, `MessageAttachment`, and server-side composer-draft writes for `matrix_e2ee` conversations. The legacy HTTP routes now fail closed for message read/write/search, forwarding, edit/delete, reactions, schedules, event sync, attachment downloads/media, public join/invites, membership, pins/read receipts, and Jitsi calls. The React UI does not render its ordinary timeline, composer, upload, search or call controls for that mode. These guards prevent the old path from being used, but they are not a substitute for a working Matrix transport.
4. Conversation list data is built using the latest Django message body as a preview and database-backed unread counts. E2EE entries must not leak body text through previews, search, Redis cache inspection, error reporting, telemetry, notifications, logs or exports. Secure-room unread/activity state must be derived from Matrix event metadata or client sync without introducing plaintext message rows.
5. Existing attachment endpoints serve Django-managed files. They are not encrypted-media endpoints. Secure media must be encrypted client-side and sent as Matrix encrypted file content; the old download/view-once flow must reject E2EE records unless a compatible secure implementation exists.
6. Current call flows use the Messenger/Jitsi integration. Encrypted messages do not make a Jitsi call end-to-end encrypted. Secure chats must either use a separately verified secure-call design or explicitly show that calls are not covered by the message encryption guarantee.

### Correct room and migration semantics

- Security mode is immutable after a conversation is created. Do not add an "Enable encryption" action that flips an existing normal conversation in place.
- A newly created secure group must have an encrypted General timeline as well as encrypted topic rooms. Do not place an unencrypted General conversation beneath a group that the UI calls secure.
- Creating a secure variant from an existing normal DM/group creates a separate secure conversation with no copied plaintext history. The original remains normal and unchanged.
- A Matrix Space is an organizational container, not an encryption boundary for its names, room hierarchy, membership, timestamps or other metadata. Do not promise that E2EE hides metadata from the homeserver operator.
- Topic membership currently inherits root-group membership/permissions by application logic, with local topic removal behavior. Secure room membership synchronization must be durable and idempotent; a best-effort Django signal is not sufficient. Reconcile the Matrix room's actual membership against a persisted desired state and block sensitive operations while required membership changes are pending or failed.
- Secure/public discovery, invite links, cross-server federation and room aliases need explicit policy. Do not make E2EE rooms searchable as public groups by default or allow arbitrary federation without a clear threat model.

### Element-like first-login and history-recovery state machine

A successful Django account login is not proof that a Matrix cryptographic device is trusted and does not itself give the new browser the keys to decrypt old messages. Match Element's explicit trust/recovery flow:

1. **Existing device already trusted:** create independent keys for the new browser and show an interactive verification request (for example, cross-signing / QR or emoji verification supported by the selected SDK). After the user verifies it, allow key requests to be handled by the trusted existing device. Do not copy private device keys from the previous browser.
2. **No old device available, recovery already set up:** ask the user for the recovery key/passphrase, validate it using Matrix Secret Storage, then restore the server-side encrypted key backup. A successful account password login alone must not unlock it.
3. **First secure-device setup:** initialize Rust crypto once for the browser profile; set up Secret Storage and cross-signing, establish key backup if absent, show the recovery key only to the user, and require an explicit saved-it confirmation before treating recovery as ready. Never reset an existing backup merely because local IndexedDB is empty.
4. **History status:** distinguish `device unverified`, `waiting for verification`, `recovery required`, `restoring`, `partially restored`, and `ready`. For an unavailable message key, show a per-message undecryptable state with actions to verify another device or restore backup. Never display an empty timeline as if the history has been successfully restored.
5. **No usable device or recovery secret:** preserve the account and future use where supported, but make unavailable old history explicit. Do not weaken trust or fallback to the normal Django transport.
6. **Device revocation:** revoke the Matrix device/session so it stops receiving future events/keys. Clearly explain that revocation cannot erase messages or keys already copied from that device.

Recovery keys are not the Django password. The recovery key and encrypted backup must not be logged, sent to analytics, placed in URLs, stored in Django/Redis, or included in plaintext error telemetry. The UI must distinguish a valid backup restore from partial history recovery. These states are requirements for the future SDK integration; they are not claimed as shipped behavior.

### Matrix identity and device safety

- Never send a Synapse admin token or application-service token to the browser. An application-service token can act as users in its configured namespace; it is not a per-user client credential.
- Do not use Synapse's admin "login as user" endpoint as the normal browser-login mechanism: official Synapse documentation states that this endpoint does not create a device entry. Device-aware authentication, token expiry/revocation and a one-device-per-browser crypto store are required.
- Use one Matrix client/crypto-store owner per browser profile and coordinate multiple tabs. The Matrix JS SDK warns that multiple clients sharing the same IndexedDB crypto store can corrupt state and cause decryption failures.
- Device verification, changed/unverified-device warnings, revoke behavior, recovery-key setup/export/import, and encrypted key backup are part of the feature—not later add-ons. Do not silently trust new devices or imply that account-password reset recovers E2EE history.
- The app-catalog template currently uses a mutable `matrixdotorg/synapse:latest` image and exposes both client and federation resources. Before production use, pin and qualify a supported image version, harden configuration/secrets and backups, decide whether federation is permitted, and test the actual reverse-proxy/public URL setup.

### Required integration gate

Before exposing a "Start encrypted chat" action, implement and test all of the following together: immutable mode and secure-room mapping; device-bound Matrix authentication without browser access to server-admin credentials; encrypted text/reply/media transport; membership reconciliation; secure list previews and unread state; explicit handling of unsupported features (search, forwarding, scheduled messages, view-once, calls); device verification; recovery; revocation; and multi-tab/browser-storage-loss tests. If any required secure path is unavailable, fail closed for that conversation rather than falling back to Django plaintext.

## Current implementation boundary

- Migration `0019_conversation_security_mode` adds the `security_mode` field, defaulting every existing conversation to `standard`.
- ORM saves reject changes to a conversation's security mode; PostgreSQL also gets a trigger to reject direct `UPDATE security_mode` attempts. SQLite-based tests use the model-level check.
- `Message.save()` and `MessageAttachment.save()` reject newly-created plaintext Django records for a conversation explicitly marked `matrix_e2ee`.
- `POST /api/messenger/conversations/` returns HTTP 503 when `security_mode=matrix_e2ee` is requested before Matrix is ready. It does not return an existing normal DM as a substitute.
- The topics endpoint rejects access/creation for encrypted records until backed by Matrix rooms; public discovery and legacy join/request/invite paths exclude or reject encrypted rooms. The ordinary Django Channels subscription does not admit encrypted rooms, server-side drafts are rejected/hidden, and message fan-out refuses to broadcast a body for those rooms. The React chat pane renders an unavailable state instead of the plaintext timeline, composer, uploads, search and ordinary calls.
- PostgreSQL triggers additionally block attempts to use `bulk_create` or direct row updates to insert/update plaintext messages, attachments, or non-empty composer drafts in encrypted conversations, and stop plaintext rows being moved out of an encrypted room. These database guards are installed only on PostgreSQL; model/API guards remain the cross-database layer.

These are safe boundaries and regression tests—not the final Element-like experience. They deliberately leave secure chat unavailable instead of simulating verification or key recovery. Do not create `matrix_e2ee` conversations in production by hand: no Matrix room provisioning/session endpoint currently exists.

## Rollout and acceptance gates

1. Deploy and configure the homeserver, its database, TLS, backups, registration policy and server-side secrets.
2. Implement Django-to-Matrix identity provisioning and a scoped session endpoint. Never send an administrator token to the browser.
3. Add explicit secure-conversation creation and room/Space mapping. Leave existing conversations unchanged.
4. Integrate Matrix SDK crypto and the crypto WASM package in the frontend; persist the crypto store safely in IndexedDB.
5. Implement device list, verification, unexpected-key-change warnings, recovery setup, recovery export/import, and device revocation.
6. Handle text, reply/quote metadata, attachments, voice/video files, reactions, search, previews, event sync, membership changes, and new-device key sharing without exposing plaintext to Django/Redis.
7. Test two users on independent devices, offline delivery, malicious/unknown device changes, device removal, lost local storage, valid/invalid recovery material, secure media download and room membership changes.
8. Only call the feature end-to-end encrypted after protocol integration and all critical tests pass. Until then the UI must say that secure chat is unavailable or not yet configured.

## Explicit non-goals

- Do not invent a custom Double Ratchet/MLS implementation.
- Do not store a shared plaintext group key in Django.
- Do not treat HTTPS or database-at-rest encryption as end-to-end encryption.
- Do not advertise server-side plaintext search for encrypted rooms.
- Do not promise that key export can recover history if the exported file or recovery secret was not saved.
