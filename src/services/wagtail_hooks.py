"""Wagtail hooks: register services models in Wagtail admin."""
from __future__ import annotations

from services.wagtail_admin import register as _register_services

_register_services()
