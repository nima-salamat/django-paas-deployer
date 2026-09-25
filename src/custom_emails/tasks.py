
import logging
from celery import shared_task
from django.utils import timezone
logger = logging.getLogger("custom_emails.tasks")

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_log_task(self, email_log_id):
    from .models import EmailLog
    from .services import send_via_resend, build_context, render_template_string, sanitize_email_html
    try:
        log = EmailLog.objects.select_related("recipient", "template").get(pk=email_log_id)
    except EmailLog.DoesNotExist:
        return {"success": False, "error": "not_found"}
    if log.status == EmailLog.Status.SENT:
        return {"success": True, "skipped": True}
    log.status = EmailLog.Status.SENDING
    log.celery_task_id = self.request.id or ""
    log.save(update_fields=["status", "celery_task_id"])
    html, subject = log.body_preview, log.subject
    if log.template_id and log.recipient_id:
        try:
            ctx = build_context(log.recipient)
            html = sanitize_email_html(render_template_string(log.template.body, ctx))
            subject = log.subject or render_template_string(log.template.subject, ctx)
        except Exception as e:
            logger.warning("Re-render failed: %s", e)
    result = send_via_resend(log.recipient_email, subject, html)
    if result.get("success"):
        log.status = EmailLog.Status.SENT
        log.sent_at = timezone.now()
        log.error_message = ""
        log.save(update_fields=["status", "sent_at", "error_message"])
        return {"success": True}
    log.status = EmailLog.Status.FAILED
    log.failed_at = timezone.now()
    log.error_message = (result.get("error") or "error")[:2000]
    log.save(update_fields=["status", "failed_at", "error_message"])
    try:
        raise self.retry(exc=Exception(log.error_message))
    except self.MaxRetriesExceededError:
        return {"success": False, "error": log.error_message}

@shared_task
def send_bulk_email_task(email_log_ids):
    for lid in email_log_ids:
        send_email_log_task.delay(lid)
    return {"queued": len(email_log_ids)}
