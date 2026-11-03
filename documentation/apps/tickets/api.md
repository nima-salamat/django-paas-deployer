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

Department and membership administration is split by privilege; department managers may manage department metadata, while membership assignment and cross-user membership replacement are superuser-only.

| Method | Route | Behavior |
|---|---|---|
| GET, POST | /admin/departments/ | Lists departments visible to staff (with counts) or creates a department under departments.manage. |
| GET, PUT, DELETE | /admin/departments/<pk>/ | Reads membership detail, updates metadata, or soft-deactivates a department. |
| POST, DELETE | /admin/departments/<pk>/members/ | Adds/updates or removes a staff membership; superuser only. |
| GET | /admin/departments/<pk>/staff/ | Lists active staff in a department for assignment controls. |
| GET | /admin/staff/ | Lists staff accounts, memberships and assigned-open-ticket counts; superuser only. |
| GET, PUT | /admin/users/<user_id>/memberships/ | Reads or replaces the selected user's department memberships; superuser only. |

These routes use the ticket admin permission classes and must not be confused with customer ownership.

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
