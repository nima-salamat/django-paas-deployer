# messenger — complete model field reference

Source-derived from `src/messenger/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## UserBio

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `user` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_bio; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `text` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the text required by the UserBio contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `user`: `OneToOneField` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_bio"`
- `text`: `CharField` — declaration: `max_length=255, blank=True, default=""`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## Contact

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `owner` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_contacts; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `contact` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_contacted_by; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `nickname` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the nickname required by the Contact contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `owner`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_contacts"`
- `contact`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_contacted_by"`
- `nickname`: `CharField` — declaration: `max_length=120, blank=True, default=""`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## Block

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `blocker` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_blocks; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `blocked` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_blocked_by; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `blocker`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_blocks"`
- `blocked`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_blocked_by"`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## ProfilePhotoPrivacy

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `user` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_photo_privacy; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `scope` | `CharField` | no | no | `Scope.EVERYONE` | DB non-null, blank not allowed, choices; choices | Stores the scope required by the ProfilePhotoPrivacy contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `user`: `OneToOneField` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_photo_privacy"`
- `scope`: `CharField` — declaration: `max_length=20, choices=Scope.choices, default=Scope.EVERYONE`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## ProfilePhotoAllowed

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `privacy` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=allowed_users; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `privacy`: `ForeignKey` — declaration: `ProfilePhotoPrivacy, on_delete=models.CASCADE, related_name="allowed_users"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## Conversation

**Bases:** `models.Model`  
**Declared fields:** 18

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `public_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stable public identifier for API/resource references. |
| `type` | `CharField` | no | no | `Type.PRIVATE` | DB non-null, blank not allowed, indexed, choices; choices | Stores the type required by the Conversation contract. |
| `security_mode` | `CharField` | no | no | `SecurityMode.STANDARD` (`standard`) | DB non-null, blank not allowed, indexed, choices | Immutable transport boundary. `matrix_e2ee` is guarded but unavailable until Matrix device and recovery integration is shipped. |
| `title` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-facing title. |
| `description` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `avatar` | `ImageField` | yes | yes | `—` | DB nullable, blank allowed | Stores the avatar required by the Conversation contract. |
| `is_public` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed, indexed | Stores the is public required by the Conversation contract. |
| `is_closed` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is closed required by the Conversation contract. |
| `is_forum` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed, indexed | Marks a root group that exposes child topic conversations. |
| `parent_conversation` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; self relation; CASCADE; related_name=topic_conversations | Links a topic to its root conversation. |
| `requires_approval` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the requires approval required by the Conversation contract. |
| `members_can_add` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the members can add required by the Conversation contract. |
| `only_admins_send` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the only admins send required by the Conversation contract. |
| `history_visibility` | `CharField` | no | no | `HistoryVisibility.ALL` | DB non-null, blank not allowed, choices; choices | Stores the history visibility required by the Conversation contract. |
| `created_by` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; related_name=created_conversations; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |
| `last_message_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Message relationship used for message context/history. |

### Declaration details

- `public_id`: `UUIDField` — declaration: `default=uuid.uuid4, unique=True, editable=False, db_index=True`
- `type`: `CharField` — declaration: `max_length=10, choices=Type.choices, default=Type.PRIVATE, db_index=True`
- `security_mode`: `CharField` — declaration: `max_length=20, choices=SecurityMode.choices, default=SecurityMode.STANDARD, db_index=True`
- `title`: `CharField` — declaration: `max_length=255, blank=True, default=""`
- `description`: `TextField` — declaration: `blank=True, default=""`
- `avatar`: `ImageField` — declaration: `upload_to="messenger/groups/", null=True, blank=True`
- `is_public`: `BooleanField` — declaration: `default=False, db_index=True`
- `is_closed`: `BooleanField` — declaration: `default=False`
- `is_forum`: `BooleanField` — declaration: `default=False, db_index=True`
- `parent_conversation`: `ForeignKey` — declaration: `self, on_delete=models.CASCADE, null=True, blank=True, related_name="topic_conversations"`
- `requires_approval`: `BooleanField` — declaration: `default=False`
- `members_can_add`: `BooleanField` — declaration: `default=True`
- `only_admins_send`: `BooleanField` — declaration: `default=False`
- `history_visibility`: `CharField` — declaration: `max_length=12, choices=HistoryVisibility.choices, default=HistoryVisibility.ALL,`
- `created_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, related_name="created_conversations"`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`
- `last_message_at`: `DateTimeField` — declaration: `null=True, blank=True, db_index=True`

