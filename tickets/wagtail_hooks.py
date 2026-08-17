"""Wagtail hooks: register tickets models in Wagtail admin."""
from __future__ import annotations

from tickets.wagtail_admin import register as _register_tickets

_register_tickets()
