# messenger serializers

## UserMiniSerializer

Viewer-aware user card: id/username/color plus derived avatar, is_contact, is_blocked, is_online and bio. These values come from bulk context maps produced by the view. The serializer deliberately uses safe defaults when a map is absent instead of issuing hidden database queries.

## MessageAttachmentSerializer

Exposes file metadata plus derived url and view_once_state. For view-once recipients, url is omitted until the explicit open operation; senders may receive a download path. A purged attachment has no usable URL.

## ReactionSerializer

Read-only reaction row nested with UserMiniSerializer.

## MessageSerializer

All message fields are read-only in representation. It derives reactions, reply_to_preview and viewer-specific read_state from bulk context/prefetched relations. It exposes scheduled state, edit/delete/system flags and forwarding metadata.

## ParticipantSerializer

Read-only membership representation containing role and per-action flags (send, media, add members, pin, change info), mute/pin/read/left timestamps.

## ConversationListSerializer

Viewer-oriented chat-list payload. It derives participants, last_message, unread_count, peer, pin state and draft text from preloaded/annotated data. In lean-list mode, group participant payloads are deliberately reduced to the caller's row to avoid multi-megabyte lists.

## ConversationDetailSerializer

Extends conversation list with invite-links and pins, both attached by the view's preparation function.

## GroupInviteLinkSerializer / ContactSerializer / ProfilePhotoSerializer / ProfilePhotoPrivacySerializer / JoinRequestSerializer

These expose bounded metadata and viewer-specific representations. Profile privacy returns allowed_user_ids; invite URLs are derived client paths; join-request user data uses UserMiniSerializer.

## Sensitivity

- viewer context affects contact/block/online/avatar/bio state;
- message/attachment URLs depend on current viewer and view-once state;
- conversation payloads depend on active participation;
- profile photos depend on privacy policy;
- nested user data comes from users.Profile/User but is not owned by messenger.

## Query contract

The module explicitly states that view/context builders should do DB work. SerializerMethodField is shaping logic, not a replacement for select_related/prefetch/annotation.

Source: src/messenger/serializers.py.
