# tickets background and implicit effects

TicketMessage.save() updates Ticket.last_message_at/updated_at, so message persistence has a synchronous model side effect.

Ticket APIs broadcast committed ticket state through Channels consumers. WebSocket notification is not authoritative storage. `TicketEventsConsumer` and `TicketNotifyConsumer` use the same session-bound JWT contract as the rest of the first-party WebSockets: handshake validation requires `sid`, and heartbeat revalidates the server-side session before continuing delivery.

Attachment downloads are authorized before file streaming. File validation happens before persistence; filenames are normalized and executable signatures are rejected.

When staff membership changes, department-scoped querysets/permissions change immediately because authorization reads current DepartmentMembership/assignment state.

Tests in src/tickets/tests.py protect ownership/permission, message, attachment and API regression contracts; read permissions.py with those tests before widening access.
