# tickets

## Purpose

tickets owns customer support workflow: departments, staff membership, tickets, messages, attachments/read state and realtime notifications.

## Why this boundary exists

Support authorization is distinct from authentication and from arbitrary resource ownership. Customers own their tickets; staff access is controlled by assignment/department membership. Optional Service/Deploy references provide troubleshooting context without granting support users access to those resources.

## Responsibilities

Department/staff membership; ticket status/priority; customer/staff messages; attachment validation and quota; read state; assignment/reassignment; Channels events.

## Non-responsibilities

Identity is users. Authentication is auth_users. Service/deployment execution remains in services/deploy/deployments. Ticket references to Service/Deploy are contextual.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)
- [state-contracts.md](state-contracts.md)
- [tests.md](tests.md)

## Authorization and security

IsTicketOwnerOrStaff permits an active superuser, ticket owner, assigned staff or department member. CanManageTicket narrows staff mutations to valid assignment/department scope. HTML is sanitized. Attachments are checked by extension/MIME/signature plus per-file and per-ticket limits.

## Invariants

1. Authentication alone never grants ticket access.
2. Department membership is evaluated server-side.
3. Service/Deploy references cannot broaden support authorization.
4. TicketMessage body is sanitized before persistence.
5. Realtime notifications follow committed database state.

## Reading order

models.md -> api.md -> serializers.md -> state-contracts.md -> background.md -> tests.md.
