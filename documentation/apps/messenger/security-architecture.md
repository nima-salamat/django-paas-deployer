# Messenger secure-chat architecture decision

## Decision status

**Architecture selected; end-to-end encryption is not implemented yet.** Existing Messenger conversations continue to use the current server-readable message path. They must not be labelled or presented as end-to-end encrypted.

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
- A self-hosted Matrix homeserver (for example, Synapse) operated alongside the existing Django platform. This avoids depending on a public third-party homeserver for private room data.

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
