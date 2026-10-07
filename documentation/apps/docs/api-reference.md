# docs — detailed API route reference

This page is a source-derived route inventory. Path parameters are required by the URL shape. Request fields shown as observed are read by the implementation; endpoint-specific validation remains authoritative in the handler/serializer.

## Request flow

```mermaid
flowchart LR
    C[Client] --> Auth[Authentication]
    Auth --> Perm[Permission / ownership]
    Perm --> Validate[Serializer / handler validation]
    Validate --> DB[Durable model state]
    DB --> Async[Optional Celery / side effect]
```

## Endpoint matrix

| Route declaration | Handler | Request fields observed in source | Requiredness / notes |
|---|---|---|---|
| `tree/` | `PublicCategoryTreeAPIView` | `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` | no path parameter ; handler-module inputs include `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` |
| `public/<slug:slug>/` | `PublicDocumentDetailAPIView` | `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` | path `slug` required ; handler-module inputs include `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` |
| `admin/assets/` | `DocumentAssetListCreateAPIView` | `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` | no path parameter ; handler-module inputs include `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` |
| `admin/assets/<uuid:asset_id>/` | `DocumentAssetAdminPreviewAPIView` | `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` | path `asset_id` required ; handler-module inputs include `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` |
| `assets/<uuid:asset_id>/` | `DocumentAssetAPIView` | `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` | path `asset_id` required ; handler-module inputs include `alt`, `document`, `file`, `ids`, `kind`, `name`, `search` |

## Observed request keys

| Key | Typical role | Optionality |
|---|---|---|
| `alt` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `document` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `file` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `ids` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `kind` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `name` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |
| `search` | Input consumed by at least one handler in this app API layer. | Conditional/operation-specific; use the handler or serializer as the final requiredness contract. |

## Source of truth

The URL declaration, handler implementation and serializer validation are authoritative. This reference deliberately does not invent requiredness when the code makes it conditional on login settings, ownership, resource state or another field.
