# custom_emails background behavior

send_email_log_task is the per-delivery execution boundary. It loads EmailLog, returns safely when status is already SENT, renders/sends through the configured provider, marks SENT on success and records FAILED/retries on recoverable errors. Its bound retry policy is up to three retries with the configured/default 60-second delay.

send_bulk_email_task is only a coordinator: it selects pending delivery rows and enqueues per-log tasks. Duplicate delivery must remain safe because EmailLog status is the idempotency fence.

Rendering path:

~~~text
build_context
 -> render_template_string
 -> sanitize_email_html
 -> prevent_header_injection
 -> send_via_resend
~~~

No Celery task should accept raw provider credentials from an HTTP request. Provider configuration is operator state in core.

Tests/contracts: template rendering/validation and delivery tests protect the PENDING -> SENT/FAILED lifecycle and duplicate safety.
