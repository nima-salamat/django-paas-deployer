# plans

## Responsibility
Defines the resource and execution envelope available to a Service: CPU, RAM, storage, plan type, platform family and availability.

A Plan is policy, not deployment configuration.

## API
GET /plans/
GET /plans/platforms/
POST /plans/plans/<uuid:planId>/apply/
GET/POST /plans/admin/plans/
GET/PUT/PATCH/DELETE /plans/admin/plans/<uuid:pk>/

The same plan APIs are also included under /users/plans/.

## Boundary
Deployment workers derive resource limits from Plan. Tenant configuration cannot raise the plan limits.
