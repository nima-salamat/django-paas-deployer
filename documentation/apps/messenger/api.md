# messenger API

Canonical mount: /api/messenger/. Routes and methods below are derived from src/messenger/urls.py and the registered APIView classes. Authentication is SessionJWTAuthentication + IsAuthenticated; authorization is participant/role/viewer scoped.

## Exact HTTP surface

### Users and profile

| Method | Route |
|---|---|
| GET | /api/messenger/users/search/ |
| GET, POST | /api/messenger/contacts/ |
| DELETE | /api/messenger/contacts/<int:user_id>/ |
| GET, POST | /api/messenger/blocks/ |
| POST | /api/messenger/blocks/<int:user_id>/unblock/ |
| GET | /api/messenger/users/<int:user_id>/profile/ |
| GET | /api/messenger/users/by-username/ |
| GET | /api/messenger/me/photos/ |
| PATCH | /api/messenger/me/photo-privacy/ |
| GET, PATCH | /api/messenger/me/bio/ |
| POST | /api/messenger/me/profile-broadcast/ |

### Conversations and messages

| Method | Route | Important contract |
|---|---|---|
| GET, POST | /api/messenger/conversations/ | List accessible conversations or create private/group conversation. |
| GET, PATCH | /api/messenger/conversations/<int:pk>/ | Conversation detail/settings; no DELETE handler is registered. |
| GET, POST | /api/messenger/conversations/<int:pk>/messages/ | History/create; create validates membership, capability, attachments and client_message_id idempotency. |
| GET | /api/messenger/conversations/<int:pk>/events/ | Durable reconnect cursor; after_id and bounded limit are query inputs. |
| GET | /api/messenger/conversations/<int:pk>/messages/search/ | Participant-scoped message search. |
| GET | /api/messenger/conversations/<int:pk>/scheduled/ | Caller-visible scheduled messages. |
| POST | /api/messenger/messages/<int:pk>/cancel-schedule/ | Cancel pending sender-owned scheduled message. |
| POST | /api/messenger/conversations/<int:pk>/read/ | Update caller read state; returns the authoritative `last_read_at` cursor and invalidates the caller's conversation-list projection when it advances. |
| POST | /api/messenger/messages/<int:pk>/react/ | Reaction toggle. |
| PATCH | /api/messenger/messages/<int:pk>/edit/ | Sender-authorized edit. |
| DELETE | /api/messenger/messages/<int:pk>/ | Sender/role-constrained delete. |
| POST | /api/messenger/messages/<int:pk>/forward/ | Forward accessible message to authorized destination. |
| GET | /api/messenger/messages/<int:pk>/readers/ | Read-receipt breakdown. |

### Pins, invites and membership

| Method | Route | Important contract |
|---|---|---|
| POST | /api/messenger/conversations/<int:pk>/pin/ | Caller conversation-list pin state. |
| POST | /api/messenger/messages/<int:pk>/pin/ | Message pin. |
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

### Media and calls

| Method | Route |
|---|---|
| GET | /api/messenger/conversations/<int:pk>/media/ |
| POST | /api/messenger/conversations/<int:pk>/cleanup/ |
| GET | /api/messenger/attachments/<int:pk>/download/ |
| POST | /api/messenger/attachments/<int:pk>/view-once/ |
| POST | /api/messenger/conversations/<int:pk>/call/ |
| GET | /api/messenger/conversations/<int:pk>/call/join/ |
| GET | /api/messenger/conversations/<int:pk>/call/active/ |
| POST | /api/messenger/conversations/<int:pk>/call/end/ |

## Durable/realtime contract

HTTP -> authentication -> participant/role/object authorization -> API validation -> durable mutation -> MessengerEvent where required -> transaction.on_commit -> cache/Channels broadcast.

The database is authoritative. Redis is a hot cache. /conversations/<pk>/events/ is the durable reconnect path. Message creation can update the message cache after commit; profile/member/join/call mutations broadcast events; view-once opening creates AttachmentViewOnceOpen and later purge may delete the file; Messenger membership changes can revoke ServiceShare access; scheduled delivery is Celery/Beat driven.

Source: src/messenger/urls.py, src/messenger/api/*.py, src/messenger/serializers.py, src/messenger/events.py, src/messenger/consumers.py, src/messenger/tasks.py.