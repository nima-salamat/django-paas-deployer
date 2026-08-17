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
#   * Models registered as individual snippets appear under the "Snippets"
#     menu (plans, services/deploy helpers that are listed individually, core,
#     auth_users, custom_emails, users companion models, deploy + deploy logs).
#   * ``messenger``, ``tickets`` and ``services`` models are grouped and appear
#     as their own top-level sidebar items with a submenu.
#   * ``users.User`` is the custom AUTH_USER_MODEL and is administered by
#     Wagtail's built-in Users interface (Settings -> Users), configured via
#     ``cms.forms.CustomUserEditForm`` / ``CustomUserCreationForm``.
#   * ``deploy.DeployLog`` is read-only and reads from the separate
#     ``deployment_logs`` database (see deploy/wagtail_admin/models.py).
