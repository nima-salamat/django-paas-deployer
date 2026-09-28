"""Central Wagtail hook documentation.

Per-app Wagtail ownership lives next to the owning application. Wagtail
auto-discovers each app's wagtail_hooks.py.
"""
from __future__ import annotations

# Current ownership:
# users -> Wagtail Users + supporting snippets
# auth_users -> authentication policy/invite/audit surfaces
# plans -> Plan
# services -> service/network/volume snippets + service inspection
# deploy -> deployment/base-image/Swarm snippets + operator actions
# app_catalog -> installed application coordinator + cancellation
# custom_emails -> templates/logs
# core -> cache/metrics views + native CoreSettings
# cms -> HomePage
#
# Messenger content and Ticket CRUD intentionally remain outside Wagtail.
# Logs and Docs keep their existing dedicated operational/admin workflows.
