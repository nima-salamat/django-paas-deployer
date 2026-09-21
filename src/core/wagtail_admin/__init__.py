"""Legacy snippet registration kept for backward compatibility.

Core operator settings are registered through wagtail.contrib.settings and
therefore appear under Wagtail's native Settings menu.
"""


def register():
    # Intentionally empty. SystemSetting remains available to legacy Django
    # admin/API consumers, while the operator-facing settings live in the
    # native Wagtail Settings menu via @register_setting.
    return None
