# tickets

## Responsibility
Customer support tickets and operator support administration. This domain is independent of deployment execution.

## User API
GET /api/tickets/departments/
GET /api/tickets/context/
GET/POST /api/tickets/
GET/PUT/PATCH /api/tickets/<int:pk>/
POST /api/tickets/<int:pk>/close/
POST /api/tickets/<int:pk>/read/
POST /api/tickets/<int:pk>/messages/
GET /api/tickets/attachments/<int:pk>/download/

## Staff API
GET /api/tickets/staff/
GET /api/tickets/staff/stats/
PATCH /api/tickets/staff/<int:pk>/status/
PATCH /api/tickets/staff/<int:pk>/priority/
PATCH /api/tickets/staff/<int:pk>/department/
PATCH /api/tickets/staff/<int:pk>/assign/
DELETE /api/tickets/staff/<int:pk>/delete/

## Admin
GET/POST /api/tickets/admin/departments/
GET/PUT/PATCH/DELETE /api/tickets/admin/departments/<int:pk>/
GET/POST/DELETE /api/tickets/admin/departments/<int:pk>/members/
GET /api/tickets/admin/departments/<int:pk>/staff/
GET/POST /api/tickets/admin/staff/
GET/POST/DELETE /api/tickets/admin/users/<int:user_id>/memberships/
