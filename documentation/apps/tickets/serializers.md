# tickets serializers

## Read serializers

DepartmentSerializer exposes id/name/slug/description/is_active/order/timestamps; id/slug/timestamps are read-only.

UserBriefSerializer is a compact identity representation with an avatar method field sourced from the user's Profile and request context. It is used inside tickets without making tickets the owner of profiles.

ServiceBriefSerializer and DeployBriefSerializer are lightweight reference serializers. They carry ids and safe display fields only.

TicketAttachmentSerializer exposes immutable file metadata and a derived download URL. It is read-only.

TicketMessageSerializer exposes author, body, staff-reply flag, seen state/timestamps and nested attachments. All fields are read-only.

TicketListSerializer is the compact ticket list representation; TicketDetailSerializer adds assigned_to, messages and attachments.

## Write serializers

TicketCreateSerializer accepts department_id, subject, body, optional priority, optional service_id and optional deploy_id.

- department_id must be an active Department.
- subject is stripped and must be at least three characters.
- body is required and sanitized with sanitize_html.
- service_id must belong to the authenticated user.
- deploy_id must belong to a Deploy whose Service belongs to the authenticated user; when service_id is omitted, it is derived from the Deploy.

TicketMessageCreateSerializer requires non-empty body and sanitizes HTML.

TicketStatusSerializer and TicketPrioritySerializer use the model choice sets.

TicketAssignDepartmentSerializer requires an active Department.

## API -> serializer -> policy

POST /api/tickets/
 -> authentication
 -> TicketCreateSerializer
 -> ownership/context validation
 -> Ticket creation
 -> realtime/cache side effect

Staff status/priority/department/assignment endpoints
 -> permission class
 -> small choice/ID serializer
 -> model mutation
 -> event broadcast

Serializers perform important field validation, but staff scope and ticket ownership are permission-layer responsibilities.

Source: src/tickets/serializers.py, permissions.py, api/*.py.
