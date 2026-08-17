"""
Central Wagtail hook wiring.

All per-app snippet administration has been moved into each app's own
``wagtail_admin`` package, registered by that app's ``wagtail_hooks.py``
(Wagtail auto-discovers ``wagtail_hooks.py`` from every installed app).

This module only documents the overall layout and re-imports each app's hook
module so the intent is explicit and there is a single obvious entry point.
It contains no model-specific administration code.
"""
from __future__ import annotations

# Wagtail auto-discovers ``wagtail_hooks`` in every installed app, so each of
# the following apps registers its own models in Wagtail admin:
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
# User management is handled by ``wagtail.users`` (with our custom forms), so
# the custom ``users.User`` model is intentionally NOT registered as a snippet.
#
# ``deploy.DeployLog`` is stored in a separate database
# (DEPLOYMENT_LOG_DB_ALIAS). It IS registered here as a read-only snippet whose
# view set routes to that database alias, mirroring the Django admin behaviour.

import plans.wagtail_hooks  # noqa: F401
import services.wagtail_hooks  # noqa: F401
import deploy.wagtail_hooks  # noqa: F401
import core.wagtail_hooks  # noqa: F401
import auth_users.wagtail_hooks  # noqa: F401
import custom_emails.wagtail_hooks  # noqa: F401
import users.wagtail_hooks  # noqa: F401
import messenger.wagtail_hooks  # noqa: F401
import tickets.wagtail_hooks  # noqa: F401
