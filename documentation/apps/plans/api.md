# plans API

Root mounts are /plans/ and the user-facing inclusion under /users/plans/.

Authentication for customer plan application is SessionJWTAuthentication + IsAuthenticated. Admin management requires staff plus the plans rule set; superusers bypass.

Global pagination defaults are page-number/page_size=10, while plan admin endpoints use a 20-item paginator with a page_size query cap of 100.

| Method | Route | Behavior |
|---|---|---|
| GET | /admin/plans/ | Staff/rule-protected plan list. Supports q/q_search, platform, plan_type, page_size and pagination. Cached. |
| POST | /admin/plans/ | Creates a plan under plans.manage. Invalidates plan cache after write. |
| GET, PUT, PATCH, DELETE | /admin/plans/<uuid>/ | Staff/rule-protected plan management. |
| GET | /platforms/ | Returns configured PLATFORM_CHOICES. |
| POST | /platforms/ | Returns plans for a supplied platform; invalid platform is 400 and no matching plan is 404. |
| GET | / | Public plan listing or id-filtered lookup. id may be one UUID or a comma-separated UUID list; malformed UUID input is 400. |
| POST | /plans/<uuid:planId>/apply/ | Applies an existing plan to an owned Service. applyImmediately may queue a deployment after commit when an active revision exists. |

The apply endpoint locks the Service, rejects invalid target type or ownership, and disallows immediate deploy while the Service is queued/deploying/stopping. It changes the Service plan, marks desired state queued when immediate execution is requested, then enqueues deployments.celery.tasks.deploy after transaction commit.

## Serializer split

PlanSerializer is the full model representation used by admin. UnauthorizedPlanSerializer is the narrower public representation and is intentionally not a permission system by itself.

## Side effects

Plan CRUD changes cache state. Immediate Service plan application may enter the deployment queue but does not execute Docker synchronously.

Source: src/plans/urls.py, apis.py, serializers.py.
