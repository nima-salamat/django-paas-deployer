"""Wagtail integration intentionally disabled for the tickets app.

Ticket administration remains in Django Admin/API because the existing staff
workflow enforces department membership and CanManageTicket checks that generic
Wagtail snippets cannot reproduce safely.
"""
from __future__ import annotations


def register():
    return None
