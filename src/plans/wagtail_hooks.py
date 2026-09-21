"""Wagtail hooks: register plans models in Wagtail admin."""
from __future__ import annotations

from plans.wagtail_admin import register as _register_plans

_register_plans()
