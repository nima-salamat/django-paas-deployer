# messenger

## Responsibility
Real-time messaging, conversations, contacts, groups, attachments, reactions and calls. Service sharing may consume this app, but deployment execution does not belong here.

## API base
/api/messenger/

## Main endpoints
Users/contacts: /users/search/, /contacts/, /blocks/.
Conversations/messages: /conversations/, /conversations/<pk>/messages/, /messages/<pk>/.
Groups/membership: /groups/, /join/, /conversations/<pk>/members/ and related management endpoints.
Media/profile: /attachments/, /me/photos/, /users/<user_id>/profile/, /me/bio/.
Join requests: /conversations/<pk>/join-requests/ and /me/join-requests/.
Calls: /conversations/<pk>/call/, /call/join/, /call/active/, /call/end/.

See messenger/urls.py for the complete route list. Channels/WebSocket routes are maintained separately.
