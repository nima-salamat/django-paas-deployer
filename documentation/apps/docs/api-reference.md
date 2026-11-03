# docs API — detailed endpoint reference

Root mount: `/api/docs/`. Public document and public asset reads are intentionally accessible without a user session. Administrative document/category/asset mutations require the docs management permission. The canonical behavior guide is [docs API](api.md).

## Public content endpoints

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/` | PublicDocumentsAPIView | Lists published documents only. Draft/unpublished records are excluded. |
| GET | `/tree/` | PublicCategoryTreeAPIView | Builds the public navigation tree from published categories/documents. |
| GET | `/public/<slug>/` | PublicDocumentDetailAPIView | Reads one published document by slug. |

Public views disable DRF authentication on purpose: an expired or malformed bearer token must not turn an otherwise public documentation read into a 401.

## Document administration

Router prefix: `/admin/documents/`, handler: `DocumentAdminViewSet`.

| Method | Route | What it does |
|---|---|---|
| GET | `/admin/documents/` | Lists admin-visible document records. |
| POST | `/admin/documents/` | Creates a document (normally in draft state) after serializer/model validation. |
| GET | `/admin/documents/<pk>/` | Reads an individual document, including editable content and publication state. |
| PUT, PATCH | `/admin/documents/<pk>/` | Updates document fields and ordering/activity metadata under docs.manage. |
| DELETE | `/admin/documents/<pk>/` | Deletes an admin-owned document under docs.manage. |
| POST | `/admin/documents/reorder/` | Rewrites document order from the submitted ordered ID list. |
| POST | `/admin/documents/<pk>/publish/` | Publishes a document and records publication time. |
| POST | `/admin/documents/<pk>/unpublish/` | Moves a published document back to draft/unpublished state. |

## Category administration

Router prefix: `/admin/categories/`, handler: `CategoryAdminViewSet`.

| Method | Route | What it does |
|---|---|---|
| GET, POST | `/admin/categories/` | Lists or creates categories. |
| GET | `/admin/categories/<pk>/` | Reads one category. |
| PUT, PATCH | `/admin/categories/<pk>/` | Updates category metadata/order under docs.manage. |
| DELETE | `/admin/categories/<pk>/` | Deletes a category transactionally after moving direct child categories and documents to its parent. |
| POST | `/admin/categories/reorder/` | Rewrites category ordering. |
| GET | `/admin/categories/tree/` | Returns the category tree for the administrative editor. |

## Asset endpoints

| Method | Route | Handler | What it does / access rule |
|---|---|---|---|
| GET | `/admin/assets/` | DocumentAssetListCreateAPIView | Lists admin-visible assets. |
| POST | `/admin/assets/` | DocumentAssetListCreateAPIView | Uploads a new asset through multipart/form parsing and file validation. |
| GET, HEAD | `/assets/<uuid:asset_id>/` | DocumentAssetAPIView | Serves an asset by unguessable UUID capability URL. Cache policy is public for published-document assets and private for draft/unattached assets. |
| PATCH | `/assets/<uuid:asset_id>/` | DocumentAssetAPIView | Updates asset metadata; mutation is admin-protected even though GET/HEAD is public. |
| DELETE | `/assets/<uuid:asset_id>/` | DocumentAssetAPIView | Deletes an asset after admin authorization. |
| GET, HEAD | `/admin/assets/<uuid:asset_id>/` | DocumentAssetAdminPreviewAPIView | Provides authenticated admin preview of an asset. |

Asset download URLs are capabilities: do not publish a private draft asset UUID in public content. Uploads are validated by DocumentAsset.clean and the asset API parser.

## Source of truth

Routes: `src/docs/urls.py`.
Handlers and access policy: `src/docs/apis.py`.
Serializers: `src/docs/serializers.py`.
Persisted content: `src/docs/models.py`.
