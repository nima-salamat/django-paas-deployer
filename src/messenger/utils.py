from __future__ import annotations

import os
from django.conf import settings
from django.core.exceptions import ValidationError

DEFAULT_MAX_VIDEO = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_FILE = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".svg",
    # video
    ".mp4", ".mov", ".mkv", ".webm",
    # audio
    ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".flac",
    # documents
    ".pdf", ".txt", ".md", ".csv", ".rtf",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    # source / code (send-as-file from messenger editor)
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".htm", ".css",
    ".scss", ".sass", ".less", ".java", ".kt", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".m", ".mm",
    ".sh", ".bash", ".zsh", ".ps1", ".sql", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".env", ".xml", ".gradle", ".dockerfile",
    ".vue", ".svelte", ".dart", ".lua", ".r", ".pl", ".pm",
    ".ipynb", ".graphql", ".gql", ".proto", ".wasm", ".map",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
GIF_EXTS = {".gif"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".webm"}
# Voice messages from MediaRecorder are typically audio/webm (Opus in WebM container)
VOICE_CONTENT_TYPES = {"audio/webm", "audio/ogg", "audio/opus", "audio/m4a"}


def detect_kind(filename: str, content_type: str = "") -> str:
    """Detect attachment kind. Voice messages (from MediaRecorder, audio/webm)
    are classified as 'voice' so the UI can render a Telegram-style voice bubble."""
    ext = os.path.splitext(filename or "")[1].lower()
    ct = (content_type or "").lower()
    name_lower = (filename or "").lower()

    # Voice message detection: explicit voice_ prefix OR audio/webm from recorder
    if name_lower.startswith("voice_") or (ct in VOICE_CONTENT_TYPES and ext == ".webm"):
        return "voice"
    # Video message detection (circular, Telegram-style)
    if name_lower.startswith("video_message_"):
        return "video"

    if ext in GIF_EXTS or "gif" in ct:
        return "gif"
    if ext in IMAGE_EXTS or ct.startswith("image/"):
        return "image"
    if ext in VIDEO_EXTS or ct.startswith("video/"):
        return "video"
    if ext in AUDIO_EXTS or ct.startswith("audio/"):
        # Default audio/* to "audio" (music file), not "voice"
        return "audio"
    return "file"


def validate_messenger_file(uploaded_file) -> None:
    name = getattr(uploaded_file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    if getattr(uploaded_file, "size", 0) <= 0:
        raise ValidationError("Empty files are not allowed.")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type {ext or '(none)'} not allowed.")
    kind = detect_kind(name, getattr(uploaded_file, "content_type", "") or "")
    max_size = DEFAULT_MAX_VIDEO if kind == "video" else DEFAULT_MAX_FILE
    if uploaded_file.size > max_size:
        mb = max_size // (1024 * 1024)
        raise ValidationError(f"File size exceeds limit ({mb}MB).")
    # Basic executable check
    uploaded_file.seek(0)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)
    if header[:2] == b"MZ" or header[:4] == b"\x7fELF":
        raise ValidationError("Executable files not allowed.")


def can_see_profile_photo(viewer, owner) -> bool:
    """Check ProfilePhotoPrivacy for whether viewer can see owner's users.Profile photos."""
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return False
    if viewer.id == owner.id:
        return True
    try:
        privacy = owner.messenger_photo_privacy
    except Exception:
        return True  # default everyone
    scope = privacy.scope
    if scope == "everyone":
        return True
    if scope == "nobody":
        return False
    if scope == "contacts":
        from .models import Contact
        return Contact.objects.filter(owner=owner, contact=viewer).exists()
    if scope == "specific":
        return privacy.allowed_users.filter(user=viewer).exists()
    return True


def users_blocked(a, b) -> bool:
    from .models import Block
    return Block.objects.filter(blocker=a, blocked=b).exists() or Block.objects.filter(blocker=b, blocked=a).exists()
