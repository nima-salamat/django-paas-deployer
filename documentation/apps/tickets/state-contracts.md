# tickets state and choice contracts

## Ticket status

The Ticket.Status choices define the support workflow; staff status mutations must use the documented staff permission scope and the serializer ChoiceField.

## Priority

Ticket.Priority is a customer/support urgency classification. It is not authorization and does not change resource ownership.

## Read state

TicketReadState tracks per-user read position and is derived from the ticket owner/staff relationship; it is not a ticket visibility grant.
