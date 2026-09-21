# core

## Responsibility
Cross-cutting infrastructure, shared model base, system settings, protected media, utilities and production-safe error handling.

## API
GET /api/system/settings/settings/
POST /api/system/settings/settings/seed/
GET/PUT/PATCH /api/system/settings/settings/<str:key>/
GET /media/<uuid:pk>/download/
GET /media/messenger/<path:path>
GET /media/images/<path:path>
GET /media/tickets/<path:path>

## Boundary
Do not put Service business rules or Docker lifecycle logic in core.
