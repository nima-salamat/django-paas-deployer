"""Wagtail hooks: register deploy models in Wagtail admin."""
from __future__ import annotations

from deploy.wagtail_admin import register as _register_deploy

_register_deploy()
