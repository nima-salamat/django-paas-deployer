from django.db import migrations


class Migration(migrations.Migration):
    """
    Final reconciliation point for the CoreSettings migration graph.

    Some releases created the URL-policy branch first, while later releases
    introduced the shell-idle setting from another branch. Keeping this
    explicit merge migration makes upgrades deterministic even when either
    branch has already been applied on a live database.
    """

    dependencies = [
        ("core", "0005_merge_core_settings"),
        ("core", "0006_coresettings_shell_idle_timeout"),
    ]

    operations = []
