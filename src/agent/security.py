from __future__ import annotations
import hashlib, hmac, json, secrets, uuid
from django.conf import settings

ACCESS_PREFIX="pd_agent_"
ENROLLMENT_PREFIX="pd_enroll_"

def token_hash(token):
    pepper=str(getattr(settings,"AGENT_TOKEN_PEPPER","") or settings.SECRET_KEY)
    return hmac.new(pepper.encode(),str(token).encode(),hashlib.sha256).hexdigest()

def issue_raw_access_token(): return ACCESS_PREFIX+secrets.token_urlsafe(32)
def issue_raw_enrollment_token(): return ENROLLMENT_PREFIX+secrets.token_urlsafe(32)
def token_prefix(token,length=20): return str(token or "")[:length]

def get_request_id(request):
    value=getattr(request,"request_id",None) or request.META.get("HTTP_X_REQUEST_ID") or request.META.get("HTTP_X_CORRELATION_ID")
    try: return str(uuid.UUID(str(value)))
    except (ValueError,TypeError,AttributeError): return str(uuid.uuid4())

def client_ip(request):
    forwarded=str(request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or str(request.META.get("REMOTE_ADDR") or "0.0.0.0")

def sanitize_metadata(value):
    secret_markers=("password","secret","token","private_key","authorization","api_key","ciphertext")
    if isinstance(value,dict):
        return {str(k):("[REDACTED]" if str(k).lower() in secret_markers or any(m in str(k).lower() for m in secret_markers) else sanitize_metadata(v)) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [sanitize_metadata(v) for v in value]
    if isinstance(value,str): return value if len(value)<=2000 else value[:1997]+"..."
    if isinstance(value,(int,float,bool)) or value is None: return value
    return str(value)

SENSITIVE_KEY_MARKERS = (
    "password", "secret", "token", "private_key", "authorization",
    "api_key", "apikey", "ciphertext", "credential",
)


def _is_sensitive_key(key) -> bool:
    lowered = str(key or "").lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def extract_sensitive_request_values(value):
    """Collect client-supplied sensitive scalar values for response scrubbing."""
    found = []

    def walk(node, sensitive=False):
        if isinstance(node, dict):
            for key, item in node.items():
                walk(item, sensitive or _is_sensitive_key(key))
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item, sensitive)
            return
        if sensitive and isinstance(node, (str, int, float)) and str(node):
            found.append(str(node))

    walk(value)
    return tuple(sorted(set(found), key=len, reverse=True))


def sanitize_error_payload(value, *, secret_values=()):
    """Sanitize error fields and redact exact sensitive values supplied by the client."""
    scrub_values = tuple(str(v) for v in secret_values if str(v))
    sensitive_fields = SENSITIVE_KEY_MARKERS

    def walk(node):
        if isinstance(node, dict):
            output = {}
            for key, item in node.items():
                if _is_sensitive_key(key):
                    output[str(key)] = "[REDACTED]"
                else:
                    output[str(key)] = walk(item)
            return output
        if isinstance(node, (list, tuple)):
            return [walk(item) for item in node]
        if isinstance(node, str):
            return scrub_text(node, scrub_values)
        return node

    return walk(value)


def stable_json_hash(value):
    return hashlib.sha256(json.dumps(sanitize_metadata(value),sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def scrub_text(text,secrets_to_replace=()):
    result=str(text or "")
    for secret in secrets_to_replace:
        if secret: result=result.replace(str(secret),"[REDACTED]")
    return result
