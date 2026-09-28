# core API and infrastructure boundary

Root mounts:
- /api/system/ -> src/core/settings_urls.py
- /media/ -> src/core/urls.py

## System settings

| Method | Route | Behavior |
|---|---|---|
| GET | /api/system/settings/ | Admin-only list of typed SystemSetting rows. Optional category filter. |
| GET, PATCH | /api/system/settings/<key>/ | Admin-only typed read/update. PATCH requires value, respects is_editable unless caller is superuser, delegates mutation to settings_service.set_setting. |
| POST | /api/system/settings/seed/ | Superuser-only. Seeds missing system settings and Dockerfile templates; update_existing controls whether existing values are overwritten. |

System settings are not tenant Service configuration.

## Protected media

Under /media/ the ProtectedMediaView serves only whitelisted prefixes:
- messenger/
- images/
- tickets/

It checks bearer token/query token/session as applicable, rejects path traversal, verifies file existence and supports range requests for media. Deployment ZIP download is a separate authenticated /media/<uuid>/download/ path with Deploy ownership/staff checks.

## Deployment download

DeploymentDownloadAPIView returns an existing deploy ZIP only to the deployment owner or allowed staff. The endpoint is intentionally separate from generic media serving to avoid treating deployment artifacts as public media.

## Cross-cutting render/error behavior

Production API rendering and exception conversion live in core.api_renderers and are configured globally in settings.py. They are presentation infrastructure rather than resource-domain authorization.

Source: src/core/apis.py, apis_settings.py, settings_urls.py, urls.py.