## ConversationParticipant

**Bases:** `models.Model`  
**Declared fields:** 16

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=participants; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_participations; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `role` | `CharField` | no | no | `Role.MEMBER` | DB non-null, blank not allowed, choices; choices | Stores the role required by the ConversationParticipant contract. |
| `can_send_messages` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Message relationship used for message context/history. |
| `can_send_media` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the can send media required by the ConversationParticipant contract. |
| `can_add_members` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the can add members required by the ConversationParticipant contract. |
| `can_pin_messages` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Message relationship used for message context/history. |
| `can_change_info` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the can change info required by the ConversationParticipant contract. |
| `is_muted` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is muted required by the ConversationParticipant contract. |
| `joined_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the joined at required by the ConversationParticipant contract. |
| `last_read_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last read at required by the ConversationParticipant contract. |
| `left_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the left at required by the ConversationParticipant contract. |
| `is_pinned` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is pinned required by the ConversationParticipant contract. |
| `pinned_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the pinned at required by the ConversationParticipant contract. |
| `draft_text` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the draft text required by the ConversationParticipant contract. |
| `draft_updated_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the draft updated at required by the ConversationParticipant contract. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="participants"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_participations"`
- `role`: `CharField` — declaration: `max_length=10, choices=Role.choices, default=Role.MEMBER`
- `can_send_messages`: `BooleanField` — declaration: `default=True`
- `can_send_media`: `BooleanField` — declaration: `default=True`
- `can_add_members`: `BooleanField` — declaration: `default=False`
- `can_pin_messages`: `BooleanField` — declaration: `default=False`
- `can_change_info`: `BooleanField` — declaration: `default=False`
- `is_muted`: `BooleanField` — declaration: `default=False`
- `joined_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `last_read_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `left_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `is_pinned`: `BooleanField` — declaration: `default=False`
- `pinned_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `draft_text`: `TextField` — declaration: `blank=True, default=""`
- `draft_updated_at`: `DateTimeField` — declaration: `null=True, blank=True`

## GroupInviteLink

**Bases:** `models.Model`  
**Declared fields:** 8

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=invite_links; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `code` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique, indexed | Short verification/invitation/action code. |
| `created_by` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable state. |
| `max_uses` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the max uses required by the GroupInviteLink contract. |
| `uses` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the uses required by the GroupInviteLink contract. |
| `expires_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Time after which the credential/session/invite is invalid. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="invite_links"`
- `code`: `CharField` — declaration: `max_length=32, unique=True, db_index=True`
- `created_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True`
- `is_active`: `BooleanField` — declaration: `default=True`
- `max_uses`: `PositiveIntegerField` — declaration: `null=True, blank=True`
- `uses`: `PositiveIntegerField` — declaration: `default=0`
- `expires_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## JoinRequest

**Bases:** `models.Model`  
**Declared fields:** 6

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=join_requests; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_join_requests; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `status` | `CharField` | no | no | `Status.PENDING` | DB non-null, blank not allowed, indexed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `decided_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=messenger_join_requests_decided; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `decided_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the decided at required by the JoinRequest contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="join_requests"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_join_requests"`
- `status`: `CharField` — declaration: `max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True`
- `decided_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="messenger_join_requests_decided",`
- `decided_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`

## Message

