"""Wagtail hooks: register auth_users models in Wagtail admin."""
from __future__ import annotations

from auth_users.wagtail_admin import register as _register_auth_users

_register_auth_users()
