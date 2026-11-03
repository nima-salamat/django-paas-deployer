# custom_emails API — detailed endpoint reference

Root mount: `/api/emails/`. Every endpoint currently requires an authenticated superuser; ordinary staff access is not sufficient. The detailed serializer and request behavior is documented in [custom_emails API](api.md).

## Endpoint matrix

| Method | Route | Handler | What it does / side effect |
|---|---|---|---|
| GET | `/templates/` | EmailTemplateListCreateAPIView | Lists email templates with optional search/status filtering and pagination. |
| POST | `/templates/` | EmailTemplateListCreateAPIView | Validates and creates a new template attributed to the authenticated administrator. |
| GET | `/templates/<pk>/` | EmailTemplateDetailAPIView | Reads one template by primary key. |
| PUT | `/templates/<pk>/` | EmailTemplateDetailAPIView | Validates and updates an existing template. |
| DELETE | `/templates/<pk>/` | EmailTemplateDetailAPIView | Soft-deactivates a template by setting `is_active=false`; it does not delete the row. |
| POST | `/templates/preview/` | EmailTemplatePreviewAPIView | Renders a template with optional user context, sanitizes the resulting HTML and returns a preview. It does not send mail or create a delivery attempt. |
| POST | `/send/` | EmailSendAPIView | Validates a send request, resolves recipients, renders/sanitizes content, creates pending EmailLog rows and queues asynchronous delivery. It does not call the external provider inline. |
| GET | `/logs/` | EmailLogListAPIView | Lists paginated delivery history; supports status and recipient/subject search. |
| GET | `/logs/<pk>/` | EmailLogDetailAPIView | Reads one delivery-attempt record and its status/error metadata. |
| POST | `/logs/<pk>/retry/` | EmailLogRetryAPIView | Resets an eligible FAILED delivery record to PENDING and queues another delivery attempt. |
| GET | `/stats/` | EmailStatsAPIView | Returns sent/pending/failed counts and daily/7-day delivery metrics. |
| GET | `/users/` | AdminUserSearchAPIView | Searches active users with email addresses for the template/send recipient picker; the result set is bounded. |

## Request and delivery semantics

- Template preview and actual send are separate operations. Preview never invokes the delivery worker.
- A send creates durable EmailLog rows before Celery performs delivery. A successful HTTP response therefore means the operation was accepted/queued, not that the provider accepted the message.
- The send endpoint supports test-mode and normal recipient resolution as described in [custom_emails/api.md](api.md). Normal batches are capped; recipient/header validation and HTML sanitization happen before enqueue.
- EmailLog retains a bounded body preview rather than the complete potentially sensitive body.
- OTP/authentication notifications belong to auth_users; this API is for administrator-managed custom email.

## Source of truth

Routes: `src/custom_emails/urls.py`.
Handlers: `src/custom_emails/apis.py`.
Validation: `src/custom_emails/serializers.py`.
Delivery and retries: `src/custom_emails/tasks.py`, `src/custom_emails/services.py`.
