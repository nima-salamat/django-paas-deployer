# tickets API — detailed endpoint reference

Root mount: `/api/tickets/`. All current routes require an authenticated active user. A successful authentication is not sufficient: ticket ownership, assigned-staff and department membership checks are applied at the owning endpoint. The detailed app guide is [tickets API](api.md).

## Customer endpoints

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/departments/` | DepartmentListAPIView | Lists active departments used by the new-ticket form. Staff may request the broader list with the supported `all=1` query option. |
| GET | `/context/` | MyTicketContextAPIView | Returns the caller's owned Services and Deploys so a ticket can optionally reference a workload/deployment. |
| GET | `/` | MyTicketListCreateAPIView | Lists only the caller's tickets; supports status, priority, department and subject/public-ID search, paginated and ordered by recent activity. |
| POST | `/` | MyTicketListCreateAPIView | Creates a ticket and its first message; validates department, optional Service/Deploy ownership, rate/open-ticket limits and attachments. |
| GET | `/<pk>/` | TicketDetailAPIView | Reads one ticket and its messages/attachments after ticket object permission checks. |
| POST | `/<pk>/close/` | TicketCloseAPIView | Closes an owned/authorized ticket and records closed_at. Repeated close is rejected as already closed. |
| POST | `/<pk>/read/` | TicketMarkReadAPIView | Marks unread messages from the other party as seen, updates TicketReadState and broadcasts a read event when something changed. |
| POST | `/<pk>/messages/` | TicketMessageCreateAPIView | Adds a sanitized reply and optional validated attachments; closed tickets reject replies and message rate limits apply. |
| GET | `/attachments/<pk>/download/` | AttachmentDownloadAPIView | Streams an attachment only after verifying access to its owning ticket. |

## Staff endpoints

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/staff/` | StaffTicketListAPIView | Lists tickets visible to staff under department/assignment scope; supports advanced filters including status, priority, assigned user, date, Service and attachment state. |
| GET | `/staff/stats/` | StaffTicketStatsAPIView | Returns staff-scoped counts by lifecycle state, urgency, assignment and department. |
| POST | `/staff/<pk>/status/` | StaffTicketStatusAPIView | Changes ticket status after staff/object permission and TicketStatusSerializer validation. |
| POST | `/staff/<pk>/priority/` | StaffTicketPriorityAPIView | Changes ticket priority after staff/object permission and TicketPrioritySerializer validation. |
| POST | `/staff/<pk>/department/` | StaffTicketAssignDepartmentAPIView | Reassigns a ticket to another department; requires superuser or manager membership in the current department. |
| POST | `/staff/<pk>/assign/` | StaffTicketAssignAPIView | Assigns or unassigns an active staff member; non-superusers can assign only a member of the ticket's department. |
| DELETE | `/staff/<pk>/delete/` | StaffTicketDeleteAPIView | Permanently deletes a ticket; requires superuser, department-manager authority or the tickets.delete rule. |

## Department and membership administration

| Method | Route | Handler | What it does / access rule |
|---|---|---|---|
| GET | `/admin/departments/` | AdminDepartmentListCreateAPIView | Lists all departments for department managers; other staff see only their assigned departments. Includes staff/open/total ticket counts. |
| POST | `/admin/departments/` | AdminDepartmentListCreateAPIView | Creates department metadata; requires departments.manage or superuser. |
| GET | `/admin/departments/<pk>/` | AdminDepartmentDetailAPIView | Reads department metadata and its staff memberships; requires manager/superuser scope. |
| PUT | `/admin/departments/<pk>/` | AdminDepartmentDetailAPIView | Updates department metadata under departments.manage. |
| DELETE | `/admin/departments/<pk>/` | AdminDepartmentDetailAPIView | Soft-deactivates the department (`is_active=false`); it is not a hard delete. |
| POST | `/admin/departments/<pk>/members/` | AdminDepartmentMembershipAPIView | Adds/updates a staff membership and manager flag; superuser only. |
| DELETE | `/admin/departments/<pk>/members/` | AdminDepartmentMembershipAPIView | Removes the membership identified by user_id; superuser only. |
| GET | `/admin/departments/<pk>/staff/` | DepartmentStaffListAPIView | Lists active staff assigned to the department for assignment controls; scoped to a member or superuser. |
| GET | `/admin/staff/` | AdminStaffListAPIView | Lists staff with department memberships and open assignment counts; superuser only. |
| GET | `/admin/users/<user_id>/memberships/` | AdminUserMembershipAPIView | Reads a user's department memberships and the active department choices; superuser only. |
| PUT | `/admin/users/<user_id>/memberships/` | AdminUserMembershipAPIView | Replaces the user's department membership set transactionally; superuser only. |

## Important security and side-effect rules

- Ticket.service and Ticket.deploy are optional context only; they do not grant access to those Service or Deploy objects.
- Ticket content is sanitized HTML; it intentionally differs from Messenger's plain-text message contract.
- Attachment type, extension, MIME/signature, per-file size and aggregate ticket quota are validated before storage.
- Read-state updates and new messages may trigger Channels events. They are durable database mutations first; realtime delivery is a projection.
- Department deletion/deactivation and membership management have separate staff/superuser rules. Do not infer membership permissions from ordinary ticket ownership.

## Source of truth

Routes: `src/tickets/urls.py`.
Customer handlers: `src/tickets/api/user_tickets.py`.
Staff handlers: `src/tickets/api/staff_tickets.py`.
Admin handlers: `src/tickets/api/admin_tickets.py`.
Permissions: `src/tickets/permissions.py`.
Serializers and upload policy: `src/tickets/serializers.py`, `src/tickets/utils.py`.
