"""Tickets intentionally remain outside Wagtail.

Ticket staff scope is department-based and the existing Django Admin/API
workflow owns status, priority and assignment semantics. Generic Wagtail CRUD
would bypass CanManageTicket and department membership checks.
"""
from __future__ import annotations


def register():
    return None
