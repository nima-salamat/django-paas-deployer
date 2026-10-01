"""Compatibility import surface for the Agent HTTP API.

Implementations are grouped under :mod:`agent.apis`; existing imports of
:mod:`agent.views` continue to work.
"""
from .apis import *  # noqa: F401,F403
from .apis import __all__  # noqa: F401
