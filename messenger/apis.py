"""Backward-compatible shim — prefer ``messenger.api`` package.

All views live in ``messenger.api.*`` modules split by feature.
This module re-exports them so existing ``from . import apis`` / ``apis.X`` keep working.
"""
from .api import *  # noqa: F401,F403
from .api import __all__  # noqa: F401
