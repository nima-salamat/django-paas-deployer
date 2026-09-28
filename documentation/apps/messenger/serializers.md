# messenger serializers

Each serializer is documented independently. Serialization is representation logic; API/queryset/participant checks remain the authorization boundary.

## UserMiniSerializer
Compact viewer-aware user card. Derived contact/block/avatar/online/bio values come from view-built context maps; absent context uses safe defaults instead of hidden per-row queries.

## MessageAttachmentSerializer
Attachment metadata plus derived URL/view-once state. View-once recipients do not receive a usable URL until the explicit open operation; purged attachments have no usable file URL.

## ReactionSerializer
Read-only reaction representation with nested user presentation. It is not an input authority for reaction ownership.

## MessageSerializer
Message representation including body, sender, reply/forward metadata, edit/delete/system flags, scheduled state and reactions. Viewer-specific read state and previews are derived from prefetched/bulk context. Mutation authorization is performed by the API.

## ParticipantSerializer
Read-only ConversationParticipant representation: role, send/media/member/pin/change-info flags, mute/pin/read/left state. These values describe current membership state.

## ConversationListSerializer
Viewer-oriented chat-list projection. It derives participants, last message, unread count, peer, pin state and draft text. Lean-list mode intentionally reduces group participant payload.

## ConversationDetailSerializer
Detailed conversation projection extending the list representation with prepared invite-link/pin/member data. It does not bypass participant checks.

## GroupInviteLinkSerializer
Invite capability metadata. Validity comes from active/use/expiry model rules; serialization does not itself grant membership.

## ContactSerializer
Caller-owned contact representation with viewer-aware user data. Contact creation/deletion authorization belongs to the contacts API.

## ProfilePhotoSerializer
Caller profile-photo metadata. File access remains subject to authenticated media and photo-privacy policy.

## ProfilePhotoPrivacySerializer
Caller photo-privacy representation. Allowed-user IDs are policy data, not authorization by themselves.

## JoinRequestSerializer
JoinRequest plus requesting-user presentation. status/decision fields are durable workflow state; legal transition is owned by the join-request API.

## Context/performance contract
SerializerMethodField values depend on view-built context. Views are responsible for select_related/prefetch/annotation; adding derived fields must be reviewed for authorization context and query cost.

Source: src/messenger/serializers.py.