"""Service secret storage.

Secrets are encrypted at rest with a key derived from Django SECRET_KEY.
The plaintext is never serialized through the API and never stored in the
ServiceRevision JSON snapshot; revisions reference exact secret versions.
"""
from __future__ import annotations

import base64
import hashlib

from django.conf import settings
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    seed = str(getattr(settings, "SERVICE_SECRET_ENCRYPTION_KEY", "") or settings.SECRET_KEY).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(str(ciphertext).encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError("Service secret cannot be decrypted with the current encryption key.") from exc
