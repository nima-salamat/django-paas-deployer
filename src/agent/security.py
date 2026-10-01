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

def stable_json_hash(value):
    return hashlib.sha256(json.dumps(sanitize_metadata(value),sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def scrub_text(text,secrets_to_replace=()):
    result=str(text or "")
    for secret in secrets_to_replace:
        if secret: result=result.replace(str(secret),"[REDACTED]")
    return result