**Bases:** `models.Model`  
**Declared fields:** 14

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messages; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `sender` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; related_name=messenger_messages; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `body` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Primary body/content payload. |
| `reply_to` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=replies; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `forwarded_from` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=forwarded_messages; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `forwarded_from_message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=forwards; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `is_edited` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is edited required by the Message contract. |
| `is_system` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is system required by the Message contract. |
| `is_deleted` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is deleted required by the Message contract. |
| `client_message_id` | `CharField` | yes | yes | `—` | DB nullable, blank allowed | Message relationship used for message context/history. |
| `scheduled_for` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the scheduled for required by the Message contract. |
| `is_scheduled` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed, indexed | Stores the is scheduled required by the Message contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="messages"`
- `sender`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, related_name="messenger_messages"`
- `body`: `TextField` — declaration: `blank=True, default=""`
- `reply_to`: `ForeignKey` — declaration: `"self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"`
- `forwarded_from`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="forwarded_messages"`
- `forwarded_from_message`: `ForeignKey` — declaration: `"self", on_delete=models.SET_NULL, null=True, blank=True, related_name="forwards"`
- `is_edited`: `BooleanField` — declaration: `default=False`
- `is_system`: `BooleanField` — declaration: `default=False`
- `is_deleted`: `BooleanField` — declaration: `default=False`
- `client_message_id`: `CharField` — declaration: `max_length=128, null=True, blank=True, help_text="Client-generated idempotency key for message submission.",`
- `scheduled_for`: `DateTimeField` — declaration: `null=True, blank=True, db_index=True`
- `is_scheduled`: `BooleanField` — declaration: `default=False, db_index=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## MessengerEvent

**Bases:** `models.Model`  
**Declared fields:** 8

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `event_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stores the event id required by the MessengerEvent contract. |
| `event_type` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the event type required by the MessengerEvent contract. |
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_events; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `actor` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=messenger_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=messenger_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `call` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=messenger_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `payload` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the payload required by the MessengerEvent contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |

### Declaration details

- `event_id`: `UUIDField` — declaration: `default=uuid.uuid4, unique=True, editable=False, db_index=True`
- `event_type`: `CharField` — declaration: `max_length=64, db_index=True`
- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="messenger_events"`
- `actor`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="messenger_events"`
- `message`: `ForeignKey` — declaration: `Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="messenger_events"`
- `call`: `ForeignKey` — declaration: `"CallSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="messenger_events"`
- `payload`: `JSONField` — declaration: `default=dict, blank=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`

## MessageReaction

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `message` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=reactions; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_reactions; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `emoji` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the emoji required by the MessageReaction contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `message`: `ForeignKey` — declaration: `Message, on_delete=models.CASCADE, related_name="reactions"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_reactions"`
- `emoji`: `CharField` — declaration: `max_length=32`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## MessageReadReceipt

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `message` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=read_receipts; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_read_receipts; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `seen_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the seen at required by the MessageReadReceipt contract. |

### Declaration details

- `message`: `ForeignKey` — declaration: `Message, on_delete=models.CASCADE, related_name="read_receipts"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_read_receipts"`
- `seen_at`: `DateTimeField` — declaration: `auto_now_add=True`

## MessageAttachment

