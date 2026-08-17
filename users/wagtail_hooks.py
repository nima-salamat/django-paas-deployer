"""Wagtail hooks: register users models in Wagtail admin."""
from __future__ import annotations

from users.wagtail_admin import register as _register_users

_register_users()
