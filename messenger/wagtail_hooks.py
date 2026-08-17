"""Wagtail hooks: register messenger models in Wagtail admin."""
from __future__ import annotations

from messenger.wagtail_admin import register as _register_messenger

_register_messenger()
