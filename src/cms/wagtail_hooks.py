"""
Central Wagtail hook wiring.

All per-app snippet administration lives in each app's own ``wagtail_admin``
package and is registered by that app's ``wagtail_hooks.py``.  Wagtail
auto-discovers ``wagtail_hooks.py`` from every installed app, so no global
imports are needed here — this module exists purely as documentation and a
single place to understand how the admin is wired.
"""
from __future__ import annotations

# Wagtail auto-discovers ``wagtail_hooks`` in every installed app.  Each of the
# following apps registers its own models in Wagtail admin from its own module:
#
#   plans         -> plans/wagtail_hooks.py
#   services      -> services/wagtail_hooks.py
#   deploy        -> deploy/wagtail_hooks.py
#   core          -> core/wagtail_hooks.py
#   auth_users    -> auth_users/wagtail_hooks.py
#   custom_emails -> custom_emails/wagtail_hooks.py
#   users         -> users/wagtail_hooks.py
#   messenger     -> messenger/wagtail_hooks.py
#   tickets       -> tickets/wagtail_hooks.py
#
# Where each model appears in the Wagtail admin:
#   * Every model is registered as a snippet inside an app-level
#     ``SnippetViewSetGroup``, so each app appears as its own top-level sidebar
#     item with a submenu of its models:
#       - Plans      -> Plans
#       - Services   -> Services, Volumes, Private networks
#       - Deploy     -> Deployments, Deploy logs
#       - System     -> System settings
#       - Auth       -> Login settings, Invite links, Invite usage, Auth codes
#       - Emails     -> Email templates, Email log
#       - Users      -> Profiles, Receipts, User rules
#       - Messenger  -> (conversations, messages, call sessions, ...)
#       - Tickets    -> (tickets, departments, messages, ...)
#   * Because every model has its own menu item, the generic "Snippets" index
#     menu is empty and hidden (Wagtail does this automatically).
#   * ``users.User`` is the custom AUTH_USER_MODEL and is administered by
#     Wagtail's built-in Users interface (Settings -> Users), configured via
#     ``cms.forms.CustomUserEditForm`` / ``CustomUserCreationForm``.
#   * ``deploy.DeployLog`` is read-only and reads from the separate
#     ``deployment_logs`` database (see deploy/wagtail_admin/models.py).
