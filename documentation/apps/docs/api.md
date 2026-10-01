# docs API

Root mount: /api/docs/

Public document APIs explicitly use AllowAny and intentionally avoid DRF authentication errors caused by an invalid/expired bearer header. Public querysets contain published content only.

## Public routes

| Method | Route | Behavior |
|---|---|---|
| GET | / | Published document list. |
| GET | /tree/ | Published category/document navigation tree. |
| GET | /public/<slug>/ | Published document detail by slug. |

## Document admin viewset

Router prefix: /admin/documents/

The router registers standard DRF list/create/retrieve/update/partial_update/destroy for DocumentAdminViewSet. Its custom operations are:

- POST /admin/documents/reorder/ — applies submitted document ordering.
- POST /admin/documents/<pk>/publish/ — publishes a document and records publication time.
- POST /admin/documents/<pk>/unpublish/ — returns a document to draft/unpublished state.

Document admin mutations require docs.manage; superusers bypass the rule.

## Category admin viewset

Router prefix: /admin/categories/

Standard list/create/retrieve/update/partial_update/destroy are registered. Custom operations:

- POST /admin/categories/reorder/
- GET /admin/categories/tree/

Deleting a category runs in a transaction, moving documents and direct child categories to the deleted node's parent before deletion.

## Assets

| Method | Route | Behavior |
|---|---|---|
| GET, POST | /admin/assets/ | List/create admin assets; upload parsing uses multipart/form data. |
| GET, HEAD | /assets/<uuid>/ | Public/capability asset delivery by UUID; published-document assets are shared-cacheable, while draft/unattached assets remain private-cacheable. |
| GET, HEAD | /admin/assets/<uuid>/ | Authenticated admin preview. |
| PATCH, DELETE | /assets/<uuid>/ | Admin-only mutation path despite the public GET capability route. |

Asset GET/HEAD is public for all assets. The UUID is the capability URL; cache policy is public only for assets attached to published documents and private otherwise. PATCH/DELETE remain protected. Uploads are validated by DocumentAsset.clean.

## Request-to-model chain

Public GET -> published queryset -> Document/Category serializer -> response.

Admin create/update -> DRF serializer -> model save/validation -> DB.

Publish -> authenticated rule check -> state mutation -> timestamp.

Asset upload -> multipart parser -> file validation -> DocumentAsset.save -> protected/public serving decision.

Source: src/docs/apis.py, serializers.py, models.py, urls.py.
