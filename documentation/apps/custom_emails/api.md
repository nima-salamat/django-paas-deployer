# custom_emails API

Root mount: /api/emails/

All current API views require an authenticated superuser.

| Method | Route | View | Behavior |
|---|---|---|---|
| GET, POST | /templates/ | EmailTemplateListCreateAPIView | List templates with optional search or create a new active/inactive template attributed to the caller. Paginated 20; page_size max 100. |
| GET, PUT, DELETE | /templates/<pk>/ | EmailTemplateDetailAPIView | Inspect or update a template. DELETE is a soft deactivation by setting is_active false, not a row deletion. |
| POST | /templates/preview/ | EmailTemplatePreviewAPIView | Renders a template against an optional user context, sanitizes HTML and returns subject/body/context without sending. |
| POST | /send/ | EmailSendAPIView | Creates EmailLog rows then queues delivery. Test mode queues one test log; normal mode accepts user ids and/or email addresses, validates recipients and caps a batch at 500. |
| GET | /logs/ | EmailLogListAPIView | Paginated delivery history, filterable by status and recipient/subject search. |
| GET | /logs/<pk>/ | EmailLogDetailAPIView | Returns one delivery record. |
| POST | /logs/<pk>/retry/ | EmailLogRetryAPIView | Only FAILED logs can be reset to PENDING and queued again. |
| GET | /stats/ | EmailStatsAPIView | Counts sent/pending/failed and today/7-day delivery metrics. |
| GET | /users/ | AdminUserSearchAPIView | Active users with email for recipient selection, limited to 30 results and optional username/email search. |

## Send request chain

POST /send/
 -> rate limit check in tickets.utils (30 requests/hour per admin)
 -> EmailSendSerializer validation
 -> template lookup or explicit subject/body
 -> recipient resolution from users or direct email list
 -> prevent header injection
 -> render per-recipient context
 -> sanitize HTML
 -> create EmailLog PENDING rows
 -> queue send_bulk_email_task / send_email_log_task
 -> external Resend API

The HTTP request does not call Resend directly.

## Sensitive behavior

Only body_preview is retained in EmailLog, truncated to 5000 characters. Authentication-sensitive OTP delivery is a separate auth_users responsibility even though core/email infrastructure may use the same Resend transport.

Source: src/custom_emails/apis.py, serializers.py, services.py, tasks.py, urls.py.
