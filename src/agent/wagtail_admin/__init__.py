"""Wagtail admin integration for the Agent application."""
from __future__ import annotations

from .models import AgentGroup

def register():
    from wagtail.snippets.models import register_snippet
    register_snippet(AgentGroup)
