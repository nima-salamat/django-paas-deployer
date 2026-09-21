
import logging, re
from django.conf import settings
from django.template import Context, Template, TemplateSyntaxError
logger = logging.getLogger("custom_emails.services")

def build_context(user=None, extra=None):
    ctx = {"site_name": getattr(settings, "DOMAIN_NAME", "App"), "support_email": getattr(settings, "EMAIL_ADDR", "")}
    if user is not None:
        first = getattr(user, "first_name", "") or getattr(user, "username", "") or ""
        ctx["user"] = {"id": getattr(user, "id", ""), "username": getattr(user, "username", "") or "", "email": getattr(user, "email", "") or "", "first_name": first, "last_name": getattr(user, "last_name", "") or ""}
    if extra:
        ctx.update(extra)
    return ctx

def render_template_string(template_str, context):
    if not template_str:
        return ""
    try:
        return Template(template_str).render(Context(context))
    except TemplateSyntaxError as e:
        raise ValueError(f"Invalid template: {e}") from e

def sanitize_email_html(html):
    if not html:
        return ""
    html = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", html, flags=re.I|re.S)
    html = re.sub(r"javascript\s*:", "", html, flags=re.I)
    html = re.sub(r"\son\w+\s*=\s*([\"']).*?\1", "", html, flags=re.I|re.S)
    return html

def prevent_header_injection(value):
    return re.sub(r"[\r\n]+", " ", str(value or "")).strip()

def send_via_resend(to_email, subject, html_body):
    import resend
    from core.tasks.email import configure_resend_proxy
    configure_resend_proxy()
    resend.api_key = settings.RESEND_API_KEY
    to_email = prevent_header_injection(to_email)
    subject = prevent_header_injection(subject)
    html_body = sanitize_email_html(html_body)
    if not to_email or "@" not in to_email:
        return {"success": False, "error": "Invalid recipient"}
    try:
        result = resend.Emails.send({"from": settings.EMAIL_ADDR, "to": [to_email], "subject": subject, "html": html_body})
        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        return {"success": True, "id": email_id}
    except Exception as e:
        logger.exception("Resend failed: %s", e)
        return {"success": False, "error": str(e)}
