# tickets API

Root mount: /api/tickets/

All current ticket APIs require an authenticated active user. Object-level access is based on ticket ownership/staff scope, not merely IsAuthenticated.

## User routes

| Method | Route | Behavior |
|---|---|---|
| GET | /departments/ | Active department list used when opening a ticket. |
| GET | /context/ | Returns support context relevant to the caller. |
| GET, POST | / | Lists or creates the caller's tickets. Creation validates active department, sanitizes body, validates optional Service/Deploy ownership and defaults priority to normal. |
| GET | /<pk>/ | Ticket detail for an authorized owner/staff member. |
| POST | /<pk>/close/ | Owner-side close operation. |
| POST | /<pk>/read/ | Updates read state for the current user. |
| POST | /<pk>/messages/ | Adds a sanitized ticket message inside the caller's allowed scope. |
| GET | /attachments/<pk>/download/ | Streams an attachment only after ticket access validation. |

## Staff routes

| Method | Route | Behavior |
|---|---|---|
| GET | /staff/ | Staff-visible ticket list within department/assignment scope. |
| GET | /staff/stats/ | Staff scoped statistics. |
| POST | /staff/<pk>/status/ | Changes status using Ticket.Status choices and staff scope. |
| POST | /staff/<pk>/priority/ | Changes priority using Ticket.Priority choices and staff scope. |
| POST | /staff/<pk>/department/ | Reassigns department after validation. |
| POST | /staff/<pk>/assign/ | Assigns staff within permitted scope. |
| DELETE | /staff/<pk>/delete/ | Staff deletion operation subject to the implemented staff policy. |

## Department/admin routes

/ admin / departments/ and / admin / staff/ provide department and membership administration through the dedicated admin API modules. Exact routes are:

- /admin/departments/
- /admin/departments/<id>/
- /admin/departments/<id>/members/
- /admin/departments/<id>/staff/
- /admin/staff/
- /admin/users/<user_id>/memberships/

These routes use the ticket admin permission classes and should not be confused with customer ownership.

## Authorization chain

Request
 -> authentication
 -> ticket/service/deploy scope resolution
 -> IsTicketOwnerOrStaff or CanManageTicket
 -> serializer validation
 -> Ticket/TicketMessage/Attachment mutation
 -> cache/event invalidation
 -> Channels notification

A Ticket.service or Ticket.deploy reference is contextual. It does not grant the caller access to that Service or Deploy.

## Upload security

Per-file size, extension, MIME prefix and executable signature are validated. Total ticket attachment size is checked before accepting incoming files. Filenames are normalized by safe_filename.

Source: src/tickets/urls.py, api/*.py, permissions.py, utils.py, serializers.py.