**Bases:** `models.Model`  
**Declared fields:** 15

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=attachments; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=attachments; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `uploaded_by` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `file` | `FileField` | no | no | `—` | DB non-null, blank not allowed | Stores the file required by the MessageAttachment contract. |
| `original_filename` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the original filename required by the MessageAttachment contract. |
| `content_type` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the content type required by the MessageAttachment contract. |
| `size` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the size required by the MessageAttachment contract. |
| `kind` | `CharField` | no | no | `Kind.FILE` | DB non-null, blank not allowed, choices; choices | Stores the kind required by the MessageAttachment contract. |
| `width` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the width required by the MessageAttachment contract. |
| `height` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the height required by the MessageAttachment contract. |
| `duration` | `FloatField` | yes | yes | `—` | DB nullable, blank allowed | Stores the duration required by the MessageAttachment contract. |
| `is_spoiler` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is spoiler required by the MessageAttachment contract. |
| `is_view_once` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is view once required by the MessageAttachment contract. |
| `is_purged` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is purged required by the MessageAttachment contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="attachments"`
- `message`: `ForeignKey` — declaration: `Message, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments"`
- `uploaded_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True`
- `file`: `FileField` — declaration: `upload_to=messenger_attachment_path`
- `original_filename`: `CharField` — declaration: `max_length=255`
- `content_type`: `CharField` — declaration: `max_length=120, blank=True, default=""`
- `size`: `PositiveIntegerField` — declaration: `default=0`
- `kind`: `CharField` — declaration: `max_length=10, choices=Kind.choices, default=Kind.FILE`
- `width`: `PositiveIntegerField` — declaration: `null=True, blank=True`
- `height`: `PositiveIntegerField` — declaration: `null=True, blank=True`
- `duration`: `FloatField` — declaration: `null=True, blank=True`
- `is_spoiler`: `BooleanField` — declaration: `default=False`
- `is_view_once`: `BooleanField` — declaration: `default=False`
- `is_purged`: `BooleanField` — declaration: `default=False`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## AttachmentViewOnceOpen

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `attachment` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=view_once_opens; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=view_once_opens; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `opened_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the opened at required by the AttachmentViewOnceOpen contract. |
| `expires_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Time after which the credential/session/invite is invalid. |

### Declaration details

- `attachment`: `ForeignKey` — declaration: `MessageAttachment, on_delete=models.CASCADE, related_name="view_once_opens"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="view_once_opens"`
- `opened_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `expires_at`: `DateTimeField` — declaration: `null=True, blank=True, db_index=True`

## PinnedMessage

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=pins; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `message` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `pinned_by` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `pinned_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the pinned at required by the PinnedMessage contract. |

### Declaration details

- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="pins"`
- `message`: `ForeignKey` — declaration: `Message, on_delete=models.CASCADE`
- `pinned_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True`
- `pinned_at`: `DateTimeField` — declaration: `auto_now_add=True`

## CallSession

**Bases:** `models.Model`  
**Declared fields:** 12

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `public_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stable public identifier for API/resource references. |
| `conversation` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=call_sessions; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `initiator` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; related_name=messenger_calls_started; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `is_video` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is video required by the CallSession contract. |
| `status` | `CharField` | no | no | `Status.RINGING` | DB non-null, blank not allowed, indexed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `room_name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the room name required by the CallSession contract. |
| `started_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the started at required by the CallSession contract. |
| `answered_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the answered at required by the CallSession contract. |
| `ended_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the ended at required by the CallSession contract. |
| `duration_seconds` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the duration seconds required by the CallSession contract. |
| `start_message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=+; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `end_message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=+; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |

### Declaration details

- `public_id`: `UUIDField` — declaration: `default=uuid.uuid4, unique=True, editable=False, db_index=True`
- `conversation`: `ForeignKey` — declaration: `Conversation, on_delete=models.CASCADE, related_name="call_sessions"`
- `initiator`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, related_name="messenger_calls_started"`
- `is_video`: `BooleanField` — declaration: `default=False`
- `status`: `CharField` — declaration: `max_length=16, choices=Status.choices, default=Status.RINGING, db_index=True`
- `room_name`: `CharField` — declaration: `max_length=120, blank=True, default=""`
- `started_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `answered_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `ended_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `duration_seconds`: `PositiveIntegerField` — declaration: `default=0`
- `start_message`: `ForeignKey` — declaration: `Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"`
- `end_message`: `ForeignKey` — declaration: `Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"`

## CallSessionParticipant

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `call` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=participants; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messenger_call_participations; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `joined_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the joined at required by the CallSessionParticipant contract. |
| `left_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the left at required by the CallSessionParticipant contract. |

### Declaration details

- `call`: `ForeignKey` — declaration: `CallSession, on_delete=models.CASCADE, related_name="participants"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="messenger_call_participations"`
- `joined_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `left_at`: `DateTimeField` — declaration: `null=True, blank=True`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.
