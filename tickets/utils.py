from __future__ import annotations

import os
import re

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.html import strip_tags

# Images + audio + video + common docs
ALLOWED_EXTENSIONS = {
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    # audio
    ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".webm", ".opus",
    # video
    ".mp4", ".mov", ".mkv", ".webm",
    # documents
    ".pdf", ".txt", ".csv", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".log", ".md",
}

ALLOWED_MIME_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "text/",
    "application/pdf",
    "application/msword",
    "application/vnd.",
    "application/zip",
    "application/x-zip",
    "application/octet-stream",  # some browsers send this for audio; extension still checked
)

_SCRIPT_RE = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.I | re.S)
_EVENT_RE = re.compile(r"\son\w+\s*=", re.I)
_JS_URL_RE = re.compile(r"javascript\s*:", re.I)


def sanitize_html(raw: str) -> str:
    if not raw:
        return ""
    try:
        import bleach
        return bleach.clean(
            raw,
            tags=[
                "p", "br", "strong", "b", "em", "i", "u", "s",
                "h1", "h2", "h3", "h4", "ul", "ol", "li", "a",
                "blockquote", "code", "pre", "span",
            ],
            attributes={
                "a": ["href", "title", "rel", "target"],
                "code": ["class"],
                "pre": ["class"],
                "span": ["class"],
            },
            protocols=["http", "https", "mailto"],
            strip=True,
        )
    except ImportError:
        text = _SCRIPT_RE.sub("", raw)
        text = _EVENT_RE.sub(" ", text)
        text = _JS_URL_RE.sub("", text)
        plain = strip_tags(text)
        lines = [ln.strip() for ln in plain.replace("\r", "").split("\n") if ln.strip()]
        return "<br>".join(lines)


def get_ticket_setting(key: str, default):
    try:
        from core.settings_service import get_setting
        val = get_setting(key, None)
        if val is not None:
            return val
    except Exception:
        pass
    return getattr(settings, key.upper().replace(".", "_"), default)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    if limit <= 0:
        return True
    cache_key = f"rl:{key}"
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=window_seconds)
        return True
    if int(current) >= limit:
        return False
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window_seconds)
    return True


def validate_upload_file(uploaded_file) -> None:
    # Default 15MB so short audio/voice notes fit
    max_size = int(get_ticket_setting("tickets.max_attachment_size", 15 * 1024 * 1024))
    if uploaded_file.size > max_size:
        raise ValidationError(f"File size exceeds limit ({max_size // (1024 * 1024)}MB).")
    name = getattr(uploaded_file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type {ext or '(none)'} not allowed.")
    content_type = getattr(uploaded_file, "content_type", "") or ""
    if content_type and not any(
        content_type.startswith(p) if p.endswith("/") else content_type.startswith(p)
        for p in ALLOWED_MIME_PREFIXES
    ):
        raise ValidationError(f"MIME type not allowed: {content_type}")
    uploaded_file.seek(0)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)
    if header[:2] == b"MZ" or header[:4] == b"\x7fELF":
        raise ValidationError("Executable files not allowed.")


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    return re.sub(r"[^\w.\-]+", "_", base)[:200] or "file"
