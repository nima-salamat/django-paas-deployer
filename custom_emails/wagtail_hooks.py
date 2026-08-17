"""Wagtail hooks: register custom_emails models in Wagtail admin."""
from __future__ import annotations

from custom_emails.wagtail_admin import register as _register_custom_emails

_register_custom_emails()
